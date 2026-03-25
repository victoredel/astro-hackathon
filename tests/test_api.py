"""Integration tests for FastAPI endpoints."""
from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="module")
async def client():
    # Use in-memory SQLite for tests
    import os
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["USE_REAL_SURYA"] = "false"
    os.environ["MODEL_CHECKPOINT"] = ""

    from api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


VALID_PAYLOAD = {
    "timestamp": "2026-03-25T12:00:00Z",
    "source": "DSCOVR",
    "bx_gse": 1.5,
    "by_gse": -2.0,
    "bz_gse": -20.0,
    "speed": 700.0,
    "density": 15.0,
    "temperature": 120000.0,
}


@pytest.mark.anyio
class TestIngestEndpoint:

    async def test_health(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    async def test_ingest_returns_201(self, client):
        r = await client.post("/ingest", json=VALID_PAYLOAD)
        assert r.status_code == 201

    async def test_ingest_response_has_prediction_fields(self, client):
        r = await client.post("/ingest", json=VALID_PAYLOAD)
        data = r.json()
        assert "prediction_id" in data
        assert "storm_probability" in data
        assert "alert_level" in data
        assert 0.0 <= data["storm_probability"] <= 1.0

    async def test_ingest_invalid_payload_422(self, client):
        bad = {**VALID_PAYLOAD, "speed": -100.0}  # below minimum
        r = await client.post("/ingest", json=bad)
        assert r.status_code == 422

    async def test_predict_latest_returns_200(self, client):
        r = await client.get("/predict/latest")
        assert r.status_code == 200
        data = r.json()
        assert "storm_probability" in data
        assert data["alert_level"] in ["NORMAL", "WARNING", "CRITICAL"]

    async def test_predict_history_returns_list(self, client):
        r = await client.get("/predict/history", params={"limit": 5})
        assert r.status_code == 200
        data = r.json()
        assert "predictions" in data
        assert isinstance(data["predictions"], list)
