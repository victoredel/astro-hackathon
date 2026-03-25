"""
Pydantic schema for incoming sensor telemetry from NOAA SWPC satellites.
Strict typing + physical range validation for all solar wind parameters.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


class SatelliteSource(str, Enum):
    DSCOVR = "DSCOVR"
    ACE = "ACE"
    WIND = "WIND"


class SensorTelemetry(BaseModel):
    """Esquema 1 — raw solar wind telemetry from L1 satellites."""

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique event identifier")
    timestamp: datetime = Field(..., description="ISO 8601 measurement timestamp")
    source: SatelliteSource = Field(default=SatelliteSource.DSCOVR, description="Data source satellite")

    # ─── IMF (Interplanetary Magnetic Field) components [nT] ──────────────────
    bx_gse: float = Field(..., description="Bx component in GSE frame [nT]")
    by_gse: float = Field(..., description="By component in GSE frame [nT]")
    bz_gse: float = Field(..., description="Bz component in GSE frame [nT] — critical for storm prediction")

    # ─── Plasma parameters ────────────────────────────────────────────────────
    speed: float = Field(..., description="Solar wind bulk speed [km/s]", ge=200.0, le=3000.0)
    density: float = Field(..., description="Proton number density [p/cc]", ge=0.0, le=200.0)
    temperature: float = Field(..., description="Proton temperature [K]", ge=0.0)

    @field_validator("bx_gse", "by_gse", "bz_gse")
    @classmethod
    def validate_imf_range(cls, v: float, info) -> float:  # noqa: ANN001
        if not (-500.0 <= v <= 500.0):
            raise ValueError(f"{info.field_name} = {v} nT is outside physical range [-500, 500]")
        return v

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v

    model_config = {"json_schema_extra": {
        "example": {
            "timestamp": "2026-03-25T12:00:00Z",
            "source": "DSCOVR",
            "bx_gse": 2.1,
            "by_gse": -3.5,
            "bz_gse": -18.7,
            "speed": 650.3,
            "density": 12.4,
            "temperature": 85000.0,
        }
    }}


class TelemetryBatch(BaseModel):
    """Optional batch ingestion wrapper."""
    records: list[SensorTelemetry] = Field(..., min_length=1, max_length=1440)
