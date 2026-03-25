"""
WebSocket endpoint /ws/realtime — streams prediction updates to dashboard clients.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.ws_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/realtime")
async def websocket_realtime(ws: WebSocket) -> None:
    """
    Clients connect here to receive real-time prediction broadcasts.
    The ingest router calls manager.broadcast() after each new prediction.
    """
    await manager.connect(ws)
    try:
        while True:
            # Keep alive — echo any ping from client
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(ws)
        logger.info("WebSocket client disconnected cleanly")
    except Exception as exc:  # noqa: BLE001
        logger.warning("WebSocket error: %s", exc)
        manager.disconnect(ws)
