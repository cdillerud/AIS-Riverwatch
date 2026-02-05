# River Watch Backend - WebSocket Manager
# Centralized WebSocket connection management

from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import logging
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections for AIS data broadcasting."""
    
    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}  # session_id -> WebSocket
        self._session_mmsi: Dict[str, str] = {}       # session_id -> mmsi
        self._subscriptions: Dict[str, Set[str]] = {} # lock_id -> set of session_ids
        self._lock = asyncio.Lock()
        self._stats = {
            "total_connections": 0,
            "total_disconnections": 0,
            "messages_sent": 0,
            "errors": 0
        }
    
    async def connect(self, websocket: WebSocket, session_id: str, mmsi: Optional[str] = None) -> None:
        """Register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections[session_id] = websocket
            if mmsi:
                self._session_mmsi[session_id] = mmsi
            self._stats["total_connections"] += 1
        logger.info(f"[WS] Client connected: {session_id} (MMSI: {mmsi})")
    
    async def disconnect(self, session_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self._connections.pop(session_id, None)
            self._session_mmsi.pop(session_id, None)
            # Remove from all subscriptions
            for subs in self._subscriptions.values():
                subs.discard(session_id)
            self._stats["total_disconnections"] += 1
        logger.info(f"[WS] Client disconnected: {session_id}")
    
    async def subscribe_to_lock(self, session_id: str, lock_id: str) -> None:
        """Subscribe a session to lock updates."""
        async with self._lock:
            if lock_id not in self._subscriptions:
                self._subscriptions[lock_id] = set()
            self._subscriptions[lock_id].add(session_id)
    
    async def unsubscribe_from_lock(self, session_id: str, lock_id: str) -> None:
        """Unsubscribe a session from lock updates."""
        async with self._lock:
            if lock_id in self._subscriptions:
                self._subscriptions[lock_id].discard(session_id)
    
    async def broadcast(self, message: dict, exclude: Optional[str] = None) -> int:
        """Broadcast message to all connected clients. Returns count of successful sends."""
        sent = 0
        disconnected = []
        
        async with self._lock:
            connections = list(self._connections.items())
        
        for session_id, ws in connections:
            if session_id == exclude:
                continue
            try:
                await ws.send_json(message)
                sent += 1
                self._stats["messages_sent"] += 1
            except Exception as e:
                logger.debug(f"[WS] Failed to send to {session_id}: {e}")
                disconnected.append(session_id)
                self._stats["errors"] += 1
        
        # Cleanup disconnected clients
        for session_id in disconnected:
            await self.disconnect(session_id)
        
        return sent
    
    async def send_to_session(self, session_id: str, message: dict) -> bool:
        """Send message to specific session. Returns True if successful."""
        async with self._lock:
            ws = self._connections.get(session_id)
        
        if not ws:
            return False
        
        try:
            await ws.send_json(message)
            self._stats["messages_sent"] += 1
            return True
        except Exception as e:
            logger.debug(f"[WS] Failed to send to {session_id}: {e}")
            await self.disconnect(session_id)
            self._stats["errors"] += 1
            return False
    
    async def broadcast_to_lock_subscribers(self, lock_id: str, message: dict) -> int:
        """Broadcast to all sessions subscribed to a specific lock."""
        async with self._lock:
            subscribers = self._subscriptions.get(lock_id, set()).copy()
        
        sent = 0
        for session_id in subscribers:
            if await self.send_to_session(session_id, message):
                sent += 1
        
        return sent
    
    def get_session_mmsi(self, session_id: str) -> Optional[str]:
        """Get MMSI for a session."""
        return self._session_mmsi.get(session_id)
    
    def set_session_mmsi(self, session_id: str, mmsi: str) -> None:
        """Set MMSI for a session."""
        self._session_mmsi[session_id] = mmsi
    
    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self._connections)
    
    @property
    def stats(self) -> dict:
        """Get WebSocket statistics."""
        return {
            **self._stats,
            "active_connections": self.connection_count,
            "subscriptions": {k: len(v) for k, v in self._subscriptions.items()}
        }


class RawDataManager:
    """Manages raw AIS data WebSocket connections."""
    
    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket) -> None:
        """Register a raw data WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info(f"[RAW] Raw data client connected")
    
    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a raw data WebSocket connection."""
        async with self._lock:
            self._connections.discard(websocket)
        logger.info(f"[RAW] Raw data client disconnected")
    
    async def broadcast(self, line: str) -> int:
        """Broadcast raw line to all connected clients."""
        sent = 0
        disconnected = []
        
        async with self._lock:
            connections = list(self._connections)
        
        for ws in connections:
            try:
                await ws.send_text(line)
                sent += 1
            except Exception:
                disconnected.append(ws)
        
        # Cleanup
        for ws in disconnected:
            await self.disconnect(ws)
        
        return sent
    
    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Global instances
ws_manager = WebSocketManager()
raw_manager = RawDataManager()
