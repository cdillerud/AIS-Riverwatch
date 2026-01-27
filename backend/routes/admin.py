# River Watch Backend - Admin Routes
# User management, system stats, and admin-only operations
from fastapi import APIRouter, HTTPException, Request, Response
from datetime import datetime, timezone, timedelta
import uuid
import logging

from services.auth_service import hash_password, generate_session_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

# Super admin email - hardcoded for security
SUPER_ADMIN_EMAIL = "cdillerud@gmail.com"


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
    
    # Check for impersonation
    if session.get("impersonated_by"):
        original = await db.users.find_one({"user_id": session["impersonated_by"]}, {"_id": 0})
        if original:
            user["_impersonated_by"] = original.get("email")
    
    return user


async def require_admin(request: Request) -> dict:
    """Require admin privileges. Returns user or raises 403."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not user.get("is_admin") and not user.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return user


async def require_super_admin(request: Request) -> dict:
    """Require super admin privileges. Returns user or raises 403."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not user.get("is_super_admin") and user.get("email") != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Super admin access required")
    
    return user


@router.get("/stats")
async def admin_get_stats(request: Request):
    """Get system statistics for admin dashboard."""
    await require_admin(request)
    db = get_db()
    
    # User counts
    total_users = await db.users.count_documents({})
    vessel_owners = await db.users.count_documents({"account_type": "vessel_owner"})
    traffic_watchers = await db.users.count_documents({"account_type": "traffic_watch"})
    admins = await db.users.count_documents({"is_admin": True})
    
    # Active sessions (last 24 hours)
    yesterday = datetime.now(timezone.utc) - timedelta(hours=24)
    active_sessions = await db.user_sessions.count_documents({
        "created_at": {"$gte": yesterday.isoformat()}
    })
    
    # Vessel counts
    users_with_vessels = await db.users.count_documents({"vessels.0": {"$exists": True}})
    
    # Recent registrations (last 7 days)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_registrations = await db.users.count_documents({
        "created_at": {"$gte": week_ago.isoformat()}
    })
    
    return {
        "total_users": total_users,
        "vessel_owners": vessel_owners,
        "traffic_watchers": traffic_watchers,
        "admins": admins,
        "active_sessions_24h": active_sessions,
        "users_with_vessels": users_with_vessels,
        "recent_registrations_7d": recent_registrations,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/users")
async def admin_get_users(request: Request, search: str = None, limit: int = 50, skip: int = 0):
    """Get list of users. Supports search by email or name."""
    await require_admin(request)
    db = get_db()
    
    query = {}
    if search:
        query = {
            "$or": [
                {"email": {"$regex": search, "$options": "i"}},
                {"name": {"$regex": search, "$options": "i"}}
            ]
        }
    
    cursor = db.users.find(query, {"_id": 0, "password_hash": 0}).skip(skip).limit(limit)
    users = await cursor.to_list(length=limit)
    
    total = await db.users.count_documents(query)
    
    return {
        "users": users,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.post("/users")
async def admin_create_user(request: Request):
    """Create a new user (admin only)."""
    await require_admin(request)
    db = get_db()
    
    body = await request.json()
    email = body.get("email")
    name = body.get("name", "")
    password = body.get("password")
    is_admin = body.get("is_admin", False)
    account_type = body.get("account_type", "vessel_owner")
    
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    
    # Check if email exists
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    user_doc = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "password_hash": hash_password(password) if password else None,
        "picture": None,
        "fleet_name": None,
        "vessels": [],
        "settings": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "auth_provider": "email" if password else "admin_created",
        "is_admin": is_admin,
        "account_type": account_type
    }
    
    await db.users.insert_one(user_doc)
    logger.info(f"[ADMIN] Created user: {email} ({user_id})")
    
    user_doc.pop("password_hash", None)
    user_doc.pop("_id", None)
    
    return {"success": True, "user": user_doc}


@router.delete("/users/{user_id}")
async def admin_delete_user(request: Request, user_id: str):
    """Delete a user (admin only)."""
    admin = await require_admin(request)
    db = get_db()
    
    # Can't delete yourself
    if admin["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    # Get user to check if super admin
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.get("email") == SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Cannot delete super admin")
    
    # Delete user and their sessions
    await db.users.delete_one({"user_id": user_id})
    await db.user_sessions.delete_many({"user_id": user_id})
    
    logger.info(f"[ADMIN] Deleted user: {user.get('email')} ({user_id})")
    
    return {"success": True}


@router.put("/users/{user_id}")
async def admin_update_user(request: Request, user_id: str):
    """Update a user's details (admin only)."""
    await require_admin(request)
    db = get_db()
    
    body = await request.json()
    update_fields = {}
    
    # Allowed fields to update
    if "name" in body:
        update_fields["name"] = body["name"]
    if "email" in body:
        update_fields["email"] = body["email"]
    if "account_type" in body:
        update_fields["account_type"] = body["account_type"]
    if "is_admin" in body:
        update_fields["is_admin"] = body["is_admin"]
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$set": update_fields}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    logger.info(f"[ADMIN] Updated user {user_id}: {list(update_fields.keys())}")
    
    return {"success": True}


@router.post("/users/{user_id}/promote")
async def admin_promote_user(request: Request, user_id: str):
    """Promote a user to admin (super admin only)."""
    await require_super_admin(request)
    db = get_db()
    
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"is_admin": True}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    logger.info(f"[ADMIN] Promoted user to admin: {user_id}")
    
    return {"success": True}


@router.post("/users/{user_id}/demote")
async def admin_demote_user(request: Request, user_id: str):
    """Demote a user from admin (super admin only)."""
    admin = await require_super_admin(request)
    db = get_db()
    
    # Can't demote yourself
    if admin["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot demote yourself")
    
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"is_admin": False}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    logger.info(f"[ADMIN] Demoted user from admin: {user_id}")
    
    return {"success": True}


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(request: Request, user_id: str):
    """Reset a user's password (admin only)."""
    await require_admin(request)
    db = get_db()
    
    body = await request.json()
    new_password = body.get("password")
    
    if not new_password:
        raise HTTPException(status_code=400, detail="Password is required")
    
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"password_hash": hash_password(new_password)}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    logger.info(f"[ADMIN] Reset password for user: {user_id}")
    
    return {"success": True}


@router.post("/impersonate/{user_id}")
async def admin_impersonate_user(request: Request, response: Response, user_id: str):
    """Impersonate a user (super admin only). Creates a new session as that user."""
    admin = await require_super_admin(request)
    db = get_db()
    
    # Get target user
    target_user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Create impersonation session
    session_token = generate_session_token()
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=2),  # Shorter for impersonation
        "created_at": datetime.now(timezone.utc),
        "impersonated_by": admin["user_id"]
    })
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=2*60*60  # 2 hours
    )
    
    logger.info(f"[ADMIN] {admin['email']} impersonating {target_user['email']}")
    
    target_user.pop("password_hash", None)
    return {"success": True, "user": target_user, "impersonating": True}


@router.delete("/impersonate")
async def admin_stop_impersonation(request: Request, response: Response):
    """Stop impersonation and return to admin session."""
    db = get_db()
    session_token = request.cookies.get("session_token")
    
    if session_token:
        session = await db.user_sessions.find_one({"session_token": session_token})
        if session and session.get("impersonated_by"):
            # Delete impersonation session
            await db.user_sessions.delete_one({"session_token": session_token})
            
            # Create new session for original admin
            admin_user_id = session["impersonated_by"]
            new_token = generate_session_token()
            
            await db.user_sessions.insert_one({
                "user_id": admin_user_id,
                "session_token": new_token,
                "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
                "created_at": datetime.now(timezone.utc)
            })
            
            response.set_cookie(
                key="session_token",
                value=new_token,
                httponly=True,
                secure=True,
                samesite="none",
                path="/",
                max_age=7*24*60*60
            )
            
            admin = await db.users.find_one({"user_id": admin_user_id}, {"_id": 0, "password_hash": 0})
            return {"success": True, "user": admin}
    
    return {"success": False, "detail": "Not impersonating anyone"}


@router.get("/vessels")
async def admin_get_all_vessels(request: Request):
    """Get all vessels across all users."""
    await require_admin(request)
    db = get_db()
    
    pipeline = [
        {"$unwind": "$vessels"},
        {"$project": {
            "_id": 0,
            "owner_email": "$email",
            "owner_name": "$name",
            "mmsi": "$vessels.mmsi",
            "boat_name": "$vessels.boat_name",
            "is_primary": "$vessels.is_primary",
            "added_at": "$vessels.added_at"
        }}
    ]
    
    cursor = db.users.aggregate(pipeline)
    vessels = await cursor.to_list(length=500)
    
    return {"vessels": vessels, "total": len(vessels)}
