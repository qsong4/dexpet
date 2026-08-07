"""WebSocket client hub for server-push events (reminders, etc.)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class WsHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def register(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def unregister(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            await self.unregister(ws)

    def schedule_broadcast(self, message: dict[str, Any]) -> None:
        """Thread-safe: call from APScheduler worker threads."""
        loop = self.loop
        if loop is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
