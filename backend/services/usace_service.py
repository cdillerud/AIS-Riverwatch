# River Watch Backend - USACE Service
# Handles fetching lock queue data, lock status, and vessel info from USACE
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from typing import Dict, Optional, List
from datetime import datetime, timezone
import re

from config import LOCKS, UPPER_MISS_LOCKS

logger = logging.getLogger(__name__)

# In-memory cache for USACE data
usace_lock_queue_data: Dict[str, dict] = {}  # Keyed by MMSI
usace_lock_queue_by_name: Dict[str, dict] = {}  # Keyed by vessel name (lowercase)
usace_lock_status_cache: Dict[str, dict] = {}  # Keyed by lock_id


async def fetch_usace_lock_queue_data() -> Dict[str, dict]:
    """
    Fetch lock queue data from USACE for all Upper Mississippi locks.
    Returns dict keyed by MMSI with vessel info including barge counts.
    """
    global usace_lock_queue_data, usace_lock_queue_by_name
    
    all_vessels = {}
    vessels_by_name = {}
    
    async with httpx.AsyncClient() as client:
        for lock_num in UPPER_MISS_LOCKS:
            try:
                url = f"https://ndc.ops.usace.army.mil/ords/lockqueue_xml?in_river=MI&in_lock={lock_num}"
                response = await client.get(url, timeout=10.0)
                
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.text, 'xml')
                
                for vessel in soup.find_all('vessel'):
                    try:
                        mmsi = vessel.find('mmsi')
                        mmsi_val = mmsi.text.strip() if mmsi and mmsi.text else None
                        
                        name = vessel.find('vessel_name')
                        name_val = name.text.strip() if name and name.text else None
                        
                        if not name_val:
                            continue
                        
                        barge_count = vessel.find('barge_count')
                        barge_count_val = int(barge_count.text) if barge_count and barge_count.text else 0
                        
                        status = vessel.find('status')
                        status_val = status.text.strip() if status and status.text else None
                        
                        direction = vessel.find('direction')
                        direction_val = direction.text.strip() if direction and direction.text else None
                        
                        vessel_data = {
                            "mmsi": mmsi_val,
                            "name": name_val,
                            "barge_count": barge_count_val,
                            "is_tow": barge_count_val > 0,
                            "usace_status": status_val,
                            "usace_direction": direction_val,
                            "usace_lock": f"lock_{lock_num.lower()}",
                            "usace_source": True,
                            "last_usace_update": datetime.now(timezone.utc).isoformat()
                        }
                        
                        if mmsi_val:
                            all_vessels[mmsi_val] = vessel_data
                        
                        if name_val:
                            vessels_by_name[name_val.lower()] = vessel_data
                            
                    except Exception as e:
                        logger.error(f"Error parsing vessel in lock {lock_num}: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error fetching lock {lock_num} queue: {e}")
                continue
    
    usace_lock_queue_data = all_vessels
    usace_lock_queue_by_name = vessels_by_name
    
    logger.info(f"Fetched USACE lock queue data: {len(all_vessels)} by MMSI, {len(vessels_by_name)} by name")
    
    return all_vessels


def get_usace_vessel_info(mmsi: str = None, vessel_name: str = None) -> Optional[dict]:
    """
    Look up a vessel in the USACE lock queue data.
    Can search by MMSI or vessel name (case-insensitive).
    """
    if mmsi and mmsi in usace_lock_queue_data:
        return usace_lock_queue_data[mmsi]
    
    if vessel_name:
        name_lower = vessel_name.lower()
        if name_lower in usace_lock_queue_by_name:
            return usace_lock_queue_by_name[name_lower]
        
        # Fuzzy match - check if vessel name contains or is contained by any USACE name
        for usace_name, data in usace_lock_queue_by_name.items():
            if name_lower in usace_name or usace_name in name_lower:
                return data
    
    return None


async def fetch_usace_lock_status() -> Dict[str, dict]:
    """
    Fetch current status for all locks from USACE.
    Returns operational status, queue counts, and wait times.
    """
    global usace_lock_status_cache
    
    status_data = {}
    
    async with httpx.AsyncClient() as client:
        for lock_num in UPPER_MISS_LOCKS:
            lock_id = f"lock_{lock_num.lower()}"
            try:
                url = f"https://ndc.ops.usace.army.mil/ords/lockqueue_xml?in_river=MI&in_lock={lock_num}"
                response = await client.get(url, timeout=10.0)
                
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.text, 'xml')
                
                # Count vessels in queue
                vessels = soup.find_all('vessel')
                upbound_count = 0
                downbound_count = 0
                
                for vessel in vessels:
                    direction = vessel.find('direction')
                    if direction and direction.text:
                        if 'up' in direction.text.lower():
                            upbound_count += 1
                        elif 'down' in direction.text.lower():
                            downbound_count += 1
                
                # Get lock info from our config
                lock_info = LOCKS.get(lock_id, {})
                
                status_data[lock_id] = {
                    "lock_id": lock_id,
                    "lock_name": lock_info.get("name", f"Lock {lock_num}"),
                    "river_mile": lock_info.get("river_mile"),
                    "status": "operational",  # Default, would need additional API for closures
                    "upbound_queue": upbound_count,
                    "downbound_queue": downbound_count,
                    "total_queue": upbound_count + downbound_count,
                    "last_update": datetime.now(timezone.utc).isoformat()
                }
                
            except Exception as e:
                logger.error(f"Error fetching lock {lock_num} status: {e}")
                continue
    
    usace_lock_status_cache = status_data
    return status_data


def get_cached_lock_status(lock_id: str = None) -> Optional[dict]:
    """Get cached lock status for one or all locks."""
    if lock_id:
        return usace_lock_status_cache.get(lock_id)
    return usace_lock_status_cache


def estimate_tow_info(vessel_data: dict) -> dict:
    """
    Estimate tow configuration from available data.
    Uses ship type and other indicators to estimate barge count if not from USACE.
    """
    result = {
        "is_tow": False,
        "barge_count": 0,
        "tow_config": None,
        "estimated_lockage_time": None,
        "is_double_lockage": False
    }
    
    ship_type = vessel_data.get("ship_type")
    name = vessel_data.get("name", "").upper()
    
    # Check if vessel is a tow
    if ship_type in [31, 32, 52]:  # Towing vessels
        result["is_tow"] = True
    elif "M/V" in name or "TUG" in name or "TOW" in name:
        result["is_tow"] = True
    
    # Get barge count from USACE if available
    usace_info = get_usace_vessel_info(
        mmsi=vessel_data.get("mmsi"),
        vessel_name=vessel_data.get("name")
    )
    
    if usace_info:
        result["barge_count"] = usace_info.get("barge_count", 0)
        result["is_tow"] = usace_info.get("is_tow", result["is_tow"])
        result["usace_status"] = usace_info.get("usace_status")
        result["usace_lock"] = usace_info.get("usace_lock")
    
    # Estimate lockage time based on barge count
    barge_count = result["barge_count"]
    if barge_count > 0:
        if barge_count <= 6:
            result["estimated_lockage_time"] = 45  # Single lockage ~45 min
            result["tow_config"] = f"{barge_count} barges (single cut)"
        elif barge_count <= 9:
            result["estimated_lockage_time"] = 60
            result["tow_config"] = f"{barge_count} barges (tight fit)"
        else:
            result["estimated_lockage_time"] = 90  # Double lockage ~90 min
            result["is_double_lockage"] = True
            result["tow_config"] = f"{barge_count} barges (double cut)"
    elif result["is_tow"]:
        result["estimated_lockage_time"] = 30  # Light boat
        result["tow_config"] = "Light boat (no barges)"
    
    return result


def get_usace_data_summary() -> dict:
    """Get summary of cached USACE data."""
    return {
        "vessels_by_mmsi": len(usace_lock_queue_data),
        "vessels_by_name": len(usace_lock_queue_by_name),
        "locks_with_status": len(usace_lock_status_cache),
        "lock_statuses": usace_lock_status_cache
    }
