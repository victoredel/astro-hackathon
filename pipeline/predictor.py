"""
Inference engine — converts normalised tensors into StormPrediction objects.

Wraps the loaded ML model and applies:
  1. Sequence padding / truncation to match model input length
  2. Forward pass
  3. Mapping output scalars → StormPrediction schema
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import torch

from config import get_settings
from schemas.prediction import AlertLevel, StormPrediction
from schemas.telemetry import SensorTelemetry

logger = logging.getLogger(__name__)
settings = get_settings()


def _alert_from_prob(p: float) -> AlertLevel:
    if p >= 0.70:
        return AlertLevel.CRITICAL
    if p >= 0.40:
        return AlertLevel.WARNING
    return AlertLevel.NORMAL


def _get_primary_driver(records: list) -> str:
    """Heuristic XAI: return a human-readable explanation of the dominant driver."""
    if not records:
        return "Stable solar wind parameters."
    latest = records[-1]
    if latest.bz_gse < -10:
        return "Strong southward magnetic field (Bz) detected."
    if latest.speed > 600:
        return "Sudden spike in solar wind speed."
    if latest.density > 20:
        return "High density plasma cloud detected."
    return "Stable solar wind parameters."


class Predictor:
    """Thread-safe inference wrapper around the loaded model."""

    def __init__(self, model=None) -> None:
        self._model = model
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def load(self) -> None:
        """Lazy-load the model (called once at API startup)."""
        from config import get_settings
        from models.surya_loader import load_model
        cfg = get_settings()
        self._model = load_model(
            use_real_surya=cfg.use_real_surya,
            checkpoint=cfg.model_checkpoint,
        )
        logger.info("Predictor model loaded on %s", self._device)

    def predict(self, records: list[SensorTelemetry]) -> StormPrediction:
        """
        Run inference on a list of telemetry records.

        Args:
            records: Up to `sequence_len` recent telemetry samples (most-recent last).

        Returns:
            A fully-populated StormPrediction.
        """
        from pipeline.normalizer import normalize

        seq_len = settings.sequence_len
        horizon = settings.prediction_horizon_mins
        now = datetime.now(tz=timezone.utc)
        target_ts = now + timedelta(minutes=horizon)

        if self._model is None:
            logger.warning("Model not loaded — returning heuristic prediction")
            return self._heuristic_predict(records, target_ts, horizon)

        # Pad or truncate to seq_len
        if len(records) < seq_len:
            records = [records[0]] * (seq_len - len(records)) + records
        else:
            records = records[-seq_len:]

        tensor = normalize(records).to(self._device)  # (seq_len, 7)

        with torch.no_grad():
            out = self._model.predict(tensor)

        prob = float(out["storm_probability"])
        conf = float(out["confidence_score"])
        kp = out.get("kp_index_estimate")

        return StormPrediction(
            generated_at=now,
            target_timestamp=target_ts,
            storm_probability=round(prob, 4),
            confidence_score=round(conf, 4),
            alert_level=_alert_from_prob(prob),
            kp_index_estimate=round(kp, 2) if kp is not None else None,
            horizon_minutes=horizon,
            primary_driver=_get_primary_driver(records),
        )

    @staticmethod
    def _heuristic_predict(
        records: list[SensorTelemetry],
        target_ts: datetime,
        horizon: int,
    ) -> StormPrediction:
        """
        Physics-based heuristic fallback when the model is unavailable.
        Uses Bz southward component + speed as primary indicators.
        """
        latest = records[-1] if records else None
        if latest is None:
            prob, conf = 0.05, 0.20
        else:
            # Burton et al. proxy: negative Bz + high speed → storm
            bz = max(-latest.bz_gse, 0)   # southward component
            v = latest.speed
            raw = (bz / 30.0) * 0.6 + ((v - 400) / 600.0) * 0.4
            prob = float(min(max(raw, 0.0), 1.0))
            # Confidence is lower for heuristic
            conf = 0.45 if prob > 0.1 else 0.30

        return StormPrediction(
            generated_at=datetime.now(tz=timezone.utc),
            target_timestamp=target_ts,
            storm_probability=round(prob, 4),
            confidence_score=round(conf, 4),
            alert_level=_alert_from_prob(prob),
            horizon_minutes=horizon,
            primary_driver=_get_primary_driver(records),
        )


# Module-level singleton
predictor = Predictor()
