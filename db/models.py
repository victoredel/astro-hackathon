"""
SQLAlchemy ORM models for persistent storage.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TelemetryRecord(Base):
    """Maps to `telemetry` table — mirrors SensorTelemetry schema."""

    __tablename__ = "telemetry"

    event_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="DSCOVR")

    bx_gse: Mapped[float] = mapped_column(Float, nullable=False)
    by_gse: Mapped[float] = mapped_column(Float, nullable=False)
    bz_gse: Mapped[float] = mapped_column(Float, nullable=False)

    speed: Mapped[float] = mapped_column(Float, nullable=False)
    density: Mapped[float] = mapped_column(Float, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (Index("ix_telemetry_timestamp", "timestamp"),)


class PredictionRecord(Base):
    """Maps to `predictions` table — mirrors StormPrediction schema."""

    __tablename__ = "predictions"

    prediction_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    storm_probability: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    alert_level: Mapped[str] = mapped_column(String(16), default="NORMAL")
    kp_index_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    horizon_minutes: Mapped[int] = mapped_column(default=30)

    __table_args__ = (Index("ix_predictions_generated_at", "generated_at"),)
