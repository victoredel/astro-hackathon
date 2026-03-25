"""
NOAA SWPC Real-Time Solar Wind Ingestion Daemon.

Polls two NOAA endpoints every minute:
  - rtsw_mag_1m.json  → IMF (Bx, By, Bz) from DSCOVR
  - rtsw_plasma_1m.json → plasma (speed, density, temperature) from DSCOVR

Merges the latest sample, validates via Pydantic,
persists to DB, and POSTs to the FastAPI /ingest endpoint.

Run standalone:
  python workers/ingest_daemon.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import get_settings
from schemas.telemetry import SatelliteSource, SensorTelemetry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ingest_daemon")
settings = get_settings()

# ── NOAA endpoint URLs ─────────────────────────────────────────────────────────
MAG_URL = f"{settings.noaa_base_url}/rtsw_mag_1m.json"
PLASMA_URL = f"{settings.noaa_base_url}/rtsw_plasma_1m.json"


def _latest_valid(data: list[dict], field: str):
    """Walk the list from the end and return first row where `field` is not None."""
    for row in reversed(data):
        val = row.get(field)
        if val is not None:
            return row
    return None


async def fetch_and_ingest(client: httpx.AsyncClient) -> None:
    """Single daemon tick: fetch NOAA data, validate, POST to API."""
    try:
        mag_resp, plasma_resp = await asyncio.gather(
            client.get(MAG_URL, timeout=15.0),
            client.get(PLASMA_URL, timeout=15.0),
        )
        mag_resp.raise_for_status()
        plasma_resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("NOAA fetch failed: %s — skipping cycle", exc)
        return

    mag_data: list[dict] = mag_resp.json()
    plasma_data: list[dict] = plasma_resp.json()

    # Pick most recent valid rows
    mag_row = _latest_valid(mag_data, "bz_gsm")
    plasma_row = _latest_valid(plasma_data, "speed")

    if not mag_row or not plasma_row:
        logger.warning("No valid NOAA rows in this cycle — skipping")
        return

    try:
        ts_str = mag_row.get("time_tag", datetime.now(tz=timezone.utc).isoformat())
        payload = SensorTelemetry(
            timestamp=ts_str,
            source=SatelliteSource.DSCOVR,
            bx_gse=float(mag_row.get("bx_gsm") or 0.0),
            by_gse=float(mag_row.get("by_gsm") or 0.0),
            bz_gse=float(mag_row.get("bz_gsm") or 0.0),
            speed=float(plasma_row.get("speed") or 400.0),
            density=float(plasma_row.get("density") or 5.0),
            temperature=float(plasma_row.get("temperature") or 100000.0),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Validation error for NOAA payload: %s", exc)
        return

    # POST to FastAPI
    try:
        resp = await client.post(
            f"{settings.api_base_url}/ingest",
            json=payload.model_dump(mode="json"),
            timeout=10.0,
        )
        resp.raise_for_status()
        prediction = resp.json()
        logger.info(
            "✓ Ingested | Bz=%.1f nT | Speed=%.0f km/s → Storm prob=%.1f%% [%s]",
            payload.bz_gse,
            payload.speed,
            prediction.get("storm_probability", 0) * 100,
            prediction.get("alert_level", "?"),
        )
    except httpx.HTTPError as exc:
        logger.error("Failed to POST to API: %s", exc)


async def run_daemon() -> None:
    """Main daemon loop using APScheduler."""
    logger.info("🛰  NOAA SWPC Ingestion Daemon starting (interval=%ds)", settings.ingest_interval_secs)

    async with httpx.AsyncClient() as client:
        # Run once immediately on startup
        await fetch_and_ingest(client)

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            fetch_and_ingest,
            "interval",
            seconds=settings.ingest_interval_secs,
            args=[client],
            id="noaa_ingest",
        )
        scheduler.start()

        logger.info("✓ Scheduler running. Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(3600)  # keep alive
        except (KeyboardInterrupt, SystemExit):
            logger.info("Daemon stopped by user")
            scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(run_daemon())
