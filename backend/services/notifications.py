"""
Layer 6 (Notification Layer) — WebSocket-based push for reminders and
caregiver alerts (6.4 / FR7). Reminders are pushed the instant they're
due; the client never polls.
"""
from typing import List

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)


# Single process-wide manager — reminders.py's scheduler pushes through
# this same instance so REST-created reminders and scheduled fires both
# reach whatever's currently connected over /api/reminders/ws.
ws_manager = ConnectionManager()
