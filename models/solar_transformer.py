"""
SolarTransformer — Spatio-Temporal Transformer for solar wind prediction.

Architecture:
  - Input projection: 7 solar-wind features → d_model
  - Positional encoding (learnable)
  - N encoder layers (multi-head attention + FFN)
  - Classification head: binary (storm / no-storm) + regression (Kp index)

Compatible with PEFT LoRA for lightweight fine-tuning.
"""
from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 512, dropout: float = 0.1) -> None:
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # (1, max_len, d_model)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len, d_model)
        x = x + self.pe[:, : x.size(1)]
        return self.dropout(x)


class SolarTransformer(nn.Module):
    """
    Spatio-temporal Transformer for solar wind → storm probability prediction.

    Args:
        n_features:  Number of input features per time step (default 7).
        d_model:     Embedding dimension (default 512).
        n_heads:     Number of attention heads (default 8).
        n_layers:    Number of encoder layers (default 6).
        d_ff:        Feed-forward hidden dim (default 2048).
        dropout:     Dropout rate.
        max_seq_len: Maximum sequence length (default 512).
    """

    def __init__(
        self,
        n_features: int = 7,
        d_model: int = 512,
        n_heads: int = 8,
        n_layers: int = 6,
        d_ff: int = 2048,
        dropout: float = 0.1,
        max_seq_len: int = 512,
    ) -> None:
        super().__init__()

        self.input_proj = nn.Linear(n_features, d_model)
        self.pos_enc = PositionalEncoding(d_model, max_len=max_seq_len, dropout=dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_ff,
            dropout=dropout,
            batch_first=True,
            norm_first=True,  # Pre-LN for stable training
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)

        # Dual classification + regression heads
        self.storm_head = nn.Sequential(
            nn.Linear(d_model, 128),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(128, 1),  # Binary logit
        )
        self.kp_head = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.GELU(),
            nn.Linear(64, 1),  # Kp index regression (0-9)
        )
        self.confidence_head = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.GELU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

        self._init_weights()

    def _init_weights(self) -> None:
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

    def forward(
        self, x: torch.Tensor, src_key_padding_mask: torch.Tensor | None = None
    ) -> dict[str, torch.Tensor]:
        """
        Args:
            x: (batch, seq_len, n_features)
            src_key_padding_mask: (batch, seq_len) bool mask for padding

        Returns:
            dict with keys: storm_logit, storm_prob, kp_estimate, confidence
        """
        h = self.input_proj(x)          # (B, T, d_model)
        h = self.pos_enc(h)
        h = self.encoder(h, src_key_padding_mask=src_key_padding_mask)

        # Pool over time — use CLS-style mean pooling
        cls = h.mean(dim=1)             # (B, d_model)

        storm_logit = self.storm_head(cls).squeeze(-1)          # (B,)
        storm_prob = torch.sigmoid(storm_logit)
        kp_estimate = self.kp_head(cls).squeeze(-1) * 9.0       # (B,) scaled to [0,9]
        confidence = self.confidence_head(cls).squeeze(-1)      # (B,)

        return {
            "storm_logit": storm_logit,
            "storm_prob": storm_prob,
            "kp_estimate": kp_estimate,
            "confidence": confidence,
        }

    @torch.no_grad()
    def predict(self, x: torch.Tensor) -> dict[str, float]:
        """Single-sample inference. x: (seq_len, n_features) → scalars."""
        self.eval()
        out = self.forward(x.unsqueeze(0))
        return {
            "storm_probability": float(out["storm_prob"][0]),
            "kp_index_estimate": float(out["kp_estimate"][0].clamp(0, 9)),
            "confidence_score": float(out["confidence"][0]),
        }
