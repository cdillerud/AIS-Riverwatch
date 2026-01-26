# River Watch Backend - User Routes (Fleet/Vessel Management)
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import logging

from models.auth import VesselAdd

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["User"])


def get_db():
    """Get database reference."""
    from database import db
    return db


async def get_current_user(request: Request):
    """Get the current authenticated user from session token."""
    db = get_db()
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        return None
    
    # Look up session
    session = await db.user_sessions.find_one({"session_token": session_token})
    if not session:
        return None
    
    # Check expiry
    expires_at = session.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        if expires_at < datetime.now(timezone.utc):
            await db.user_sessions.delete_one({"session_token": session_token})
            return None
    
    # Get user
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    return user


@router.get("/vessels")
async def get_user_vessels(request: Request):
    """Get all vessels for current user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {"vessels": user.get("vessels", [])}


@router.post("/vessels")
async def add_user_vessel(request: Request, vessel: VesselAdd):
    """Add a vessel to user's fleet."""
    db = get_db()
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check if MMSI is already claimed by another user
    existing_claim = await db.users.find_one(
        {
            "user_id": {"$ne": user["user_id"]},
            "vessels.mmsi": vessel.mmsi
        },
        {"_id": 0, "email": 1}
    )
    if existing_claim:
        raise HTTPException(
            status_code=400, 
            detail=f"MMSI {vessel.mmsi} is already claimed by another user"
        )
    
    # Check if user already has this MMSI
    existing_vessels = user.get("vessels", [])
    if any(v["mmsi"] == vessel.mmsi for v in existing_vessels):
        raise HTTPException(status_code=400, detail="Vessel already in your fleet")
    
    # If this is primary, unset other primaries
    if vessel.is_primary:
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"vessels.$[].is_primary": False}}
        )
    
    # Add vessel
    vessel_doc = {
        "mmsi": vessel.mmsi,
        "boat_name": vessel.boat_name,
        "is_primary": vessel.is_primary,
        "added_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$push": {"vessels": vessel_doc}}
    )
    
    # Migrate any existing settings for this MMSI to user
    existing_settings = await db.user_settings.find_one({"mmsi": vessel.mmsi}, {"_id": 0})
    if existing_settings:
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {f"vessel_settings.{vessel.mmsi}": existing_settings.get("settings", {})}}
        )
    
    logger.info(f"[USER:{user['user_id']}] Added vessel: {vessel.mmsi} ({vessel.boat_name})")
    
    return {"success": True, "vessel": vessel_doc}


@router.delete("/vessels/{mmsi}")
async def remove_user_vessel(request: Request, mmsi: str):
    """Remove a vessel from user's fleet."""
    db = get_db()
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$pull": {"vessels": {"mmsi": mmsi}}}
    )
    
    logger.info(f"[USER:{user['user_id']}] Removed vessel: {mmsi}")
    
    return {"success": True}


@router.put("/vessels/{mmsi}/primary")
async def set_primary_vessel(request: Request, mmsi: str):
    """Set a vessel as the primary vessel."""
    db = get_db()
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Unset all primaries
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"vessels.$[].is_primary": False}}
    )
    
    # Set this one as primary
    await db.users.update_one(
        {"user_id": user["user_id"], "vessels.mmsi": mmsi},
        {"$set": {"vessels.$.is_primary": True}}
    )
    
    return {"success": True}


@router.put("/profile")
async def update_user_profile(request: Request):
    """Update user profile (name, fleet name)."""
    db = get_db()
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    body = await request.json()
    update_fields = {}
    
    if "name" in body:
        update_fields["name"] = body["name"]
    if "fleet_name" in body:
        update_fields["fleet_name"] = body["fleet_name"]
    
    if update_fields:
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": update_fields}
        )
    
    return {"success": True}


@router.put("/settings")
async def update_user_settings(request: Request):
    """Update user settings."""
    db = get_db()
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    body = await request.json()
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"settings": body}}
    )
    
    return {"success": True}
