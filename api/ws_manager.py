"""
WebSocket connection manager — broadcasts real-time predictions to all connected clients.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Thread-safe WebSocket connection pool."""

    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        logger.info("WS client connected. Total: %d", len(self.active))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)
        logger.info("WS client disconnected. Total: %d", len(self.active))

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Send JSON to all connected clients, dropping dead connections."""
        payload = json.dumps(data, default=str)
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
