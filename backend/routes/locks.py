# River Watch Backend - Lock Routes
# Lock information, status, lockage times, and traffic summaries
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import Dict, List
import logging

from config import LOCKS
from services.usace_service import get_cached_lock_status, fetch_usace_lock_status, get_usace_data_summary
from services.usgs_service import get_water_conditions_for_lock, format_water_conditions_for_display

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/locks", tags=["Locks"])


def get_db():
    """Get database reference."""
    from database import db
    return db


@router.get("")
async def get_locks():
    """Get list of all locks with basic info."""
    locks_list = []
    for lock_id, lock_data in LOCKS.items():
        locks_list.append({
            "lock_id": lock_id,
            "name": lock_data["name"],
            "river_mile": lock_data["river_mile"],
            "lat": lock_data.get("lat"),
            "lon": lock_data.get("lon"),
            "phone": lock_data.get("phone")
        })
    
    # Sort by river mile (descending - upstream first)
    locks_list.sort(key=lambda x: x["river_mile"], reverse=True)
    
    return locks_list


@router.get("/status")
async def get_all_lock_status():
    """Get current status for all locks."""
    status_data = get_cached_lock_status()
    
    if not status_data:
        # Fetch fresh data if cache is empty
        status_data = await fetch_usace_lock_status()
    
    result = []
    for lock_id, lock_info in LOCKS.items():
        status = status_data.get(lock_id, {})
        result.append({
            "lock_id": lock_id,
            "name": lock_info["name"],
            "river_mile": lock_info["river_mile"],
            "status": status.get("status", "unknown"),
            "upbound_queue": status.get("upbound_queue", 0),
            "downbound_queue": status.get("downbound_queue", 0),
            "total_queue": status.get("total_queue", 0),
            "last_update": status.get("last_update")
        })
    
    return result


@router.get("/{lock_id}/status")
async def get_lock_status(lock_id: str):
    """Get current status for a specific lock."""
    if lock_id not in LOCKS:
        raise HTTPException(status_code=404, detail=f"Lock {lock_id} not found")
    
    status_data = get_cached_lock_status(lock_id)
    lock_info = LOCKS[lock_id]
    
    if not status_data:
        # Try to fetch fresh data
        all_status = await fetch_usace_lock_status()
        status_data = all_status.get(lock_id, {})
    
    return {
        "lock_id": lock_id,
        "name": lock_info["name"],
        "river_mile": lock_info["river_mile"],
        "phone": lock_info.get("phone"),
        "status": status_data.get("status", "unknown"),
        "upbound_queue": status_data.get("upbound_queue", 0),
        "downbound_queue": status_data.get("downbound_queue", 0),
        "total_queue": status_data.get("total_queue", 0),
        "last_update": status_data.get("last_update")
    }


@router.get("/{lock_id}/details")
async def get_lock_details(lock_id: str):
    """Get detailed information for a specific lock including water conditions."""
    if lock_id not in LOCKS:
        raise HTTPException(status_code=404, detail=f"Lock {lock_id} not found")
    
    lock_info = LOCKS[lock_id]
    status_data = get_cached_lock_status(lock_id) or {}
    
    # Get water conditions
    water_data = await get_water_conditions_for_lock(lock_id)
    water_display = format_water_conditions_for_display(water_data)
    
    # Get lockage time averages from database
    db = get_db()
    lockage_stats = await db.lockage_averages.find_one({"lock_id": lock_id}, {"_id": 0})
    
    return {
        "lock_id": lock_id,
        "name": lock_info["name"],
        "river_mile": lock_info["river_mile"],
        "lat": lock_info.get("lat"),
        "lon": lock_info.get("lon"),
        "phone": lock_info.get("phone"),
        "status": status_data.get("status", "operational"),
        "queue": {
            "upbound": status_data.get("upbound_queue", 0),
            "downbound": status_data.get("downbound_queue", 0),
            "total": status_data.get("total_queue", 0)
        },
        "water_conditions": water_display,
        "lockage_times": lockage_stats,
        "last_update": datetime.now(timezone.utc).isoformat()
    }


@router.get("/lockage-times")
async def get_all_lockage_times():
    """Get average lockage times for all locks."""
    db = get_db()
    
    # Get from database or return baseline estimates
    cursor = db.lockage_averages.find({}, {"_id": 0})
    results = await cursor.to_list(length=100)
    
    # Create response with all locks
    lockage_times = []
    for lock_id in LOCKS.keys():
        # Find existing data or use baseline
        existing = next((r for r in results if r.get("lock_id") == lock_id), None)
        
        if existing:
            lockage_times.append(existing)
        else:
            # Baseline estimates
            lockage_times.append({
                "lock_id": lock_id,
                "avg_tow_lockage_minutes": 45,
                "avg_recreational_lockage_minutes": 15,
                "avg_tow_wait_minutes": 30,
                "avg_recreational_wait_minutes": 15,
                "sample_count": 0,
                "is_baseline": True
            })
    
    return lockage_times


@router.get("/{lock_id}/lockage-times")
async def get_lock_lockage_times(lock_id: str):
    """Get average lockage times for a specific lock."""
    if lock_id not in LOCKS:
        raise HTTPException(status_code=404, detail=f"Lock {lock_id} not found")
    
    db = get_db()
    result = await db.lockage_averages.find_one({"lock_id": lock_id}, {"_id": 0})
    
    if result:
        return result
    
    # Return baseline estimates
    return {
        "lock_id": lock_id,
        "avg_tow_lockage_minutes": 45,
        "avg_recreational_lockage_minutes": 15,
        "avg_tow_wait_minutes": 30,
        "avg_recreational_wait_minutes": 15,
        "sample_count": 0,
        "is_baseline": True
    }
