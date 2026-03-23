"""
AIS Connection Manager Service

This module handles the TCP connection to the AIS data feed.
It provides a singleton manager that all WebSocket clients share.

Key features:
- Single long-lived TCP connection to AIS feed
- Automatic reconnection with exponential backoff
- Thread-safe state management
- Per-user session isolation via MMSI tracking
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Callable, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class AISConnectionManager:
    """
    Singleton manager for AIS TCP connection.
    
    Key principles:
    - Exactly ONE TCP connection to the AIS feed at any time
    - All WebSocket clients share this connection
    - Automatic reconnection with exponential backoff
    - Thread-safe state management
    """
    
    def __init__(self):
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._config: Optional[dict] = None
        self._connected: bool = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._read_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._subscribers: dict = {}  # {websocket: {"mmsi": str, "boat_name": str}}
        self._lock = asyncio.Lock()
        self._should_run: bool = False
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 60.0
        self._last_data_time: Optional[datetime] = None
        self._gps_update_count: int = 0
        
        # Callbacks for processing data
        self._line_processor: Optional[Callable] = None
        self._raw_broadcaster: Optional[Callable] = None
        self._session_creator: Optional[Callable] = None
        self._vessel_cache_setter: Optional[Callable] = None
        
    def set_callbacks(
        self,
        line_processor: Callable,
        raw_broadcaster: Callable,
        session_creator: Callable = None,
        vessel_cache_setter: Callable = None
    ):
        """Set callback functions for processing AIS data."""
        self._line_processor = line_processor
        self._raw_broadcaster = raw_broadcaster
        self._session_creator = session_creator
        self._vessel_cache_setter = vessel_cache_setter
        
    @property
    def is_connected(self) -> bool:
        return self._connected and self._writer is not None
    
    @property
    def config(self) -> Optional[dict]:
        return self._config
    
    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
    
    @property
    def last_data_time(self) -> Optional[datetime]:
        return self._last_data_time
    
    def get_status(self) -> dict:
        """Get current connection status."""
        return {
            "connected": self._connected,
            "config": self._config,
            "subscriber_count": len(self._subscribers),
            "last_data_time": self._last_data_time.isoformat() if self._last_data_time else None,
            "reconnect_delay": self._reconnect_delay
        }
    
    async def configure(
        self, 
        ip_address: str, 
        port: int, 
        user_mmsi_param: str = "", 
        boat_name: str = ""
    ) -> bool:
        """
        Configure and start the AIS connection.
        If already connected with different config, reconnects.
        """
        new_config = {
            "ip_address": ip_address,
            "port": port,
            "user_mmsi": user_mmsi_param,
            "boat_name": boat_name
        }
        
        logger.info(f"[SESSION:{user_mmsi_param}] AISConnectionManager.configure called with {ip_address}:{port}")
        
        async with self._lock:
            # Create session for this MMSI
            if user_mmsi_param and self._session_creator:
                self._session_creator(user_mmsi_param)
            
            # Pre-populate user vessel in cache
            if user_mmsi_param and boat_name and self._vessel_cache_setter:
                self._vessel_cache_setter(user_mmsi_param, {
                    'name': boat_name,
                    'is_user': True
                })
                logger.info(f"[SESSION:{user_mmsi_param}] Pre-cached vessel name: {boat_name}")
            
            # Check if config changed
            connection_same = (
                self._config and 
                self._config.get("ip_address") == ip_address and 
                self._config.get("port") == port and 
                self._connected
            )
            
            if connection_same:
                logger.info(f"[SESSION:{user_mmsi_param}] AIS connection already active, reusing")
                return True
            
            # Store new config
            self._config = new_config
            self._should_run = True
            self._reconnect_delay = 1.0
            
            # Start connection
            await self._connect()
            
            # Start watchdog if not running
            if self._watchdog_task is None or self._watchdog_task.done():
                self._watchdog_task = asyncio.create_task(self._watchdog_loop())
            
            return self._connected
    
    async def _connect(self):
        """Internal method to establish TCP connection."""
        if not self._config:
            logger.warning("Cannot connect: no config set")
            return
        
        # Close existing connection
        await self._close_connection()
        
        ip = self._config["ip_address"]
        port = self._config["port"]
        
        try:
            logger.info(f"Connecting to AIS feed at {ip}:{port}...")
            
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=10.0
            )
            
            self._connected = True
            self._last_data_time = datetime.now(timezone.utc)
            self._reconnect_delay = 1.0
            
            logger.info(f"Connected to AIS feed at {ip}:{port}")
            
            # Notify all subscribers
            await self._broadcast_status("connected", f"Connected to {ip}:{port}")
            
            # Start the read loop
            if self._read_task is None or self._read_task.done():
                self._read_task = asyncio.create_task(self._read_loop())
                
        except asyncio.TimeoutError:
            logger.error(f"Connection timeout to {ip}:{port}")
            self._connected = False
            await self._broadcast_status("error", f"Connection timeout to {ip}:{port}")
            await self._schedule_reconnect()
            
        except ConnectionRefusedError:
            logger.error(f"Connection refused by {ip}:{port}")
            self._connected = False
            await self._broadcast_status("error", f"Connection refused by {ip}:{port}")
            await self._schedule_reconnect()
            
        except OSError as e:
            logger.error(f"OS error connecting to AIS feed: {e}")
            self._connected = False
            await self._broadcast_status("error", f"Connection failed: {str(e)}")
            await self._schedule_reconnect()
            
        except Exception as e:
            logger.error(f"Failed to connect to AIS feed: {e}")
            self._connected = False
            await self._broadcast_status("error", f"Connection failed: {str(e)}")
            await self._schedule_reconnect()
    
    async def _close_connection(self):
        """Safely close the TCP connection."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as e:
                logger.debug(f"Error closing connection: {e}")
            finally:
                self._writer = None
                self._reader = None
                self._connected = False
    
    async def _schedule_reconnect(self):
        """Schedule a reconnection attempt with exponential backoff."""
        if not self._should_run:
            return
        
        if self._reconnect_task and not self._reconnect_task.done():
            return  # Already scheduled
        
        async def reconnect_after_delay():
            logger.info(f"Scheduling reconnect in {self._reconnect_delay:.1f}s...")
            await asyncio.sleep(self._reconnect_delay)
            
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
            
            if self._should_run:
                await self._connect()
        
        self._reconnect_task = asyncio.create_task(reconnect_after_delay())
    
    async def _watchdog_loop(self):
        """Watchdog to detect silent connection failures."""
        logger.info("Starting AIS connection watchdog")
        
        while self._should_run:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if self._connected and self._last_data_time:
                    data_age = (datetime.now(timezone.utc) - self._last_data_time).total_seconds()
                    
                    if data_age > 90:  # No data for 90 seconds
                        logger.warning(f"Watchdog: No AIS data for {data_age:.0f}s, forcing reconnect")
                        self._connected = False
                        await self._broadcast_status("disconnected", "Connection stale - watchdog triggered")
                        await self._schedule_reconnect()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
        
        logger.info("AIS connection watchdog stopped")
    
    async def _read_loop(self):
        """Main loop for reading AIS data from the TCP connection."""
        logger.info("Starting AIS read loop")
        
        while self._should_run and self._connected and self._reader:
            try:
                try:
                    line_bytes = await asyncio.wait_for(
                        self._reader.readline(),
                        timeout=30.0
                    )
                    
                    if not line_bytes:
                        logger.warning("AIS connection closed by remote host (EOF)")
                        self._connected = False
                        await self._broadcast_status("disconnected", "Connection closed by remote host")
                        await self._schedule_reconnect()
                        break
                    
                    line = line_bytes.decode('ascii', errors='ignore').strip()
                    self._last_data_time = datetime.now(timezone.utc)
                    
                    if line:
                        # Broadcast raw line
                        if self._raw_broadcaster:
                            await self._raw_broadcaster(line)
                        
                        # Process the line
                        if self._line_processor:
                            await self._line_processor(line, self._config, self._broadcast_vessel_update)
                        
                except asyncio.TimeoutError:
                    if self._last_data_time:
                        data_age = (datetime.now(timezone.utc) - self._last_data_time).total_seconds()
                        if data_age > 60:
                            logger.warning(f"No AIS data received for {data_age:.0f}s, reconnecting...")
                            self._connected = False
                            await self._broadcast_status("disconnected", "Connection stale - no data received")
                            await self._schedule_reconnect()
                            break
                    continue
                    
            except asyncio.CancelledError:
                logger.info("AIS read loop cancelled")
                break
            except asyncio.IncompleteReadError:
                logger.warning("Incomplete read from AIS connection")
                self._connected = False
                await self._broadcast_status("disconnected", "Connection interrupted")
                await self._schedule_reconnect()
                break
            except Exception as e:
                logger.error(f"Error in AIS read loop: {e}")
                self._connected = False
                await self._broadcast_status("error", f"Read error: {str(e)}")
                await self._schedule_reconnect()
                break
        
        logger.info("AIS read loop ended")
    
    async def _broadcast_status(self, status_type: str, message: str):
        """Broadcast connection status to all subscribers."""
        msg = {"type": status_type, "message": message}
        disconnected = []
        
        for ws in list(self._subscribers.keys()):
            try:
                await ws.send_json(msg)
            except Exception:
                disconnected.append(ws)
        
        for ws in disconnected:
            self._subscribers.pop(ws, None)
    
    async def _broadcast_vessel_update(self, vessel_dict: dict):
        """Broadcast vessel update to all subscribers."""
        disconnected = []
        vessel_mmsi = vessel_dict.get('mmsi', '')
        
        for ws, user_info in list(self._subscribers.items()):
            try:
                user_vessel_dict = vessel_dict.copy()
                user_mmsi = user_info.get('mmsi', '')
                user_vessel_dict['is_user_vessel'] = (vessel_mmsi == user_mmsi)
                
                await ws.send_json({"type": "vessel_update", "vessel": user_vessel_dict})
            except Exception:
                disconnected.append(ws)
        
        for ws in disconnected:
            self._subscribers.pop(ws, None)
    
    async def subscribe(self, websocket: WebSocket, user_mmsi: str = "", boat_name: str = ""):
        """Add a WebSocket client as a subscriber."""
        self._subscribers[websocket] = {"mmsi": user_mmsi, "boat_name": boat_name}
        logger.info(f"WebSocket subscribed (MMSI: {user_mmsi}). Total: {len(self._subscribers)}")
        
        # Send current status
        if self._connected:
            config_str = f"{self._config['ip_address']}:{self._config['port']}" if self._config else "Connected"
            await websocket.send_json({
                "type": "connected",
                "message": f"Connected to {config_str}"
            })
        else:
            await websocket.send_json({
                "type": "disconnected",
                "message": "Not connected to AIS feed"
            })
    
    async def unsubscribe(self, websocket: WebSocket):
        """Remove a WebSocket client from subscribers."""
        if websocket in self._subscribers:
            user_info = self._subscribers.pop(websocket)
            logger.info(f"WebSocket unsubscribed (MMSI: {user_info.get('mmsi', 'unknown')}). Total: {len(self._subscribers)}")
    
    async def disconnect(self):
        """Disconnect from AIS feed and stop all tasks."""
        logger.info("Disconnecting AIS connection manager...")
        self._should_run = False
        
        # Cancel tasks
        for task in [self._reconnect_task, self._read_task, self._watchdog_task]:
            if task and not task.done():
                task.cancel()
        
        await self._close_connection()
        await self._broadcast_status("disconnected", "Disconnected from AIS feed")
        
        logger.info("AIS connection manager disconnected")


# Global singleton instance
ais_manager = AISConnectionManager()
