"""
GET /predict/latest — returns most recent prediction.
GET /predict/history — returns last N predictions for time-series chart.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from db.models import PredictionRecord
from schemas.prediction import PredictionHistory, StormPrediction

router = APIRouter(prefix="/predict", tags=["predict"])


def _row_to_schema(r: PredictionRecord) -> StormPrediction:
    return StormPrediction(
        prediction_id=r.prediction_id,  # type: ignore[arg-type]
        generated_at=r.generated_at,
        target_timestamp=r.target_timestamp,
        storm_probability=r.storm_probability,
        confidence_score=r.confidence_score,
        alert_level=r.alert_level,  # type: ignore[arg-type]
        kp_index_estimate=r.kp_index_estimate,
        horizon_minutes=r.horizon_minutes,
    )


@router.get("/latest", response_model=StormPrediction)
async def get_latest(session: AsyncSession = Depends(get_session)) -> StormPrediction:
    """Return the most recent storm prediction."""
    result = await session.execute(
        select(PredictionRecord).order_by(desc(PredictionRecord.generated_at)).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        # Return default NORMAL state when no predictions exist yet
        from datetime import datetime, timedelta, timezone
        now = datetime.now(tz=timezone.utc)
        return StormPrediction(
            generated_at=now,
            target_timestamp=now + timedelta(minutes=30),
            storm_probability=0.0,
            confidence_score=0.0,
            alert_level="NORMAL",
        )
    return _row_to_schema(row)


@router.get("/history", response_model=PredictionHistory)
async def get_history(
    limit: int = Query(default=120, ge=1, le=1440),
    session: AsyncSession = Depends(get_session),
) -> PredictionHistory:
    """Return the last `limit` predictions for time-series charts."""
    result = await session.execute(
        select(PredictionRecord)
        .order_by(desc(PredictionRecord.generated_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    predictions = [_row_to_schema(r) for r in reversed(rows)]
    return PredictionHistory(predictions=predictions, count=len(predictions))
