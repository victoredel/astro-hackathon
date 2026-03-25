"""
Variational Autoencoder (VAE) for compressing historical solar-wind sequences.

Used to:
  1. Learn a compact latent representation of solar wind patterns
  2. Generate conditioning vectors for the StormGAN
  3. Detect anomalous telemetry (reconstruction error > threshold → flag)
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class Encoder(nn.Module):
    def __init__(self, input_dim: int, seq_len: int, latent_dim: int, hidden_dim: int = 256) -> None:
        super().__init__()
        flat = input_dim * seq_len
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(flat, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.GELU(),
        )
        self.mu_head = nn.Linear(hidden_dim // 2, latent_dim)
        self.logvar_head = nn.Linear(hidden_dim // 2, latent_dim)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.net(x)
        return self.mu_head(h), self.logvar_head(h)


class Decoder(nn.Module):
    def __init__(self, latent_dim: int, seq_len: int, output_dim: int, hidden_dim: int = 256) -> None:
        super().__init__()
        self.seq_len = seq_len
        self.output_dim = output_dim
        flat = output_dim * seq_len
        self.net = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim // 2),
            nn.GELU(),
            nn.Linear(hidden_dim // 2, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, flat),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        return self.net(z).view(-1, self.seq_len, self.output_dim)


class SolarVAE(nn.Module):
    """
    Variational Autoencoder for solar wind time-series.

    Args:
        input_dim:  Features per time step (7 for our schema).
        seq_len:    Sequence length (60 minutes default).
        latent_dim: Bottleneck size (default 64).
    """

    def __init__(self, input_dim: int = 7, seq_len: int = 60, latent_dim: int = 64) -> None:
        super().__init__()
        self.encoder = Encoder(input_dim, seq_len, latent_dim)
        self.decoder = Decoder(latent_dim, seq_len, input_dim)
        self.latent_dim = latent_dim

    @staticmethod
    def reparameterize(mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mu + eps * std

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        mu, logvar = self.encoder(x)
        z = self.reparameterize(mu, logvar)
        recon = self.decoder(z)
        return {"recon": recon, "mu": mu, "logvar": logvar, "z": z}

    def loss(self, x: torch.Tensor, out: dict) -> torch.Tensor:
        recon_loss = F.mse_loss(out["recon"], x, reduction="mean")
        # KL divergence
        kl = -0.5 * torch.mean(1 + out["logvar"] - out["mu"].pow(2) - out["logvar"].exp())
        return recon_loss + 0.001 * kl

    @torch.no_grad()
    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """Return mean latent vector (no sampling)."""
        mu, _ = self.encoder(x)
        return mu

    @torch.no_grad()
    def anomaly_score(self, x: torch.Tensor) -> float:
        """MSE reconstruction error — high score = anomalous telemetry."""
        self.eval()
        out = self.forward(x.unsqueeze(0))
        return float(F.mse_loss(out["recon"][0], x))
