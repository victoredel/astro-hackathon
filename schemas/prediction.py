"""
Pydantic schema for AI storm prediction output (Esquema 2).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class AlertLevel(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


def _probability_to_alert(prob: float) -> AlertLevel:
    if prob >= 0.70:
        return AlertLevel.CRITICAL
    if prob >= 0.40:
        return AlertLevel.WARNING
    return AlertLevel.NORMAL


class StormPrediction(BaseModel):
    """Esquema 2 — AI-generated storm probability prediction."""

    prediction_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    target_timestamp: datetime = Field(..., description="Future timestamp this prediction applies to")

    storm_probability: float = Field(..., ge=0.0, le=1.0, description="Probability of geomagnetic storm (0–1)")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Model confidence in prediction (0–1)")
    alert_level: AlertLevel = Field(default=AlertLevel.NORMAL)

    # Optional extras for the dashboard
    kp_index_estimate: float | None = Field(default=None, description="Estimated Kp index (0–9)")
    horizon_minutes: int = Field(default=30, description="Prediction horizon in minutes")
    primary_driver: str | None = Field(default=None, description="Human-readable XAI explanation of the dominant factor")

    @field_validator("alert_level", mode="before")
    @classmethod
    def auto_alert(cls, v, info):
        """Auto-derive alert level from probability if not explicitly provided."""
        if v is None or v == AlertLevel.NORMAL:
            prob = info.data.get("storm_probability")
            if prob is not None:
                return _probability_to_alert(prob)
        return v

    model_config = {"json_schema_extra": {
        "example": {
            "target_timestamp": "2026-03-25T12:30:00Z",
            "storm_probability": 0.82,
            "confidence_score": 0.91,
            "alert_level": "CRITICAL",
            "kp_index_estimate": 7.2,
            "horizon_minutes": 30,
        }
    }}


class PredictionHistory(BaseModel):
    predictions: list[StormPrediction]
    count: int
