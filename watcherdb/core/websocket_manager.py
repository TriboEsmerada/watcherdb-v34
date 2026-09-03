"""
WebSocket Manager
Real-time notification management via WebSocket connections
"""

import logging
from typing import List, Dict
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Gerenciador de WebSocket para notificacoes em tempo real
    """

    def __init__(self):
        self.connections: List[WebSocket] = []
        self.subscriptions: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        """Conectar novo WebSocket"""
        await websocket.accept()
        self.connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.connections)}")

        await self.send_to_websocket(websocket, {
            'type': 'connection',
            'message': 'Connected to Watcher DB System',
            'features': [
                'Real server data from your Excel',
                'Smart schema detection',
                'Intelligent column mapping',
                'Zero fictional data'
            ]
        })

    async def disconnect(self, websocket: WebSocket):
        """Desconectar WebSocket"""
        if websocket in self.connections:
            self.connections.remove(websocket)

        for channel, subscribers in self.subscriptions.items():
            if websocket in subscribers:
                subscribers.remove(websocket)

        logger.info(f"WebSocket disconnected. Total: {len(self.connections)}")

    async def send_to_websocket(self, websocket: WebSocket, data: dict):
        """Enviar dados para um WebSocket especifico"""
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error(f"WebSocket send error: {e}")
            await self.disconnect(websocket)

    async def broadcast(self, data: dict):
        """Broadcast para todos os WebSockets conectados"""
        disconnected = []

        for websocket in self.connections:
            try:
                await websocket.send_json(data)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            await self.disconnect(websocket)
