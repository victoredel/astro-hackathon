"""
LoRA configuration wrapper for SolarTransformer.

Uses Hugging Face PEFT to inject low-rank adapters into the
attention projection matrices, enabling efficient fine-tuning
with < 1% of the original parameter count.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_lora_model(base_model):
    """
    Wrap a SolarTransformer with LoRA adapters.

    LoRA targets the linear layers inside TransformerEncoderLayer:
    - in_proj / out_proj (mapped to q_proj / v_proj names via PEFT)

    Args:
        base_model: SolarTransformer instance

    Returns:
        PEFT model with LoRA adapters, or base_model if PEFT unavailable
    """
    try:
        from peft import LoraConfig, TaskType, get_peft_model

        lora_cfg = LoraConfig(
            task_type=TaskType.FEATURE_EXTRACTION,
            r=16,                             # rank
            lora_alpha=32,                    # scaling factor
            lora_dropout=0.05,
            bias="none",
            # Target the linear sub-layers of the encoder
            target_modules=["in_proj_weight", "out_proj"],
            modules_to_save=["storm_head", "kp_head", "confidence_head"],
        )
        model = get_peft_model(base_model, lora_cfg)
        model.print_trainable_parameters()
        return model

    except Exception as exc:  # noqa: BLE001
        logger.warning("PEFT/LoRA unavailable (%s) — using base model without adapters", exc)
        return base_model


def save_lora_adapter(model, path: str) -> None:
    """Save only the LoRA adapter weights (tiny files, ~MB range)."""
    try:
        model.save_pretrained(path)
        logger.info("LoRA adapter saved to %s", path)
    except AttributeError:
        import torch
        torch.save(model.state_dict(), path + "_full.pt")
        logger.info("Saved full state dict to %s_full.pt", path)


def load_lora_adapter(base_model, path: str):
    """Load a saved LoRA adapter onto a base model."""
    try:
        from peft import PeftModel
        return PeftModel.from_pretrained(base_model, path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load LoRA adapter from %s: %s — using base model", path, exc)
        return base_model
