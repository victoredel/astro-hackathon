"""
DAGGER-inspired Conditional GAN for synthetic extreme-storm generation.

Architecture:
  - Generator: conditioned on latent vector z → storm time-series
  - Discriminator: classifies real vs. synthetic sequences
  - Training: WGAN-GP loss for stable training on rare-event data

Purpose: Augment the training set with synthetic extreme-storm sequences
to improve the model's ability to detect Kp≥7 events (very rare in real data).
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class StormGenerator(nn.Module):
    """
    Generates synthetic solar-wind time-series conditioned on a latent code.

    Args:
        latent_dim: Input noise + conditioning vector size.
        seq_len:    Output sequence length.
        output_dim: Features per time step (7).
        hidden_dim: Hidden dimension.
    """

    def __init__(
        self,
        latent_dim: int = 128,
        seq_len: int = 60,
        output_dim: int = 7,
        hidden_dim: int = 512,
    ) -> None:
        super().__init__()
        self.seq_len = seq_len
        self.output_dim = output_dim

        self.mlp = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
        )
        self.gru = nn.GRU(hidden_dim, hidden_dim, batch_first=True, num_layers=2)
        self.out_proj = nn.Linear(hidden_dim, output_dim)

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        """z: (B, latent_dim) → (B, seq_len, output_dim)"""
        h = self.mlp(z)                          # (B, hidden_dim)
        h = h.unsqueeze(1).repeat(1, self.seq_len, 1)  # (B, T, hidden_dim)
        h, _ = self.gru(h)
        return self.out_proj(h)                  # (B, T, output_dim)


class StormDiscriminator(nn.Module):
    """Distinguishes real vs. GAN-generated solar-wind sequences."""

    def __init__(self, seq_len: int = 60, input_dim: int = 7, hidden_dim: int = 256) -> None:
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(input_dim, 64, kernel_size=3, padding=1),
            nn.LeakyReLU(0.2),
            nn.Conv1d(64, 128, kernel_size=3, stride=2, padding=1),
            nn.LeakyReLU(0.2),
            nn.Conv1d(128, 256, kernel_size=3, stride=2, padding=1),
            nn.LeakyReLU(0.2),
        )
        conv_out = 256 * (seq_len // 4)
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(conv_out, hidden_dim),
            nn.LeakyReLU(0.2),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, T, input_dim) → (B, 1) Wasserstein critic score"""
        x = x.permute(0, 2, 1)  # (B, C, T) for Conv1d
        h = self.conv(x)
        return self.classifier(h)


def gradient_penalty(disc: StormDiscriminator, real: torch.Tensor, fake: torch.Tensor) -> torch.Tensor:
    """WGAN-GP gradient penalty term."""
    B = real.size(0)
    alpha = torch.rand(B, 1, 1, device=real.device)
    interpolated = (alpha * real + (1 - alpha) * fake).requires_grad_(True)
    d_interp = disc(interpolated)
    grad = torch.autograd.grad(
        outputs=d_interp,
        inputs=interpolated,
        grad_outputs=torch.ones_like(d_interp),
        create_graph=True,
        retain_graph=True,
    )[0]
    gp = ((grad.norm(2, dim=(1, 2)) - 1) ** 2).mean()
    return gp


class StormGAN(nn.Module):
    """Convenience wrapper holding Generator and Discriminator together."""

    def __init__(self, latent_dim: int = 128, seq_len: int = 60, output_dim: int = 7) -> None:
        super().__init__()
        self.latent_dim = latent_dim
        self.generator = StormGenerator(latent_dim, seq_len, output_dim)
        self.discriminator = StormDiscriminator(seq_len, output_dim)

    @torch.no_grad()
    def generate_storms(self, n: int = 16, device: str = "cpu") -> torch.Tensor:
        """Sample n synthetic storm sequences."""
        self.generator.eval()
        z = torch.randn(n, self.latent_dim, device=device)
        return self.generator(z)  # (n, seq_len, output_dim)
