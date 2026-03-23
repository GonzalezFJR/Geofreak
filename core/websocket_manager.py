"""WebSocket connection manager for real-time duels and tournaments.

Single-instance design (no Redis needed). Tracks connections by room_id
and broadcasts JSON messages to all participants in a room.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Manage WebSocket connections grouped by room_id (duel or tournament)."""

    def __init__(self) -> None:
        self._connections: dict[str, dict[str, WebSocket]] = defaultdict(dict)

    async def connect(self, room_id: str, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[room_id][user_id] = ws

    def disconnect(self, room_id: str, user_id: str) -> None:
        conns = self._connections.get(room_id)
        if conns:
            conns.pop(user_id, None)
            if not conns:
                del self._connections[room_id]

    async def send_personal(self, room_id: str, user_id: str, data: dict) -> None:
        conns = self._connections.get(room_id, {})
        ws = conns.get(user_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(room_id, user_id)

    async def broadcast(self, room_id: str, data: dict, exclude: str | None = None) -> None:
        """Send a JSON message to all connected clients in a room."""
        conns = self._connections.get(room_id, {})
        dead: list[str] = []
        for uid, ws in conns.items():
            if uid == exclude:
                continue
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.disconnect(room_id, uid)

    async def broadcast_all(self, room_id: str, data: dict) -> None:
        """Send to ALL connected clients including sender."""
        await self.broadcast(room_id, data, exclude=None)

    def get_connected_users(self, room_id: str) -> list[str]:
        return list(self._connections.get(room_id, {}).keys())


# Singleton instances — one for duels, one for tournaments
manager = ConnectionManager()
tournament_manager = ConnectionManager()
