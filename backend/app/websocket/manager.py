"""WebSocket fan-out restricted to each user's authorized devices."""

import asyncio
import logging
import time
from dataclasses import dataclass

from fastapi import WebSocket

log = logging.getLogger("aiids.ws")


@dataclass
class Client:
    user_id: int
    role: str
    expires_at: int  # token expiry (unix seconds)


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, Client] = {}
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        return len(self._clients)

    async def add(self, ws: WebSocket, client: Client) -> None:
        async with self._lock:
            self._clients[ws] = client

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.pop(ws, None)

    async def publish(self, message: dict, owner_user_id: int) -> None:
        """Send to admins and to the owner of the device the message concerns."""
        now = int(time.time())
        async with self._lock:
            targets = list(self._clients.items())
        for ws, c in targets:
            if c.expires_at < now:
                await self._drop(ws, code=4401)
                continue
            if c.role != "admin" and c.user_id != owner_user_id:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                await self._drop(ws)

    async def _drop(self, ws: WebSocket, code: int = 1011) -> None:
        await self.remove(ws)
        try:
            await ws.close(code=code)
        except Exception:
            pass


manager = ConnectionManager()
