"""
FastAPI application entrypoint.

Lifespan:
  - Initialise SQLite DB tables
  - Preload the ML model
  - Register all routers

Endpoints:
  POST /ingest          — push telemetry + trigger prediction
  POST /ingest/batch    — bulk ingestion
  GET  /predict/latest  — most recent prediction JSON
  GET  /predict/history — last N predictions
  GET  /health          — liveness check
  WS   /ws/realtime     — real-time prediction stream
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import ingest as ingest_router
from api.routers import predict as predict_router
from api.routers import telemetry as telemetry_router
from api.routers import ws as ws_router
from db.database import init_db
from pipeline.predictor import predictor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("🚀 Solar Storm Warning API starting up...")

    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    # Initialise database tables
    await init_db()
    logger.info("✓ Database initialised")

    # Preload ML model
    predictor.load()
    logger.info("✓ ML model ready")

    yield  # ← app runs here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("🛑 Shutting down...")


app = FastAPI(
    title="Solar Storm Early Warning API",
    description=(
        "Real-time geomagnetic storm prediction engine. "
        "Ingests NOAA SWPC solar wind telemetry and returns probabilistic storm forecasts "
        "30–60 minutes ahead using a Transformer-based AI model."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS (allow Streamlit dashboard on port 8501) ──────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ingest_router.router)
app.include_router(predict_router.router)
app.include_router(telemetry_router.router)
app.include_router(ws_router.router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "service": "solar-storm-warning-api", "version": "1.0.0"}
