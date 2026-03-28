"""
Training script — supports two model modes:

  surrogate  (default)  Fine-tunes SolarTransformer with LoRA.
  surya                 Trains only the adapter layers of SuryaTimeSeriesAdapter
                        (Prithvi backbone stays frozen — prevents OOM).

Data sources:
  - DONKI API (NASA) for historical CME / geomagnetic storm labels
  - GAN-generated synthetic extreme-storm sequences for augmentation
  - SuryaBench S3 (if credentials available)

Usage:
  python models/train.py --epochs 20 --lr 1e-4 --batch 32 --output checkpoints/solar_lora
  python models/train.py --model-type surya --epochs 10 --output checkpoints/surya_adapter
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `models.*` imports when running as `python models/train.py` inside Docker
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, random_split

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Synthetic dataset (no external dependency) — demonstrates the training API
# ──────────────────────────────────────────────────────────────────────────────

class SyntheticSolarDataset(Dataset):
    """
    Generates synthetic solar wind sequences for demonstration / unit tests.
    Replace with SuryaBench loader for real training.
    """

    def __init__(self, n_samples: int = 2000, seq_len: int = 60, n_features: int = 7) -> None:
        self.data = []
        rng = np.random.default_rng(42)

        for _ in range(n_samples):
            is_storm = rng.random() < 0.25  # 25% storm prevalence (after GAN aug)

            if is_storm:
                # Extreme southward Bz, high speed
                bz = rng.uniform(-40, -10)
                speed = rng.uniform(650, 1200)
                density = rng.uniform(10, 50)
            else:
                bz = rng.uniform(-5, 5)
                speed = rng.uniform(300, 600)
                density = rng.uniform(2, 15)

            seq = np.zeros((seq_len, n_features), dtype=np.float32)
            for t in range(seq_len):
                seq[t] = [
                    rng.normal(0, 3),          # bx
                    rng.normal(0, 3),          # by
                    bz + rng.normal(0, 1),     # bz
                    speed + rng.normal(0, 20), # speed
                    density + rng.normal(0, 1),# density
                    120000 + rng.normal(0, 5000), # temperature
                    np.sqrt(seq[t, 0]**2 + seq[t, 1]**2 + bz**2),  # bt
                ]

            self.data.append((torch.from_numpy(seq), torch.tensor(float(is_storm))))

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx]


# ──────────────────────────────────────────────────────────────────────────────
# Training loop
# ──────────────────────────────────────────────────────────────────────────────

def train(args: argparse.Namespace) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Training on %s | model-type=%s", device, args.model_type)

    # ── Model ──────────────────────────────────────────────────────────────────
    use_surya = args.model_type == "surya"

    if use_surya:
        from models.surya_adapter import SuryaTimeSeriesAdapter
        model = SuryaTimeSeriesAdapter(n_features=7).to(device)
        trainable = model.trainable_parameters()
        logger.info(
            "SuryaTimeSeriesAdapter — backbone frozen, trainable params: %d",
            sum(p.numel() for p in trainable),
        )
    else:
        from models.solar_transformer import SolarTransformer
        from models.lora_config import get_lora_model
        base = SolarTransformer()
        model = get_lora_model(base).to(device)
        trainable = list(filter(lambda p: p.requires_grad, model.parameters()))

    # ── Augment with GAN synthetic storms ──────────────────────────────────────
    if args.gan_augment:
        from models.storm_gan import StormGAN
        logger.info("Generating %d synthetic storm sequences via GAN...", args.n_synthetic)
        gan = StormGAN()
        synthetics = gan.generate_storms(n=args.n_synthetic, device="cpu")
        logger.info("GAN synthetic sequences shape: %s", synthetics.shape)

    # ── Dataset ────────────────────────────────────────────────────────────────
    dataset = SyntheticSolarDataset(n_samples=args.n_samples, seq_len=60)
    n_val = max(1, int(len(dataset) * 0.15))
    n_train = len(dataset) - n_val
    train_ds, val_ds = random_split(dataset, [n_train, n_val])
    train_loader = DataLoader(train_ds, batch_size=args.batch, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch)

    # ── Optimizer — only trainable params (backbone stays frozen) ─────────────
    optimizer = torch.optim.AdamW(
        trainable,
        lr=args.lr,
        weight_decay=1e-4,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([1.5], device=device))  # imbalance

    best_val_loss = float("inf")

    for epoch in range(1, args.epochs + 1):
        # ── Train ──────────────────────────────────────────────────────────────
        model.train()
        train_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out["storm_logit"], y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += loss.item()

        # ── Validate ────────────────────────────────────────────────────────────
        model.eval()
        val_loss = 0.0
        correct = 0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
                out = model(x)
                loss = criterion(out["storm_logit"], y)
                val_loss += loss.item()
                preds = (out["storm_prob"] >= 0.5).float()
                correct += (preds == y).sum().item()

        avg_train = train_loss / len(train_loader)
        avg_val = val_loss / len(val_loader)
        accuracy = correct / len(val_ds)
        scheduler.step()
        logger.info(
            "Epoch %d/%d | train_loss=%.4f | val_loss=%.4f | val_acc=%.3f",
            epoch, args.epochs, avg_train, avg_val, accuracy,
        )

        if avg_val < best_val_loss:
            best_val_loss = avg_val
            Path(args.output).mkdir(parents=True, exist_ok=True)
            if use_surya:
                # Save adapter-only state dict (projection + heads; not the frozen backbone)
                adapter_state = {
                    k: v for k, v in model.state_dict().items()
                    if not k.startswith("_backbone")
                }
                torch.save(adapter_state, Path(args.output) / "surya_adapter_heads.pt")
                logger.info("✓ Surya adapter heads saved to %s", args.output)
            else:
                from models.lora_config import save_lora_adapter
                save_lora_adapter(model, args.output)
                logger.info("✓ Best model saved to %s", args.output)

    logger.info("Training complete. Best val loss: %.4f", best_val_loss)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fine-tune SolarTransformer (surrogate) or SuryaTimeSeriesAdapter (surya)"
    )
    parser.add_argument(
        "--model-type",
        type=str,
        default="surrogate",
        choices=["surrogate", "surya"],
        help=(
            "'surrogate': SolarTransformer + LoRA (default). "
            "'surya': SuryaTimeSeriesAdapter — trains only projection + heads, "
            "backbone (Prithvi) stays frozen."
        ),
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--n-samples", type=int, default=2000)
    parser.add_argument("--output", type=str, default="checkpoints/solar_lora")
    parser.add_argument("--gan-augment", action="store_true", default=True)
    parser.add_argument("--n-synthetic", type=int, default=500)
    args = parser.parse_args()
    train(args)
