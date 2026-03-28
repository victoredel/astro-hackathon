"""
SuryaTimeSeriesAdapter — Adapter pattern bridging IBM/NASA Prithvi-EO-1.0
with our solar-wind time-series pipeline.

Problem: Prithvi is a Vision Transformer (ViT) that expects image patches,
not (seq_len, 7) tabular time-series tensors, and its output has no notion
of storm_probability / kp_index / confidence.

Solution: Wrap Prithvi's encoder as a frozen backbone and bolt on:
  1. Input projection  : nn.Linear(n_features → hidden_dim) to embed our
                         7 solar-wind features into Prithvi's embedding space.
  2. Positional encoding re-used from SolarTransformer.
  3. Output heads       : identical to SolarTransformer (storm_head, kp_head,
                          confidence_head).

Only the projection layer and the three heads are trainable; the backbone
stays frozen to prevent OOM on commodity hardware.
"""
from __future__ import annotations

import logging
from typing import Optional

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)

# Prithvi-EO-1.0-100M uses ViT-Base hidden dim
PRITHVI_HIDDEN_DIM = 768


class _PositionalEncoding(nn.Module):
    """Sinusoidal PE — same implementation as SolarTransformer."""

    import math as _math

    def __init__(self, d_model: int, max_len: int = 512, dropout: float = 0.1) -> None:
        super().__init__()
        import math

        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))  # (1, max_len, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, : x.size(1)]
        return self.dropout(x)


class SuryaTimeSeriesAdapter(nn.Module):
    """
    Adapter that wraps Prithvi-EO-1.0 as a frozen backbone and adds
    learnable projection + output heads for solar-wind prediction.

    Args:
        n_features:  Number of solar-wind input features (default 7).
        hidden_dim:  Prithvi's internal hidden dimension (default 1024).
        dropout:     Dropout applied in the new layers.
        max_seq_len: Maximum time-series length for positional encoding.
    """

    def __init__(
        self,
        n_features: int = 7,
        hidden_dim: int = PRITHVI_HIDDEN_DIM,
        dropout: float = 0.1,
        max_seq_len: int = 512,
    ) -> None:
        super().__init__()

        self.hidden_dim = hidden_dim

        # ── 1. Load & freeze the Prithvi backbone ─────────────────────────────
        logger.info("Downloading and loading IBM/NASA Prithvi-EO-1.0-100M manually...")
        try:
            from huggingface_hub import hf_hub_download
            import importlib.util

            # Download official NASA source + weights
            model_def_path = hf_hub_download(
                repo_id="ibm-nasa-geospatial/Prithvi-EO-1.0-100M",
                filename="prithvi_mae.py",
            )
            weights_path = hf_hub_download(
                repo_id="ibm-nasa-geospatial/Prithvi-EO-1.0-100M",
                filename="Prithvi_EO_V1_100M.pt",
            )

            # Dynamically import the module so no pip install of the model code is needed
            spec = importlib.util.spec_from_file_location("prithvi_mae", model_def_path)
            prithvi_mae = importlib.util.module_from_spec(spec)
            sys.modules["prithvi_mae"] = prithvi_mae
            spec.loader.exec_module(prithvi_mae)

            # Instantiate the 100M ViT-Base architecture
            self._backbone = prithvi_mae.MaskedAutoencoderViT(
                img_size=224, patch_size=16, num_frames=3, tubelet_size=1,
                in_chans=6, embed_dim=768, depth=12, num_heads=12,
                decoder_embed_dim=512, decoder_depth=8, decoder_num_heads=16,
                mlp_ratio=4., norm_pix_loss=False,
            )

            # Load pretrained weights (strict=False tolerates decoder mismatch)
            state_dict = torch.load(weights_path, map_location="cpu")
            if "model" in state_dict:
                state_dict = state_dict["model"]
            self._backbone.load_state_dict(state_dict, strict=False)

            self._freeze_backbone()
            self._backbone_loaded = True
            logger.info("✓ Prithvi backbone loaded natively and frozen (%d params frozen).",
                        sum(p.numel() for p in self._backbone.parameters()))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not load Prithvi backbone (%s). "
                "Adapter will use a lightweight Transformer stub for the backbone. "
                "Frozen-backbone semantics are preserved.",
                exc,
            )
            self._backbone = self._build_stub_backbone(hidden_dim, dropout)
            self._freeze_backbone()
            self._backbone_loaded = False

        # ── 2. Learnable input projection (7 → hidden_dim) ───────────────────
        self.input_proj = nn.Linear(n_features, hidden_dim)
        self.pos_enc = _PositionalEncoding(hidden_dim, max_len=max_seq_len, dropout=dropout)

        # ── 3. Output heads (identical contract to SolarTransformer) ──────────
        self.storm_head = nn.Sequential(
            nn.Linear(hidden_dim, 128),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(128, 1),  # binary logit
        )
        self.kp_head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.GELU(),
            nn.Linear(64, 1),  # Kp regression [0, 9]
        )
        self.confidence_head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.GELU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

        self._init_new_weights()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _freeze_backbone(self) -> None:
        """Freeze all backbone parameters to prevent OOM during fine-tuning."""
        for param in self._backbone.parameters():
            param.requires_grad = False

    @staticmethod
    def _build_stub_backbone(hidden_dim: int, dropout: float) -> nn.Module:
        """
        Lightweight Transformer stub used when the real Prithvi weights are
        unavailable (offline / CI environments).  Mirrors the interface we need:
        a module whose parameters can be frozen and that transforms
        (B, T, hidden_dim) → (B, T, hidden_dim).
        """
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=8,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True,
            norm_first=True,
        )
        stub = nn.TransformerEncoder(encoder_layer, num_layers=4)
        stub.is_stub = True  # flag for logging / tests
        return stub

    def _init_new_weights(self) -> None:
        """Xavier init for the newly created (trainable) layers only."""
        for module in [self.input_proj, self.storm_head, self.kp_head, self.confidence_head]:
            for p in module.parameters():
                if p.dim() > 1:
                    nn.init.xavier_uniform_(p)

    # ── Core forward ──────────────────────────────────────────────────────────

    def _encode(self, x: torch.Tensor) -> torch.Tensor:
        """
        Project time-series features into Prithvi's latent space and run
        the (frozen) backbone encoder.

        Args:
            x: (B, T, n_features)

        Returns:
            h: (B, T, hidden_dim) — contextual representations
        """
        h = self.input_proj(x)   # (B, T, hidden_dim)
        h = self.pos_enc(h)

        if self._backbone_loaded:
            # Bypass the 5D spatial patch_embed; inject our projected 1D
            # time-series directly into the pre-trained Transformer blocks.
            for blk in self._backbone.blocks:
                h = blk(h)
            h = self._backbone.norm(h)
        else:
            h = self._backbone(h)

        return h  # (B, T, hidden_dim)

    def forward(
        self,
        x: torch.Tensor,
        src_key_padding_mask: Optional[torch.Tensor] = None,
    ) -> dict[str, torch.Tensor]:
        """
        Args:
            x: (batch, seq_len, n_features) — solar-wind time-series
            src_key_padding_mask: (batch, seq_len) bool mask (optional)

        Returns:
            dict: storm_logit, storm_prob, kp_estimate, confidence
                  — same keys as SolarTransformer.forward()
        """
        h = self._encode(x)                   # (B, T, hidden_dim)
        cls = h.mean(dim=1)                   # mean-pool over time → (B, hidden_dim)

        storm_logit = self.storm_head(cls).squeeze(-1)          # (B,)
        storm_prob  = torch.sigmoid(storm_logit)
        kp_estimate = self.kp_head(cls).squeeze(-1) * 9.0       # (B,) → [0, 9]
        confidence  = self.confidence_head(cls).squeeze(-1)     # (B,)

        return {
            "storm_logit": storm_logit,
            "storm_prob":  storm_prob,
            "kp_estimate": kp_estimate,
            "confidence":  confidence,
        }

    @torch.no_grad()
    def predict(self, x: torch.Tensor) -> dict[str, float]:
        """
        Single-sample inference interface — mirrors SolarTransformer.predict().

        Args:
            x: (seq_len, n_features)

        Returns:
            dict: storm_probability, kp_index_estimate, confidence_score
        """
        self.eval()
        out = self.forward(x.unsqueeze(0))  # add batch dim
        return {
            "storm_probability": float(out["storm_prob"][0]),
            "kp_index_estimate": float(out["kp_estimate"][0].clamp(0, 9)),
            "confidence_score":  float(out["confidence"][0]),
        }

    # ── Utility ───────────────────────────────────────────────────────────────

    def trainable_parameters(self) -> list:
        """Return only the trainable (non-frozen) parameters."""
        return [p for p in self.parameters() if p.requires_grad]

    def backbone_is_real_prithvi(self) -> bool:
        """True if the real IBM/NASA weights were loaded successfully."""
        return self._backbone_loaded
