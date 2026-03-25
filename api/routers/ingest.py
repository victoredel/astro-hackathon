"""
POST /ingest — Accepts validated SensorTelemetry and persists it.

Prediction is now DECOUPLED from ingestion via a config flag
(`ENABLE_AI_INFERENCE`) and an optional query parameter (`run_inference`).

This allows the daemon to bulk-insert telemetry without triggering
the ML model on every record — useful during the data-collection phase.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.ws_manager import manager
from config import get_settings
from db.database import get_session
from db.models import PredictionRecord, TelemetryRecord
from schemas.prediction import StormPrediction
from schemas.telemetry import SensorTelemetry, TelemetryBatch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])
cfg = get_settings()


# ── Persistence helpers ───────────────────────────────────────────────────────

async def _persist_telemetry(rec: SensorTelemetry, session: AsyncSession) -> None:
    row = TelemetryRecord(
        event_id=str(rec.event_id),
        timestamp=rec.timestamp,
        source=rec.source.value,
        bx_gse=rec.bx_gse,
        by_gse=rec.by_gse,
        bz_gse=rec.bz_gse,
        speed=rec.speed,
        density=rec.density,
        temperature=rec.temperature,
    )
    session.add(row)
    await session.commit()


async def _persist_prediction(pred: StormPrediction, session: AsyncSession) -> None:
    row = PredictionRecord(
        prediction_id=str(pred.prediction_id),
        generated_at=pred.generated_at,
        target_timestamp=pred.target_timestamp,
        storm_probability=pred.storm_probability,
        confidence_score=pred.confidence_score,
        alert_level=pred.alert_level.value,
        kp_index_estimate=pred.kp_index_estimate,
        horizon_minutes=pred.horizon_minutes,
    )
    session.add(row)
    await session.commit()


async def _fetch_sequence(session: AsyncSession) -> list[SensorTelemetry]:
    """Return the last `sequence_len` telemetry records in chronological order."""
    result = await session.execute(
        select(TelemetryRecord)
        .order_by(desc(TelemetryRecord.timestamp))
        .limit(cfg.sequence_len)
    )
    rows = result.scalars().all()
    return [
        SensorTelemetry(
            event_id=r.event_id,
            timestamp=r.timestamp,
            source=r.source,  # type: ignore[arg-type]
            bx_gse=r.bx_gse,
            by_gse=r.by_gse,
            bz_gse=r.bz_gse,
            speed=r.speed,
            density=r.density,
            temperature=r.temperature,
        )
        for r in reversed(rows)
    ]


def _should_run_inference(run_inference_param: bool | None) -> bool:
    """
    Decide whether AI inference runs.

    Priority (highest → lowest):
      1. Explicit `run_inference` query param, if provided
      2. `ENABLE_AI_INFERENCE` setting from config / .env
    """
    if run_inference_param is not None:
        return run_inference_param
    return cfg.enable_ai_inference


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
async def ingest_single(
    payload: SensorTelemetry,
    run_inference: Annotated[bool | None, Query(
        description="Override ENABLE_AI_INFERENCE for this request. "
                    "Pass false to skip AI and just persist telemetry."
    )] = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Ingest a single telemetry sample.

    - Always persists telemetry to `telemetry` table.
    - Runs AI inference **only** if enabled (config or query param).
    - Returns `{status, event_id}` when inference is off,
      or the full StormPrediction payload when inference is on.
    """
    await _persist_telemetry(payload, session)

    if not _should_run_inference(run_inference):
        logger.debug("Inference skipped for event %s (flag disabled)", payload.event_id)
        return {
            "status": "persisted",
            "event_id": str(payload.event_id),
            "inference": "disabled",
        }

    # ── AI inference path ─────────────────────────────────────────────────────
    from pipeline.predictor import predictor

    records = await _fetch_sequence(session)
    pred = predictor.predict(records)
    await _persist_prediction(pred, session)
    await manager.broadcast(pred.model_dump(mode="json"))

    return {
        "status": "predicted",
        "event_id": str(payload.event_id),
        "inference": "enabled",
        "prediction": pred.model_dump(mode="json"),
    }


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def ingest_batch(
    payload: TelemetryBatch,
    run_inference: Annotated[bool | None, Query(
        description="Run inference after batch insert? Defaults to ENABLE_AI_INFERENCE setting."
    )] = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Bulk-ingest telemetry records.

    Persists all records first, then optionally runs a single inference
    pass on the last sequence window. Efficient for historical back-fill.
    """
    for rec in payload.records:
        await _persist_telemetry(rec, session)

    result: dict = {"ingested": len(payload.records), "inference": "disabled"}

    if _should_run_inference(run_inference):
        from pipeline.predictor import predictor
        records = await _fetch_sequence(session)
        pred = predictor.predict(records)
        await _persist_prediction(pred, session)
        await manager.broadcast(pred.model_dump(mode="json"))
        result["inference"] = "enabled"
        result["prediction"] = pred.model_dump(mode="json")

    return result
