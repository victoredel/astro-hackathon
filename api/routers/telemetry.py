"""
GET /telemetry/history — returns the last N telemetry records for the dashboard chart.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from db.models import TelemetryRecord

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/history")
async def telemetry_history(
    limit: int = Query(default=120, ge=1, le=1440),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(TelemetryRecord).order_by(desc(TelemetryRecord.timestamp)).limit(limit)
    )
    rows = result.scalars().all()
    records = [
        {
            "event_id": r.event_id,
            "timestamp": r.timestamp.isoformat(),
            "source": r.source,
            "bx_gse": r.bx_gse,
            "by_gse": r.by_gse,
            "bz_gse": r.bz_gse,
            "speed": r.speed,
            "density": r.density,
            "temperature": r.temperature,
        }
        for r in reversed(rows)
    ]
    return {"records": records, "count": len(records)}
