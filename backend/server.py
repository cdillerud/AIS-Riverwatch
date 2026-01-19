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
from datetime import datetime, timezone, timedelta
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

# MMSI numbers to permanently filter out (test beacons, known noise)
FILTERED_MMSI = {
    "2339005",   # Boat Beacon UK test signal
}

# User-blocked MMSIs (loaded from database on startup)
user_blocked_mmsi: set = set()

# Lock positions (River Mile markers) - All Upper Mississippi Locks (1-27, excluding 23 which was never built)
LOCKS = {
    "lock_1": {"name": "Lock & Dam #1 (Minneapolis)", "river_mile": 847.6, "lat": 44.9178, "lon": -93.2056, "phone": "612-724-2971"},
    "lock_2": {"name": "Lock & Dam #2 (Hastings)", "river_mile": 815.2, "lat": 44.7433, "lon": -92.8506, "phone": "651-436-2900"},
    "lock_3": {"name": "Lock & Dam #3 (Red Wing)", "river_mile": 796.9, "lat": 44.5533, "lon": -92.5356, "phone": "651-388-5794"},
    "lock_4": {"name": "Lock & Dam #4 (Alma)", "river_mile": 752.8, "lat": 44.3189, "lon": -91.9150, "phone": "608-685-4421"},
    "lock_5": {"name": "Lock & Dam #5 (Minnesota City)", "river_mile": 738.1, "lat": 44.1047, "lon": -91.7428, "phone": "507-689-2101"},
    "lock_5a": {"name": "Lock & Dam #5A (Fountain City)", "river_mile": 728.5, "lat": 44.0317, "lon": -91.7089, "phone": "507-452-2789"},
    "lock_6": {"name": "Lock & Dam #6 (Trempealeau)", "river_mile": 714.3, "lat": 43.8697, "lon": -91.5006, "phone": "608-534-6424"},
    "lock_7": {"name": "Lock & Dam #7 (Dresbach)", "river_mile": 702.5, "lat": 43.8128, "lon": -91.3053, "phone": "507-895-2170"},
    "lock_8": {"name": "Lock & Dam #8 (Genoa)", "river_mile": 679.2, "lat": 43.5789, "lon": -91.2294, "phone": "608-689-2625"},
    "lock_9": {"name": "Lock & Dam #9 (Lynxville)", "river_mile": 647.9, "lat": 43.2108, "lon": -91.0836, "phone": "608-874-4311"},
    "lock_10": {"name": "Lock & Dam #10 (Guttenberg)", "river_mile": 615.1, "lat": 42.7856, "lon": -91.1003, "phone": "563-252-1261"},
    "lock_11": {"name": "Lock & Dam #11 (Dubuque)", "river_mile": 583.0, "lat": 42.5036, "lon": -90.6581, "phone": "563-582-0881"},
    "lock_12": {"name": "Lock & Dam #12 (Bellevue)", "river_mile": 556.7, "lat": 42.2578, "lon": -90.4214, "phone": "563-872-4384"},
    "lock_13": {"name": "Lock & Dam #13 (Fulton)", "river_mile": 522.5, "lat": 41.8711, "lon": -90.1547, "phone": "815-589-2274"},
    "lock_14": {"name": "Lock & Dam #14 (Le Claire)", "river_mile": 493.3, "lat": 41.5978, "lon": -90.4336, "phone": "563-289-4233"},
    "lock_15": {"name": "Lock & Dam #15 (Rock Island)", "river_mile": 482.9, "lat": 41.5189, "lon": -90.5628, "phone": "309-794-5338"},
    "lock_16": {"name": "Lock & Dam #16 (Muscatine)", "river_mile": 457.2, "lat": 41.4231, "lon": -91.0439, "phone": "563-263-7913"},
    "lock_17": {"name": "Lock & Dam #17 (New Boston)", "river_mile": 437.1, "lat": 41.1725, "lon": -91.0142, "phone": "309-587-8461"},
    "lock_18": {"name": "Lock & Dam #18 (Gladstone)", "river_mile": 410.5, "lat": 40.8681, "lon": -91.0506, "phone": "319-524-2933"},
    "lock_19": {"name": "Lock & Dam #19 (Keokuk)", "river_mile": 364.2, "lat": 40.3883, "lon": -91.3750, "phone": "319-524-2933"},
    "lock_20": {"name": "Lock & Dam #20 (Canton)", "river_mile": 343.2, "lat": 40.1411, "lon": -91.5153, "phone": "573-853-4213"},
    "lock_21": {"name": "Lock & Dam #21 (Quincy)", "river_mile": 324.9, "lat": 39.9131, "lon": -91.4097, "phone": "217-228-0890"},
    "lock_22": {"name": "Lock & Dam #22 (Saverton)", "river_mile": 301.2, "lat": 39.6428, "lon": -91.2461, "phone": "573-754-4451"},
    "lock_24": {"name": "Lock & Dam #24 (Clarksville)", "river_mile": 273.4, "lat": 39.3706, "lon": -90.9042, "phone": "573-242-3564"},
    "lock_25": {"name": "Lock & Dam #25 (Cap au Gris)", "river_mile": 241.4, "lat": 39.0044, "lon": -90.8536, "phone": "636-899-2301"},
    "melvin_price": {"name": "Melvin Price Lock & Dam (Alton)", "river_mile": 200.8, "lat": 38.8697, "lon": -90.1492, "phone": "618-462-6979"},
    "chain_of_rocks": {"name": "Chain of Rocks Lock (Granite City)", "river_mile": 185.0, "lat": 38.7542, "lon": -90.1711, "phone": "314-355-6100"},
}

# Cache for USACE lock status data
usace_cache = {
    "data": {},
    "last_updated": None,
    "cache_duration_seconds": 300  # 5 minutes
}

# Cache for LPMS lockage times data
lpms_cache = {
    "data": {},
    "last_updated": None,
    "cache_duration_seconds": 600  # 10 minutes
}

# Vessel Lock Passage Tracking
# Tracks vessels as they approach and transit locks to calculate real lockage times
# Structure: {mmsi: {lock_id: {state, arrival_time, entry_time, direction, ...}}}
vessel_lock_tracking: Dict[str, Dict[str, dict]] = {}

# Distance thresholds for lock tracking (in river miles)
LOCK_APPROACH_DISTANCE = 2.0  # Start tracking when within 2 miles
LOCK_CHAMBER_DISTANCE = 0.3   # Consider "in chamber" when within 0.3 miles
LOCK_CLEARED_DISTANCE = 1.5   # Consider cleared when 1.5 miles past lock

# Cache for vessel static data (names, ship types, dimensions)
# AIS sends position data frequently (every 2-10s) but static data only every 6 minutes
# This cache persists names once we receive them from Type 5 or Type 24 messages
vessel_static_cache: Dict[str, dict] = {}

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
    # Ship information
    ship_type: Optional[int] = None  # AIS ship type code
    length: Optional[float] = None  # meters
    width: Optional[float] = None  # meters
    draught: Optional[float] = None  # meters
    # Tow/Barge information
    barge_count: Optional[int] = None  # Estimated or reported barge count
    tow_config: Optional[str] = None  # e.g., "2x3" (2 wide, 3 long)
    is_tow: bool = False
    estimated_lockage_time: Optional[int] = None  # minutes
    # Additional AIS fields
    heading_true: Optional[float] = None  # True heading (degrees) from AIS
    turn_rate: Optional[float] = None  # Rate of turn (deg/min)
    nav_status: Optional[int] = None  # Navigation status code
    nav_status_text: Optional[str] = None  # Human-readable status
    destination: Optional[str] = None  # Vessel destination
    callsign: Optional[str] = None  # Radio call sign
    imo: Optional[int] = None  # IMO number
    eta: Optional[str] = None  # ETA as string

# Navigation status codes
NAV_STATUS = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted maneuverability",
    4: "Constrained by draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    9: "Reserved (HSC)",
    10: "Reserved (WIG)",
    11: "Power-driven towing astern",
    12: "Power-driven pushing/towing alongside",
    13: "Reserved",
    14: "AIS-SART active",
    15: "Undefined"
}

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
    
    Tow configurations (Upper Mississippi locks are 600ft):
    - Single lock (fits in one pass): up to 9 barges
    - Double lock (requires 2 passes): 10+ barges
    
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
    # Upper Mississippi locks are 600ft - anything over 9 barges requires double lockage
    if barge_count > 0:
        if barge_count <= 6:
            estimated_lockage_time = 30  # Single cut, quick
        elif barge_count <= 9:
            estimated_lockage_time = 45  # Single cut, larger tow
        else:
            # Double lockage required (>9 barges)
            estimated_lockage_time = 90 + (barge_count - 9) * 5  # Base + extra per barge
    elif is_tow:
        estimated_lockage_time = 45  # Unknown tow, assume medium
    else:
        # Non-tow vessel
        estimated_lockage_time = 20 if length < 30 else 30
    
    return {
        'is_tow': is_tow,
        'barge_count': barge_count if barge_count > 0 else None,
        'tow_config': tow_config,
        'estimated_lockage_time': estimated_lockage_time,
        'is_double_lockage': barge_count > 9  # Flag for UI
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


# LPMS Lockage Data Tracking
class LockageRecord(BaseModel):
    """Record of a single vessel lockage."""
    model_config = ConfigDict(extra="ignore")
    lock_id: str
    vessel_name: str
    direction: str  # "upbound" or "downbound"
    arrival_time: Optional[datetime] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    lockage_duration_minutes: Optional[float] = None
    wait_time_minutes: Optional[float] = None
    barge_count: int = 0
    is_tow: bool = False
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


async def fetch_lpms_lockage_data(lock_number: int = None) -> Dict[str, list]:
    """
    Fetch recent lockage data from USACE LPMS system.
    This provides actual lockage times we can use for running averages.
    
    Returns dict keyed by lock_id with list of recent lockage records.
    """
    global lpms_cache
    
    now = datetime.now(timezone.utc)
    
    # Check cache validity
    if lpms_cache["last_updated"]:
        cache_age = (now - lpms_cache["last_updated"]).total_seconds()
        if cache_age < lpms_cache["cache_duration_seconds"] and lpms_cache["data"]:
            return lpms_cache["data"]
    
    lockage_data = {}
    
    try:
        # Map lock numbers to LPMS river/lock codes
        # Upper Mississippi = "MISS", locks are numbered
        locks_to_fetch = [lock_number] if lock_number else list(range(1, 28))
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for lock_num in locks_to_fetch:
                if lock_num == 23:  # Lock 23 was never built
                    continue
                    
                lock_id = f"lock_{lock_num}"
                lockage_data[lock_id] = []
                
                try:
                    # Fetch the Lock Flotilla Report which has detailed timing data
                    # URL pattern: f?p=108:4:::NO:4:P4_RIVER,P4_LOCK:MISS,{lock_num}
                    url = f"https://ndc.ops.usace.army.mil/ords/f?p=108:4:::NO:4:P4_RIVER,P4_LOCK:MISS,{lock_num}"
                    
                    response = await client.get(url)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Find data tables - LPMS uses specific table structures
                        tables = soup.find_all('table', {'class': re.compile(r'.*report.*', re.I)})
                        if not tables:
                            tables = soup.find_all('table')
                        
                        for table in tables:
                            rows = table.find_all('tr')
                            headers = []
                            
                            for row in rows:
                                cells = row.find_all(['th', 'td'])
                                
                                # Get headers
                                if row.find('th'):
                                    headers = [c.get_text(strip=True).lower() for c in cells]
                                    continue
                                
                                if not headers or len(cells) < 3:
                                    continue
                                
                                cell_data = [c.get_text(strip=True) for c in cells]
                                
                                # Parse row data based on common LPMS fields
                                record_data = dict(zip(headers, cell_data))
                                
                                vessel_name = record_data.get('vessel', record_data.get('vessel name', record_data.get('name', '')))
                                if not vessel_name:
                                    continue
                                
                                # Parse times if available
                                lockage_mins = None
                                wait_mins = None
                                direction = 'unknown'
                                barges = 0
                                
                                # Look for direction indicators
                                dir_field = record_data.get('direction', record_data.get('dir', ''))
                                if 'up' in dir_field.lower():
                                    direction = 'upbound'
                                elif 'down' in dir_field.lower() or 'dn' in dir_field.lower():
                                    direction = 'downbound'
                                
                                # Look for lockage duration
                                for key in ['lockage time', 'lock time', 'lockage', 'duration']:
                                    if key in record_data:
                                        try:
                                            time_str = record_data[key]
                                            # Parse HH:MM or minutes format
                                            if ':' in time_str:
                                                parts = time_str.split(':')
                                                lockage_mins = int(parts[0]) * 60 + int(parts[1])
                                            else:
                                                lockage_mins = float(re.sub(r'[^\d.]', '', time_str))
                                        except:
                                            pass
                                        break
                                
                                # Look for barge count
                                for key in ['barges', 'barge count', 'cuts', 'flotilla']:
                                    if key in record_data:
                                        try:
                                            barges = int(re.sub(r'[^\d]', '', record_data[key]) or 0)
                                        except:
                                            pass
                                        break
                                
                                is_tow = barges > 0 or 'tow' in vessel_name.lower() or 'm/v' in vessel_name.lower()
                                
                                lockage_record = LockageRecord(
                                    lock_id=lock_id,
                                    vessel_name=vessel_name,
                                    direction=direction,
                                    lockage_duration_minutes=lockage_mins,
                                    wait_time_minutes=wait_mins,
                                    barge_count=barges,
                                    is_tow=is_tow
                                )
                                
                                lockage_data[lock_id].append(lockage_record.model_dump())
                                
                except Exception as e:
                    logger.warning(f"Error fetching LPMS data for lock {lock_num}: {e}")
                    continue
        
        # Update cache
        lpms_cache["data"] = lockage_data
        lpms_cache["last_updated"] = now
        
        # Store in MongoDB for persistence and historical analysis
        for lock_id, records in lockage_data.items():
            for record in records:
                # Upsert based on lock_id, vessel_name, and approximate time
                record["_lock_id"] = lock_id
                await db.lockage_history.update_one(
                    {
                        "lock_id": lock_id,
                        "vessel_name": record["vessel_name"],
                        "recorded_at": {"$gte": now.replace(hour=0, minute=0, second=0)}
                    },
                    {"$set": record},
                    upsert=True
                )
        
        logger.info(f"Fetched LPMS lockage data for {len(lockage_data)} locks")
        
    except Exception as e:
        logger.error(f"Error fetching LPMS lockage data: {e}")
        
        # Try to load from database cache
        cached = await db.lockage_history.find(
            {"recorded_at": {"$gte": now.replace(hour=0, minute=0, second=0)}},
            {"_id": 0}
        ).to_list(500)
        
        for item in cached:
            lock_id = item.get("lock_id")
            if lock_id:
                if lock_id not in lockage_data:
                    lockage_data[lock_id] = []
                lockage_data[lock_id].append(item)
    
    return lockage_data


async def get_lockage_averages(lock_id: str = None) -> Dict[str, dict]:
    """
    Calculate running averages for lockage times based on historical data.
    Returns averages for tows vs recreational vessels, plus wait times.
    Uses baseline data from USACE historical statistics plus any observed passages.
    """
    # Lock-specific baseline data from USACE statistics and studies
    # Sources: USACE LPMS, Iowa DOT studies, bridgecalculator.com live data
    # All Upper Mississippi locks are 110' x 600' except Lock 19 (1200') and Lock 26/27
    # 600' locks require double lockage for 15-barge tows (90-120 min)
    # Wait times based on traffic volume - busier locks at southern end
    
    # Lock-specific baselines: {lock_num: {tow_lockage, rec_lockage, tow_wait, rec_wait}}
    # Traffic increases going south (more commercial traffic)
    lock_baselines = {
        1:  {"tow_lockage": 45, "rec_lockage": 15, "tow_wait": 10, "rec_wait": 5},   # Minneapolis - lower traffic
        2:  {"tow_lockage": 50, "rec_lockage": 15, "tow_wait": 15, "rec_wait": 5},   # Hastings
        3:  {"tow_lockage": 55, "rec_lockage": 18, "tow_wait": 20, "rec_wait": 8},   # Welch - moderate
        4:  {"tow_lockage": 60, "rec_lockage": 18, "tow_wait": 25, "rec_wait": 10},  # Alma
        5:  {"tow_lockage": 55, "rec_lockage": 15, "tow_wait": 15, "rec_wait": 5},   # Winona area - lower
        "5a": {"tow_lockage": 50, "rec_lockage": 15, "tow_wait": 10, "rec_wait": 0}, # Winona - very low wait
        6:  {"tow_lockage": 55, "rec_lockage": 18, "tow_wait": 20, "rec_wait": 8},   # Trempealeau
        7:  {"tow_lockage": 60, "rec_lockage": 18, "tow_wait": 25, "rec_wait": 10},  # La Crescent - busier
        8:  {"tow_lockage": 60, "rec_lockage": 18, "tow_wait": 30, "rec_wait": 12},  # Genoa
        9:  {"tow_lockage": 65, "rec_lockage": 20, "tow_wait": 35, "rec_wait": 15},  # Harpers Ferry
        10: {"tow_lockage": 70, "rec_lockage": 20, "tow_wait": 40, "rec_wait": 15},  # Guttenberg - high traffic
        11: {"tow_lockage": 70, "rec_lockage": 20, "tow_wait": 45, "rec_wait": 18},  # Dubuque
        12: {"tow_lockage": 75, "rec_lockage": 20, "tow_wait": 50, "rec_wait": 20},  # Bellevue
        13: {"tow_lockage": 80, "rec_lockage": 22, "tow_wait": 70, "rec_wait": 25},  # Fulton - high congestion
        14: {"tow_lockage": 85, "rec_lockage": 22, "tow_wait": 80, "rec_wait": 30},  # Le Claire - very high delays
        15: {"tow_lockage": 70, "rec_lockage": 18, "tow_wait": 25, "rec_wait": 10},  # Rock Island - aux lock helps
        16: {"tow_lockage": 75, "rec_lockage": 20, "tow_wait": 55, "rec_wait": 20},  # Muscatine
        17: {"tow_lockage": 80, "rec_lockage": 20, "tow_wait": 60, "rec_wait": 22},  # New Boston
        18: {"tow_lockage": 85, "rec_lockage": 22, "tow_wait": 115, "rec_wait": 35}, # Gladstone - very high wait
        19: {"tow_lockage": 45, "rec_lockage": 12, "tow_wait": 25, "rec_wait": 8},   # Keokuk - 1200' lock, faster
        20: {"tow_lockage": 90, "rec_lockage": 22, "tow_wait": 90, "rec_wait": 30},  # Canton - high congestion
        21: {"tow_lockage": 90, "rec_lockage": 22, "tow_wait": 85, "rec_wait": 28},  # Quincy
        22: {"tow_lockage": 95, "rec_lockage": 25, "tow_wait": 100, "rec_wait": 35}, # Saverton - major bottleneck
        # Lock 23 was never built
        24: {"tow_lockage": 95, "rec_lockage": 25, "tow_wait": 95, "rec_wait": 32},  # Clarksville - high delays
        25: {"tow_lockage": 100, "rec_lockage": 25, "tow_wait": 108, "rec_wait": 38},# Winfield - highest delays
        26: {"tow_lockage": 50, "rec_lockage": 15, "tow_wait": 70, "rec_wait": 25},  # Alton - 1200' lock
        27: {"tow_lockage": 55, "rec_lockage": 18, "tow_wait": 72, "rec_wait": 28},  # Chain of Rocks
    }
    
    # Get any observed data from last 7 days
    seven_days_ago = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
    seven_days_ago = seven_days_ago - timedelta(days=7)
    
    query = {"recorded_at": {"$gte": seven_days_ago}}
    if lock_id:
        query["lock_id"] = lock_id
    
    records = await db.lockage_history.find(query, {"_id": 0}).to_list(1000)
    
    # Group by lock and direction, calculate averages
    averages = {}
    lock_data = {}
    
    for record in records:
        lid = record.get("lock_id")
        direction = record.get("direction", "unknown")
        if not lid:
            continue
            
        key = f"{lid}_{direction}"
        if key not in lock_data:
            lock_data[key] = {"tow_times": [], "rec_times": [], "all_times": [], 
                             "tow_waits": [], "rec_waits": [], "all_waits": []}
        
        duration = record.get("lockage_duration_minutes")
        wait = record.get("wait_time_minutes")
        
        if duration and duration > 0:
            lock_data[key]["all_times"].append(duration)
            if record.get("is_tow"):
                lock_data[key]["tow_times"].append(duration)
            else:
                lock_data[key]["rec_times"].append(duration)
        
        if wait and wait >= 0:
            lock_data[key]["all_waits"].append(wait)
            if record.get("is_tow"):
                lock_data[key]["tow_waits"].append(wait)
            else:
                lock_data[key]["rec_waits"].append(wait)
    
    # Generate averages for all 27 locks (Lock 23 was never built)
    # Also handle Lock 5A
    lock_nums_to_process = list(range(1, 28)) + ["5a"]
    
    for lock_num in lock_nums_to_process:
        if lock_num == 23:
            continue
        
        # Get lock-specific baseline
        baseline = lock_baselines.get(lock_num, lock_baselines.get(10))  # Default to Lock 10 if missing
        
        lid = f"lock_{lock_num}"
        
        for direction in ["upbound", "downbound"]:
            key = f"{lid}_{direction}"
            data = lock_data.get(key, {"tow_times": [], "rec_times": [], "all_times": [],
                                       "tow_waits": [], "rec_waits": [], "all_waits": []})
            
            # Calculate observed averages or use lock-specific baseline
            if data["tow_times"]:
                avg_tow = sum(data["tow_times"]) / len(data["tow_times"])
            else:
                avg_tow = baseline["tow_lockage"]
                
            if data["rec_times"]:
                avg_rec = sum(data["rec_times"]) / len(data["rec_times"])
            else:
                avg_rec = baseline["rec_lockage"]
            
            if data["tow_waits"]:
                avg_tow_wait = sum(data["tow_waits"]) / len(data["tow_waits"])
            else:
                avg_tow_wait = baseline["tow_wait"]
                
            if data["rec_waits"]:
                avg_rec_wait = sum(data["rec_waits"]) / len(data["rec_waits"])
            else:
                avg_rec_wait = baseline["rec_wait"]
            
            if lid not in averages:
                averages[lid] = {}
            
            averages[lid][direction] = {
                "avg_tow_lockage_minutes": round(avg_tow, 1),
                "avg_recreational_lockage_minutes": round(avg_rec, 1),
                "avg_tow_wait_minutes": round(avg_tow_wait, 1),
                "avg_recreational_wait_minutes": round(avg_rec_wait, 1),
                "tow_sample_count": len(data["tow_times"]),
                "rec_sample_count": len(data["rec_times"]),
                "is_baseline": len(data["tow_times"]) == 0 and len(data["rec_times"]) == 0
            }
        
        # Also provide combined averages (both directions)
        all_tow_times = []
        all_rec_times = []
        all_tow_waits = []
        all_rec_waits = []
        
        for direction in ["upbound", "downbound"]:
            key = f"{lid}_{direction}"
            data = lock_data.get(key, {})
            all_tow_times.extend(data.get("tow_times", []))
            all_rec_times.extend(data.get("rec_times", []))
            all_tow_waits.extend(data.get("tow_waits", []))
            all_rec_waits.extend(data.get("rec_waits", []))
        
        # Use lock-specific baseline for combined averages
        avg_tow = sum(all_tow_times) / len(all_tow_times) if all_tow_times else baseline["tow_lockage"]
        avg_rec = sum(all_rec_times) / len(all_rec_times) if all_rec_times else baseline["rec_lockage"]
        avg_tow_wait = sum(all_tow_waits) / len(all_tow_waits) if all_tow_waits else baseline["tow_wait"]
        avg_rec_wait = sum(all_rec_waits) / len(all_rec_waits) if all_rec_waits else baseline["rec_wait"]
        
        averages[lid]["combined"] = {
            "avg_tow_lockage_minutes": round(avg_tow, 1),
            "avg_recreational_lockage_minutes": round(avg_rec, 1),
            "avg_tow_wait_minutes": round(avg_tow_wait, 1),
            "avg_recreational_wait_minutes": round(avg_rec_wait, 1),
            "tow_sample_count": len(all_tow_times),
            "rec_sample_count": len(all_rec_times),
            "is_baseline": len(all_tow_times) == 0 and len(all_rec_times) == 0
        }
        
        # For backwards compatibility, also set top-level values
        averages[lid]["avg_tow_lockage_minutes"] = round(avg_tow, 1)
        averages[lid]["avg_recreational_lockage_minutes"] = round(avg_rec, 1)
        averages[lid]["avg_tow_wait_minutes"] = round(avg_tow_wait, 1)
        averages[lid]["avg_recreational_wait_minutes"] = round(avg_rec_wait, 1)
        averages[lid]["sample_count"] = len(all_tow_times) + len(all_rec_times)
    
    return averages


async def track_vessel_lock_passage(vessel: dict):
    """
    Track a vessel's passage through locks based on position updates.
    This function is called whenever a vessel position is updated.
    
    States: approaching -> waiting -> in_chamber -> cleared
    """
    global vessel_lock_tracking
    
    mmsi = vessel.get("mmsi")
    river_mile = vessel.get("river_mile")
    heading = vessel.get("heading")  # "northbound" or "southbound"
    is_tow = vessel.get("is_tow", False)
    
    if not mmsi or not river_mile or not heading or heading == "stationary":
        return
    
    now = datetime.now(timezone.utc)
    
    # Initialize tracking for this vessel if needed
    if mmsi not in vessel_lock_tracking:
        vessel_lock_tracking[mmsi] = {}
    
    # Check each lock for potential tracking
    for lock_id, lock_info in LOCKS.items():
        lock_rm = lock_info["river_mile"]
        distance_to_lock = river_mile - lock_rm  # Positive = north of lock
        
        # Determine if vessel is approaching this lock based on heading
        is_approaching = False
        direction = None
        
        if heading == "southbound" and distance_to_lock > 0:
            # Going south, north of lock = approaching
            is_approaching = distance_to_lock <= LOCK_APPROACH_DISTANCE
            direction = "downbound"
        elif heading == "northbound" and distance_to_lock < 0:
            # Going north, south of lock = approaching  
            is_approaching = abs(distance_to_lock) <= LOCK_APPROACH_DISTANCE
            direction = "upbound"
        
        abs_distance = abs(distance_to_lock)
        tracking = vessel_lock_tracking[mmsi].get(lock_id, {})
        current_state = tracking.get("state")
        
        # State machine for lock passage tracking
        if is_approaching and not current_state:
            # New approach detected - start tracking
            vessel_lock_tracking[mmsi][lock_id] = {
                "state": "approaching",
                "direction": direction,
                "arrival_time": now,
                "vessel_name": vessel.get("name", "Unknown"),
                "is_tow": is_tow,
                "barge_count": vessel.get("barge_count", 0)
            }
            logger.info(f"🔒 Vessel {mmsi} ({vessel.get('name', 'Unknown')}) approaching {lock_id} ({direction})")
        
        elif current_state == "approaching" and abs_distance <= LOCK_CHAMBER_DISTANCE:
            # Vessel has entered the lock chamber area
            tracking["state"] = "in_chamber"
            tracking["entry_time"] = now
            tracking["wait_time_minutes"] = (now - tracking["arrival_time"]).total_seconds() / 60
            vessel_lock_tracking[mmsi][lock_id] = tracking
            logger.info(f"🚢 Vessel {mmsi} entering {lock_id} chamber (waited {tracking['wait_time_minutes']:.1f} min)")
        
        elif current_state == "in_chamber":
            # Check if vessel has cleared the lock
            has_cleared = False
            if direction == "downbound" and distance_to_lock < -LOCK_CLEARED_DISTANCE:
                has_cleared = True
            elif direction == "upbound" and distance_to_lock > LOCK_CLEARED_DISTANCE:
                has_cleared = True
            
            if has_cleared:
                # Vessel has completed the lockage!
                tracking["state"] = "cleared"
                tracking["exit_time"] = now
                tracking["lockage_duration_minutes"] = (now - tracking["entry_time"]).total_seconds() / 60
                tracking["total_time_minutes"] = (now - tracking["arrival_time"]).total_seconds() / 60
                
                # Save to database
                await save_lockage_record(lock_id, tracking)
                
                logger.info(f"✅ Vessel {mmsi} cleared {lock_id}: lockage={tracking['lockage_duration_minutes']:.1f}min, wait={tracking['wait_time_minutes']:.1f}min")
                
                # Clear tracking for this lock
                del vessel_lock_tracking[mmsi][lock_id]
        
        elif current_state in ["approaching", "in_chamber"]:
            # Check for abandoned tracking (vessel went the wrong way or timed out)
            tracking_age = (now - tracking.get("arrival_time", now)).total_seconds() / 60
            
            # If tracking for more than 4 hours, abandon it
            if tracking_age > 240:
                logger.warning(f"⚠️ Abandoning stale lock tracking for {mmsi} at {lock_id}")
                del vessel_lock_tracking[mmsi][lock_id]
            
            # If vessel is now far from lock in wrong direction, abandon
            elif current_state == "approaching":
                if direction == "downbound" and distance_to_lock < -LOCK_APPROACH_DISTANCE:
                    del vessel_lock_tracking[mmsi][lock_id]
                elif direction == "upbound" and distance_to_lock > LOCK_APPROACH_DISTANCE:
                    del vessel_lock_tracking[mmsi][lock_id]


async def save_lockage_record(lock_id: str, tracking: dict):
    """Save a completed lockage record to the database."""
    try:
        record = {
            "lock_id": lock_id,
            "vessel_name": tracking.get("vessel_name", "Unknown"),
            "direction": tracking.get("direction"),
            "arrival_time": tracking.get("arrival_time"),
            "entry_time": tracking.get("entry_time"),
            "exit_time": tracking.get("exit_time"),
            "wait_time_minutes": round(tracking.get("wait_time_minutes", 0), 1),
            "lockage_duration_minutes": round(tracking.get("lockage_duration_minutes", 0), 1),
            "total_time_minutes": round(tracking.get("total_time_minutes", 0), 1),
            "is_tow": tracking.get("is_tow", False),
            "barge_count": tracking.get("barge_count", 0),
            "recorded_at": datetime.now(timezone.utc)
        }
        
        await db.lockage_history.insert_one(record)
        logger.info(f"📊 Saved lockage record for {lock_id}: {record['vessel_name']} - {record['lockage_duration_minutes']}min lockage, {record['wait_time_minutes']}min wait")
        
    except Exception as e:
        logger.error(f"Error saving lockage record: {e}")


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

def river_mile_to_coords(rm: float) -> tuple:
    """
    Convert a river mile to approximate lat/lon coordinates.
    This is the reverse of estimate_river_mile().
    Returns (lat, lon) tuple.
    """
    # Using same linear model as estimate_river_mile but reversed
    # RM = ref_rm + (lat - ref_lat) * slope
    # lat = ref_lat + (RM - ref_rm) / slope
    slope = 102.6
    ref_lat = 44.74
    ref_rm = 815.2
    
    # Average longitude for the Upper Mississippi in this region
    # Roughly -91.5 to -93.0, we'll use a slight adjustment based on RM
    ref_lon = -92.0
    lon_slope = 0.003  # slight eastward drift as you go north
    
    lat = ref_lat + (rm - ref_rm) / slope
    lon = ref_lon + (rm - ref_rm) * lon_slope
    
    return (round(lat, 6), round(lon, 6))

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

def calculate_required_speed(user_rm: float, user_heading: str, target_lock_rm: float, competitor_eta_minutes: float, buffer_minutes: float = 20) -> Optional[float]:
    """
    Calculate required speed in MPH to beat competitor to lock.
    
    Buffer time accounts for:
    - Commercial vessels always have lock priority
    - User needs to arrive AND complete lockage before the tow arrives
    - Typical recreational lockage takes 15-20 minutes
    """
    if competitor_eta_minutes is None or competitor_eta_minutes <= 0:
        return None
    
    distance_rm = abs(user_rm - target_lock_rm)
    
    # Check if user is heading toward the lock
    if user_heading == "northbound" and user_rm >= target_lock_rm:
        return None  # User past the lock going north
    elif user_heading == "southbound" and user_rm <= target_lock_rm:
        return None  # User past the lock going south
    
    # Required speed in MPH to arrive with enough buffer before competitor
    # Buffer time ensures user can complete lockage before tow arrives
    target_time_minutes = max(competitor_eta_minutes - buffer_minutes, 1)
    required_mph = (distance_rm / target_time_minutes) * 60
    
    return round(required_mph, 1)

def parse_nmea_gps(line: str) -> Optional[dict]:
    """
    Parse NMEA GPS sentences for user's own position.
    Supports: $GPGGA, $GPRMC, $GPGLL, $GNGGA, $GNRMC, $GNGLL
    
    Returns dict with lat, lon, speed (if available), or None if parsing fails.
    """
    try:
        line = line.strip()
        
        # Check for GPS sentence types
        if not any(line.startswith(prefix) for prefix in ['$GPGGA', '$GPRMC', '$GPGLL', '$GNGGA', '$GNRMC', '$GNGLL']):
            return None
        
        # Remove checksum if present
        if '*' in line:
            line = line.split('*')[0]
        
        parts = line.split(',')
        sentence_type = parts[0]
        
        # Parse GPGGA / GNGGA (GPS Fix Data)
        if 'GGA' in sentence_type and len(parts) >= 10:
            lat_raw = parts[2]
            lat_dir = parts[3]
            lon_raw = parts[4]
            lon_dir = parts[5]
            
            if lat_raw and lon_raw:
                # Convert NMEA format (DDMM.MMMM) to decimal degrees
                lat_deg = float(lat_raw[:2])
                lat_min = float(lat_raw[2:])
                lat = lat_deg + lat_min / 60
                if lat_dir == 'S':
                    lat = -lat
                
                lon_deg = float(lon_raw[:3])
                lon_min = float(lon_raw[3:])
                lon = lon_deg + lon_min / 60
                if lon_dir == 'W':
                    lon = -lon
                
                return {
                    'lat': lat,
                    'lon': lon,
                    'speed': 0,  # GGA doesn't have speed
                    'course': 0,
                    'is_gps': True,
                    'sentence': sentence_type
                }
        
        # Parse GPRMC / GNRMC (Recommended Minimum)
        elif 'RMC' in sentence_type and len(parts) >= 10:
            status = parts[2]  # A=valid, V=invalid
            if status != 'A':
                return None
            
            lat_raw = parts[3]
            lat_dir = parts[4]
            lon_raw = parts[5]
            lon_dir = parts[6]
            speed_knots = parts[7]  # Speed over ground in knots
            course = parts[8]  # Course over ground
            
            if lat_raw and lon_raw:
                lat_deg = float(lat_raw[:2])
                lat_min = float(lat_raw[2:])
                lat = lat_deg + lat_min / 60
                if lat_dir == 'S':
                    lat = -lat
                
                lon_deg = float(lon_raw[:3])
                lon_min = float(lon_raw[3:])
                lon = lon_deg + lon_min / 60
                if lon_dir == 'W':
                    lon = -lon
                
                return {
                    'lat': lat,
                    'lon': lon,
                    'speed': float(speed_knots) if speed_knots else 0,
                    'course': float(course) if course else 0,
                    'is_gps': True,
                    'sentence': sentence_type
                }
        
        # Parse GPGLL / GNGLL (Geographic Position)
        elif 'GLL' in sentence_type and len(parts) >= 6:
            lat_raw = parts[1]
            lat_dir = parts[2]
            lon_raw = parts[3]
            lon_dir = parts[4]
            
            if lat_raw and lon_raw:
                lat_deg = float(lat_raw[:2])
                lat_min = float(lat_raw[2:])
                lat = lat_deg + lat_min / 60
                if lat_dir == 'S':
                    lat = -lat
                
                lon_deg = float(lon_raw[:3])
                lon_min = float(lon_raw[3:])
                lon = lon_deg + lon_min / 60
                if lon_dir == 'W':
                    lon = -lon
                
                return {
                    'lat': lat,
                    'lon': lon,
                    'speed': 0,
                    'course': 0,
                    'is_gps': True,
                    'sentence': sentence_type
                }
    except Exception as e:
        logger.debug(f"GPS parse error: {e}")
    
    return None

def parse_nmea_ais(data: str) -> Optional[dict]:
    """
    Parse NMEA/AIS data. Boat Beacon typically sends !AIVDM sentences.
    Returns vessel info dict or None if parsing fails.
    
    AIS Message Types:
    - Types 1,2,3: Class A position reports (frequent, NO name)
    - Type 5: Class A static/voyage data (every 6 min, HAS name, dimensions, ship type)
    - Type 18: Class B position report (frequent, NO name)  
    - Type 19: Class B extended position (infrequent, HAS name)
    - Type 24: Class B static data (HAS name)
    """
    global vessel_static_cache
    
    try:
        from pyais import decode
        
        lines = data.strip().split('\n')
        for line in lines:
            line = line.strip()
            
            # Handle AIVDO (own vessel) and AIVDM (other vessels) messages
            is_own_vessel = line.startswith('!AIVDO')
            
            if line.startswith('!AIVDM') or line.startswith('!AIVDO'):
                try:
                    msg = decode(line)
                    decoded = msg.asdict()
                    
                    if 'mmsi' not in decoded:
                        continue
                        
                    mmsi = str(decoded.get('mmsi', ''))
                    msg_type = decoded.get('msg_type', 0)
                    
                    # Mark if this is own vessel data (AIVDO)
                    if is_own_vessel:
                        logger.debug(f"Own vessel data received: MMSI {mmsi}")
                    
                    # Handle static data messages (Type 5, 19, 24) - cache the vessel info
                    if msg_type in [5, 19, 24]:
                        static_data = {'is_own_vessel': is_own_vessel}
                        
                        # Get vessel name
                        shipname = decoded.get('shipname', '') or decoded.get('name', '')
                        if shipname and shipname.strip() and shipname.strip() != '@@@@@@@@@@@@@@@@@@@@':
                            static_data['name'] = shipname.strip()
                        
                        # Get call sign
                        callsign = decoded.get('callsign', '')
                        if callsign and callsign.strip() and '@' not in callsign:
                            static_data['callsign'] = callsign.strip()
                        
                        # Get IMO number
                        if decoded.get('imo'):
                            static_data['imo'] = decoded.get('imo')
                        
                        # Get destination
                        destination = decoded.get('destination', '')
                        if destination and destination.strip() and '@' not in destination:
                            static_data['destination'] = destination.strip()
                        
                        # Get ETA (from Type 5)
                        if decoded.get('month') and decoded.get('day'):
                            eta_month = decoded.get('month', 0)
                            eta_day = decoded.get('day', 0)
                            eta_hour = decoded.get('hour', 0)
                            eta_min = decoded.get('minute', 0)
                            if eta_month > 0 and eta_day > 0:
                                static_data['eta'] = f"{eta_month:02d}/{eta_day:02d} {eta_hour:02d}:{eta_min:02d}"
                        
                        # Get ship type and dimensions
                        if decoded.get('ship_type'):
                            static_data['ship_type'] = decoded.get('ship_type')
                        
                        # Calculate dimensions from bow/stern/port/starboard
                        to_bow = decoded.get('to_bow', 0) or 0
                        to_stern = decoded.get('to_stern', 0) or 0
                        to_port = decoded.get('to_port', 0) or 0
                        to_starboard = decoded.get('to_starboard', 0) or 0
                        
                        if to_bow + to_stern > 0:
                            static_data['length'] = to_bow + to_stern
                        if to_port + to_starboard > 0:
                            static_data['width'] = to_port + to_starboard
                        
                        if decoded.get('draught'):
                            static_data['draught'] = decoded.get('draught')
                        
                        # Update cache
                        if static_data:
                            if mmsi not in vessel_static_cache:
                                vessel_static_cache[mmsi] = {}
                            vessel_static_cache[mmsi].update(static_data)
                            logger.info(f"Cached static data for MMSI {mmsi}: {static_data.get('name', 'unnamed')}")
                            
                            # Mark for persistence to database (will be done in async context)
                            if static_data.get('name'):
                                static_data['_persist_to_db'] = True
                                static_data['_mmsi'] = mmsi
                    
                    # Handle position messages (Type 1,2,3,18,19)
                    if msg_type in [1, 2, 3, 18, 19]:
                        lat = decoded.get('lat')
                        lon = decoded.get('lon')
                        
                        # Filter invalid positions
                        if lat is None or lon is None:
                            continue
                        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                            continue
                        if lat == 91.0 or lon == 181.0:  # AIS "not available" values
                            continue
                        
                        # Get navigation status
                        nav_status = decoded.get('status')
                        nav_status_text = NAV_STATUS.get(nav_status, 'Unknown') if nav_status is not None else None
                        
                        # Get heading (true heading, different from course over ground)
                        heading_true = decoded.get('heading')
                        if heading_true == 511:  # 511 = not available
                            heading_true = None
                        
                        # Get rate of turn
                        turn_rate = decoded.get('turn')
                        if turn_rate == -128 or turn_rate == 128:  # not available
                            turn_rate = None
                        
                        # Build vessel data from position report
                        vessel = {
                            'mmsi': mmsi,
                            'lat': lat,
                            'lon': lon,
                            'speed': decoded.get('speed', 0) or 0,  # knots
                            'course': decoded.get('course', 0) or 0,
                            'name': '',
                            'vessel_type': 'unknown',
                            'ship_type': 0,
                            'length': None,
                            'width': None,
                            'draught': None,
                            'is_own_vessel': is_own_vessel,
                            'heading_true': heading_true,
                            'turn_rate': turn_rate,
                            'nav_status': nav_status,
                            'nav_status_text': nav_status_text,
                        }
                        
                        # Merge in cached static data if available
                        if mmsi in vessel_static_cache:
                            cached = vessel_static_cache[mmsi]
                            if cached.get('name'):
                                vessel['name'] = cached['name']
                            if cached.get('ship_type'):
                                vessel['ship_type'] = cached['ship_type']
                                vessel['vessel_type'] = str(cached['ship_type'])
                            if cached.get('length'):
                                vessel['length'] = cached['length']
                            if cached.get('width'):
                                vessel['width'] = cached['width']
                            if cached.get('draught'):
                                vessel['draught'] = cached['draught']
                            if cached.get('destination'):
                                vessel['destination'] = cached['destination']
                            if cached.get('callsign'):
                                vessel['callsign'] = cached['callsign']
                            if cached.get('imo'):
                                vessel['imo'] = cached['imo']
                            if cached.get('eta'):
                                vessel['eta'] = cached['eta']
                            if cached.get('is_own_vessel') or cached.get('is_user'):
                                vessel['is_own_vessel'] = True
                        
                        # Type 19 includes name directly
                        if msg_type == 19:
                            shipname = decoded.get('shipname', '')
                            if shipname and shipname.strip():
                                vessel['name'] = shipname.strip()
                        
                        # Add tow/barge information
                        tow_info = estimate_tow_info(vessel)
                        vessel.update(tow_info)
                        
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


@api_router.get("/locks/lockage-times")
async def get_all_lockage_times():
    """Get recent lockage times and running averages for all locks."""
    # Note: LPMS scraping is blocked by JS rendering, so we use baseline + observed data
    # lockage_data = await fetch_lpms_lockage_data()  # Disabled - returns empty
    
    # Get running averages (includes baseline data)
    averages = await get_lockage_averages()
    
    result = []
    for lock_id, lock_info in LOCKS.items():
        lock_averages = averages.get(lock_id, {})
        
        result.append({
            "lock_id": lock_id,
            "name": lock_info["name"],
            "river_mile": lock_info["river_mile"],
            "avg_tow_lockage_minutes": lock_averages.get("avg_tow_lockage_minutes"),
            "avg_recreational_lockage_minutes": lock_averages.get("avg_recreational_lockage_minutes"),
            "avg_tow_wait_minutes": lock_averages.get("avg_tow_wait_minutes"),
            "avg_recreational_wait_minutes": lock_averages.get("avg_recreational_wait_minutes"),
            "sample_count": lock_averages.get("sample_count", 0),
            "is_baseline": lock_averages.get("combined", {}).get("is_baseline", True),
            "upbound": lock_averages.get("upbound", {}),
            "downbound": lock_averages.get("downbound", {})
        })
    
    return result


@api_router.get("/locks/{lock_id}/lockage-times")
async def get_lock_lockage_times(lock_id: str):
    """Get recent lockage times and averages for a specific lock."""
    if lock_id not in LOCKS:
        return {"error": "Invalid lock ID"}
    
    lock_info = LOCKS[lock_id]
    lock_num = int(lock_id.replace("lock_", ""))
    
    # Fetch LPMS data for this lock
    lockage_data = await fetch_lpms_lockage_data(lock_num)
    
    # Get averages
    averages = await get_lockage_averages(lock_id)
    lock_averages = averages.get(lock_id, {})
    
    return {
        "lock_id": lock_id,
        "name": lock_info["name"],
        "river_mile": lock_info["river_mile"],
        "recent_lockages": lockage_data.get(lock_id, []),
        "avg_lockage_minutes": lock_averages.get("avg_lockage_minutes"),
        "avg_tow_lockage_minutes": lock_averages.get("avg_tow_lockage_minutes"),
        "avg_recreational_lockage_minutes": lock_averages.get("avg_recreational_lockage_minutes"),
        "sample_count": lock_averages.get("sample_count", 0),
        "tow_sample_count": lock_averages.get("tow_sample_count", 0),
        "rec_sample_count": lock_averages.get("rec_sample_count", 0)
    }


@api_router.post("/lockage/record")
async def record_lockage(lock_id: str, vessel_name: str, duration_minutes: float, is_tow: bool = False, barge_count: int = 0, direction: str = "unknown"):
    """Manually record a lockage time (for when live data isn't available)."""
    if lock_id not in LOCKS:
        return {"error": "Invalid lock ID"}
    
    record = {
        "lock_id": lock_id,
        "vessel_name": vessel_name,
        "direction": direction,
        "lockage_duration_minutes": duration_minutes,
        "barge_count": barge_count,
        "is_tow": is_tow,
        "recorded_at": datetime.now(timezone.utc),
        "source": "manual"
    }
    
    await db.lockage_history.insert_one(record)
    
    return {"success": True, "message": "Lockage time recorded", "record": {k: v for k, v in record.items() if k != "_id"}}


@api_router.get("/debug/state")
async def get_debug_state():
    """Get current application state for debugging."""
    return {
        "user_mmsi": user_mmsi,
        "active_vessels_count": len(active_vessels),
        "active_vessel_mmsis": list(active_vessels.keys()),
        "vessel_cache_count": len(vessel_static_cache),
        "cached_vessel_names": {k: v.get('name', 'unnamed') for k, v in vessel_static_cache.items()},
        "filtered_mmsis": list(FILTERED_MMSI),
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

@api_router.get("/vessel-cache")
async def get_vessel_cache():
    """Get cached vessel static data (names, dimensions, etc.)"""
    return {
        "cached_vessels": len(vessel_static_cache),
        "cache": vessel_static_cache
    }

@api_router.get("/river-mile-to-coords/{rm}")
async def convert_rm_to_coords(rm: float):
    """Convert a river mile to approximate lat/lon coordinates."""
    lat, lon = river_mile_to_coords(rm)
    # Also return the estimated RM back (for verification)
    estimated_rm = estimate_river_mile(lat, lon)
    return {
        "river_mile": rm,
        "lat": lat,
        "lon": lon,
        "estimated_rm_back": estimated_rm
    }

@api_router.post("/vessel-cache/{mmsi}")
async def set_vessel_name(mmsi: str, data: dict):
    """
    Manually set a vessel name in the cache.
    This persists to MongoDB and is shared across all users/sessions.
    """
    global vessel_static_cache
    
    if mmsi not in vessel_static_cache:
        vessel_static_cache[mmsi] = {}
    
    update_data = {"mmsi": mmsi, "updated_at": datetime.now(timezone.utc).isoformat()}
    
    if data.get('name'):
        vessel_static_cache[mmsi]['name'] = data['name']
        update_data['name'] = data['name']
    if data.get('ship_type'):
        vessel_static_cache[mmsi]['ship_type'] = data['ship_type']
        update_data['ship_type'] = data['ship_type']
    
    # Persist to MongoDB for sharing across users and sessions
    await db.vessel_names.update_one(
        {"mmsi": mmsi},
        {"$set": update_data},
        upsert=True
    )
    logger.info(f"Saved vessel name to database: MMSI {mmsi} = {data.get('name')}")
    
    # Also update active vessel if present
    if mmsi in active_vessels:
        vessel = active_vessels[mmsi]
        if data.get('name'):
            vessel.name = data['name']
        if data.get('ship_type') is not None:
            vessel.ship_type = data['ship_type']
    
    return {"success": True, "cached": vessel_static_cache.get(mmsi), "persisted": True}

async def load_vessel_names_from_db():
    """Load all persisted vessel names from MongoDB on startup."""
    global vessel_static_cache
    
    try:
        cursor = db.vessel_names.find({}, {"_id": 0})
        vessels = await cursor.to_list(length=1000)
        
        for v in vessels:
            mmsi = v.get("mmsi")
            if mmsi:
                if mmsi not in vessel_static_cache:
                    vessel_static_cache[mmsi] = {}
                if v.get("name"):
                    vessel_static_cache[mmsi]["name"] = v["name"]
                if v.get("ship_type"):
                    vessel_static_cache[mmsi]["ship_type"] = v["ship_type"]
        
        logger.info(f"Loaded {len(vessels)} vessel names from database")
    except Exception as e:
        logger.error(f"Failed to load vessel names from database: {e}")

@api_router.get("/vessels")
async def get_vessels():
    """Get all tracked vessels."""
    vessels = []
    for mmsi, vessel in active_vessels.items():
        # Skip filtered/blocked MMSI
        if is_mmsi_blocked(mmsi):
            continue
        v_dict = vessel.model_dump()
        v_dict['timestamp'] = v_dict['timestamp'].isoformat()
        vessels.append(v_dict)
    return vessels

@api_router.get("/race-analysis/{lock_id}")
async def get_race_analysis(lock_id: str, buffer_minutes: int = 20):
    """
    Get race analysis for a specific lock.
    
    Args:
        lock_id: Target lock ID
        buffer_minutes: Minutes of buffer needed before a commercial tow arrives
                       (to complete your lockage before they get priority)
    """
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
                if comp_eta and (user_eta is None or comp_eta < user_eta + buffer_minutes):
                    # User needs to arrive buffer_minutes BEFORE the tow to get through first
                    threat = comp
                    required_speed = calculate_required_speed(user_rm, user_heading, lock["river_mile"], comp_eta, buffer_minutes)
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
            "max_speed_mph": 25,
            "buffer_minutes": buffer_minutes
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

@api_router.post("/user-position")
async def update_user_position(data: dict):
    """
    Update user's vessel position directly (bypasses AIS feed).
    
    This solves the common AIS "self-suppression" issue where Boat Beacon
    and similar apps intentionally filter out your own MMSI from the feed.
    
    Position can come from:
    - Browser Geolocation API
    - Manual lat/lon entry
    - External GPS source
    """
    global user_mmsi
    
    lat = data.get("lat")
    lon = data.get("lon")
    speed = data.get("speed", 0)  # knots
    course = data.get("course", 0)
    source = data.get("source", "manual")  # "geolocation", "manual", "external"
    
    if lat is None or lon is None:
        return {"success": False, "error": "lat and lon required"}
    
    # Use MMSI from request, then global user_mmsi, then default
    mmsi = data.get("mmsi") or user_mmsi or "USER_VESSEL"
    
    # If MMSI provided in request, also update the global user_mmsi
    if data.get("mmsi") and data.get("mmsi") != user_mmsi:
        user_mmsi = data.get("mmsi")
        logger.info(f"Updated user_mmsi to: {user_mmsi}")
    
    # Get boat name - prefer request, then cache, then default
    boat_name = data.get("name") or "Your Vessel"
    if mmsi in vessel_static_cache:
        boat_name = vessel_static_cache[mmsi].get("name", boat_name)
    
    # Calculate river mile and heading
    rm = estimate_river_mile(lat, lon)
    heading = determine_heading(speed, course)
    
    # Create or update user vessel
    vessel = VesselPosition(
        mmsi=mmsi,
        name=boat_name,
        lat=lat,
        lon=lon,
        speed=speed,
        course=course,
        river_mile=rm,
        heading=heading,
        is_user_vessel=True,
        vessel_type="recreational",
    )
    
    active_vessels[mmsi] = vessel
    
    logger.info(f"User position updated via {source}: lat={lat:.4f}, lon={lon:.4f}, RM={rm:.1f}")
    
    v_dict = vessel.model_dump()
    v_dict['timestamp'] = v_dict['timestamp'].isoformat()
    v_dict['source'] = source
    
    return {"success": True, "vessel": v_dict}

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

# Blocked MMSI Management
@api_router.get("/blocked-mmsi")
async def get_blocked_mmsi():
    """Get list of user-blocked MMSIs."""
    blocked = await db.blocked_mmsi.find({}, {"_id": 0}).to_list(100)
    return {
        "blocked": blocked,
        "system_filtered": list(FILTERED_MMSI)
    }

@api_router.post("/blocked-mmsi")
async def add_blocked_mmsi(data: dict):
    """Add an MMSI to the block list."""
    global user_blocked_mmsi
    
    mmsi = str(data.get("mmsi", "")).strip()
    reason = data.get("reason", "User blocked")
    
    if not mmsi:
        return {"success": False, "error": "MMSI required"}
    
    # Add to database
    await db.blocked_mmsi.update_one(
        {"mmsi": mmsi},
        {"$set": {
            "mmsi": mmsi,
            "reason": reason,
            "blocked_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    # Add to in-memory set
    user_blocked_mmsi.add(mmsi)
    
    # Remove from active vessels if present
    if mmsi in active_vessels:
        del active_vessels[mmsi]
        logger.info(f"Removed blocked vessel {mmsi} from active vessels")
    
    logger.info(f"Blocked MMSI {mmsi}: {reason}")
    return {"success": True, "mmsi": mmsi}

@api_router.delete("/blocked-mmsi/{mmsi}")
async def remove_blocked_mmsi(mmsi: str):
    """Remove an MMSI from the block list."""
    global user_blocked_mmsi
    
    # Remove from database
    result = await db.blocked_mmsi.delete_one({"mmsi": mmsi})
    
    # Remove from in-memory set
    user_blocked_mmsi.discard(mmsi)
    
    if result.deleted_count > 0:
        logger.info(f"Unblocked MMSI {mmsi}")
        return {"success": True, "mmsi": mmsi}
    else:
        return {"success": False, "error": "MMSI not found in block list"}

async def load_blocked_mmsi():
    """Load user-blocked MMSIs from database on startup."""
    global user_blocked_mmsi
    blocked = await db.blocked_mmsi.find({}, {"_id": 0}).to_list(100)
    user_blocked_mmsi = {item["mmsi"] for item in blocked}
    logger.info(f"Loaded {len(user_blocked_mmsi)} blocked MMSIs from database")

def is_mmsi_blocked(mmsi: str) -> bool:
    """Check if an MMSI is blocked (system or user)."""
    return mmsi in FILTERED_MMSI or mmsi in user_blocked_mmsi

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
                boat_name = msg.get("boat_name", "")
                
                global user_mmsi
                user_mmsi = mmsi
                
                try:
                    # Close existing connection
                    if ais_socket:
                        ais_socket.close()
                    
                    # Pre-populate user vessel in cache if we have their MMSI
                    # This ensures they show up even if their own AIS data isn't in the feed
                    if mmsi and boat_name:
                        vessel_static_cache[mmsi] = {
                            'name': boat_name,
                            'is_user': True
                        }
                        logger.info(f"Pre-cached user vessel: {mmsi} = {boat_name}")
                    
                    # Connect to AIS feed
                    ais_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    ais_socket.settimeout(5)
                    ais_socket.connect((ip, port))
                    ais_socket.setblocking(False)
                    connection_active = True
                    
                    await websocket.send_json({"type": "connected", "message": f"Connected to {ip}:{port}"})
                    
                    # Start reading AIS data
                    buffer = ""
                    gps_update_count = 0  # Track GPS updates for logging
                    
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
                                        
                                        # Broadcast raw line to debug subscribers
                                        if len(line.strip()) > 0:
                                            await broadcast_raw_line(line.strip())
                                        
                                        # Log raw data for debugging (first 100 chars)
                                        if len(line) > 5:
                                            logger.debug(f"Raw NMEA: {line[:100]}")
                                        
                                        # First try to parse as GPS (for user's own position)
                                        gps_data = parse_nmea_gps(line)
                                        if gps_data and user_mmsi:
                                            # Update user vessel from GPS data
                                            rm = estimate_river_mile(gps_data['lat'], gps_data['lon'])
                                            heading = determine_heading(gps_data['speed'], gps_data['course'])
                                            
                                            logger.info(f"GPS position for user {user_mmsi}: lat={gps_data['lat']:.4f}, lon={gps_data['lon']:.4f}, RM={rm:.1f}")
                                            
                                            # Get name from cache or settings
                                            vessel_name = boat_name
                                            if user_mmsi in vessel_static_cache:
                                                vessel_name = vessel_static_cache[user_mmsi].get('name', boat_name)
                                            
                                            vessel = VesselPosition(
                                                mmsi=user_mmsi,
                                                name=vessel_name,
                                                lat=gps_data['lat'],
                                                lon=gps_data['lon'],
                                                speed=gps_data['speed'],
                                                course=gps_data['course'],
                                                river_mile=rm,
                                                heading=heading,
                                                is_user_vessel=True,
                                                vessel_type='recreational',
                                            )
                                            
                                            active_vessels[user_mmsi] = vessel
                                            
                                            # Send update to client (throttle GPS updates)
                                            gps_update_count += 1
                                            if gps_update_count % 5 == 0:  # Send every 5th GPS update
                                                v_dict = vessel.model_dump()
                                                v_dict['timestamp'] = v_dict['timestamp'].isoformat()
                                                v_dict['source'] = 'GPS'
                                                await websocket.send_json({"type": "vessel_update", "vessel": v_dict})
                                            continue
                                        
                                        # Then try to parse as AIS
                                        vessel_data = parse_nmea_ais(line)
                                        
                                        if vessel_data and vessel_data.get('mmsi'):
                                            mmsi_parsed = vessel_data['mmsi']
                                            
                                            # Skip filtered/blocked MMSI (test beacons, user-blocked)
                                            if is_mmsi_blocked(mmsi_parsed):
                                                continue
                                            
                                            # Calculate river mile and heading
                                            rm = estimate_river_mile(vessel_data['lat'], vessel_data['lon'])
                                            heading = determine_heading(vessel_data['speed'], vessel_data['course'])
                                            
                                            # Preserve existing name if new data doesn't have one
                                            vessel_name = vessel_data.get('name', '')
                                            if not vessel_name and mmsi_parsed in active_vessels:
                                                vessel_name = active_vessels[mmsi_parsed].name
                                            
                                            # Determine if this is the user's vessel
                                            is_user = (mmsi_parsed == user_mmsi) or vessel_data.get('is_own_vessel', False)
                                            
                                            vessel = VesselPosition(
                                                mmsi=mmsi_parsed,
                                                name=vessel_name,
                                                lat=vessel_data['lat'],
                                                lon=vessel_data['lon'],
                                                speed=vessel_data['speed'],
                                                course=vessel_data['course'],
                                                river_mile=rm,
                                                heading=heading,
                                                is_user_vessel=is_user,
                                                vessel_type=vessel_data.get('vessel_type', 'unknown'),
                                                ship_type=vessel_data.get('ship_type'),
                                                length=vessel_data.get('length'),
                                                width=vessel_data.get('width'),
                                                draught=vessel_data.get('draught'),
                                                is_tow=vessel_data.get('is_tow', False),
                                                barge_count=vessel_data.get('barge_count'),
                                                tow_config=vessel_data.get('tow_config'),
                                                estimated_lockage_time=vessel_data.get('estimated_lockage_time'),
                                                # Additional AIS fields
                                                turn_rate=vessel_data.get('turn_rate'),
                                                nav_status=vessel_data.get('nav_status'),
                                                nav_status_text=vessel_data.get('nav_status_text'),
                                                destination=vessel_data.get('destination'),
                                                callsign=vessel_data.get('callsign'),
                                                imo=vessel_data.get('imo'),
                                                eta=vessel_data.get('eta'),
                                            )
                                            
                                            # If this is the user vessel, update user_mmsi if not set
                                            if vessel_data.get('is_own_vessel') and not user_mmsi:
                                                user_mmsi = mmsi_parsed
                                                logger.info(f"Auto-detected user vessel MMSI: {mmsi_parsed}")
                                            
                                            active_vessels[vessel.mmsi] = vessel
                                            
                                            # Track vessel passage through locks
                                            await track_vessel_lock_passage(vessel.model_dump())
                                            
                                            # Persist vessel name to database if we got one from AIS
                                            if vessel_data.get('name') and vessel_data.get('_persist_to_db'):
                                                try:
                                                    await db.vessel_names.update_one(
                                                        {"mmsi": mmsi_parsed},
                                                        {"$set": {
                                                            "mmsi": mmsi_parsed,
                                                            "name": vessel_data['name'],
                                                            "ship_type": vessel_data.get('ship_type'),
                                                            "source": "AIS",
                                                            "updated_at": datetime.now(timezone.utc).isoformat()
                                                        }},
                                                        upsert=True
                                                    )
                                                except Exception as e:
                                                    logger.error(f"Failed to persist vessel name to DB: {e}")
                                            
                                            # Send update to client
                                            v_dict = vessel.model_dump()
                                            v_dict['timestamp'] = v_dict['timestamp'].isoformat()
                                            v_dict['source'] = 'AIS'
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
    
    # Track vessel passage through locks
    await track_vessel_lock_passage(vessel.model_dump())
    
    v_dict = vessel.model_dump()
    v_dict['timestamp'] = v_dict['timestamp'].isoformat()
    return {"success": True, "vessel": v_dict}

@api_router.post("/demo/add-tow")
async def add_demo_tow(data: dict):
    """Add a demo tow with specific barge configuration for testing."""
    barge_count = data.get('barge_count', 6)
    
    vessel = VesselPosition(
        mmsi=data.get('mmsi', str(uuid.uuid4())[:9]),
        name=data.get('name', 'M/V TEST TOW'),
        lat=data.get('lat', 44.7),
        lon=data.get('lon', -92.8),
        speed=data.get('speed', 4),
        course=data.get('course', 0),
        vessel_type='towing',
        is_tow=True,
        barge_count=barge_count,
        tow_config=data.get('tow_config', '2x3'),
        length=data.get('length', 200),
        width=data.get('width', 22),
    )
    
    vessel.river_mile = estimate_river_mile(vessel.lat, vessel.lon)
    vessel.heading = determine_heading(vessel.speed, vessel.course)
    
    # Calculate lockage time based on barge count
    # Upper Mississippi locks are 600ft - >9 barges requires double lockage
    if barge_count:
        if barge_count <= 6:
            vessel.estimated_lockage_time = 30
        elif barge_count <= 9:
            vessel.estimated_lockage_time = 45
        else:
            # Double lockage required
            vessel.estimated_lockage_time = 90 + (barge_count - 9) * 5
    
    active_vessels[vessel.mmsi] = vessel
    v_dict = vessel.model_dump()
    v_dict['timestamp'] = v_dict['timestamp'].isoformat()
    return {"success": True, "vessel": v_dict}

@api_router.delete("/demo/clear-vessels")
async def clear_demo_vessels():
    """Clear all demo vessels."""
    active_vessels.clear()
    return {"success": True}

# Store raw data subscribers for broadcasting
raw_data_subscribers: set = set()

# WebSocket for raw NMEA data streaming (debug/diagnostic tool)
@app.websocket("/ws/raw")
async def websocket_raw(websocket: WebSocket):
    """
    WebSocket endpoint for streaming raw NMEA data for debugging.
    Clients connect here to see every line received from the AIS TCP feed.
    """
    await websocket.accept()
    raw_data_subscribers.add(websocket)
    logger.info(f"Raw data subscriber connected. Total subscribers: {len(raw_data_subscribers)}")
    
    try:
        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for any message from client (ping/pong or disconnect)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(data)
                
                if msg.get("action") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except asyncio.TimeoutError:
                # Send keepalive
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
        logger.info(f"Raw data subscriber removed. Total subscribers: {len(raw_data_subscribers)}")

async def broadcast_raw_line(line: str):
    """Broadcast a raw NMEA line to all subscribed clients."""
    if not raw_data_subscribers:
        return
    
    message = json.dumps({"type": "raw", "line": line})
    
    # Send to all subscribers, remove any that fail
    disconnected = set()
    for ws in raw_data_subscribers:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    
    # Clean up disconnected clients
    raw_data_subscribers.difference_update(disconnected)

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Load settings, blocked MMSIs, and vessel names from database on startup."""
    global user_mmsi
    
    # Load user MMSI from settings
    try:
        mmsi_setting = await db.settings.find_one({"key": "user_mmsi"})
        if mmsi_setting and mmsi_setting.get("value"):
            user_mmsi = mmsi_setting["value"]
            logger.info(f"Loaded user MMSI from settings: {user_mmsi}")
    except Exception as e:
        logger.error(f"Failed to load user MMSI: {e}")
    
    # Load blocked MMSIs
    await load_blocked_mmsi()
    
    # Load persisted vessel names (shared across all users)
    await load_vessel_names_from_db()

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
