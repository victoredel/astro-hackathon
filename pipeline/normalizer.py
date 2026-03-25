"""
Data normalizer: raw SensorTelemetry records → normalised torch.Tensor.

Normalization strategy: Z-score with pre-computed statistics calibrated
on the NOAA SWPC climatological mean/std for each solar-wind parameter.

Feature order (column index):
  0: bx_gse    [nT]
  1: by_gse    [nT]
  2: bz_gse    [nT]   ← most storm-predictive feature
  3: speed     [km/s]
  4: density   [p/cc]
  5: temperature [K]
  6: bt        [nT]   ← derived: total field magnitude = sqrt(bx²+by²+bz²)
"""
from __future__ import annotations

import numpy as np
import torch

from schemas.telemetry import SensorTelemetry

# ── Climatological statistics (NOAA SWPC L1 historical averages) ──────────────
# Values sourced from published DSCOVR/ACE solar wind statistics.
FEATURE_MEANS = np.array([
    0.0,       # bx_gse  [nT]
    0.0,       # by_gse  [nT]
    -0.5,      # bz_gse  [nT]
    450.0,     # speed   [km/s]
    6.0,       # density [p/cc]
    120_000.0, # temperature [K]
    5.0,       # bt      [nT]
], dtype=np.float32)

FEATURE_STDS = np.array([
    4.0,       # bx_gse
    4.0,       # by_gse
    4.5,       # bz_gse
    100.0,     # speed
    5.0,       # density
    80_000.0,  # temperature
    4.0,       # bt
], dtype=np.float32)

FEATURE_NAMES = ["bx_gse", "by_gse", "bz_gse", "speed", "density", "temperature", "bt"]
N_FEATURES = 7


def _record_to_array(rec: SensorTelemetry) -> np.ndarray:
    bt = np.sqrt(rec.bx_gse**2 + rec.by_gse**2 + rec.bz_gse**2)
    return np.array([
        rec.bx_gse,
        rec.by_gse,
        rec.bz_gse,
        rec.speed,
        rec.density,
        rec.temperature,
        bt,
    ], dtype=np.float32)


def normalize(
    records: list[SensorTelemetry],
    means: np.ndarray = FEATURE_MEANS,
    stds: np.ndarray = FEATURE_STDS,
) -> torch.Tensor:
    """
    Convert a list of SensorTelemetry records into a normalised float32 tensor.

    Returns: torch.Tensor of shape (seq_len, N_FEATURES)
    """
    if not records:
        raise ValueError("records must be non-empty")

    raw = np.stack([_record_to_array(r) for r in records], axis=0)  # (T, 7)
    normalised = (raw - means) / (stds + 1e-8)
    return torch.from_numpy(normalised)


def denormalize(tensor: torch.Tensor) -> np.ndarray:
    """Inverse transform for display / reconstruction."""
    return tensor.numpy() * FEATURE_STDS + FEATURE_MEANS
