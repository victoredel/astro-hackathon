"""
NOAA SWPC Real-Time Solar Wind Ingestion Daemon — v2.

Scheduled jobs:
  1. [every INGEST_INTERVAL_SECS]  NOAA SWPC telemetry ingestion
       - Primary source: DSCOVR mag + plasma
       - Fallback source: ACE mag + plasma (if DSCOVR data invalid)
  2. [every DONKI_SYNC_INTERVAL_MINS * 60]  NASA DONKI event sync
       - Fetches GST (geomagnetic storms) and CME events
       - Stores them in `storm_events` table as ground-truth labels

Run standalone:
  python workers/ingest_daemon.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
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

# ── NOAA SWPC endpoint URLs ────────────────────────────────────────────────────
# DSCOVR (primary)
DSCOVR_MAG_URL = f"{settings.noaa_base_url}/rtsw_mag_1m.json"
DSCOVR_PLASMA_URL = f"{settings.noaa_base_url}/rtsw_wind_1m.json"

# ACE (fallback) — NOAA hosts ACE data in the same format family
ACE_MAG_URL = "https://services.swpc.noaa.gov/json/ace/mag/ace_mag_1m.json"
ACE_PLASMA_URL = "https://services.swpc.noaa.gov/json/ace/swepam/ace_swepam_1m.json"

# ── NASA DONKI URLs ────────────────────────────────────────────────────────────
DONKI_GST_URL = f"{settings.donki_base_url}/GST"
DONKI_CME_URL = f"{settings.donki_base_url}/CME"


# ──────────────────────────────────────────────────────────────────────────────
# Helper: pick most-recent valid row
# ──────────────────────────────────────────────────────────────────────────────

def _latest_valid(data: list[dict], field: str) -> dict | None:
    """Return the most-recent row where `field` is not None/null."""
    for row in reversed(data):
        val = row.get(field)
        if val is not None:
            return row
    return None


def _is_mag_valid(row: dict | None) -> bool:
    """Return True if the magnetometer row has non-null, non-zero Bz."""
    if row is None:
        return False
    bz = row.get("bz_gsm") or row.get("Bz")
    return bz is not None


def _is_plasma_valid(row: dict | None) -> bool:
    """Return True if the plasma row has a reasonable solar wind speed."""
    if row is None:
        return False
    speed = row.get("speed") or row.get("proton_speed")
    return speed is not None and float(speed) > 150.0


# ──────────────────────────────────────────────────────────────────────────────
# ACE data field normalisation
# ACE JSON uses different field names than DSCOVR
# ──────────────────────────────────────────────────────────────────────────────

def _ace_mag_to_dscovr(row: dict) -> dict:
    """Map ACE magnetometer fields → DSCOVR-compatible dict."""
    return {
        "time_tag": row.get("time_tag"),
        "bx_gsm": row.get("Bx") or row.get("bx_gsm"),
        "by_gsm": row.get("By") or row.get("by_gsm"),
        "bz_gsm": row.get("Bz") or row.get("bz_gsm"),
    }


def _ace_plasma_to_dscovr(row: dict) -> dict:
    """Map ACE SWEPAM plasma fields → DSCOVR-compatible dict."""
    return {
        "time_tag": row.get("time_tag"),
        "speed": row.get("proton_speed") or row.get("speed"),
        "density": row.get("proton_density") or row.get("density"),
        "temperature": row.get("ion_temperature") or row.get("temperature"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Job 1 — NOAA SWPC telemetry ingestion (DSCOVR with ACE fallback)
# ──────────────────────────────────────────────────────────────────────────────

async def _fetch_noaa_source(
    client: httpx.AsyncClient,
    mag_url: str,
    plasma_url: str,
) -> tuple[dict | None, dict | None]:
    """Fetch mag + plasma from a given satellite URL pair. Returns (mag_row, plasma_row)."""
    try:
        mag_resp, plasma_resp = await asyncio.gather(
            client.get(mag_url, timeout=15.0),
            client.get(plasma_url, timeout=15.0),
        )
        mag_resp.raise_for_status()
        plasma_resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Fetch failed for %s: %s", mag_url, exc)
        return None, None

    mag_data: list[dict] = mag_resp.json()
    plasma_data: list[dict] = plasma_resp.json()
    
    # Check for the new NOAA field 'proton_speed', fallback to old 'speed'
    plasma_row = _latest_valid(plasma_data, "proton_speed") or _latest_valid(plasma_data, "speed")
    
    return _latest_valid(mag_data, "bz_gsm"), plasma_row


async def _fetch_ace_source(
    client: httpx.AsyncClient,
) -> tuple[dict | None, dict | None]:
    """Fetch ACE mag + plasma and normalise field names."""
    try:
        mag_resp, plasma_resp = await asyncio.gather(
            client.get(ACE_MAG_URL, timeout=15.0),
            client.get(ACE_PLASMA_URL, timeout=15.0),
        )
        mag_resp.raise_for_status()
        plasma_resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("ACE fetch failed: %s", exc)
        return None, None

    # ACE field names vary — normalise
    ace_mag_data: list[dict] = mag_resp.json()
    ace_plasma_data: list[dict] = plasma_resp.json()

    raw_mag = _latest_valid(ace_mag_data, "Bz") or _latest_valid(ace_mag_data, "bz_gsm")
    raw_plasma = _latest_valid(ace_plasma_data, "proton_speed") or _latest_valid(ace_plasma_data, "speed")

    mag_row = _ace_mag_to_dscovr(raw_mag) if raw_mag else None
    plasma_row = _ace_plasma_to_dscovr(raw_plasma) if raw_plasma else None
    return mag_row, plasma_row


async def fetch_and_ingest(client: httpx.AsyncClient) -> None:
    """
    Single daemon tick:
      1. Try DSCOVR as primary source
      2. Fall back to ACE if DSCOVR data is invalid/null
      3. Build and validate SensorTelemetry
      4. POST to FastAPI /ingest (with inference disabled by default)
    """
    source = SatelliteSource.DSCOVR
    mag_row, plasma_row = await _fetch_noaa_source(client, DSCOVR_MAG_URL, DSCOVR_PLASMA_URL)

    # ── ACE fallback ──────────────────────────────────────────────────────────
    if not _is_mag_valid(mag_row) or not _is_plasma_valid(plasma_row):
        logger.warning(
            "DSCOVR data invalid (mag_valid=%s, plasma_valid=%s) → switching to ACE fallback",
            _is_mag_valid(mag_row),
            _is_plasma_valid(plasma_row),
        )
        mag_row, plasma_row = await _fetch_ace_source(client)
        source = SatelliteSource.ACE

        if not _is_mag_valid(mag_row) or not _is_plasma_valid(plasma_row):
            logger.error("Both DSCOVR and ACE data invalid — skipping cycle")
            return

    # ── Build validated payload ───────────────────────────────────────────────
    try:
        ts_str = mag_row.get("time_tag", datetime.now(tz=timezone.utc).isoformat())
        payload = SensorTelemetry(
            timestamp=ts_str,
            source=source,
            bx_gse=float(mag_row.get("bx_gsm") or 0.0),
            by_gse=float(mag_row.get("by_gsm") or 0.0),
            bz_gse=float(mag_row.get("bz_gsm") or 0.0),
            speed=float(plasma_row.get("speed") or plasma_row.get("proton_speed") or 400.0),
            density=float(plasma_row.get("density") or plasma_row.get("proton_density") or 5.0),
            temperature=float(plasma_row.get("temperature") or plasma_row.get("proton_temperature") or 100_000.0),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Validation error building SensorTelemetry: %s", exc)
        return

    # ── POST to API — inference is off by default in data-collection phase ────
    ingest_url = (
        f"{settings.api_base_url}/ingest"
        f"?run_inference={'true' if settings.enable_ai_inference else 'false'}"
    )
    try:
        resp = await client.post(
            ingest_url,
            json=payload.model_dump(mode="json"),
            timeout=10.0,
        )
        resp.raise_for_status()
        body = resp.json()
        logger.info(
            "✓ [%s] Bz=%.1f nT | Speed=%.0f km/s | AI=%s",
            source.value,
            payload.bz_gse,
            payload.speed,
            body.get("inference", "?"),
        )
    except httpx.HTTPError as exc:
        logger.error("Failed to POST to API: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# Job 2 — NASA DONKI event synchronisation
# ──────────────────────────────────────────────────────────────────────────────

async def sync_donki_events(client: httpx.AsyncClient) -> None:
    """
    Fetch recent GST and CME events from NASA DONKI and store them
    in the `storm_events` table as ground-truth labels.
    """
    now = datetime.now(tz=timezone.utc)
    start_date = (now - timedelta(days=settings.donki_lookback_days)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")
    params = {
        "startDate": start_date,
        "endDate": end_date,
        "api_key": settings.nasa_api_key,
    }

    # ── Fetch both event types concurrently ───────────────────────────────────
    try:
        gst_resp, cme_resp = await asyncio.gather(
            client.get(DONKI_GST_URL, params=params, timeout=20.0),
            client.get(DONKI_CME_URL, params=params, timeout=20.0),
        )
    except httpx.HTTPError as exc:
        logger.warning("DONKI fetch failed: %s", exc)
        return

    gst_events: list[dict] = gst_resp.json() if gst_resp.status_code == 200 else []
    cme_events: list[dict] = cme_resp.json() if cme_resp.status_code == 200 else []

    if not isinstance(gst_events, list):
        gst_events = []
    if not isinstance(cme_events, list):
        cme_events = []

    logger.info(
        "DONKI sync: %d GST events, %d CME events (%s → %s)",
        len(gst_events), len(cme_events), start_date, end_date,
    )

    # ── Persist via API ───────────────────────────────────────────────────────
    total_stored = 0
    for event in gst_events:
        stored = await _store_donki_gst(client, event)
        if stored:
            total_stored += 1

    for event in cme_events:
        stored = await _store_donki_cme(client, event)
        if stored:
            total_stored += 1

    logger.info("✓ DONKI sync complete — %d new events stored", total_stored)


async def _store_donki_gst(client: httpx.AsyncClient, event: dict) -> bool:
    """POST a GST event to the /donki/events endpoint."""
    try:
        payload = {
            "donki_id": event.get("gstID"),
            "event_type": "GST",
            "start_time": event.get("startTime"),
            "kp_max": _extract_kp_max(event),
            "is_storm": True,
            "severity": _kp_to_severity(_extract_kp_max(event)),
            "raw_json": json.dumps(event),
        }
        resp = await client.post(
            f"{settings.api_base_url}/donki/events",
            json=payload,
            timeout=8.0,
        )
        return resp.status_code in (200, 201)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to store GST event: %s", exc)
        return False


async def _store_donki_cme(client: httpx.AsyncClient, event: dict) -> bool:
    """POST a CME event to the /donki/events endpoint."""
    try:
        # Extract analysis data (first entry if available)
        analyses = event.get("cmeAnalyses") or []
        analysis = analyses[0] if analyses else {}

        payload = {
            "donki_id": event.get("activityID"),
            "event_type": "CME",
            "start_time": event.get("startTime"),
            "cme_speed_kms": analysis.get("speed"),
            "cme_half_angle": analysis.get("halfAngle"),
            "is_earth_directed": analysis.get("note", "").lower().find("earth") != -1
                                 or str(analysis.get("type", "")).upper() == "S",
            "is_storm": False,  # CMEs get storm label retroactively after GST correlation
            "raw_json": json.dumps(event),
        }
        resp = await client.post(
            f"{settings.api_base_url}/donki/events",
            json=payload,
            timeout=8.0,
        )
        return resp.status_code in (200, 201)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to store CME event: %s", exc)
        return False


def _extract_kp_max(gst_event: dict) -> float | None:
    """Parse the maximum Kp index from a GST event's allKpIndex list."""
    entries = gst_event.get("allKpIndex") or []
    kps = []
    for e in entries:
        kp = e.get("kpIndex")
        if kp is not None:
            try:
                kps.append(float(kp))
            except (TypeError, ValueError):
                pass
    return max(kps) if kps else None


def _kp_to_severity(kp: float | None) -> str | None:
    """Map Kp index to NOAA G-scale."""
    if kp is None:
        return None
    if kp >= 9:
        return "G5"
    if kp >= 8:
        return "G4"
    if kp >= 7:
        return "G3"
    if kp >= 6:
        return "G2"
    if kp >= 5:
        return "G1"
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Main daemon loop
# ──────────────────────────────────────────────────────────────────────────────

async def run_daemon() -> None:
    """Start all scheduled jobs and run until stopped."""
    logger.info(
        "🛰  Ingestion Daemon v2 starting | "
        "telemetry_interval=%ds | DONKI_sync_interval=%dmin | AI_inference=%s",
        settings.ingest_interval_secs,
        settings.donki_sync_interval_mins,
        settings.enable_ai_inference,
    )

    async with httpx.AsyncClient() as client:
        # ── Initial runs before scheduler starts ──────────────────────────────
        await fetch_and_ingest(client)
        await sync_donki_events(client)

        scheduler = AsyncIOScheduler()

        # Job 1 — NOAA telemetry (every N seconds)
        scheduler.add_job(
            fetch_and_ingest,
            "interval",
            seconds=settings.ingest_interval_secs,
            args=[client],
            id="noaa_telemetry",
        )

        # Job 2 — DONKI sync (every M minutes)
        scheduler.add_job(
            sync_donki_events,
            "interval",
            minutes=settings.donki_sync_interval_mins,
            args=[client],
            id="donki_sync",
        )

        scheduler.start()
        logger.info("✓ Scheduler running. Jobs: noaa_telemetry + donki_sync. Press Ctrl+C to stop.")

        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Daemon stopped by user")
            scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(run_daemon())
