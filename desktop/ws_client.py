"""Desktop WebSocket client running on a background thread."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from backend.paths import DEFAULT_HOST, DEFAULT_PORT, WS_PATH


class WsClient:
    def __init__(
        self,
        on_message: Callable[[dict[str, Any]], None],
        on_status: Callable[[str], None] | None = None,
        url: str | None = None,
    ) -> None:
        self.url = url or f"ws://{DEFAULT_HOST}:{DEFAULT_PORT}{WS_PATH}"
        self.on_message = on_message
        self.on_status = on_status or (lambda _s: None)
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws: Any = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._close(), self._loop)

    async def _close(self) -> None:
        if self._ws is not None:
            await self._ws.close()

    def send_user_message(self, text: str, session_id: str | None = None, request_id: str | None = None) -> bool:
        """Send a chat message. Returns False if the WebSocket is not connected."""
        payload = {
            "type": "user_message",
            "payload": {"text": text, "session_id": session_id},
            "request_id": request_id,
        }
        if self._loop and self._ws is not None:
            asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(payload)), self._loop)
            return True
        return False

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())

    async def _main(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self.on_status("connecting")
                async with websockets.connect(self.url, ping_interval=20) as ws:
                    self._ws = ws
                    self.on_status("connected")
                    backoff = 1.0
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                            self.on_message(data)
                        except json.JSONDecodeError:
                            continue
            except (ConnectionClosed, OSError, Exception):  # noqa: BLE001
                self._ws = None
                self.on_status("disconnected")
                if self._stop.is_set():
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)
