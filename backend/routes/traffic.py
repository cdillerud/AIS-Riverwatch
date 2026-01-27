# River Watch Backend - Traffic Routes
# Traffic summary, watch points, and observer mode endpoints
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from typing import Dict, Optional
import logging

from config import LOCKS
from services.usace_service import get_cached_lock_status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Traffic"])


def get_db():
    """Get database reference."""
    from database import db
    return db


def get_active_vessels():
    """Get active vessels from main server module."""
    try:
        from server import active_vessels
        return active_vessels
    except ImportError:
        return {}


async def get_current_user(request: Request):
    """Get the current authenticated user from session token."""
    db = get_db()
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        return None
    
    session = await db.user_sessions.find_one({"session_token": session_token})
    if not session:
        return None
    
    expires_at = session.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        if expires_at < datetime.now(timezone.utc):
            await db.user_sessions.delete_one({"session_token": session_token})
            return None
    
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    return user


@router.get("/traffic-summary/{lock_id}")
async def get_traffic_summary(lock_id: str):
    """
    Get traffic summary for a lock - vessels approaching, recent lockages, queue info.
    Used by Traffic Watch mode.
    """
    if lock_id not in LOCKS:
        raise HTTPException(status_code=404, detail=f"Lock {lock_id} not found")
    
    lock_info = LOCKS[lock_id]
    lock_rm = lock_info["river_mile"]
    
    # Get active vessels
    active_vessels = get_active_vessels()
    
    # Count vessels by direction relative to lock
    northbound = []  # Heading upstream (toward higher RM)
    southbound = []  # Heading downstream (toward lower RM)
    near_lock = []   # Within 10 miles of lock
    
    for mmsi, vessel in active_vessels.items():
        rm = vessel.get("river_mile")
        if not rm:
            continue
        
        heading = vessel.get("heading_direction", "unknown")
        distance = abs(rm - lock_rm)
        
        vessel_summary = {
            "mmsi": mmsi,
            "name": vessel.get("name", f"MMSI {mmsi}"),
            "river_mile": rm,
            "speed": vessel.get("speed", 0),
            "heading": heading,
            "distance_to_lock": round(distance, 1),
            "is_tow": vessel.get("is_tow", False),
            "barge_count": vessel.get("barge_count", 0)
        }
        
        # Near lock (within 10 miles)
        if distance <= 10:
            near_lock.append(vessel_summary)
        
        # Determine if approaching this lock
        if heading == "upstream" and rm < lock_rm:
            northbound.append(vessel_summary)
        elif heading == "downstream" and rm > lock_rm:
            southbound.append(vessel_summary)
    
    # Sort by distance to lock
    near_lock.sort(key=lambda x: x["distance_to_lock"])
    northbound.sort(key=lambda x: x["distance_to_lock"])
    southbound.sort(key=lambda x: x["distance_to_lock"])
    
    # Get lock status
    lock_status = get_cached_lock_status(lock_id) or {}
    
    # Get recent lockages from database
    db = get_db()
    recent_lockages = []
    try:
        cursor = db.lockage_history.find(
            {"lock_id": lock_id},
            {"_id": 0}
        ).sort("completed_at", -1).limit(10)
        recent_lockages = await cursor.to_list(length=10)
    except Exception as e:
        logger.error(f"Error fetching recent lockages: {e}")
    
    return {
        "lock_id": lock_id,
        "lock_name": lock_info["name"],
        "lock_river_mile": lock_rm,
        "summary": {
            "northbound_count": len(northbound),
            "southbound_count": len(southbound),
            "near_lock_count": len(near_lock),
            "queue_upbound": lock_status.get("upbound_queue", 0),
            "queue_downbound": lock_status.get("downbound_queue", 0)
        },
        "near_lock": near_lock[:5],  # Top 5 nearest
        "northbound": northbound[:10],
        "southbound": southbound[:10],
        "recent_lockages": recent_lockages,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.post("/user/watch-point")
async def set_watch_point(request: Request):
    """Set user's watch point for traffic monitoring."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db = get_db()
    body = await request.json()
    
    watch_point = {
        "river_mile": body.get("river_mile"),
        "name": body.get("name", ""),
        "set_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"watch_point": watch_point}}
    )
    
    return {"success": True, "watch_point": watch_point}


@router.get("/user/watch-point")
async def get_watch_point(request: Request):
    """Get user's current watch point."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {"watch_point": user.get("watch_point")}


@router.post("/user/account-type")
async def update_account_type(request: Request):
    """Update user's account type (vessel_owner or traffic_watch)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db = get_db()
    body = await request.json()
    account_type = body.get("account_type")
    
    if account_type not in ["vessel_owner", "traffic_watch"]:
        raise HTTPException(status_code=400, detail="Invalid account type")
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"account_type": account_type}}
    )
    
    logger.info(f"[USER] {user['email']} set account type to: {account_type}")
    
    return {"success": True, "account_type": account_type}


@router.get("/user/account-type")
async def get_account_type(request: Request):
    """Get user's current account type."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {"account_type": user.get("account_type", "vessel_owner")}
