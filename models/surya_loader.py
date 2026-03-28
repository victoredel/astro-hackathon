"""
Model loader — tries IBM Surya via HuggingFace, falls back to SolarTransformer surrogate.
"""
from __future__ import annotations

import logging
import os

import torch

logger = logging.getLogger(__name__)


def load_model(use_real_surya: bool = False, checkpoint: str | None = None):
    """
    Load the prediction model.

    Priority:
      1. IBM/NASA Surya from HuggingFace Hub   (if use_real_surya=True)
      2. SolarTransformer + LoRA adapter        (if checkpoint exists)
      3. Untrained SolarTransformer surrogate   (fallback for demo/dev)

    Returns the model in eval() mode on the best available device.
    """
    from models.solar_transformer import SolarTransformer

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Using device: %s", device)

    if use_real_surya:
        try:
            from models.surya_adapter import SuryaTimeSeriesAdapter
            logger.info("Instantiating SuryaTimeSeriesAdapter (Prithvi backbone + trainable heads)...")
            adapter = SuryaTimeSeriesAdapter(n_features=7)  # uses ibm-nasa-geospatial/Prithvi-EO-1.0-100M
            logger.info(
                "Adapter ready — backbone real=%s | trainable params=%d",
                adapter.backbone_is_real_prithvi(),
                sum(p.numel() for p in adapter.trainable_parameters()),
            )
            return adapter.to(device).eval()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "SuryaTimeSeriesAdapter unavailable (%s). Falling back to SolarTransformer surrogate.", exc
            )

    base = SolarTransformer(
        n_features=7,
        d_model=512,
        n_heads=8,
        n_layers=6,
        d_ff=2048,
    )

    if checkpoint and os.path.exists(checkpoint):
        logger.info("Loading LoRA adapter from %s", checkpoint)
        from models.lora_config import load_lora_adapter
        base = load_lora_adapter(base, checkpoint)
    else:
        logger.warning("No checkpoint found — running untrained surrogate model (demo mode)")

    return base.to(device).eval()
