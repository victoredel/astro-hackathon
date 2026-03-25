"""
POST /ingest — Accepts validated SensorTelemetry, runs prediction, broadcasts via WS.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.ws_manager import manager
from db.database import get_session
from db.models import PredictionRecord, TelemetryRecord
from pipeline.predictor import predictor
from schemas.prediction import StormPrediction
from schemas.telemetry import SensorTelemetry, TelemetryBatch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])


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


@router.post("", status_code=status.HTTP_201_CREATED, response_model=StormPrediction)
async def ingest_single(
    payload: SensorTelemetry,
    session: AsyncSession = Depends(get_session),
) -> StormPrediction:
    """Ingest a single telemetry sample and return the resulting prediction."""
    await _persist_telemetry(payload, session)

    # Fetch recent records for sequence context
    from sqlalchemy import select, desc
    from config import get_settings
    cfg = get_settings()

    result = await session.execute(
        select(TelemetryRecord)
        .order_by(desc(TelemetryRecord.timestamp))
        .limit(cfg.sequence_len)
    )
    rows = result.scalars().all()

    # Convert DB rows back to schema objects for predictor
    records: list[SensorTelemetry] = []
    for r in reversed(rows):  # chronological order
        records.append(SensorTelemetry(
            event_id=r.event_id,
            timestamp=r.timestamp,
            source=r.source,  # type: ignore[arg-type]
            bx_gse=r.bx_gse,
            by_gse=r.by_gse,
            bz_gse=r.bz_gse,
            speed=r.speed,
            density=r.density,
            temperature=r.temperature,
        ))

    pred = predictor.predict(records)
    await _persist_prediction(pred, session)

    # Broadcast to all WebSocket clients
    await manager.broadcast(pred.model_dump(mode="json"))

    return pred


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def ingest_batch(
    payload: TelemetryBatch,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Ingest multiple telemetry records at once. Returns last prediction only."""
    last_pred = None
    for rec in payload.records:
        await _persist_telemetry(rec, session)
    last_pred = predictor.predict(payload.records)
    await _persist_prediction(last_pred, session)
    await manager.broadcast(last_pred.model_dump(mode="json"))
    return {"ingested": len(payload.records), "prediction": last_pred.model_dump(mode="json")}
