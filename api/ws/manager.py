import asyncio
import json
from collections import defaultdict

import structlog
from fastapi import WebSocket

log = structlog.get_logger()


class ConnectionManager:
    def __init__(self) -> None:
        # room -> list of websockets (room "" = broadcast all)
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, ws: WebSocket, room: str = "") -> None:
        await ws.accept()
        self._connections[room].append(ws)
        log.info("ws_connected", room=room, total=len(self._connections[room]))

    def disconnect(self, ws: WebSocket, room: str = "") -> None:
        try:
            self._connections[room].remove(ws)
        except ValueError:
            pass
        log.info("ws_disconnected", room=room, total=len(self._connections[room]))

    async def send(self, ws: WebSocket, data: dict) -> None:
        try:
            await ws.send_json(data)
        except Exception:
            pass

    async def broadcast(self, data: dict, room: str = "") -> None:
        """Send to all clients in room, and always to room '' (global)."""
        targets = list(self._connections.get(room, []))
        if room != "":
            targets += list(self._connections.get("", []))

        dead: list[tuple[WebSocket, str]] = []
        results = await asyncio.gather(
            *[ws.send_json(data) for ws in targets],
            return_exceptions=True,
        )
        for ws, result in zip(targets, results):
            if isinstance(result, Exception):
                dead.append((ws, room))

        for ws, r in dead:
            self.disconnect(ws, r)

    def total_connections(self) -> int:
        return sum(len(v) for v in self._connections.values())


manager = ConnectionManager()
