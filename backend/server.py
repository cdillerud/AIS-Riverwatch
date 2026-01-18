from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import socket
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
import uuid
from datetime import datetime, timezone
import json
import httpx
from bs4 import BeautifulSoup
import re

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Lock positions (River Mile markers) - Upper Mississippi Locks 2-10
LOCKS = {
    "lock_2": {"name": "Lock & Dam #2 (Hastings)", "river_mile": 815.2, "lat": 44.7433, "lon": -92.8506, "phone": "651-436-2900"},
    "lock_3": {"name": "Lock & Dam #3 (Red Wing)", "river_mile": 796.9, "lat": 44.5533, "lon": -92.5356, "phone": "612-388-5794"},
    "lock_4": {"name": "Lock & Dam #4 (Alma)", "river_mile": 752.8, "lat": 44.3189, "lon": -91.9150, "phone": "608-685-4421"},
    "lock_5": {"name": "Lock & Dam #5 (Minnesota City)", "river_mile": 738.1, "lat": 44.1047, "lon": -91.7428, "phone": "507-689-2101"},
    "lock_5a": {"name": "Lock & Dam #5A (Fountain City)", "river_mile": 728.5, "lat": 44.0317, "lon": -91.7089, "phone": "507-452-2789"},
    "lock_6": {"name": "Lock & Dam #6 (Trempealeau)", "river_mile": 714.3, "lat": 43.8697, "lon": -91.5006, "phone": "608-534-6424"},
    "lock_7": {"name": "Lock & Dam #7 (Dresbach)", "river_mile": 702.5, "lat": 43.8128, "lon": -91.3053, "phone": "507-895-2170"},
    "lock_8": {"name": "Lock & Dam #8 (Genoa)", "river_mile": 679.2, "lat": 43.5789, "lon": -91.2294, "phone": "608-689-2625"},
    "lock_9": {"name": "Lock & Dam #9 (Lynxville)", "river_mile": 647.9, "lat": 43.2108, "lon": -91.0836, "phone": "608-874-4311"},
    "lock_10": {"name": "Lock & Dam #10 (Guttenberg)", "river_mile": 615.1, "lat": 42.7856, "lon": -91.1003, "phone": "319-252-1261"}
}

# Cache for USACE lock status data
usace_cache = {
    "data": {},
    "last_updated": None,
    "cache_duration_seconds": 300  # 5 minutes
}

# Global state for AIS connections
ais_connections: Dict[str, dict] = {}

# Models
class ConnectionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ip_address: str
    port: int = 5353
    user_mmsi: str

class VesselPosition(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mmsi: str
    name: Optional[str] = None
    lat: float
    lon: float
    speed: float  # knots
    course: float
    river_mile: Optional[float] = None
    heading: Optional[str] = None  # "northbound" or "southbound"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_user_vessel: bool = False
    vessel_type: str = "unknown"
    # Tow/Barge information
    ship_type_code: Optional[int] = None
    length: Optional[float] = None  # meters
    width: Optional[float] = None  # meters
    draught: Optional[float] = None  # meters
    barge_count: Optional[int] = None  # Estimated or reported barge count
    tow_config: Optional[str] = None  # e.g., "2x3" (2 wide, 3 long)
    is_tow: bool = False
    estimated_lockage_time: Optional[int] = None  # minutes

class RaceAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_vessel: Optional[dict] = None
    target_lock: str
    target_lock_name: str
    target_lock_rm: float
    competitors: List[dict] = []
    analysis: Optional[dict] = None

class LockInfo(BaseModel):
    id: str
    name: str
    river_mile: float
    lat: float
    lon: float
    phone: Optional[str] = None

class LockStatus(BaseModel):
    lock_id: str
    status: str  # "OPEN", "CLOSED", "RESTRICTED"
    avg_wait_minutes: Optional[int] = None
    upbound_queue: int = 0
    downbound_queue: int = 0
    vessels_in_queue: List[dict] = []
    last_updated: Optional[str] = None
    closure_info: Optional[str] = None

# Store active vessels
active_vessels: Dict[str, VesselPosition] = {}
user_mmsi: str = ""

def estimate_tow_info(vessel_data: dict) -> dict:
    """
    Estimate barge count and lockage time based on AIS data.
    
    Standard barge dimensions: ~195ft (59m) long x 35ft (10.7m) wide
    Lock chamber: ~600ft (183m) long x 110ft (33.5m) wide
    
    Tow configurations:
    - Single lock (fits in one pass): up to 15 barges (3 wide x 5 long = ~975ft)
    - Double lock (requires 2 passes): 16+ barges
    
    Ship type codes (AIS):
    - 30: Fishing
    - 31-32: Towing
    - 60-69: Passenger
    - 70-79: Cargo
    - 80-89: Tanker
    """
    ship_type = vessel_data.get('ship_type', 0)
    length = vessel_data.get('length', 0) or 0
    width = vessel_data.get('width', 0) or 0
    name = (vessel_data.get('shipname', '') or vessel_data.get('name', '') or '').upper()
    
    is_tow = False
    barge_count = 0
    tow_config = None
    estimated_lockage_time = 30  # Default for small vessels
    
    # Check if it's a towing vessel by ship type
    if ship_type in [31, 32, 52]:  # Towing, Towing and length > 200m, Tug
        is_tow = True
    
    # Check name for tow indicators
    tow_keywords = ['M/V', 'MV ', 'CAPT', 'MISS', 'TUG', 'TOWBOAT', 'BARGE', 'PUSH']
    if any(kw in name for kw in tow_keywords):
        is_tow = True
    
    # Estimate barge count from length if it's a tow
    if is_tow and length > 0:
        # Towboat itself is about 100-200ft (30-60m)
        # Each barge adds ~195ft (59m) in length
        towboat_length = 50  # meters, average
        barge_length = 59  # meters, standard barge
        
        tow_length = length - towboat_length
        if tow_length > 0:
            # Estimate barges in line (assuming 2-3 wide typical)
            barges_long = max(1, int(tow_length / barge_length))
            
            # Estimate width configuration
            if width > 25:  # More than 2 barges wide
                barges_wide = 3
            elif width > 15:
                barges_wide = 2
            else:
                barges_wide = 1
            
            barge_count = barges_long * barges_wide
            tow_config = f"{barges_wide}x{barges_long}"
    
    # If no length data but it's a tow, estimate from vessel type
    if is_tow and barge_count == 0:
        # Default assumption for commercial tow
        barge_count = 6  # Conservative estimate
        tow_config = "2x3"
    
    # Calculate estimated lockage time
    if barge_count > 0:
        # Lock chamber is ~600ft, can fit about 3x5 barges (15 barges)
        if barge_count <= 6:
            estimated_lockage_time = 30  # Single cut, quick
        elif barge_count <= 12:
            estimated_lockage_time = 45  # Single cut, larger tow
        elif barge_count <= 15:
            estimated_lockage_time = 60  # Single cut, maximum size
        else:
            # Double lockage required
            estimated_lockage_time = 90 + (barge_count - 15) * 5  # Base + extra per barge
    elif is_tow:
        estimated_lockage_time = 45  # Unknown tow, assume medium
    else:
        # Non-tow vessel
        estimated_lockage_time = 20 if length < 30 else 30
    
    return {
        'is_tow': is_tow,
        'barge_count': barge_count if barge_count > 0 else None,
        'tow_config': tow_config,
        'estimated_lockage_time': estimated_lockage_time
    }

async def fetch_usace_lock_status() -> Dict[str, LockStatus]:
    """
    Fetch lock status data from USACE Corps Locks system.
    Data is updated every 15 minutes by USACE.
    """
    global usace_cache
    
    # Check cache
    if usace_cache["last_updated"]:
        age = (datetime.now(timezone.utc) - usace_cache["last_updated"]).total_seconds()
        if age < usace_cache["cache_duration_seconds"] and usace_cache["data"]:
            return usace_cache["data"]
    
    lock_status_data = {}
    
    try:
        # Fetch from St. Paul District (Locks 2-10)
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try the MVR lock status page for basic open/closed status
            mvp_url = "https://www.mvp.usace.army.mil/Missions/Navigation/Locks-Dams/"
            
            # Map our lock IDs to river miles for matching
            lock_rm_map = {lock_id: data["river_mile"] for lock_id, data in LOCKS.items()}
            
            # Initialize all locks with default status
            for lock_id, lock_data in LOCKS.items():
                lock_status_data[lock_id] = LockStatus(
                    lock_id=lock_id,
                    status="OPEN",
                    avg_wait_minutes=0,
                    upbound_queue=0,
                    downbound_queue=0,
                    vessels_in_queue=[],
                    last_updated=datetime.now(timezone.utc).isoformat()
                )
            
            # Try to fetch queue data from Corps Locks
            try:
                queue_url = "https://ndc.ops.usace.army.mil/ords/f?p=108:3"
                response = await client.get(queue_url, follow_redirects=True)
                
                if response.status_code == 200:
                    # Parse the page for queue data
                    # Note: This page requires JavaScript, so we may get limited data
                    logger.info("Successfully fetched Corps Locks page")
            except Exception as e:
                logger.warning(f"Could not fetch Corps Locks queue data: {e}")
            
            # Try MVR lock status for closure info
            try:
                mvr_url = "https://www.mvr.usace.army.mil/missions/navigation/lock-status/"
                response = await client.get(mvr_url, follow_redirects=True)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Find the status table
                    tables = soup.find_all('table')
                    for table in tables:
                        rows = table.find_all('tr')
                        for row in rows:
                            cells = row.find_all(['td', 'th'])
                            if len(cells) >= 3:
                                # Try to extract lock name and status
                                name_cell = cells[0].get_text(strip=True)
                                
                                # Check if this mentions any of our locks
                                for lock_id in LOCKS.keys():
                                    lock_num = lock_id.replace('lock_', '').upper()
                                    if f"Lock" in name_cell and lock_num in name_cell.upper():
                                        status_cell = cells[2].get_text(strip=True) if len(cells) > 2 else "OPEN"
                                        
                                        if "CLOSED" in status_cell.upper():
                                            lock_status_data[lock_id].status = "CLOSED"
                                            # Try to get closure reason
                                            if len(cells) > 2:
                                                lock_status_data[lock_id].closure_info = status_cell
                                        elif "OPEN" in status_cell.upper():
                                            lock_status_data[lock_id].status = "OPEN"
                                        
                                        logger.info(f"Found status for {lock_id}: {status_cell}")
                                        break
                                        
            except Exception as e:
                logger.warning(f"Could not fetch MVR lock status: {e}")
        
        # Update cache
        usace_cache["data"] = lock_status_data
        usace_cache["last_updated"] = datetime.now(timezone.utc)
        
        # Also save to database for persistence
        for lock_id, status in lock_status_data.items():
            await db.lock_status.update_one(
                {"lock_id": lock_id},
                {"$set": status.model_dump()},
                upsert=True
            )
        
    except Exception as e:
        logger.error(f"Error fetching USACE data: {e}")
        
        # Try to load from database cache
        cached = await db.lock_status.find({}, {"_id": 0}).to_list(100)
        for item in cached:
            lock_id = item.get("lock_id")
            if lock_id:
                lock_status_data[lock_id] = LockStatus(**item)
    
    return lock_status_data

def estimate_river_mile(lat: float, lon: float) -> float:
    """
    Estimate river mile based on latitude for Upper Mississippi (simplified linear approximation).
    Extended coverage: Lock 2 (RM 815) to Lock 10 (RM 615)
    Latitude range roughly 44.95 (north) to 42.7 (south)
    """
    # Linear interpolation based on known points
    # Lock 2 at Hastings: RM 815.2, lat ~44.74
    # Lock 10 at Guttenberg: RM 615.1, lat ~42.79
    # Slope: (815.2 - 615.1) / (44.74 - 42.79) = 200.1 / 1.95 ≈ 102.6 RM per degree lat
    slope = 102.6
    ref_lat = 44.74
    ref_rm = 815.2
    
    estimated_rm = ref_rm + (lat - ref_lat) * slope
    return round(estimated_rm, 1)

def determine_heading(speed: float, course: float) -> str:
    """Determine if vessel is heading northbound or southbound based on course."""
    if speed < 0.5:
        return "stationary"
    # Course 0-180 is roughly northbound on the Mississippi
    # Course 180-360 is roughly southbound
    # Adjusted for river direction (flows south)
    if 270 <= course <= 360 or 0 <= course < 90:
        return "northbound"
    else:
        return "southbound"

def calculate_eta_to_lock(vessel_rm: float, vessel_speed_knots: float, heading: str, lock_rm: float) -> Optional[float]:
    """Calculate ETA in minutes to reach a lock. Returns None if vessel moving away."""
    if vessel_speed_knots < 0.1:
        return None
    
    distance_rm = abs(vessel_rm - lock_rm)
    
    # Check if vessel is moving toward the lock
    if heading == "northbound" and vessel_rm < lock_rm:
        # Northbound vessel heading toward lock north of it
        pass
    elif heading == "southbound" and vessel_rm > lock_rm:
        # Southbound vessel heading toward lock south of it
        pass
    elif heading == "stationary":
        return None
    else:
        # Vessel moving away from lock
        return None
    
    # Convert speed from knots to statute miles per hour (1 knot = 1.15078 mph)
    speed_mph = vessel_speed_knots * 1.15078
    
    # Calculate time in minutes (distance in river miles, speed in mph)
    if speed_mph > 0:
        eta_minutes = (distance_rm / speed_mph) * 60
        return round(eta_minutes, 1)
    return None

def calculate_required_speed(user_rm: float, user_heading: str, target_lock_rm: float, competitor_eta_minutes: float) -> Optional[float]:
    """Calculate required speed in MPH to beat competitor to lock."""
    if competitor_eta_minutes is None or competitor_eta_minutes <= 0:
        return None
    
    distance_rm = abs(user_rm - target_lock_rm)
    
    # Check if user is heading toward the lock
    if user_heading == "northbound" and user_rm >= target_lock_rm:
        return None  # User past the lock going north
    elif user_heading == "southbound" and user_rm <= target_lock_rm:
        return None  # User past the lock going south
    
    # Required speed in MPH to arrive just before competitor
    # Subtract 5 minutes buffer to actually beat them
    target_time_minutes = max(competitor_eta_minutes - 5, 1)
    required_mph = (distance_rm / target_time_minutes) * 60
    
    return round(required_mph, 1)

def parse_nmea_ais(data: str) -> Optional[dict]:
    """
    Parse NMEA/AIS data. Boat Beacon typically sends !AIVDM sentences.
    Returns vessel info dict or None if parsing fails.
    """
    try:
        from pyais import decode
        
        lines = data.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('!AIVDM') or line.startswith('!AIVDO'):
                try:
                    msg = decode(line)
                    decoded = msg.asdict()
                    
                    # Extract relevant fields
                    if 'mmsi' in decoded:
                        vessel = {
                            'mmsi': str(decoded.get('mmsi', '')),
                            'lat': decoded.get('lat'),
                            'lon': decoded.get('lon'),
                            'speed': decoded.get('speed', 0),  # knots
                            'course': decoded.get('course', 0),
                            'name': decoded.get('shipname', ''),
                            'vessel_type': str(decoded.get('ship_type', 'unknown')),
                            'ship_type': decoded.get('ship_type', 0),
                            'length': decoded.get('to_bow', 0) + decoded.get('to_stern', 0) if decoded.get('to_bow') else None,
                            'width': decoded.get('to_port', 0) + decoded.get('to_starboard', 0) if decoded.get('to_port') else None,
                            'draught': decoded.get('draught'),
                        }
                        
                        # Add tow/barge information
                        tow_info = estimate_tow_info(vessel)
                        vessel.update(tow_info)
                        
                        # Filter invalid positions
                        if vessel['lat'] and vessel['lon']:
                            if -90 <= vessel['lat'] <= 90 and -180 <= vessel['lon'] <= 180:
                                return vessel
                except Exception as e:
                    logger.debug(f"Failed to parse AIS message: {e}")
                    continue
    except Exception as e:
        logger.error(f"AIS parsing error: {e}")
    return None

# API Routes
@api_router.get("/")
async def root():
    return {"message": "AIS Vessel Tracker API", "status": "online"}

@api_router.get("/locks", response_model=List[LockInfo])
async def get_locks():
    """Get all lock positions."""
    return [
        LockInfo(id=k, name=v["name"], river_mile=v["river_mile"], lat=v["lat"], lon=v["lon"], phone=v.get("phone"))
        for k, v in LOCKS.items()
    ]

@api_router.get("/locks/status")
async def get_all_lock_status():
    """Get USACE status for all locks including wait times and queue info."""
    status_data = await fetch_usace_lock_status()
    
    result = []
    for lock_id, lock_info in LOCKS.items():
        status = status_data.get(lock_id, LockStatus(lock_id=lock_id, status="UNKNOWN"))
        result.append({
            "lock_id": lock_id,
            "name": lock_info["name"],
            "river_mile": lock_info["river_mile"],
            "phone": lock_info.get("phone"),
            "status": status.status,
            "avg_wait_minutes": status.avg_wait_minutes,
            "upbound_queue": status.upbound_queue,
            "downbound_queue": status.downbound_queue,
            "vessels_in_queue": status.vessels_in_queue,
            "closure_info": status.closure_info,
            "last_updated": status.last_updated
        })
    
    return result

@api_router.get("/locks/{lock_id}/status")
async def get_lock_status(lock_id: str):
    """Get USACE status for a specific lock."""
    if lock_id not in LOCKS:
        return {"error": "Invalid lock ID"}
    
    status_data = await fetch_usace_lock_status()
    status = status_data.get(lock_id, LockStatus(lock_id=lock_id, status="UNKNOWN"))
    lock_info = LOCKS[lock_id]
    
    return {
        "lock_id": lock_id,
        "name": lock_info["name"],
        "river_mile": lock_info["river_mile"],
        "phone": lock_info.get("phone"),
        "status": status.status,
        "avg_wait_minutes": status.avg_wait_minutes,
        "upbound_queue": status.upbound_queue,
        "downbound_queue": status.downbound_queue,
        "vessels_in_queue": status.vessels_in_queue,
        "closure_info": status.closure_info,
        "last_updated": status.last_updated
    }

@api_router.post("/connection/test")
async def test_connection(config: ConnectionConfig):
    """Test AIS TCP connection."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((config.ip_address, config.port))
        sock.close()
        
        if result == 0:
            return {"success": True, "message": "Connection successful"}
        elif result == 111:
            return {"success": False, "message": "Connection refused - Boat Beacon may not be running or the IP is unreachable from this server. For local networks (192.168.x.x), you may need to use Demo Mode."}
        elif result == 110:
            return {"success": False, "message": "Connection timed out - check the IP address and ensure Boat Beacon TCP server is enabled."}
        else:
            return {"success": False, "message": f"Connection failed (error code: {result})"}
    except socket.gaierror:
        return {"success": False, "message": "Invalid IP address format"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@api_router.get("/vessels")
async def get_vessels():
    """Get all tracked vessels."""
    vessels = []
    for mmsi, vessel in active_vessels.items():
        v_dict = vessel.model_dump()
        v_dict['timestamp'] = v_dict['timestamp'].isoformat()
        vessels.append(v_dict)
    return vessels

@api_router.get("/race-analysis/{lock_id}")
async def get_race_analysis(lock_id: str):
    """Get race analysis for a specific lock."""
    global user_mmsi
    
    if lock_id not in LOCKS:
        return {"error": "Invalid lock ID"}
    
    lock = LOCKS[lock_id]
    
    # Find user vessel
    user_vessel = None
    if user_mmsi and user_mmsi in active_vessels:
        user_vessel = active_vessels[user_mmsi].model_dump()
        user_vessel['timestamp'] = user_vessel['timestamp'].isoformat()
    
    # Find competitors heading toward this lock
    competitors = []
    for mmsi, vessel in active_vessels.items():
        if mmsi == user_mmsi:
            continue
        
        eta = calculate_eta_to_lock(
            vessel.river_mile or estimate_river_mile(vessel.lat, vessel.lon),
            vessel.speed,
            vessel.heading or determine_heading(vessel.speed, vessel.course),
            lock["river_mile"]
        )
        
        if eta is not None and eta > 0:
            v_dict = vessel.model_dump()
            v_dict['timestamp'] = v_dict['timestamp'].isoformat()
            v_dict['eta_minutes'] = eta
            competitors.append(v_dict)
    
    # Sort by ETA
    competitors.sort(key=lambda x: x.get('eta_minutes', float('inf')))
    
    # Calculate analysis if user vessel exists
    analysis = None
    if user_vessel and user_vessel.get('river_mile'):
        user_rm = user_vessel['river_mile']
        user_heading = user_vessel.get('heading', 'southbound')
        user_distance = abs(user_rm - lock["river_mile"])
        user_speed_knots = user_vessel.get('speed', 0)
        user_speed_mph = user_speed_knots * 1.15078
        
        user_eta = calculate_eta_to_lock(user_rm, user_speed_knots, user_heading, lock["river_mile"])
        
        # Find most threatening competitor
        threat = None
        required_speed = None
        can_beat = True
        
        if competitors:
            for comp in competitors:
                comp_eta = comp.get('eta_minutes')
                if comp_eta and (user_eta is None or comp_eta < user_eta):
                    threat = comp
                    required_speed = calculate_required_speed(user_rm, user_heading, lock["river_mile"], comp_eta)
                    if required_speed and required_speed > 25:
                        can_beat = False
                    break
        
        analysis = {
            "user_distance_to_lock": round(user_distance, 1),
            "user_eta_minutes": user_eta,
            "user_current_speed_mph": round(user_speed_mph, 1),
            "threatening_vessel": threat,
            "required_speed_mph": required_speed,
            "can_beat_at_25mph": can_beat,
            "max_speed_mph": 25
        }
    
    return RaceAnalysis(
        user_vessel=user_vessel,
        target_lock=lock_id,
        target_lock_name=lock["name"],
        target_lock_rm=lock["river_mile"],
        competitors=competitors,
        analysis=analysis
    )

@api_router.post("/set-user-mmsi")
async def set_user_mmsi(data: dict):
    """Set the user's MMSI number."""
    global user_mmsi
    user_mmsi = data.get("mmsi", "")
    
    # Update vessel if already tracked
    if user_mmsi in active_vessels:
        active_vessels[user_mmsi].is_user_vessel = True
    
    # Save to database
    await db.settings.update_one(
        {"key": "user_mmsi"},
        {"$set": {"value": user_mmsi, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    
    return {"success": True, "mmsi": user_mmsi}

@api_router.get("/settings")
async def get_settings():
    """Get saved settings."""
    settings = await db.settings.find({}, {"_id": 0}).to_list(100)
    return {s["key"]: s["value"] for s in settings}

@api_router.post("/settings")
async def save_settings(data: dict):
    """Save connection settings."""
    for key, value in data.items():
        await db.settings.update_one(
            {"key": key},
            {"$set": {"value": value, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True
        )
    return {"success": True}

# WebSocket for real-time AIS data
@app.websocket("/ws/ais")
async def websocket_ais(websocket: WebSocket):
    """WebSocket endpoint for real-time AIS data streaming."""
    await websocket.accept()
    
    ais_socket = None
    connection_active = False
    
    try:
        while True:
            # Receive config or commands from client
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg.get("action") == "connect":
                ip = msg.get("ip_address")
                port = msg.get("port", 5353)
                mmsi = msg.get("user_mmsi", "")
                
                global user_mmsi
                user_mmsi = mmsi
                
                try:
                    # Close existing connection
                    if ais_socket:
                        ais_socket.close()
                    
                    # Connect to AIS feed
                    ais_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    ais_socket.settimeout(5)
                    ais_socket.connect((ip, port))
                    ais_socket.setblocking(False)
                    connection_active = True
                    
                    await websocket.send_json({"type": "connected", "message": f"Connected to {ip}:{port}"})
                    
                    # Start reading AIS data
                    buffer = ""
                    while connection_active:
                        try:
                            # Try to receive data (non-blocking)
                            try:
                                chunk = ais_socket.recv(4096).decode('ascii', errors='ignore')
                                if chunk:
                                    buffer += chunk
                                    
                                    # Process complete lines
                                    while '\n' in buffer:
                                        line, buffer = buffer.split('\n', 1)
                                        vessel_data = parse_nmea_ais(line)
                                        
                                        if vessel_data and vessel_data.get('mmsi'):
                                            # Calculate river mile and heading
                                            rm = estimate_river_mile(vessel_data['lat'], vessel_data['lon'])
                                            heading = determine_heading(vessel_data['speed'], vessel_data['course'])
                                            
                                            vessel = VesselPosition(
                                                mmsi=vessel_data['mmsi'],
                                                name=vessel_data.get('name', ''),
                                                lat=vessel_data['lat'],
                                                lon=vessel_data['lon'],
                                                speed=vessel_data['speed'],
                                                course=vessel_data['course'],
                                                river_mile=rm,
                                                heading=heading,
                                                is_user_vessel=(vessel_data['mmsi'] == user_mmsi),
                                                vessel_type=vessel_data.get('vessel_type', 'unknown')
                                            )
                                            
                                            active_vessels[vessel.mmsi] = vessel
                                            
                                            # Send update to client
                                            v_dict = vessel.model_dump()
                                            v_dict['timestamp'] = v_dict['timestamp'].isoformat()
                                            await websocket.send_json({"type": "vessel_update", "vessel": v_dict})
                                            
                            except BlockingIOError:
                                pass
                            
                            # Check for client messages (non-blocking)
                            try:
                                client_msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                                client_data = json.loads(client_msg)
                                if client_data.get("action") == "disconnect":
                                    connection_active = False
                                    break
                            except asyncio.TimeoutError:
                                pass
                            
                            await asyncio.sleep(0.1)
                            
                        except Exception as e:
                            logger.error(f"Error reading AIS data: {e}")
                            await asyncio.sleep(1)
                            
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"Connection failed: {str(e)}"})
                    
            elif msg.get("action") == "disconnect":
                connection_active = False
                if ais_socket:
                    ais_socket.close()
                    ais_socket = None
                await websocket.send_json({"type": "disconnected", "message": "Disconnected from AIS feed"})
                
            elif msg.get("action") == "get_vessels":
                vessels = []
                for mmsi, vessel in active_vessels.items():
                    v_dict = vessel.model_dump()
                    v_dict['timestamp'] = v_dict['timestamp'].isoformat()
                    vessels.append(v_dict)
                await websocket.send_json({"type": "vessels", "vessels": vessels})
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if ais_socket:
            ais_socket.close()

# Demo endpoint to add test vessels (for development)
@api_router.post("/demo/add-vessel")
async def add_demo_vessel(vessel: VesselPosition):
    """Add a demo vessel for testing."""
    vessel.river_mile = vessel.river_mile or estimate_river_mile(vessel.lat, vessel.lon)
    vessel.heading = vessel.heading or determine_heading(vessel.speed, vessel.course)
    
    # Estimate tow info if not provided
    if vessel.is_tow and vessel.barge_count is None:
        tow_info = estimate_tow_info({
            'shipname': vessel.name,
            'ship_type': vessel.ship_type_code or 31,  # Default to towing
            'length': vessel.length,
            'width': vessel.width,
        })
        vessel.barge_count = tow_info.get('barge_count')
        vessel.tow_config = tow_info.get('tow_config')
        vessel.estimated_lockage_time = tow_info.get('estimated_lockage_time')
    
    active_vessels[vessel.mmsi] = vessel
    v_dict = vessel.model_dump()
    v_dict['timestamp'] = v_dict['timestamp'].isoformat()
    return {"success": True, "vessel": v_dict}

@api_router.post("/demo/add-tow")
async def add_demo_tow(data: dict):
    """Add a demo tow with specific barge configuration for testing."""
    vessel = VesselPosition(
        mmsi=data.get('mmsi', str(uuid.uuid4())[:9]),
        name=data.get('name', 'M/V TEST TOW'),
        lat=data.get('lat', 44.7),
        lon=data.get('lon', -92.8),
        speed=data.get('speed', 4),
        course=data.get('course', 0),
        vessel_type='towing',
        is_tow=True,
        barge_count=data.get('barge_count', 6),
        tow_config=data.get('tow_config', '2x3'),
        length=data.get('length', 200),
        width=data.get('width', 22),
    )
    
    vessel.river_mile = estimate_river_mile(vessel.lat, vessel.lon)
    vessel.heading = determine_heading(vessel.speed, vessel.course)
    
    # Calculate lockage time based on barge count
    if vessel.barge_count:
        if vessel.barge_count <= 6:
            vessel.estimated_lockage_time = 30
        elif vessel.barge_count <= 12:
            vessel.estimated_lockage_time = 45
        elif vessel.barge_count <= 15:
            vessel.estimated_lockage_time = 60
        else:
            vessel.estimated_lockage_time = 90 + (vessel.barge_count - 15) * 5
    
    active_vessels[vessel.mmsi] = vessel
    v_dict = vessel.model_dump()
    v_dict['timestamp'] = v_dict['timestamp'].isoformat()
    return {"success": True, "vessel": v_dict}

@api_router.delete("/demo/clear-vessels")
async def clear_demo_vessels():
    """Clear all demo vessels."""
    active_vessels.clear()
    return {"success": True}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
