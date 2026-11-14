"""Dashboard WebSocket.

The client connects, then sends {"type": "auth", "token": "<access token>"}
as its first message (tokens are not put in URLs, where they could be logged).
The server only forwards updates for devices the user is authorized to see.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.deps import user_from_token
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.websocket.manager import Client, manager

router = APIRouter()


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    origin = ws.headers.get("origin")
    if origin and origin not in get_settings().cors_origins:
        await ws.close(code=4403)
        return
    await ws.accept()
    try:
        msg = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=10))
        token = msg.get("token") if isinstance(msg, dict) and msg.get("type") == "auth" else None
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
        token = None
    payload = decode_access_token(token) if isinstance(token, str) else None
    user = None
    if payload:
        with SessionLocal() as db:
            user = user_from_token(db, token)
    if user is None:
        try:
            await ws.close(code=4401)
        except RuntimeError:
            pass
        return

    await manager.add(ws, Client(user_id=user.id, role=user.role, expires_at=int(payload["exp"])))
    try:
        await ws.send_json({"type": "ready", "user_id": user.id})
        while True:
            text = await ws.receive_text()
            if text == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.remove(ws)
