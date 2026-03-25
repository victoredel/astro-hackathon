"""
POST /donki/events — Upsert DONKI storm events into the storm_events table.
GET  /donki/events — Query stored ground-truth storm events.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from db.models import StormEventRecord

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/donki", tags=["donki"])


# ── Request / Response schemas (inline — no separate file needed) ─────────────

class StormEventPayload(BaseModel):
    donki_id: str | None = None
    event_type: Literal["GST", "CME", "IPS", "SEP"]
    start_time: datetime
    end_time: datetime | None = None
    impact_time: datetime | None = None
    kp_max: float | None = None
    dst_min: float | None = None
    cme_speed_kms: float | None = None
    cme_half_angle: float | None = None
    is_earth_directed: bool = False
    is_storm: bool = False
    severity: str | None = None
    source_api: str = "NASA_DONKI"
    raw_json: str | None = None


class StormEventOut(StormEventPayload):
    event_id: str
    ingested_at: datetime


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/events", status_code=201)
async def upsert_storm_event(
    payload: StormEventPayload,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Upsert a DONKI storm event.
    If `donki_id` already exists in the DB, the record is skipped (idempotent).
    """
    # ── Idempotency check ─────────────────────────────────────────────────────
    if payload.donki_id:
        existing = await session.execute(
            select(StormEventRecord).where(StormEventRecord.donki_id == payload.donki_id)
        )
        if existing.scalar_one_or_none() is not None:
            return {"status": "already_exists", "donki_id": payload.donki_id}

    row = StormEventRecord(
        donki_id=payload.donki_id,
        event_type=payload.event_type,
        start_time=payload.start_time,
        end_time=payload.end_time,
        impact_time=payload.impact_time,
        kp_max=payload.kp_max,
        dst_min=payload.dst_min,
        cme_speed_kms=payload.cme_speed_kms,
        cme_half_angle=payload.cme_half_angle,
        is_earth_directed=payload.is_earth_directed,
        is_storm=payload.is_storm,
        severity=payload.severity,
        source_api=payload.source_api,
        raw_json=payload.raw_json,
        ingested_at=datetime.now(tz=timezone.utc),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    logger.info(
        "✓ DONKI event stored: type=%s donki_id=%s is_storm=%s kp_max=%s",
        payload.event_type, payload.donki_id, payload.is_storm, payload.kp_max,
    )
    return {"status": "created", "event_id": row.event_id}


@router.get("/events")
async def list_storm_events(
    event_type: str | None = Query(default=None, description="Filter by event type: GST | CME | IPS"),
    storms_only: bool = Query(default=False, description="Return only confirmed storm events (Kp≥5)"),
    limit: int = Query(default=100, ge=1, le=2000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return stored DONKI ground-truth events, optionally filtered."""
    query = select(StormEventRecord).order_by(desc(StormEventRecord.start_time)).limit(limit)

    if event_type:
        query = query.where(StormEventRecord.event_type == event_type.upper())
    if storms_only:
        query = query.where(StormEventRecord.is_storm == True)  # noqa: E712

    result = await session.execute(query)
    rows = result.scalars().all()

    events = [
        {
            "event_id": r.event_id,
            "donki_id": r.donki_id,
            "event_type": r.event_type,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "end_time": r.end_time.isoformat() if r.end_time else None,
            "impact_time": r.impact_time.isoformat() if r.impact_time else None,
            "kp_max": r.kp_max,
            "dst_min": r.dst_min,
            "cme_speed_kms": r.cme_speed_kms,
            "is_earth_directed": r.is_earth_directed,
            "is_storm": r.is_storm,
            "severity": r.severity,
            "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
        }
        for r in rows
    ]
    return {"events": events, "count": len(events)}
