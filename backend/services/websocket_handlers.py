"""
WebSocket Handlers

This module contains all WebSocket endpoint handlers for real-time data streaming.
- /ws/ais - Main AIS vessel data stream
- /ws/raw - Raw NMEA data for debugging
"""

import asyncio
import json
import logging
from typing import Set, Callable
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


# Raw data subscribers for broadcasting NMEA lines
raw_data_subscribers: Set[WebSocket] = set()


async def broadcast_raw_line(line: str):
    """Broadcast a raw NMEA line to all subscribed clients."""
    if not raw_data_subscribers:
        return
    
    message = json.dumps({"type": "raw", "line": line})
    
    disconnected = set()
    for ws in raw_data_subscribers:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    
    raw_data_subscribers.difference_update(disconnected)


def get_raw_subscriber_count() -> int:
    """Get the number of raw data subscribers."""
    return len(raw_data_subscribers)


async def handle_ais_websocket(
    websocket: WebSocket,
    ais_manager,
    active_vessels: dict,
    prepare_vessel_for_output: Callable
):
    """
    Handle the main AIS WebSocket connection.
    
    Args:
        websocket: The WebSocket connection
        ais_manager: The AIS connection manager singleton
        active_vessels: Dict of active vessels
        prepare_vessel_for_output: Function to prepare vessel data for output
    """
    await websocket.accept()
    logger.info("WebSocket client connected to /ws/ais")
    subscribed = False
    client_mmsi = ""
    client_boat_name = ""
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            logger.info(f"WebSocket received action: {msg.get('action')}")
            
            if msg.get("action") == "connect":
                ip = msg.get("ip_address")
                port = msg.get("port", 5353)
                client_mmsi = msg.get("user_mmsi", "")
                client_boat_name = msg.get("boat_name", "")
                
                logger.info(f"Configuring AIS connection: {ip}:{port}, User MMSI: {client_mmsi}")
                
                await ais_manager.configure(ip, port, client_mmsi, client_boat_name)
                
                if not subscribed:
                    await ais_manager.subscribe(websocket, client_mmsi, client_boat_name)
                    subscribed = True
                    logger.info(f"WebSocket subscribed to AIS updates (MMSI: {client_mmsi})")
                else:
                    ais_manager._subscribers[websocket] = {
                        "mmsi": client_mmsi, 
                        "boat_name": client_boat_name
                    }
                    logger.info(f"Updated subscription MMSI: {client_mmsi}")
                
                # Send current vessels
                vessels = []
                for mmsi, vessel in active_vessels.items():
                    v_dict = prepare_vessel_for_output(vessel, client_mmsi)
                    vessels.append(v_dict)
                await websocket.send_json({"type": "vessels", "vessels": vessels})
                    
            elif msg.get("action") == "disconnect":
                if subscribed:
                    await ais_manager.unsubscribe(websocket)
                    subscribed = False
                await websocket.send_json({
                    "type": "disconnected", 
                    "message": "Unsubscribed from AIS feed"
                })
                
            elif msg.get("action") == "get_vessels":
                vessels = []
                for mmsi, vessel in active_vessels.items():
                    v_dict = prepare_vessel_for_output(vessel, client_mmsi)
                    vessels.append(v_dict)
                await websocket.send_json({"type": "vessels", "vessels": vessels})
                
            elif msg.get("action") == "status":
                await websocket.send_json({
                    "type": "status",
                    "status": ais_manager.get_status()
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected (MMSI: {client_mmsi})")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if subscribed:
            await ais_manager.unsubscribe(websocket)


async def handle_raw_websocket(websocket: WebSocket):
    """
    Handle the raw NMEA data WebSocket connection.
    Used for debugging and diagnostics.
    """
    await websocket.accept()
    raw_data_subscribers.add(websocket)
    logger.info(f"Raw data subscriber connected. Total: {len(raw_data_subscribers)}")
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(data)
                
                if msg.get("action") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "keepalive"})
                except:
                    break
                    
    except WebSocketDisconnect:
        logger.info("Raw data subscriber disconnected")
    except Exception as e:
        logger.error(f"Raw WebSocket error: {e}")
    finally:
        raw_data_subscribers.discard(websocket)
        logger.info(f"Raw data subscriber removed. Total: {len(raw_data_subscribers)}")


def generate_nmea_checksum(sentence: str) -> str:
    """Calculate NMEA checksum for a sentence (without $ and *)."""
    checksum = 0
    for char in sentence:
        checksum ^= ord(char)
    return f"{checksum:02X}"


async def broadcast_demo_nmea(mmsi: str, lat: float, lon: float, speed_knots: float, course: float):
    """Generate and broadcast simulated NMEA sentences for demo vessels."""
    if not raw_data_subscribers:
        return
    
    from datetime import datetime, timezone
    
    now = datetime.now(timezone.utc)
    time_str = now.strftime("%H%M%S")
    date_str = now.strftime("%d%m%y")
    
    # Convert lat/lon to NMEA format (DDMM.MMMM)
    lat_deg = int(abs(lat))
    lat_min = (abs(lat) - lat_deg) * 60
    lat_dir = 'N' if lat >= 0 else 'S'
    lat_nmea = f"{lat_deg:02d}{lat_min:07.4f}"
    
    lon_deg = int(abs(lon))
    lon_min = (abs(lon) - lon_deg) * 60
    lon_dir = 'W' if lon < 0 else 'E'
    lon_nmea = f"{lon_deg:03d}{lon_min:07.4f}"
    
    # Generate simulated GPRMC
    gprmc_body = f"GPRMC,{time_str}.00,A,{lat_nmea},{lat_dir},{lon_nmea},{lon_dir},{speed_knots:.1f},{course:.1f},{date_str},,,A"
    gprmc_checksum = generate_nmea_checksum(gprmc_body)
    gprmc_sentence = f"${gprmc_body}*{gprmc_checksum}"
    
    # Generate simulated AIS VDM comment
    aivdm_comment = f"!AIVDM,1,1,,A,DEMO:{mmsi}:LAT{lat:.4f}:LON{lon:.4f}:SPD{speed_knots:.1f}:CRS{course:.0f},0*00"
    
    # Broadcast both sentences
    await broadcast_raw_line(f"[DEMO] {gprmc_sentence}")
    await broadcast_raw_line(f"[DEMO] {aivdm_comment}")
