# River Watch Backend - Authentication Routes
from fastapi import APIRouter, HTTPException, Request, Response
from datetime import datetime, timezone, timedelta
import uuid
import logging
import httpx

from models.auth import UserRegistration, UserLogin, VesselAdd
from services.auth_service import hash_password, verify_password, generate_session_token

logger = logging.getLogger(__name__)

# Router will be included in main app with /api prefix
router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_db():
    """Get database reference - imported from main server."""
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


@router.post("/register")
async def register_user(data: UserRegistration, response: Response):
    """Register a new user with email/password."""
    db = get_db()
    
    # Check if email already exists
    existing = await db.users.find_one({"email": data.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    user_doc = {
        "user_id": user_id,
        "email": data.email,
        "name": data.name,
        "password_hash": hash_password(data.password),
        "picture": None,
        "fleet_name": None,
        "vessels": [],
        "settings": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "auth_provider": "email"
    }
    
    await db.users.insert_one(user_doc)
    logger.info(f"[AUTH] New user registered: {data.email} ({user_id})")
    
    # Create session
    session_token = generate_session_token()
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": datetime.now(timezone.utc)
    })
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7*24*60*60
    )
    
    # Return user (without password)
    user_doc.pop("password_hash", None)
    user_doc.pop("_id", None)
    
    return {"success": True, "user": user_doc}


@router.post("/login")
async def login_user(data: UserLogin, response: Response):
    """Login with email/password."""
    db = get_db()
    
    # Find user
    user_doc = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Verify password
    if not user_doc.get("password_hash") or not verify_password(data.password, user_doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    logger.info(f"[AUTH] User logged in: {data.email}")
    
    # Create session
    session_token = generate_session_token()
    await db.user_sessions.insert_one({
        "user_id": user_doc["user_id"],
        "session_token": session_token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": datetime.now(timezone.utc)
    })
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7*24*60*60
    )
    
    # Return user (without password)
    user_doc.pop("password_hash", None)
    
    return {"success": True, "user": user_doc}


@router.post("/google/session")
async def google_auth_session(request: Request, response: Response):
    """Exchange Google OAuth session_id for user session."""
    db = get_db()
    body = await request.json()
    session_id = body.get("session_id")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
    # Exchange session_id for user data from Emergent Auth
    async with httpx.AsyncClient() as client:
        try:
            auth_response = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id},
                timeout=10.0
            )
            
            if auth_response.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid session_id")
            
            google_data = auth_response.json()
        except httpx.RequestError as e:
            logger.error(f"[AUTH] Google auth error: {e}")
            raise HTTPException(status_code=500, detail="Authentication service unavailable")
    
    # Find or create user
    email = google_data.get("email")
    existing_user = await db.users.find_one({"email": email}, {"_id": 0})
    
    if existing_user:
        user_id = existing_user["user_id"]
        # Update user info from Google
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "name": google_data.get("name", existing_user.get("name")),
                "picture": google_data.get("picture"),
                "google_id": google_data.get("id"),
                "last_login": datetime.now(timezone.utc).isoformat()
            }}
        )
        user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        logger.info(f"[AUTH] Google user logged in: {email}")
    else:
        # Create new user
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user_doc = {
            "user_id": user_id,
            "email": email,
            "name": google_data.get("name", ""),
            "picture": google_data.get("picture"),
            "google_id": google_data.get("id"),
            "fleet_name": None,
            "vessels": [],
            "settings": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "auth_provider": "google"
        }
        await db.users.insert_one(user_doc)
        logger.info(f"[AUTH] New Google user created: {email} ({user_id})")
    
    # Create session
    session_token = generate_session_token()
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": datetime.now(timezone.utc)
    })
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7*24*60*60
    )
    
    # Return user (without sensitive data)
    user_doc.pop("password_hash", None)
    user_doc.pop("_id", None)
    
    return {"success": True, "user": user_doc}


@router.get("/me")
async def get_current_user_info(request: Request):
    """Get current authenticated user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Remove sensitive fields
    user.pop("password_hash", None)
    user.pop("_id", None)
    
    return user


@router.post("/logout")
async def logout_user(request: Request, response: Response):
    """Logout current user."""
    db = get_db()
    session_token = request.cookies.get("session_token")
    
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    
    response.delete_cookie(key="session_token", path="/")
    
    return {"success": True}
