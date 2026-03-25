"""
SQLAlchemy ORM models for persistent storage.
Tables:
  - telemetry       : raw solar wind samples from satellites
  - predictions     : AI-generated storm probability forecasts
  - storm_events    : ground-truth CME/GST events from NASA DONKI (new)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
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


class StormEventRecord(Base):
    """
    Maps to `storm_events` table.

    Ground-truth geomagnetic storm / CME events sourced from NASA DONKI API.
    Used as labels for model training and offline evaluation.

    Event types ingested:
      - GST  (Geomagnetic Storm) — direct Kp/Dst labels
      - CME  (Coronal Mass Ejection) — source event with travel time
      - IPS  (Interplanetary Shock) — precursor arrival at L1
    """

    __tablename__ = "storm_events"

    # ── Identity ──────────────────────────────────────────────────────────────
    event_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # External DONKI identifier, e.g. "2024-07-01T12:00:00-CME-001"
    donki_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True, index=True)

    event_type: Mapped[str] = mapped_column(
        String(8), nullable=False, index=True,
        comment="GST | CME | IPS | SEP",
    )

    # ── Timing ───────────────────────────────────────────────────────────────
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # For CMEs: when the ejecta is predicted / observed to arrive at Earth
    impact_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Storm severity (GST events) ───────────────────────────────────────────
    kp_max: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Maximum observed Kp index during storm (0-9)",
    )
    dst_min: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Minimum Dst index [nT] — more negative = more intense",
    )

    # ── CME parameters ────────────────────────────────────────────────────────
    cme_speed_kms: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="CME propagation speed [km/s] from DONKI catalog",
    )
    cme_half_angle: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="CME half-angle [deg] — proxy for angular width",
    )
    is_earth_directed: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="Whether the CME is flagged as Earth-directed",
    )

    # ── Classification label ──────────────────────────────────────────────────
    is_storm: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True,
        comment="True if event produced Kp≥5 (G1+ storm threshold)",
    )
    severity: Mapped[str | None] = mapped_column(
        String(16), nullable=True,
        comment="G1 | G2 | G3 | G4 | G5 (NOAA geomagnetic scale)",
    )

    # ── Source metadata ───────────────────────────────────────────────────────
    source_api: Mapped[str] = mapped_column(
        String(32), default="NASA_DONKI",
        comment="Which API / catalog this record came from",
    )
    raw_json: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Full JSON response payload from DONKI for auditability",
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.utcnow(),
        comment="When this record was written to our DB",
    )

    __table_args__ = (
        Index("ix_storm_events_start_time", "start_time"),
        Index("ix_storm_events_type_storm", "event_type", "is_storm"),
    )
