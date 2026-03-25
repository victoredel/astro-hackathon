"""Tests for Pydantic telemetry and prediction schemas."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from schemas.telemetry import SatelliteSource, SensorTelemetry, TelemetryBatch
from schemas.prediction import AlertLevel, StormPrediction


class TestSensorTelemetry:

    def _valid(self, **overrides) -> dict:
        base = {
            "timestamp": "2026-03-25T12:00:00Z",
            "source": "DSCOVR",
            "bx_gse": 2.0,
            "by_gse": -3.0,
            "bz_gse": -18.0,
            "speed": 600.0,
            "density": 10.0,
            "temperature": 100000.0,
        }
        base.update(overrides)
        return base

    def test_valid_record(self):
        rec = SensorTelemetry(**self._valid())
        assert isinstance(rec.event_id, uuid.UUID)
        assert rec.source == SatelliteSource.DSCOVR
        assert rec.bz_gse == -18.0

    def test_bz_out_of_range(self):
        with pytest.raises(ValidationError, match="bz_gse"):
            SensorTelemetry(**self._valid(bz_gse=-600.0))

    def test_speed_below_minimum(self):
        with pytest.raises(ValidationError):
            SensorTelemetry(**self._valid(speed=50.0))  # below 200 km/s

    def test_speed_above_maximum(self):
        with pytest.raises(ValidationError):
            SensorTelemetry(**self._valid(speed=5000.0))  # above 3000 km/s

    def test_negative_density(self):
        with pytest.raises(ValidationError):
            SensorTelemetry(**self._valid(density=-1.0))

    def test_timestamp_z_suffix(self):
        rec = SensorTelemetry(**self._valid(timestamp="2026-01-01T00:00:00Z"))
        assert rec.timestamp is not None

    def test_batch_model(self):
        records = [self._valid() for _ in range(5)]
        batch = TelemetryBatch(records=records)
        assert len(batch.records) == 5

    def test_batch_empty_fails(self):
        with pytest.raises(ValidationError):
            TelemetryBatch(records=[])


class TestStormPrediction:

    def test_alert_auto_derive_critical(self):
        target = datetime.now(tz=timezone.utc)
        pred = StormPrediction(
            target_timestamp=target,
            storm_probability=0.85,
            confidence_score=0.90,
        )
        assert pred.alert_level == AlertLevel.CRITICAL

    def test_alert_auto_derive_warning(self):
        target = datetime.now(tz=timezone.utc)
        pred = StormPrediction(
            target_timestamp=target,
            storm_probability=0.55,
            confidence_score=0.75,
        )
        assert pred.alert_level == AlertLevel.WARNING

    def test_alert_normal(self):
        target = datetime.now(tz=timezone.utc)
        pred = StormPrediction(
            target_timestamp=target,
            storm_probability=0.10,
            confidence_score=0.60,
        )
        assert pred.alert_level == AlertLevel.NORMAL

    def test_probability_out_of_range(self):
        with pytest.raises(ValidationError):
            StormPrediction(
                target_timestamp=datetime.now(tz=timezone.utc),
                storm_probability=1.5,
                confidence_score=0.8,
            )

    def test_json_serialisation(self):
        pred = StormPrediction(
            target_timestamp=datetime.now(tz=timezone.utc),
            storm_probability=0.72,
            confidence_score=0.88,
        )
        data = pred.model_dump(mode="json")
        assert "prediction_id" in data
        assert data["alert_level"] == "CRITICAL"
