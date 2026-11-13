# River Watch Backend - Version 2026-01-27
# SESSION ISOLATION: All user data is strictly isolated by MMSI (session ID)
# USER AUTHENTICATION: Email/password + Google OAuth
#
# ARCHITECTURE NOTE:
# This file is being incrementally refactored. New modular structure:
#   - /backend/config.py                    - Configuration and constants ✓
#   - /backend/database.py                  - Database connection ✓
#   - /backend/models/                      - Pydantic models
#   - /backend/services/                    - Business logic
#       - auth_service.py                   - Password hashing, session gen ✓
#       - navigation_service.py             - River mile, ETA, speed calc ✓
#       - usace_service.py                  - USACE lock queue/status ✓
#       - usgs_service.py                   - Water conditions ✓
#       - ais_parser.py                     - NMEA/AIS parsing ✓ (NEW)
#   - /backend/routes/                      - API route handlers
#       - admin.py                          - Admin endpoints ✓
#       - locks.py                          - Lock info endpoints ✓
#       - traffic.py                        - Traffic watch endpoints ✓
#       - water.py                          - Water conditions endpoints ✓
#   - /backend/websocket/                   - WebSocket handlers (TODO)
#
# NEW: Service modules imported and available as _function_name
# For new features, use the modular structure. See /backend/README.md

from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request, Response, Cookie, Depends
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne
import math
import os
import logging
import asyncio
import socket
from collections import deque
from email.message import EmailMessage
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict
import uuid
from datetime import datetime, timezone, timedelta
import json
import httpx
from bs4 import BeautifulSoup
import re
import hashlib
import secrets

from services import river_geometry as _river_geo
from services.google_auth import GoogleAuthError, google_client_id, verify_google_credential
from services import aisstream as _aisstream
# Identify RiverWatch on outbound requests. USACE sites answer 403 to the
# default python-httpx User-Agent (lock status never loaded because of it),
# and to any User-Agent containing a URL - keep this one URL-free.
RIVERWATCH_UA = "RiverWatch/1.0 (Upper Mississippi lock planning)"
OUTBOUND_HEADERS = {"User-Agent": RIVERWATCH_UA}
from services import usace_lockages as _usace_lockages
from services import lock_board as _lock_board
from services import transits as _transits
from services import live_arrivals as _live_arrivals
from services import trip_timeline as _trip_timeline
from services import calibration as _calibration
from services.db_indexes import ensure_indexes as _ensure_indexes
from services import feed_health as _health
from services import wait_log as _wait_log
from services import season_log as _season_log
from services import marinas as _marinas
from services import user_settings as _user_settings
from services import live_ais as _live_ais
from services import api_access as _api_access
from services import user_sim as _user_sim
from services import home_berth as _home_berth
from services import arrival_learning as _arrival_learning
from services import traffic_report as _traffic_report
from services import report_mailer as _report_mailer
_aisstream_task = None
# Import from new modular structure (for reusable logic)
from config import LOCKS, RIVER_MILE_POINTS, get_cors_origins, USGS_GAUGES, USGS_PARAMS, FLOOD_STAGES, LOCK_GAUGES, UPPER_MISS_LOCKS, is_on_upper_mississippi
from services.navigation_service import (
    estimate_river_mile as _estimate_river_mile,
    river_mile_to_coords as _river_mile_to_coords,
    determine_heading as _determine_heading,
    calculate_eta_to_lock as _calculate_eta_to_lock,
    calculate_required_speed as _calculate_required_speed
)

# Import new service modules (refactored code)
from services.usgs_service import (
    get_water_conditions_for_lock as _get_water_conditions_for_lock,
    format_water_conditions_for_display as _format_water_conditions
)
from services.ais_parser import (
    NmeaFragmentAssembler,
    clean_sog,
    clean_cog,
    parse_nmea_gps as _parse_nmea_gps,
    NAV_STATUS as _NAV_STATUS,
    vessel_static_cache as _vessel_static_cache,
    get_cached_vessel_name,
    set_cached_vessel_info
)
# Import new performance services
from services.vessel_service import (
    vessel_cache,
    prepare_vessel_for_output as _prepare_vessel_for_output,
    estimate_river_mile as _estimate_rm_fast,
    determine_heading as _determine_heading_fast,
    calculate_eta_to_lock as _calc_eta_fast,
    calculate_required_speed as _calc_speed_fast
)
from services.cache_service import (
    usace_cache as usace_ttl_cache,
    usgs_cache as usgs_ttl_cache,
    get_cache_stats
)
from services.http_client import (
    get_http_client,
    close_http_client,
    fetch_with_retry
)
# Import WebSocket handlers (for reference, not actively replacing yet)
# These will be used incrementally as we refactor
from services.websocket_handlers import (
    broadcast_raw_line as _ws_broadcast_raw_line,
    broadcast_demo_nmea as _ws_broadcast_demo_nmea,
    get_raw_subscriber_count as _ws_get_raw_subscriber_count
)
# Import repositories
from repositories import RepositoryFactory


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Initialize repository factory for cleaner database access
repos = RepositoryFactory(db)

# Helper function to persist vessel sighting with USACE data
HISTORY_INTERVAL = timedelta(minutes=10)
_last_history_write: Dict[tuple, datetime] = {}
SIGHTING_INTERVAL = timedelta(seconds=30)
_last_sighting_write: Dict[str, tuple] = {}


async def persist_vessel_sighting(vessel_data: dict):
    """
    Persist vessel sighting to database for historical analysis.
    Only saves vessels with meaningful data (position or USACE info).
    """
    if not vessel_data or not vessel_data.get('mmsi'):
        return
    
    mmsi = vessel_data['mmsi']
    # Simulated demo boats never go into real vessel history / statistics
    if _is_demo_vessel(vessel_data, str(mmsi)):
        return
    asyncio.create_task(_record_track_point(vessel_data))
    
    # Build the sighting record
    sighting = {
        "mmsi": mmsi,
        "timestamp": datetime.now(timezone.utc),
        "name": vessel_data.get('name'),
        "lat": vessel_data.get('lat'),
        "lon": vessel_data.get('lon'),
        "river_mile": vessel_data.get('river_mile'),
        "speed": vessel_data.get('speed'),
        "course": vessel_data.get('course'),
        "heading_direction": vessel_data.get('heading_direction'),
        "ship_type": vessel_data.get('ship_type'),
        "last_ais_checkin": vessel_data.get('last_ais_checkin') or vessel_data.get('timestamp'),
        # USACE data
        "usace_source": vessel_data.get('usace_source', False),
        "barge_count": vessel_data.get('barge_count'),
        "is_tow": vessel_data.get('is_tow', False),
        "tow_config": vessel_data.get('tow_config'),
        "usace_lock": vessel_data.get('usace_lock'),
        "usace_status": vessel_data.get('usace_status'),
        "estimated_lockage_time": vessel_data.get('estimated_lockage_time'),
        "is_double_lockage": vessel_data.get('is_double_lockage', False),
    }
    
    # Update or insert the vessel's latest sighting (one "current" record per
    # vessel). AIS sends positions every few seconds: write at most every
    # SIGHTING_INTERVAL per vessel unless its USACE state changed.
    now_s = datetime.now(timezone.utc)
    state = (vessel_data.get('usace_status'), vessel_data.get('usace_lock'), vessel_data.get('barge_count'))
    prev = _last_sighting_write.get(str(mmsi))
    if prev is None or now_s - prev[0] >= SIGHTING_INTERVAL or prev[1] != state:
        _last_sighting_write[str(mmsi)] = (now_s, state)
        if len(_last_sighting_write) > 20000:
            _last_sighting_write.clear()
        await _upsert_sighting(mmsi, sighting)

    await _append_history(mmsi, vessel_data, sighting)


async def _upsert_sighting(mmsi, sighting: dict) -> None:
    await db.vessel_sightings.update_one(
        {"mmsi": mmsi},
        {
            "$set": sighting,
            "$setOnInsert": {"first_seen": datetime.now(timezone.utc)}
        },
        upsert=True
    )


async def _append_history(mmsi, vessel_data: dict, sighting: dict) -> None:
    # Also append to historical sightings if USACE data present (for analysis),
    # at most once per vessel per lock every HISTORY_INTERVAL - position updates
    # can arrive every few seconds.
    history_key = (str(mmsi), vessel_data.get('usace_lock'))
    now_ts = datetime.now(timezone.utc)
    last_ts = _last_history_write.get(history_key)
    if last_ts is not None and now_ts - last_ts < HISTORY_INTERVAL:
        return
    if vessel_data.get('usace_source') and vessel_data.get('barge_count') is not None:
        _last_history_write[history_key] = now_ts
        historical_record = {
            **sighting,
            "recorded_at": datetime.now(timezone.utc)
        }
        await db.vessel_history.insert_one(historical_record)
        logger.debug(f"Persisted USACE sighting for {mmsi}: {vessel_data.get('barge_count')} barges at {vessel_data.get('usace_lock')}")


async def persist_vessel_position_to_user(mmsi: str, position_data: dict):
    """
    Persist vessel position to the user's account.
    This allows the vessel position to be restored on login.
    """
    if not mmsi:
        return
    
    # Find user who owns this vessel
    user = await db.users.find_one({"vessels.mmsi": mmsi}, {"_id": 0, "user_id": 1})
    if not user:
        return
    
    # Update the vessel's last known position in the user's account
    await db.users.update_one(
        {"user_id": user["user_id"], "vessels.mmsi": mmsi},
        {"$set": {
            "vessels.$.last_position": position_data
        }}
    )
    logger.debug(f"Persisted position to user account for MMSI {mmsi}: RM {position_data.get('river_mile')}")


async def restore_user_vessel_position(user_id: str, mmsi: str) -> dict:
    """
    Restore a user's vessel position from their account.
    Called on login to automatically position their vessel.
    """
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return None
    
    # Find the vessel in user's fleet
    for vessel in user.get("vessels", []):
        if vessel.get("mmsi") == mmsi:
            last_pos = vessel.get("last_position")
            if last_pos and last_pos.get("lat") and last_pos.get("lon"):
                return last_pos
    
    return None


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

# Session cookie policy. "lax" blocks cross-site use of the session (CSRF);
# set COOKIE_SAMESITE=none only if the frontend is on a different site and you
# also list it explicitly in CORS_ORIGINS. COOKIE_SECURE=false for plain-HTTP
# local development.
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax").lower()
if COOKIE_SAMESITE not in ("lax", "strict", "none"):
    COOKIE_SAMESITE = "lax"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() != "false" or COOKIE_SAMESITE == "none"


# =============================================================================
# USER AUTHENTICATION MODELS
# =============================================================================
class UserRegistration(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class VesselAdd(BaseModel):
    mmsi: str
    boat_name: str
    is_primary: bool = False

class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    fleet_name: Optional[str] = None
    vessels: List[dict] = []
    settings: dict = {}
    account_type: str = "vessel_owner"  # "vessel_owner" or "traffic_watch"
    watch_point: Optional[dict] = None  # {river_mile: float, name: str}
    favorite_locks: List[str] = []
    vessel_watch_list: List[dict] = []
    is_admin: bool = False
    is_super_admin: bool = False
    last_login: Optional[str] = None
    created_at: Optional[str] = None

# Super admin email - this user has full system access. Override per deployment.
SUPER_ADMIN_EMAIL = (os.environ.get("SUPER_ADMIN_EMAIL") or "cdillerud@gmail.com").strip()


# =============================================================================
# PASSWORD HASHING
# =============================================================================
# Format: "pbkdf2_sha256$<iterations>$<salt>$<hex digest>".
# Legacy hashes ("<salt>$<sha256 hex>", one unstretched SHA-256 round) still
# verify, and are upgraded to PBKDF2 on the user's next successful login.
PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """Hash a password with salted PBKDF2-HMAC-SHA256."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time check of a password against a stored hash (current or legacy format)."""
    try:
        parts = hashed.split("$")
        if parts[0] == "pbkdf2_sha256" and len(parts) == 4:
            iterations, salt, expected = int(parts[1]), parts[2], parts[3]
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
        elif len(parts) == 2:
            salt, expected = parts
            digest = hashlib.sha256((salt + password).encode()).hexdigest()
        else:
            return False
        return secrets.compare_digest(digest, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def password_needs_rehash(hashed: str) -> bool:
    parts = (hashed or "").split("$")
    return not (parts[0] == "pbkdf2_sha256" and len(parts) == 4 and parts[1] == str(PBKDF2_ITERATIONS))


# =============================================================================
# SESSION TOKEN HELPERS
# =============================================================================
def generate_session_token() -> str:
    """Generate a secure session token."""
    return f"session_{secrets.token_urlsafe(32)}"

async def get_current_user(request: Request) -> Optional[dict]:
    """Get current user from session token (cookie or header). Cached on the
    request: the router-wide login check and route dependencies share it."""
    state = getattr(request, "state", None)
    if state is not None and hasattr(state, "rw_user"):
        return state.rw_user
    user = await _lookup_current_user(request)
    if state is not None:
        state.rw_user = user
    return user


async def _lookup_current_user(request: Request) -> Optional[dict]:
    # Try cookie first
    session_token = request.cookies.get("session_token")
    
    # Fallback to Authorization header
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ")[1]
    
    if not session_token:
        return None
    
    # Find session in database
    session_doc = await repos.sessions.get_session_by_token(session_token)
    
    if not session_doc:
        return None
    
    # Check expiry
    expires_at = session_doc.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return None
    
    # Get user
    user_doc = await repos.users.get_user_by_id(session_doc["user_id"])
    
    return user_doc


# =============================================================================
# AUTH ENDPOINTS
# =============================================================================
@api_router.post("/auth/register")
async def register_user(data: UserRegistration, response: Response):
    """Register a new user with email/password."""
    # Check if email already exists
    existing = await repos.users.get_user_by_email(data.email)
    if existing:
        # Return a friendly message instead of error
        return {
            "success": False, 
            "user_exists": True,
            "message": "An account with this email already exists. Would you like to reset your password?"
        }
    
    # Create user
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    
    # Check if this is the super admin
    is_super = data.email.lower() == SUPER_ADMIN_EMAIL.lower()
    
    user_doc = {
        "user_id": user_id,
        "email": data.email,
        "name": data.name,
        "password_hash": await asyncio.to_thread(hash_password, data.password),
        "picture": None,
        "fleet_name": None,
        "vessels": [],
        "settings": {},
        "is_admin": is_super,
        "is_super_admin": is_super,
        "last_login": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "auth_provider": "email"
    }
    
    await repos.users.create_user(user_doc)
    logger.info(f"[AUTH] New user registered: {data.email} ({user_id})" + (" [SUPER ADMIN]" if is_super else ""))
    
    # Create session
    session_token = generate_session_token()
    await repos.sessions.create_session({
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
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
        max_age=7*24*60*60
    )
    
    # Return user (without password)
    user_doc.pop("password_hash", None)
    user_doc.pop("_id", None)
    
    return {"success": True, "user": user_doc}


@api_router.post("/auth/login")
async def login_user(data: UserLogin, response: Response):
    """Login with email/password."""
    # Find user
    user_doc = await repos.users.get_user_by_email(data.email)
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Verify password
    if not user_doc.get("password_hash") or not await asyncio.to_thread(verify_password, data.password, user_doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    logger.info(f"[AUTH] User logged in: {data.email}")
    
    # Update last_login and ensure super admin has admin rights
    update_fields = {"last_login": datetime.now(timezone.utc).isoformat()}
    if password_needs_rehash(user_doc["password_hash"]):
        update_fields["password_hash"] = await asyncio.to_thread(hash_password, data.password)
    if data.email.lower() == SUPER_ADMIN_EMAIL.lower():
        update_fields["is_admin"] = True
        update_fields["is_super_admin"] = True
    
    await repos.users.update_user(user_doc["user_id"], update_fields)
    user_doc.update(update_fields)
    
    # Create session
    session_token = generate_session_token()
    await repos.sessions.create_session({
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
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
        max_age=7*24*60*60
    )
    
    # Return user (without password)
    user_doc.pop("password_hash", None)
    
    return {"success": True, "user": user_doc}


@api_router.get("/auth/config")
async def auth_config():
    """Public sign-in options for the login page (no secrets)."""
    return {"google_client_id": google_client_id()}


@api_router.post("/auth/google")
async def google_auth(request: Request, response: Response):
    """Sign in with a Google Identity Services ID token ({"credential": "<jwt>"})."""
    client_id = google_client_id()
    if not client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    try:
        body = await request.json()
    except ValueError:
        body = None
    credential = body.get("credential") if isinstance(body, dict) else None
    if not credential:
        raise HTTPException(status_code=400, detail="credential required")
    try:
        claims = await asyncio.to_thread(verify_google_credential, credential, client_id)
    except GoogleAuthError as e:
        logger.warning(f"[AUTH] Google sign-in rejected: {e}")
        raise HTTPException(status_code=401, detail="Google sign-in failed")
    except Exception as e:  # network trouble fetching Google's signing keys
        logger.error(f"[AUTH] Google verification unavailable: {e}")
        raise HTTPException(status_code=503, detail="Google sign-in is temporarily unavailable")
    google_data = {"email": claims["email"], "name": claims["name"],
                   "picture": claims["picture"], "id": claims["sub"]}

    # Find or create user
    email = google_data.get("email")
    is_super = email.lower() == SUPER_ADMIN_EMAIL.lower()
    existing_user = await repos.users.get_user_by_email(email)
    
    if existing_user:
        user_id = existing_user["user_id"]
        # Update user info from Google
        update_fields = {
            "name": google_data.get("name", existing_user.get("name")),
            "picture": google_data.get("picture"),
            "google_id": google_data.get("id"),
            "last_login": datetime.now(timezone.utc).isoformat()
        }
        # Ensure super admin has admin rights
        if is_super:
            update_fields["is_admin"] = True
            update_fields["is_super_admin"] = True
        
        await repos.users.update_user(user_id, update_fields)
        user_doc = await repos.users.get_user_by_id(user_id)
        logger.info(f"[AUTH] Google user logged in: {email}" + (" [SUPER ADMIN]" if is_super else ""))
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
            "is_admin": is_super,
            "is_super_admin": is_super,
            "last_login": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "auth_provider": "google"
        }
        await repos.users.create_user(user_doc)
        logger.info(f"[AUTH] New Google user created: {email} ({user_id})" + (" [SUPER ADMIN]" if is_super else ""))
    
    # Create session
    session_token = generate_session_token()
    await repos.sessions.create_session({
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
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
        max_age=7*24*60*60
    )
    
    # Return user (without sensitive data)
    user_doc.pop("password_hash", None)
    user_doc.pop("_id", None)
    
    return {"success": True, "user": user_doc}


@api_router.get("/auth/me")
async def get_current_user_info(request: Request):
    """Get current authenticated user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Remove sensitive fields
    user.pop("password_hash", None)
    user.pop("_id", None)
    
    return user


@api_router.post("/auth/logout")
async def logout_user(request: Request, response: Response):
    """Logout current user and clear their vessel data."""
    session_token = request.cookies.get("session_token")
    
    if session_token:
        # Get the user's session to find their MMSI
        session = await repos.sessions.get_session_by_token(session_token)
        if session:
            user_id = session.get("user_id")
            if user_id:
                # Get user's vessels to clear them from active_vessels
                user = await repos.users.get_user_by_id(user_id)
                if user and user.get("vessels"):
                    for vessel in user["vessels"]:
                        mmsi = vessel.get("mmsi")
                        if mmsi and mmsi in active_vessels:
                            del active_vessels[mmsi]
                            logger.info(f"[AUTH] Cleared vessel {mmsi} from active_vessels on logout")
        
        # Delete the session
        await repos.sessions.delete_session_by_token(session_token)
    
    response.delete_cookie(key="session_token", path="/")
    
    return {"success": True}


# =============================================================================
# USER VESSEL MANAGEMENT
# =============================================================================
@api_router.get("/user/vessels")
async def get_user_vessels(request: Request):
    """Get all vessels for current user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {"vessels": user.get("vessels", [])}


@api_router.post("/user/vessels/restore")
async def restore_user_vessels(request: Request):
    """
    Restore all user's vessels to active_vessels from their saved positions.
    Called on login/app load to automatically position their vessels.
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    restored = []
    now = datetime.now(timezone.utc)
    for vessel_info in user.get("vessels", []):
        mmsi = vessel_info.get("mmsi")
        boat_name = vessel_info.get("boat_name", "Your Vessel")
        # Recent real fix as reported, else parked at its home berth (stopped).
        last_pos, pos_source = _home_berth.position_to_show(vessel_info, now)

        if mmsi and _live_ais.on_live_ais(mmsi):
            continue  # live AIS position already on the map; don't put an old one over it
        if mmsi and (user_vessel_simulation.get(mmsi) or {}).get('enabled'):
            continue  # being simulated: a page reload must not jump it back to the saved spot
        if mmsi and last_pos and last_pos.get("lat") and last_pos.get("lon"):
            # Create vessel and add to active_vessels
            lat = last_pos["lat"]
            lon = last_pos["lon"]
            speed = last_pos.get("speed", 0)
            course = last_pos.get("course", 0)
            rm = last_pos.get("river_mile") or estimate_river_mile(lat, lon)
            heading = last_pos.get("heading_direction") or determine_heading(speed, course, lat, lon)
            
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
            )
            
            active_vessels[mmsi] = vessel
            
            restored.append({
                "mmsi": mmsi,
                "name": boat_name,
                "river_mile": rm,
                "lat": lat,
                "lon": lon,
                "source": pos_source,
            })

            logger.info(f"[AUTH] Restored vessel {mmsi} ({boat_name}) at RM {rm} ({pos_source})")
    
    return {"success": True, "restored": restored, "count": len(restored)}


async def _park_at_home(mmsi: str) -> bool:
    """Show the boat stopped at its home berth (when its simulation ends).
    Not over live AIS. Saved as its last position so reloads agree."""
    if not mmsi or _live_ais.on_live_ais(mmsi):
        return False
    owner = await db.users.find_one({"vessels.mmsi": mmsi}, {"_id": 0, "vessels": 1})
    info = next((v for v in (owner or {}).get("vessels", []) if v.get("mmsi") == mmsi), None)
    home = (info or {}).get("home_berth") or {}
    if home.get("lat") is None or home.get("lon") is None:
        return False
    rm = home.get("river_mile") or estimate_river_mile(home["lat"], home["lon"])
    vessel = VesselPosition(mmsi=mmsi, name=info.get("boat_name") or "Your Vessel",
                            lat=home["lat"], lon=home["lon"], speed=0.0, course=0.0,
                            river_mile=rm, heading="stationary", is_user_vessel=True,
                            timestamp=datetime.now(timezone.utc))
    active_vessels[mmsi] = vessel
    v_dict = prepare_vessel_for_output(vessel, mmsi)
    v_dict['source'] = 'home_berth'
    await ais_manager._broadcast_vessel_update(v_dict)
    # Parked, not a live fix: no last_position_update, so it never outranks
    # a real position later.
    await persist_vessel_position_to_user(mmsi, {"lat": home["lat"], "lon": home["lon"], "speed": 0.0,
                                                 "course": 0.0, "river_mile": rm,
                                                 "heading_direction": "stationary"})
    logger.info(f"[HOME] {mmsi} parked at its home berth, RM {rm}")
    return True


class HomeBerth(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    use_current: bool = False   # the boat's position on the map right now


@api_router.put("/user/vessels/{mmsi}/home-berth")
async def set_home_berth(mmsi: str, body: HomeBerth, request: Request):
    """Set a boat's home berth (its slip): where it is shown, stopped, when it
    isn't being simulated and has no recent real position."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_owner(user, mmsi)
    lat, lon = body.lat, body.lon
    if body.use_current:
        v = active_vessels.get(mmsi)
        g = v.get if isinstance(v, dict) else (lambda k, d=None: getattr(v, k, d))
        lat, lon = (g("lat"), g("lon")) if v is not None else (None, None)
    if lat is None or lon is None:
        raise HTTPException(status_code=400, detail="Give lat and lon, or use_current with the boat on the map")
    rm = estimate_river_mile(lat, lon)
    if rm is None:
        raise HTTPException(status_code=400, detail="That spot isn't on the Upper Mississippi")
    home = {"lat": round(float(lat), 6), "lon": round(float(lon), 6), "river_mile": round(rm, 1),
            "set_at": datetime.now(timezone.utc).isoformat()}
    # The caller's own account when the boat is on it (two accounts could hold
    # the same MMSI); an admin setting someone else's boat matches by MMSI.
    own = any(str(v.get("mmsi")) == str(mmsi) for v in user.get("vessels") or [])
    match = {"user_id": user["user_id"], "vessels.mmsi": mmsi} if own else {"vessels.mmsi": mmsi}
    res = await db.users.update_one(match, {"$set": {"vessels.$.home_berth": home}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="That boat isn't on an account")
    sim = user_vessel_simulation.get(mmsi) or {}
    parked = False if sim.get('enabled') else await _park_at_home(mmsi)
    return {"success": True, "home_berth": home, "parked": parked}


@api_router.post("/user/vessels")
async def add_user_vessel(request: Request, vessel: VesselAdd):
    """Add a vessel to user's fleet."""
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
    existing_settings = await db.user_settings.find_one(_user_settings.read_filter(vessel.mmsi, user), {"_id": 0})
    if existing_settings:
        # Merge settings into user's settings
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {f"vessel_settings.{vessel.mmsi}": existing_settings.get("settings", {})}}
        )
    
    logger.info(f"[USER:{user['user_id']}] Added vessel: {vessel.mmsi} ({vessel.boat_name})")
    
    return {"success": True, "vessel": vessel_doc}


@api_router.delete("/user/vessels/{mmsi}")
async def remove_user_vessel(request: Request, mmsi: str):
    """Remove a vessel from user's fleet."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    res = await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$pull": {"vessels": {"mmsi": mmsi}}}
    )
    if res.modified_count:
        # Once removed, the owner can no longer stop its simulation, and a
        # simulated or parked copy kept showing on everyone's map.
        sim = user_vessel_simulation.pop(mmsi, None)
        if (sim and sim.get('enabled')) or not _live_ais.on_live_ais(mmsi):
            active_vessels.pop(mmsi, None)
    
    logger.info(f"[USER:{user['user_id']}] Removed vessel: {mmsi}")
    
    return {"success": True}


@api_router.put("/user/vessels/{mmsi}/primary")
async def set_primary_vessel(request: Request, mmsi: str):
    """Set a vessel as the primary vessel."""
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


@api_router.put("/user/profile")
async def update_user_profile(request: Request):
    """Update user profile (name, fleet name)."""
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


@api_router.put("/user/settings")
async def update_user_settings(request: Request):
    """Update user settings."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    body = await request.json()
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"settings": body}}
    )
    
    return {"success": True}


# =============================================================================
# ACCOUNT TYPE & TRAFFIC WATCH MODE
# =============================================================================

class AccountTypeUpdate(BaseModel):
    account_type: str  # "vessel_owner" or "traffic_watch"

class WatchPointUpdate(BaseModel):
    river_mile: float
    name: Optional[str] = None

class FavoriteLockUpdate(BaseModel):
    lock_ids: List[str]

class VesselWatchItem(BaseModel):
    mmsi: str
    name: Optional[str] = None
    alert_enabled: bool = True
    alert_rm: Optional[float] = None  # Alert when vessel passes this RM

@api_router.post("/user/account-type")
async def update_account_type(request: Request, data: AccountTypeUpdate):
    """Set user account type (vessel_owner or traffic_watch)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if data.account_type not in ["vessel_owner", "traffic_watch"]:
        raise HTTPException(status_code=400, detail="Invalid account type")
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"account_type": data.account_type}}
    )
    
    logger.info(f"[USER] {user['email']} set account type to: {data.account_type}")
    return {"success": True, "account_type": data.account_type}

@api_router.get("/user/account-type")
async def get_account_type(request: Request):
    """Get user account type."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {"account_type": user.get("account_type", "vessel_owner")}

@api_router.post("/user/watch-point")
async def set_watch_point(request: Request, data: WatchPointUpdate):
    """Set the watch point (center RM) for Traffic Watch users."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    watch_point = {
        "river_mile": data.river_mile,
        "name": data.name or f"RM {data.river_mile}"
    }
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"watch_point": watch_point}}
    )
    
    return {"success": True, "watch_point": watch_point}

@api_router.get("/user/watch-point")
async def get_watch_point(request: Request):
    """Get the user's watch point."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {"watch_point": user.get("watch_point")}

@api_router.post("/user/favorite-locks")
async def set_favorite_locks(request: Request, data: FavoriteLockUpdate):
    """Set user's favorite locks for quick switching."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Validate lock IDs
    valid_locks = [lid for lid in data.lock_ids if lid in LOCKS]
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"favorite_locks": valid_locks}}
    )
    
    return {"success": True, "favorite_locks": valid_locks}

@api_router.get("/user/favorite-locks")
async def get_favorite_locks(request: Request):
    """Get user's favorite locks."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {"favorite_locks": user.get("favorite_locks", [])}

@api_router.post("/user/vessel-watch")
async def add_vessel_to_watch(request: Request, data: VesselWatchItem):
    """Add a vessel to the watch list for alerts."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    watch_list = user.get("vessel_watch_list", [])
    
    # Check if already watching
    existing = next((v for v in watch_list if v["mmsi"] == data.mmsi), None)
    if existing:
        # Update existing
        existing["name"] = data.name or existing.get("name")
        existing["alert_enabled"] = data.alert_enabled
        existing["alert_rm"] = data.alert_rm
    else:
        # Add new
        watch_list.append({
            "mmsi": data.mmsi,
            "name": data.name,
            "alert_enabled": data.alert_enabled,
            "alert_rm": data.alert_rm,
            "added_at": datetime.now(timezone.utc).isoformat()
        })
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"vessel_watch_list": watch_list}}
    )
    
    return {"success": True, "vessel_watch_list": watch_list}

@api_router.delete("/user/vessel-watch/{mmsi}")
async def remove_vessel_from_watch(request: Request, mmsi: str):
    """Remove a vessel from the watch list."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    watch_list = user.get("vessel_watch_list", [])
    watch_list = [v for v in watch_list if v["mmsi"] != mmsi]
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"vessel_watch_list": watch_list}}
    )
    
    return {"success": True, "vessel_watch_list": watch_list}

@api_router.get("/user/vessel-watch")
async def get_vessel_watch_list(request: Request):
    """Get user's vessel watch list."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {"vessel_watch_list": user.get("vessel_watch_list", [])}

TRAFFIC_SUMMARY_RADIUS_MI = 20


@api_router.get("/traffic-summary/{lock_id}")
async def get_traffic_summary(lock_id: str):
    """Get traffic summary for a lock - useful for Traffic Watch users."""
    if lock_id not in LOCKS:
        raise HTTPException(status_code=404, detail="Invalid lock ID")
    
    lock = LOCKS[lock_id]
    lock_rm = lock["river_mile"]
    
    # Counts describe the watched lock only: AIS vessels within
    # TRAFFIC_SUMMARY_RADIUS_MI river miles plus vessels USACE reports at the
    # lock, each counted once (by MMSI, or name when USACE has no MMSI).
    vessels_near_lock = []
    counted = {}  # identity -> "northbound" | "southbound" | "stationary"
    
    for mmsi, vessel in active_vessels.items():
        if hasattr(vessel, 'river_mile'):
            vessel_rm = vessel.river_mile
            heading = vessel.heading
            speed = vessel.speed
        else:
            vessel_rm = vessel.get('river_mile')
            heading = vessel.get('heading') or vessel.get('heading_direction')
            speed = vessel.get('speed', 0)
        
        if vessel_rm is None:
            continue
            
        distance = abs(vessel_rm - lock_rm)
        
        # Track vessels near the lock
        if distance <= TRAFFIC_SUMMARY_RADIUS_MI:
            counted[str(mmsi)] = heading if heading in ("northbound", "southbound") else "stationary"
            v_dict = prepare_vessel_for_output(vessel, None)  # another boat: never "yours"
            v_dict['distance_to_lock'] = round(distance, 1)
            
            # Calculate ETA for vessels heading TOWARD the lock
            eta_minutes = None
            is_heading_to_lock = False
            
            if heading == 'northbound' and vessel_rm < lock_rm:
                # Northbound vessel below lock - heading toward it
                is_heading_to_lock = True
            elif heading == 'southbound' and vessel_rm > lock_rm:
                # Southbound vessel above lock - heading toward it
                is_heading_to_lock = True
            
            if is_heading_to_lock and speed and speed > 0.1:
                speed_mph = speed * 1.15078  # knots to mph
                eta_minutes = (distance / speed_mph) * 60
                v_dict['eta_to_lock'] = round(eta_minutes, 1)
            else:
                v_dict['eta_to_lock'] = None
                
            v_dict['heading_to_lock'] = is_heading_to_lock
            vessels_near_lock.append(v_dict)
    
    # Sort by ETA (arrival order) - vessels heading to lock with ETA come first, then by distance
    # Vessels with ETA (heading toward lock) sorted by ETA
    # Vessels without ETA (heading away or stationary) sorted by distance
    def sort_key(v):
        eta = v.get('eta_to_lock')
        if eta is not None:
            return (0, eta)  # Priority 0 = heading to lock, sort by ETA
        else:
            return (1, v.get('distance_to_lock', 999))  # Priority 1 = not heading to lock, sort by distance
    
    vessels_near_lock.sort(key=sort_key)

    # Vessels USACE reports at this lock (waiting or locking), even with no AIS position
    at_lock = 0
    for lock_no, infos in usace_lock_rows.items():
        if usace_lock_id(lock_no) != lock_id:
            continue
        for v in infos:
            at_lock += 1
            ident = str(v.get("mmsi") or v.get("vessel_name") or "")
            if not ident or ident in counted:
                continue
            counted[ident] = {"U": "northbound", "D": "southbound"}.get(v.get("direction") or "", "stationary")
    directions = list(counted.values())
    
    # Get recent lockage data
    recent_lockages = []
    try:
        cursor = db.lockage_history.find(
            {"lock_id": lock_id},
            {"_id": 0}
        ).sort("recorded_at", -1).limit(5)
        recent_lockages = [lockage_for_output(r) for r in await cursor.to_list(length=5)]
    except Exception as e:
        logger.error(f"Failed to fetch lockage history: {e}")
    
    return {
        "lock_id": lock_id,
        "lock_name": lock["name"],
        "lock_rm": lock_rm,
        # All counts are for this lock: within TRAFFIC_SUMMARY_RADIUS_MI or in its USACE queue.
        "total_vessels": len(counted),
        "northbound": directions.count("northbound"),
        "southbound": directions.count("southbound"),
        "stationary": directions.count("stationary"),
        "at_lock_usace": at_lock,
        "radius_mi": TRAFFIC_SUMMARY_RADIUS_MI,
        "feed_vessels": len(active_vessels),
        "vessels_near_lock": vessels_near_lock[:10],  # Top 10 nearest
        "recent_lockages": recent_lockages
    }


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

async def require_admin(request: Request) -> dict:
    """Helper to require admin access."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not user.get("is_admin") and not user.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

async def require_super_admin(request: Request) -> dict:
    """Helper to require super admin access."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not user.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Super admin access required")
    return user


async def require_user(request: Request) -> dict:
    """Dependency: any signed-in user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# --- AIS feed target validation (SSRF guard) ---------------------------------
# The server dials the host:port a user supplies (their Boat Beacon phone or a
# relay). Without a check, anyone could make it connect to cloud metadata
# endpoints, the database, or other internal services.
#   AIS_TARGET_ALLOWLIST       comma-separated hostnames always allowed (default "ais-relay")
#   AIS_ALLOW_PRIVATE_TARGETS  "true" (default, self-hosted on the boat LAN) /
#                              "false" (hosted SaaS: only public addresses)
import ipaddress as _ipaddress  # noqa: E402


def validate_feed_target(host: str, port) -> Optional[str]:
    """Return an error message if host:port is not an acceptable AIS feed target."""
    if not host or not isinstance(host, str) or len(host) > 253:
        return "A feed host is required"
    try:
        port = int(port)
    except (TypeError, ValueError):
        return "Invalid port"
    if not (1 <= port <= 65535):
        return "Invalid port"
    allow = {h.strip().lower() for h in os.environ.get("AIS_TARGET_ALLOWLIST", "ais-relay").split(",") if h.strip()}
    if host.strip().lower() in allow:
        return None
    allow_private = os.environ.get("AIS_ALLOW_PRIVATE_TARGETS", "true").lower() != "false"
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return "Host could not be resolved"
    for info in infos:
        ip = _ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            return "That address is not allowed as an AIS feed"
        if ip.is_private and not allow_private:
            return "Private network addresses are not allowed on this server"
    return None


def _ingest_token_ok(request: Request) -> bool:
    """Push-ingest auth: if AIS_INGEST_TOKEN is set, relays must send it."""
    expected = os.environ.get("AIS_INGEST_TOKEN", "")
    if not expected:
        return True
    supplied = request.headers.get("X-Ingest-Token", "")
    return secrets.compare_digest(supplied, expected)

@api_router.get("/admin/users")
async def admin_get_users(request: Request, search: str = None, limit: int = 50, skip: int = 0):
    """Get all users (admin only)."""
    await require_admin(request)
    
    query = {}
    if search:
        query["$or"] = [
            {"email": {"$regex": search, "$options": "i"}},
            {"name": {"$regex": search, "$options": "i"}}
        ]
    
    users = await repos.users.get_all_users(skip=skip, limit=limit, query=query)
    total = await repos.users.count_users(query)
    
    return {"users": users, "total": total, "limit": limit, "skip": skip}

@api_router.post("/admin/users")
async def admin_create_user(request: Request):
    """Create a new user (admin only)."""
    admin = await require_admin(request)
    body = await request.json()
    
    email = body.get("email")
    name = body.get("name", "")
    password = body.get("password")
    is_admin = body.get("is_admin", False)
    account_type = body.get("account_type", "vessel_owner")
    
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    
    # Check if user exists
    existing = await repos.users.get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
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
        "account_type": account_type,
        "is_admin": is_admin,
        "is_super_admin": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "auth_provider": "admin_created"
    }
    
    await repos.users.create_user(user_doc)
    logger.info(f"[ADMIN] User created by {admin['email']}: {email}")
    
    user_doc.pop("password_hash", None)
    user_doc.pop("_id", None)
    return {"success": True, "user": user_doc}

@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(request: Request, user_id: str):
    """Delete a user (admin only)."""
    admin = await require_admin(request)
    
    # Find the user first
    user = await repos.users.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent deleting super admin
    if user.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Cannot delete super admin")
    
    # Prevent deleting yourself
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=403, detail="Cannot delete your own account")
    
    # Delete user sessions
    await repos.sessions.delete_user_sessions(user_id)
    
    # Delete user
    await repos.users.delete_user(user_id)
    
    logger.info(f"[ADMIN] User deleted by {admin['email']}: {user['email']}")
    return {"success": True, "deleted_user_id": user_id}

@api_router.put("/admin/users/{user_id}")
async def admin_update_user(request: Request, user_id: str):
    """Update a user (admin only)."""
    admin = await require_admin(request)
    body = await request.json()
    
    user = await repos.users.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Build update fields
    update_fields = {}
    
    if "name" in body:
        update_fields["name"] = body["name"]
    if "email" in body:
        update_fields["email"] = body["email"]
    if "account_type" in body:
        update_fields["account_type"] = body["account_type"]
    if "password" in body and body["password"]:
        update_fields["password_hash"] = hash_password(body["password"])
    
    # Only super admin can change admin status
    if "is_admin" in body:
        if admin.get("is_super_admin"):
            # Can't demote super admin
            if user.get("is_super_admin") and not body["is_admin"]:
                raise HTTPException(status_code=403, detail="Cannot demote super admin")
            update_fields["is_admin"] = body["is_admin"]
        else:
            raise HTTPException(status_code=403, detail="Only super admin can change admin status")
    
    if update_fields:
        await repos.users.update_user(user_id, update_fields)
        logger.info(f"[ADMIN] User updated by {admin['email']}: {user['email']}")
    
    updated_user = await repos.users.get_user_by_id_exclude_password(user_id)
    return {"success": True, "user": updated_user}

@api_router.post("/admin/users/{user_id}/promote")
async def admin_promote_user(request: Request, user_id: str):
    """Promote a user to admin (super admin only)."""
    await require_super_admin(request)
    
    user = await repos.users.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await repos.users.update_user(user_id, {"is_admin": True})
    logger.info(f"[ADMIN] User promoted to admin: {user['email']}")
    
    return {"success": True, "message": f"{user['email']} is now an admin"}

@api_router.post("/admin/users/{user_id}/demote")
async def admin_demote_user(request: Request, user_id: str):
    """Demote a user from admin (super admin only)."""
    admin = await require_super_admin(request)
    
    user = await repos.users.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Cannot demote super admin")
    
    await repos.users.update_user(user_id, {"is_admin": False})
    logger.info(f"[ADMIN] User demoted from admin: {user['email']}")
    
    return {"success": True, "message": f"{user['email']} is no longer an admin"}

@api_router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_password(request: Request, user_id: str):
    """Reset a user's password (admin only)."""
    admin = await require_admin(request)
    body = await request.json()
    
    new_password = body.get("password")
    if not new_password:
        raise HTTPException(status_code=400, detail="New password is required")
    
    user = await repos.users.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await repos.users.update_user(user_id, {"password_hash": hash_password(new_password)})
    
    logger.info(f"[ADMIN] Password reset by {admin['email']} for: {user['email']}")
    return {"success": True, "message": f"Password reset for {user['email']}"}

@api_router.post("/admin/impersonate/{user_id}")
async def admin_impersonate_user(request: Request, response: Response, user_id: str):
    """Impersonate a user (admin only). Creates a session as that user."""
    admin = await require_admin(request)
    
    user = await repos.users.get_user_by_id_exclude_password(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Create impersonation session
    session_token = generate_session_token()
    await repos.sessions.create_session({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=2),
        "created_at": datetime.now(timezone.utc),
        "impersonated_by": admin["user_id"],
        "impersonated_by_email": admin["email"]
    })
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
        max_age=2*60*60  # 2 hours
    )
    
    logger.info(f"[ADMIN] {admin['email']} started impersonating {user['email']}")
    
    user.pop("password_hash", None)
    return {"success": True, "user": user, "message": f"Now viewing as {user['email']}"}

@api_router.get("/admin/stats")
async def admin_get_stats(request: Request):
    """Get system statistics (admin only)."""
    await require_admin(request)
    
    total_users = await repos.users.count_users()
    admin_users = await repos.users.count_users({"is_admin": True})
    vessel_owners = await repos.users.count_users({"account_type": "vessel_owner"})
    traffic_watchers = await repos.users.count_users({"account_type": "traffic_watch"})
    
    # Active sessions (not expired)
    active_sessions = await db.user_sessions.count_documents({
        "expires_at": {"$gt": datetime.now(timezone.utc)}
    })
    
    # Recent signups (last 7 days)
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_signups = await repos.users.count_users({
        "created_at": {"$gte": week_ago}
    })
    
    # Vessels being tracked
    total_vessels = len(active_vessels)
    
    # Recent lockages
    recent_lockages = await db.lockage_history.count_documents({})
    
    return {
        "users": {
            "total": total_users,
            "admins": admin_users,
            "vessel_owners": vessel_owners,
            "traffic_watchers": traffic_watchers,
            "recent_signups": recent_signups
        },
        "sessions": {
            "active": active_sessions
        },
        "vessels": {
            "currently_tracked": total_vessels,
            "demo_active": demo_vessels_active
        },
        "lockages": {
            "total_recorded": recent_lockages
        }
    }

@api_router.get("/admin/vessels")
async def admin_get_all_vessels(request: Request):
    """Get all vessels currently being tracked (admin only)."""
    await require_admin(request)
    
    vessels_list = []
    for mmsi, vessel in active_vessels.items():
        v_dict = prepare_vessel_for_output(vessel, None)
        vessels_list.append(v_dict)
    
    # Sort by river mile
    vessels_list.sort(key=lambda x: x.get('river_mile') or 0, reverse=True)
    
    return {"vessels": vessels_list, "total": len(vessels_list)}

@api_router.post("/admin/vessels")
async def admin_add_vessel(request: Request):
    """Manually add a vessel to the system (admin only)."""
    admin = await require_admin(request)
    body = await request.json()
    
    mmsi = body.get("mmsi")
    name = body.get("name", f"Vessel {mmsi}")
    river_mile = body.get("river_mile")
    heading = body.get("heading", "stationary")
    
    if not mmsi:
        raise HTTPException(status_code=400, detail="MMSI is required")
    
    # Create vessel in active_vessels
    from types import SimpleNamespace
    vessel = SimpleNamespace(
        mmsi=mmsi,
        name=name,
        river_mile=river_mile,
        lat=body.get("lat"),
        lon=body.get("lon"),
        speed=body.get("speed", 0),
        course=body.get("course", 0),
        heading=heading,
        heading_direction=heading,
        ship_type=body.get("ship_type", 0),
        is_tow=body.get("is_tow", False),
        barge_count=body.get("barge_count", 0),
        last_update=datetime.now(timezone.utc),
        source="admin_added"
    )
    
    active_vessels[mmsi] = vessel
    logger.info(f"[ADMIN] Vessel added by {admin['email']}: {mmsi} ({name})")
    
    return {"success": True, "vessel": prepare_vessel_for_output(vessel, mmsi)}

@api_router.delete("/admin/vessels/{mmsi}")
async def admin_delete_vessel(request: Request, mmsi: str):
    """Remove a vessel from tracking (admin only)."""
    admin = await require_admin(request)
    
    if mmsi not in active_vessels:
        raise HTTPException(status_code=404, detail="Vessel not found")
    
    del active_vessels[mmsi]
    logger.info(f"[ADMIN] Vessel removed by {admin['email']}: {mmsi}")
    
    return {"success": True, "message": f"Vessel {mmsi} removed from tracking"}


# ---------------------------------------------------------------------------
# Live-AIS / demo-vessel / stale-prune helpers
# ---------------------------------------------------------------------------

def _demo_mmsi_set() -> set:
    """Set of MMSIs that belong to demo vessels."""
    return {cfg["mmsi"] for cfg in DEMO_VESSELS.values()}


def _is_demo_vessel(vessel, mmsi: str) -> bool:
    """Return True if a vessel object/MMSI represents a demo vessel."""
    if mmsi in _demo_mmsi_set():
        return True
    if isinstance(vessel, dict):
        return bool(vessel.get("is_demo"))
    return bool(getattr(vessel, "is_demo", False))


# Per-source coverage: {source: {mmsi: {"last_seen": datetime, "name": str}}}
# Used to compare what each AIS source sees (GET /api/admin/feeds/coverage).
source_sightings: Dict[str, Dict[str, dict]] = {}


def _record_source_sighting(source: str, mmsi: str, name: Optional[str] = None) -> None:
    if not mmsi:
        return
    bucket = source_sightings.setdefault(source, {})
    entry = bucket.setdefault(mmsi, {"first_seen": datetime.now(timezone.utc), "reports": 0})
    entry["last_seen"] = datetime.now(timezone.utc)
    entry["reports"] += 1
    if name:
        entry["name"] = name


def _record_live_ais_event(mmsi: str) -> None:
    """Record that a real (non-demo, non-filtered) AIS vessel update arrived."""
    if not mmsi or mmsi in _demo_mmsi_set():
        return
    live_ais_state["last_seen"] = datetime.now(timezone.utc)
    live_ais_state["lines_received"] = int(live_ais_state.get("lines_received") or 0) + 1
    live_ais_state["last_mmsi"] = mmsi


def _has_live_ais_traffic() -> bool:
    """Return True if any real AIS vessel exists in the active set OR has been seen recently."""
    if live_ais_state.get("last_seen") is not None:
        return True
    demo_set = _demo_mmsi_set()
    for m in active_vessels.keys():
        if m in demo_set:
            continue
        if is_mmsi_blocked(m):
            continue
        return True
    return False


def _should_suppress_demo_vessels() -> bool:
    """Resolve whether demo vessels should be hidden from /api/vessels right now."""
    if DEMO_VESSELS_MODE == "off" or not demo_vessels_active:
        return True
    if DEMO_VESSELS_MODE == "on":
        return False
    # auto: hide demo vessels as soon as real AIS traffic is available
    return _has_live_ais_traffic()


@api_router.get("/admin/feeds/coverage")
async def admin_feed_coverage(request: Request, hours: float = 24.0):
    """Compare which vessels each AIS source has seen (admin only).

    For the source trial: unique MMSIs per source in the window, how many
    only that source saw, and the overlap. In-memory since server start."""
    await require_admin(request)
    since = datetime.now(timezone.utc) - timedelta(hours=max(0.1, min(hours, 24 * 30)))
    seen = {
        src: {m: e for m, e in bucket.items() if e.get("last_seen") and e["last_seen"] >= since}
        for src, bucket in source_sightings.items()
    }
    sets = {src: set(v) for src, v in seen.items()}
    union = set().union(*sets.values()) if sets else set()
    sources = {}
    for src, mmsis in sets.items():
        others = set().union(*(v for k, v in sets.items() if k != src)) if len(sets) > 1 else set()
        sources[src] = {
            "unique_vessels": len(mmsis),
            "only_this_source": len(mmsis - others),
            "reports": sum(e.get("reports", 0) for e in seen[src].values()),
        }
    return {
        "window_hours": hours,
        "all_sources_vessels": len(union),
        # Overlap only means something with two or more sources reporting.
        "seen_by_every_source": len(set.intersection(*sets.values())) if len(sets) > 1 else None,
        "sources": sources,
        "aisstream": {k: v for k, v in _aisstream.status.items()},
        "vessels": sorted(
            ({"mmsi": m, "name": next((seen[s][m].get("name") for s in seen if m in seen[s] and seen[s][m].get("name")), None),
              "sources": sorted(s for s in sets if m in sets[s])} for m in union),
            key=lambda v: (v["name"] or "~", v["mmsi"]),
        ),
    }


@api_router.get("/admin/vessels/live-status")
async def admin_live_ais_status(request: Request):
    """Return live-AIS state + demo suppression decision (admin only)."""
    admin = await require_admin(request)
    last_seen = live_ais_state.get("last_seen")
    return {
        "demo_mode": DEMO_VESSELS_MODE,
        "demo_vessels_suppressed": _should_suppress_demo_vessels(),
        "live_ais_seen": _has_live_ais_traffic(),
        "live_ais_lines_received": int(live_ais_state.get("lines_received") or 0),
        "live_ais_last_mmsi": live_ais_state.get("last_mmsi"),
        "live_ais_last_seen": last_seen.isoformat() if last_seen else None,
        "vessel_stale_seconds": VESSEL_STALE_SECONDS,
        "requested_by": admin["email"],
    }


def _vessel_timestamp(vessel) -> Optional[datetime]:
    """Best-effort timestamp for a vessel object (Pydantic model or dict)."""
    ts = None
    if hasattr(vessel, "timestamp"):
        ts = getattr(vessel, "timestamp", None)
    elif isinstance(vessel, dict):
        ts = vessel.get("timestamp") or vessel.get("last_update")
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _prune_stale_vessels(max_age_seconds: int = None,
                        protect_mmsis: Optional[set] = None) -> List[str]:
    """Remove vessels whose last update is older than ``max_age_seconds``.

    Demo vessels are always skipped (they refresh themselves), and any MMSIs in
    ``protect_mmsis`` are also retained.
    Returns the list of removed MMSIs.
    """
    if max_age_seconds is None:
        max_age_seconds = VESSEL_STALE_SECONDS
    if max_age_seconds <= 0:
        return []
    protect = set(protect_mmsis or set()) | _demo_mmsi_set()
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    removed: List[str] = []
    for mmsi in list(active_vessels.keys()):
        if mmsi in protect:
            continue
        ts = _vessel_timestamp(active_vessels[mmsi])
        if ts is None:
            # No timestamp = unknown age; treat as stale on first sweep to avoid
            # leaking manually-injected test data forever.
            removed.append(mmsi)
            del active_vessels[mmsi]
            continue
        if ts < cutoff:
            removed.append(mmsi)
            del active_vessels[mmsi]
    if removed:
        logger.info(f"[STALE-PRUNE] Removed {len(removed)} stale vessel(s): {removed}")
    return removed


@api_router.post("/admin/vessels/clear-stale")
async def admin_clear_stale_vessels(request: Request):
    """Force-remove vessels older than the stale window (admin only)."""
    admin = await require_admin(request)
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    max_age = int(body.get("max_age_seconds") or VESSEL_STALE_SECONDS)
    removed = _prune_stale_vessels(max_age_seconds=max_age)
    logger.info(f"[ADMIN] {admin['email']} cleared {len(removed)} stale vessels (max_age={max_age}s)")
    return {
        "success": True,
        "removed": removed,
        "removed_count": len(removed),
        "max_age_seconds": max_age,
    }


async def _repark_pruned(removed: List[str]) -> List[str]:
    """A parked boat sends no updates, so the stale sweep drops it after
    VESSEL_STALE_SECONDS and it vanished from the map until the next page load.
    Put an account's boat back at its home berth when that is where it would be
    shown anyway (no real fix in the last 6 h). A boat whose recent real fix
    went quiet stays pruned, as before."""
    if not removed:
        return []
    now = datetime.now(timezone.utc)
    parked: List[str] = []
    async for owner in db.users.find({"vessels.mmsi": {"$in": removed}}, {"_id": 0, "vessels": 1}):
        for info in owner.get("vessels", []):
            mmsi = info.get("mmsi")
            if mmsi not in removed or mmsi in active_vessels:
                continue
            if (user_vessel_simulation.get(mmsi) or {}).get('enabled'):
                continue
            _, source = _home_berth.position_to_show(info, now)
            if source == "home" and await _park_at_home(mmsi):
                parked.append(mmsi)
    return parked


async def _park_all_at_home() -> List[str]:
    """At startup: every account boat whose shown position is its home berth."""
    try:
        mmsis = [v.get("mmsi") async for owner in db.users.find({"vessels.mmsi": {"$exists": True}}, {"_id": 0, "vessels": 1})
                 for v in owner.get("vessels", []) if v.get("mmsi")]
        parked = await _repark_pruned(mmsis)
        if parked:
            logger.info(f"[HOME] parked {len(parked)} boat(s) at home berth on startup")
        return parked
    except Exception as e:
        logger.warning(f"[HOME] startup parking failed: {e}")
        return []


async def stale_vessel_sweep_task():
    """Background task that periodically removes stale vessels from active_vessels."""
    if VESSEL_STALE_SECONDS <= 0 or VESSEL_STALE_SWEEP_SECONDS <= 0:
        logger.info("Stale vessel sweep disabled (VESSEL_STALE_SECONDS<=0)")
        return
    logger.info(
        f"Stale vessel sweep enabled: max_age={VESSEL_STALE_SECONDS}s, "
        f"interval={VESSEL_STALE_SWEEP_SECONDS}s"
    )
    while True:
        try:
            await asyncio.sleep(VESSEL_STALE_SWEEP_SECONDS)
            removed = _prune_stale_vessels()
            if removed:
                await _repark_pruned(removed)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in stale_vessel_sweep_task: {e}")
            await asyncio.sleep(VESSEL_STALE_SWEEP_SECONDS)


# Demo vessel toggle state (in-memory, reset on server restart)
# Off unless an admin switches them on (Settings), or the deployment is a
# sales/demo instance (RIVERWATCH_DEMO_VESSELS_MODE=on). Fake boats must never
# appear on a customer's live map by default.
demo_vessels_active = os.environ.get("RIVERWATCH_DEMO_VESSELS_MODE", "").strip().lower() == "on"
demo_vessels_paused = {}  # {mmsi: True} - paused vessels won't auto-move

# Demo vessel display mode: "auto" (hide when live AIS active), "on", "off".
# Override via env RIVERWATCH_DEMO_VESSELS_MODE. Default: "auto".
DEMO_VESSELS_MODE = (os.environ.get("RIVERWATCH_DEMO_VESSELS_MODE", "auto") or "auto").strip().lower()
if DEMO_VESSELS_MODE not in ("auto", "on", "off"):
    DEMO_VESSELS_MODE = "auto"

# Tracks the most recent timestamp of a real (non-demo) AIS vessel update.
# Used by /api/vessels to decide whether demo vessels should be suppressed.
live_ais_state = {
    "last_seen": None,        # datetime of latest live AIS line
    "lines_received": 0,      # cumulative non-demo AIS updates since startup
    "last_mmsi": None,
}

# Stale-vessel pruning window. Vessels older than this are removed from the
# active set (with exceptions for demo vessels and the configured user vessel).
VESSEL_STALE_SECONDS = int(os.environ.get("RIVERWATCH_VESSEL_STALE_SECONDS", "600"))
# How often the stale-prune loop runs.
VESSEL_STALE_SWEEP_SECONDS = int(os.environ.get("RIVERWATCH_VESSEL_STALE_SWEEP_SECONDS", "60"))

# User vessel simulation state
user_vessel_simulation = {}  # {mmsi: {enabled: bool, speed_knots: float, heading: str, river_mile: float}}

# Illinois River filter toggle and stats
illinois_filter_enabled = False  # DISABLED by default - enable in settings if needed
filter_stats = {"passed": 0, "filtered": 0}

@api_router.get("/filter/stats")
async def get_filter_stats():
    """Get Illinois River filter statistics."""
    return {
        "enabled": illinois_filter_enabled,
        "passed": filter_stats["passed"],
        "filtered": filter_stats["filtered"],
        "total": filter_stats["passed"] + filter_stats["filtered"]
    }

@api_router.post("/filter/toggle", dependencies=[Depends(require_admin)])
async def toggle_illinois_filter(request: Request):
    """Toggle Illinois River filter on/off."""
    global illinois_filter_enabled
    body = await request.json()
    illinois_filter_enabled = body.get("enabled", not illinois_filter_enabled)
    logger.info(f"Illinois River filter {'enabled' if illinois_filter_enabled else 'disabled'}")
    return {"enabled": illinois_filter_enabled}


# ============================================================================
# USER VESSEL SIMULATION
# ============================================================================

@api_router.get("/user-vessel/simulation/{mmsi}")
async def get_user_vessel_simulation(mmsi: str, request: Request = None):
    """Get user vessel simulation status."""
    await _check_session_owner(request, mmsi)
    sim = user_vessel_simulation.get(mmsi, {})
    vessel = active_vessels.get(mmsi, {})
    
    # Get current position from active_vessels
    if isinstance(vessel, dict):
        current_rm = vessel.get('river_mile', 815.0)
        current_speed = vessel.get('speed', 0)
        current_heading = vessel.get('heading', 'southbound')
    else:
        current_rm = getattr(vessel, 'river_mile', 815.0)
        current_speed = getattr(vessel, 'speed', 0)
        current_heading = getattr(vessel, 'heading', 'southbound')
    
    return {
        "mmsi": mmsi,
        "simulation_enabled": sim.get('enabled', False),
        "river_mile": sim.get('river_mile', current_rm),
        "speed_knots": sim.get('speed_knots', current_speed),
        "heading": sim.get('heading', current_heading),
        "in_active_vessels": mmsi in active_vessels
    }


@api_router.post("/user-vessel/simulation/{mmsi}")
async def set_user_vessel_simulation(mmsi: str, request: Request, user: dict = Depends(require_user)):
    """Enable/configure user vessel simulation (own boat, or admin)."""
    _require_owner(user, mmsi)
    body = await request.json()
    ais_refusal = _live_ais.refusal(mmsi)
    if body.get('enabled') and ais_refusal:
        raise HTTPException(status_code=409, detail=ais_refusal)
    
    sim = user_vessel_simulation.get(mmsi, {
        'enabled': False,
        'river_mile': 815.0,
        'speed_knots': 5.0,
        'heading': 'southbound'
    })
    
    was_on = bool(sim.get('enabled'))
    # Update simulation config
    if 'enabled' in body:
        sim['enabled'] = body['enabled']
    if 'river_mile' in body:
        sim['river_mile'] = float(body['river_mile'])
        # Moved by hand: forget any lock stop in progress.
        sim['hold_until'] = None
        sim['holding'] = False
        sim['last_lock_mile'] = None
    if 'lock_dwell_minutes' in body:
        sim['lock_dwell_minutes'] = max(0.0, float(body['lock_dwell_minutes']))
    if 'speed_knots' in body:
        sim['speed_knots'] = float(body['speed_knots'])
    if 'heading' in body:
        sim['heading'] = body['heading']
    
    user_vessel_simulation[mmsi] = sim
    
    # If enabling, create/update the vessel in active_vessels
    if sim['enabled']:
        await _update_simulated_user_vessel(mmsi, sim)
    elif was_on:
        await _park_at_home(mmsi)  # simulation turned off: back to its slip

    logger.info(f"[USER SIM] {mmsi}: enabled={sim['enabled']}, RM={sim['river_mile']}, speed={sim['speed_knots']}, heading={sim['heading']}")
    
    return {"success": True, "simulation": sim}


@api_router.post("/user-vessel/simulation/{mmsi}/stop")
async def stop_user_vessel_simulation(mmsi: str, user: dict = Depends(require_user)):
    """Stop user vessel simulation (own boat, or admin)."""
    _require_owner(user, mmsi)
    was_on = (user_vessel_simulation.get(mmsi) or {}).get('enabled')
    if mmsi in user_vessel_simulation:
        user_vessel_simulation[mmsi]['enabled'] = False
    if was_on:
        await _park_at_home(mmsi)  # back to its slip, if it has one
        logger.info(f"[USER SIM] {mmsi}: simulation stopped")
    return {"success": True, "mmsi": mmsi, "enabled": False}


async def _update_simulated_user_vessel(mmsi: str, sim: dict):
    """Update/create the simulated user vessel in active_vessels."""
    # The boat came up on live AIS: its transponder position wins, so the
    # simulation stops writing over it.
    if _live_ais.on_live_ais(mmsi):
        return

    rm = sim['river_mile']
    # Held at a lock (waiting / locking through): stopped, like a real boat.
    speed = 0.0 if sim.get('holding') else sim['speed_knots']
    heading = sim['heading']

    # Get coordinates from river mile
    coords = river_mile_to_coords(rm)
    if coords:
        lat, lon = coords
    else:
        lat, lon = 44.74, -92.85  # Default to Lock 2 area
    
    # Calculate course from heading
    course = 0 if heading == 'northbound' else 180
    
    # Get existing vessel name from cache or active_vessels
    name = "Your Vessel"
    if mmsi in vessel_static_cache:
        name = vessel_static_cache[mmsi].get('name', name)
    elif mmsi in active_vessels:
        v = active_vessels[mmsi]
        name = v.get('name', name) if isinstance(v, dict) else getattr(v, 'name', name)
    
    vessel = {
        "mmsi": mmsi,
        "name": name,
        "lat": lat,
        "lon": lon,
        "speed": speed,
        "course": course,
        "heading": heading,
        "heading_direction": heading,
        "direction": "upriver" if heading == "northbound" else "downriver",
        "river_mile": round(rm, 1),
        "is_user_vessel": True,
        "is_simulated": True,
        "ship_type": 37,  # Pleasure craft
        "nav_status": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    active_vessels[mmsi] = vessel

    # Push to open dashboards like any AIS update (each viewer's own boat is
    # marked per session). Without this the map kept the boat where it was
    # when the page loaded, while the API had it miles further on.
    v_dict = prepare_vessel_for_output(vessel, mmsi)
    v_dict['source'] = 'SIM'
    await ais_manager._broadcast_vessel_update(v_dict)

    # Broadcast to raw data subscribers
    await broadcast_demo_nmea(mmsi, lat, lon, speed, course)

@api_router.get("/demo-vessels/status")
async def get_demo_vessels_status():
    """Get current demo vessel simulation status."""
    return {
        "enabled": demo_vessels_active,
        "mode": DEMO_VESSELS_MODE,
        # auto mode: hidden while real AIS traffic is flowing even if enabled
        "hidden_by_live_traffic": demo_vessels_active and DEMO_VESSELS_MODE == "auto" and _has_live_ais_traffic(),
        "vessels": list(DEMO_VESSELS.keys()) if demo_vessels_active else [],
        "paused": list(demo_vessels_paused.keys())
    }


@api_router.get("/demo-vessels")
async def get_demo_vessels():
    """Get current demo vessel data for editing."""
    demo_data = []
    for vessel_id, config in DEMO_VESSELS.items():
        mmsi = config["mmsi"]
        # Get current position from active_vessels if available
        current = active_vessels.get(mmsi, {})
        is_paused = mmsi in demo_vessels_paused
        if isinstance(current, dict):
            demo_data.append({
                "id": vessel_id,
                "mmsi": mmsi,
                "name": current.get("name", config["name"]),
                "river_mile": current.get("river_mile", config["start_rm"]),
                "lat": current.get("lat"),
                "lon": current.get("lon"),
                "speed": current.get("speed", config["speed_knots"]),
                "heading": current.get("heading", "southbound"),
                "barge_count": current.get("barge_count", config["barge_count"]),
                "paused": is_paused,
            })
        else:
            # Pydantic model
            demo_data.append({
                "id": vessel_id,
                "mmsi": mmsi,
                "name": getattr(current, "name", config["name"]),
                "river_mile": getattr(current, "river_mile", config["start_rm"]),
                "lat": getattr(current, "lat", None),
                "lon": getattr(current, "lon", None),
                "speed": getattr(current, "speed", config["speed_knots"]),
                "heading": getattr(current, "heading", "southbound"),
                "barge_count": getattr(current, "barge_count", config["barge_count"]),
                "paused": is_paused,
            })
    return {"demo_vessels": demo_data, "enabled": demo_vessels_active}


@api_router.post("/demo-vessels/{mmsi}/position", dependencies=[Depends(require_admin)])
async def update_demo_vessel_position(mmsi: str, request: Request):
    """Manually update a demo vessel's position for testing."""
    # Verify this is a demo vessel
    is_demo = any(config["mmsi"] == mmsi for config in DEMO_VESSELS.values())
    if not is_demo:
        raise HTTPException(status_code=400, detail="Not a demo vessel")
    
    body = await request.json()
    
    if mmsi not in active_vessels:
        raise HTTPException(status_code=404, detail="Demo vessel not active")
    
    vessel = active_vessels[mmsi]
    
    # Update position fields
    if isinstance(vessel, dict):
        if "river_mile" in body:
            vessel["river_mile"] = float(body["river_mile"])
            # Estimate lat/lon from river mile
            coords = river_mile_to_coords(body["river_mile"])
            if coords:
                vessel["lat"] = coords[0]
                vessel["lon"] = coords[1]
        if "lat" in body:
            vessel["lat"] = float(body["lat"])
        if "lon" in body:
            vessel["lon"] = float(body["lon"])
        if "speed" in body:
            vessel["speed"] = float(body["speed"])
        if "heading" in body:
            vessel["heading"] = body["heading"]
            vessel["heading_direction"] = body["heading"]
            vessel["direction"] = "upriver" if body["heading"] == "northbound" else "downriver"
        if "barge_count" in body:
            vessel["barge_count"] = int(body["barge_count"])
        vessel["timestamp"] = datetime.now(timezone.utc).isoformat()
    else:
        # Pydantic model - need to replace
        if "river_mile" in body:
            vessel.river_mile = float(body["river_mile"])
            coords = river_mile_to_coords(body["river_mile"])
            if coords:
                vessel.lat = coords[0]
                vessel.lon = coords[1]
        if "lat" in body:
            vessel.lat = float(body["lat"])
        if "lon" in body:
            vessel.lon = float(body["lon"])
        if "speed" in body:
            vessel.speed = float(body["speed"])
        if "heading" in body:
            vessel.heading = body["heading"]
        if "barge_count" in body:
            vessel.barge_count = int(body["barge_count"])
    
    logger.info(f"[DEMO] Updated {mmsi} position: RM {body.get('river_mile')}, heading {body.get('heading')}")
    
    # Pause auto-movement for this vessel (manual control mode)
    demo_vessels_paused[mmsi] = True
    
    return {"success": True, "mmsi": mmsi, "updated": body, "paused": True}


@api_router.post("/demo-vessels/{mmsi}/resume", dependencies=[Depends(require_admin)])
async def resume_demo_vessel(mmsi: str):
    """Resume auto-movement for a demo vessel."""
    global demo_vessels_paused
    
    if mmsi in demo_vessels_paused:
        del demo_vessels_paused[mmsi]
        logger.info(f"[DEMO] Resumed auto-movement for {mmsi}")
        return {"success": True, "mmsi": mmsi, "paused": False}
    
    return {"success": True, "mmsi": mmsi, "paused": False, "message": "Vessel was not paused"}


@api_router.post("/demo-vessels/resume-all", dependencies=[Depends(require_admin)])
async def resume_all_demo_vessels():
    """Resume auto-movement for all demo vessels."""
    global demo_vessels_paused
    count = len(demo_vessels_paused)
    demo_vessels_paused.clear()
    logger.info(f"[DEMO] Resumed auto-movement for all demo vessels")
    return {"success": True, "resumed_count": count}


@api_router.post("/demo-vessels/toggle")
async def toggle_demo_vessels(request: Request):
    """Toggle demo vessel simulation on/off. Admin only: it changes what
    every viewer sees."""
    global demo_vessels_active
    
    user = await require_admin(request)
    
    body = await request.json()
    enabled = body.get("enabled", not demo_vessels_active)
    
    demo_vessels_active = enabled
    
    if not enabled:
        # Remove demo vessels from active_vessels
        for vessel_id, config in DEMO_VESSELS.items():
            mmsi = config["mmsi"]
            if mmsi in active_vessels:
                del active_vessels[mmsi]
        logger.info(f"[DEMO] Demo vessels disabled by user {user['email']}")
    else:
        logger.info(f"[DEMO] Demo vessels enabled by user {user['email']}")
    
    return {"success": True, "enabled": demo_vessels_active}


# =============================================================================
# SESSION MANAGER - Strict isolation by MMSI
# =============================================================================
class SessionManager:
    """
    Manages isolated sessions by MMSI.
    
    CRITICAL: Each MMSI is a completely separate session.
    - Settings are stored per-MMSI
    - Vessel positions are stored per-MMSI
    - WebSocket subscriptions track their MMSI
    - No data leaks between sessions
    """
    
    def __init__(self):
        # Active sessions: {mmsi: session_data}
        self._sessions: Dict[str, dict] = {}
        # WebSocket to MMSI mapping: {websocket_id: mmsi}
        self._ws_sessions: Dict[int, str] = {}
        
    def create_session(self, mmsi: str) -> dict:
        """Create or get a session for an MMSI."""
        if not mmsi:
            raise ValueError("MMSI is required for session")
        
        mmsi = str(mmsi).strip()
        
        if mmsi not in self._sessions:
            self._sessions[mmsi] = {
                "mmsi": mmsi,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_active": datetime.now(timezone.utc).isoformat(),
                "websocket_count": 0
            }
            logger.info(f"[SESSION:{mmsi}] New session created")
        
        return self._sessions[mmsi]
    
    def get_session(self, mmsi: str) -> Optional[dict]:
        """Get session data for an MMSI."""
        return self._sessions.get(str(mmsi).strip())
    
    def update_session_activity(self, mmsi: str):
        """Update last active time for a session."""
        mmsi = str(mmsi).strip()
        if mmsi in self._sessions:
            self._sessions[mmsi]["last_active"] = datetime.now(timezone.utc).isoformat()
    
    def register_websocket(self, ws_id: int, mmsi: str):
        """Register a WebSocket connection with an MMSI session."""
        mmsi = str(mmsi).strip()
        self._ws_sessions[ws_id] = mmsi
        if mmsi in self._sessions:
            self._sessions[mmsi]["websocket_count"] += 1
        logger.info(f"[SESSION:{mmsi}] WebSocket {ws_id} registered. Active connections: {self._sessions.get(mmsi, {}).get('websocket_count', 0)}")
    
    def unregister_websocket(self, ws_id: int):
        """Unregister a WebSocket connection."""
        mmsi = self._ws_sessions.pop(ws_id, None)
        if mmsi and mmsi in self._sessions:
            self._sessions[mmsi]["websocket_count"] = max(0, self._sessions[mmsi]["websocket_count"] - 1)
            logger.info(f"[SESSION:{mmsi}] WebSocket {ws_id} unregistered. Active connections: {self._sessions[mmsi]['websocket_count']}")
        return mmsi
    
    def get_mmsi_for_websocket(self, ws_id: int) -> Optional[str]:
        """Get the MMSI associated with a WebSocket."""
        return self._ws_sessions.get(ws_id)
    
    def get_active_sessions(self) -> List[dict]:
        """Get list of active sessions (for admin/debugging)."""
        return [
            {
                "mmsi": mmsi,
                "websocket_count": data.get("websocket_count", 0),
                "last_active": data.get("last_active")
            }
            for mmsi, data in self._sessions.items()
        ]

# Global session manager instance
session_manager = SessionManager()


# =============================================================================
# VESSEL DATA STORE - Isolated by MMSI
# =============================================================================
class VesselDataStore:
    """
    Stores vessel position data.
    
    NOTE: Vessel positions from AIS feed are SHARED (everyone sees all vessels).
    But "user vessel" status is determined PER-SESSION based on MMSI.
    """
    
    def __init__(self):
        # All vessels from AIS: {mmsi: vessel_data}
        self._vessels: Dict[str, dict] = {}
    
    def update_vessel(self, mmsi: str, vessel_data: dict):
        """Update vessel data (from AIS or manual position)."""
        mmsi = str(mmsi).strip()
        self._vessels[mmsi] = vessel_data
    
    def get_vessel(self, mmsi: str) -> Optional[dict]:
        """Get vessel data by MMSI."""
        return self._vessels.get(str(mmsi).strip())
    
    def get_all_vessels(self) -> Dict[str, dict]:
        """Get all vessels (for map display)."""
        return self._vessels.copy()
    
    def get_vessels_for_session(self, session_mmsi: str) -> List[dict]:
        """
        Get all vessels with is_user_vessel flag set correctly for this session.
        
        CRITICAL: The is_user_vessel flag is determined by comparing each vessel's
        MMSI against the SESSION's MMSI. This ensures each session sees their own
        vessel highlighted.
        """
        session_mmsi = str(session_mmsi).strip()
        result = []
        
        for mmsi, vessel in self._vessels.items():
            vessel_copy = vessel.copy()
            # EXPLICIT SESSION ISOLATION: Only mark as user vessel if MMSIs match
            vessel_copy["is_user_vessel"] = (mmsi == session_mmsi)
            result.append(vessel_copy)
        
        return result
    
    def remove_vessel(self, mmsi: str):
        """Remove a vessel from the store."""
        self._vessels.pop(str(mmsi).strip(), None)

# NOTE: We'll use active_vessels dict for backward compatibility
# but vessel_data_store provides the session-aware methods

# =============================================================================

# MMSI numbers to permanently filter out (test beacons, known noise)
FILTERED_MMSI = {
    "2339005",   # Boat Beacon UK test signal
}

# User-blocked MMSIs (loaded from database on startup)
user_blocked_mmsi: set = set()

# Lock positions (River Mile markers) - All Upper Mississippi Locks (1-27, excluding 23 which was never built)
# LOCKS comes from config.py (single source of truth)

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

# Cache for USACE Lock Queue data (vessel info with barge counts)
usace_lock_queue_cache = {
    "data": {},  # {mmsi: {vessel_name, num_barges, direction, lock_id, ...}}
    "last_updated": None,
    "cache_duration_seconds": 900  # 15 minutes (matches USACE update interval)
}

# Upper Mississippi lock numbers for USACE API
# UPPER_MISS_LOCKS comes from config.py

# Vessel Lock Passage Tracking
# Tracks vessels as they approach and transit locks to calculate real lockage times
# Structure: {mmsi: {lock_id: {state, arrival_time, entry_time, direction, ...}}}
vessel_lock_tracking: Dict[str, Dict[str, dict]] = {}

# Distance thresholds for lock tracking (in river miles)
LOCK_APPROACH_DISTANCE = 2.0  # Start tracking when within 2 miles
LOCK_CHAMBER_DISTANCE = 0.3   # Consider "in chamber" when within 0.3 miles
LOCK_CLEARED_DISTANCE = 1.5   # Consider cleared when 1.5 miles past lock

# AIS-inferred lockage dwell detector
# A vessel sitting inside ±LOCK_DWELL_DISTANCE_RM at or below LOCK_DWELL_MAX_SPEED_KT
# for at least LOCK_DWELL_MIN_SECONDS is treated as undergoing a lockage and gets
# a record written to db.lockage_history with source="ais_inferred".
LOCK_DWELL_DISTANCE_RM = 0.2
LOCK_DWELL_MAX_SPEED_KT = 0.3
LOCK_DWELL_MIN_SECONDS = 60
LOCK_DWELL_EXIT_DISTANCE_RM = 0.4

# Open dwell sessions: { (mmsi, lock_id): {start_time, last_seen, vessel_name, direction_at_entry} }
ais_dwell_sessions: Dict[tuple, dict] = {}

# Cache for vessel static data (names, ship types, dimensions)
# AIS sends position data frequently (every 2-10s) but static data only every 6 minutes
# This cache persists names once we receive them from Type 5 or Type 24 messages
vessel_static_cache: Dict[str, dict] = {}


# =============================================================================
# AIS Connection Manager - Singleton Pattern
# =============================================================================
# This class manages a SINGLE long-lived TCP connection to the AIS feed.
# All frontend clients share this connection via WebSocket subscriptions.
# =============================================================================

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
        self._subscribers: dict = {}  # {websocket: {"mmsi": str, "boat_name": str}} - per-user tracking
        self._lock = asyncio.Lock()
        self._should_run: bool = False
        self._reconnect_delay: float = 1.0  # Start with 1 second
        self._max_reconnect_delay: float = 60.0  # Max 60 seconds
        self._last_data_time: Optional[datetime] = None
        self._gps_update_count: int = 0
        
    @property
    def is_connected(self) -> bool:
        return self._connected and self._writer is not None
    
    @property
    def config(self) -> Optional[dict]:
        return self._config
    
    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
    
    def get_status(self) -> dict:
        """Get current connection status."""
        return {
            "connected": self._connected,
            "config": self._config,
            "subscriber_count": len(self._subscribers),
            "last_data_time": self._last_data_time.isoformat() if self._last_data_time else None,
            "reconnect_delay": self._reconnect_delay
        }
    
    async def configure(self, ip_address: str, port: int, user_mmsi_param: str = "", boat_name: str = ""):
        """
        Configure and start the AIS connection.
        If already connected with different config, reconnects.
        
        NOTE: user_mmsi_param is stored per-connection config but NOT in a global variable.
        Each WebSocket subscriber tracks its own MMSI for session isolation.
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
            if user_mmsi_param:
                session_manager.create_session(user_mmsi_param)
            
            # Pre-populate user vessel in cache
            if user_mmsi_param and boat_name:
                vessel_static_cache[user_mmsi_param] = {
                    'name': boat_name,
                    'is_user': True
                }
                logger.info(f"[SESSION:{user_mmsi_param}] Pre-cached vessel name: {boat_name}")
            
            # Check if config changed (ignore user_mmsi for connection comparison)
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
            self._reconnect_delay = 1.0  # Reset backoff on new config
            
            # Start connection
            await self._connect()
            
            return self._connected
    
    async def _connect(self):
        """Internal method to establish TCP connection using asyncio streams."""
        if not self._config:
            logger.warning("Cannot connect: no config set")
            return
        
        # Close existing connection
        await self._close_connection()
        
        ip = self._config["ip_address"]
        port = self._config["port"]
        
        try:
            logger.info(f"Connecting to AIS feed at {ip}:{port}...")
            
            # Use asyncio.open_connection for non-blocking connect
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=10.0
            )
            
            self._connected = True
            self._last_data_time = datetime.now(timezone.utc)
            self._reconnect_delay = 1.0  # Reset backoff on success
            
            logger.info(f"✅ Connected to AIS feed at {ip}:{port}")
            
            # Notify all subscribers
            # Broadcast goes to every viewer: no feed address (it's the admin's phone/receiver).
            await self._broadcast_status("connected", "Connected to AIS feed")
            
            # One read loop per connection. Stop the previous connection's loop
            # so it can't mistake our own close for a remote hang-up and
            # schedule a reconnect that would tear down this new connection.
            old_task = self._read_task
            if old_task and not old_task.done() and old_task is not asyncio.current_task():
                old_task.cancel()
            self._read_task = asyncio.create_task(self._read_loop(self._reader))
                
        except asyncio.TimeoutError:
            logger.error(f"Connection timeout to {ip}:{port}")
            self._connected = False
            await self._broadcast_status("error", "AIS feed: connection timed out")
            await self._schedule_reconnect()
            
        except ConnectionRefusedError:
            logger.error(f"Connection refused by {ip}:{port}")
            self._connected = False
            await self._broadcast_status("error", "AIS feed: connection refused")
            await self._schedule_reconnect()
            
        except OSError as e:
            logger.error(f"OS error connecting to AIS feed: {e}")
            self._connected = False
            await self._broadcast_status("error", "AIS feed: connection failed")
            await self._schedule_reconnect()
            
        except Exception as e:
            logger.error(f"Failed to connect to AIS feed: {e}")
            self._connected = False
            await self._broadcast_status("error", "AIS feed: connection failed")
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
        
        # Cancel any existing reconnect task
        if self._reconnect_task and not self._reconnect_task.done():
            return  # Already scheduled
        
        async def reconnect_after_delay():
            logger.info(f"Scheduling reconnect in {self._reconnect_delay:.1f}s...")
            await asyncio.sleep(self._reconnect_delay)
            
            # Increase backoff for next time (exponential with cap)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
            
            # Clear our own handle first: if _connect() fails it calls
            # _schedule_reconnect() again, which would otherwise see this
            # still-running task as "already scheduled" and stop retrying.
            self._reconnect_task = None
            # Something else (Settings, manual reconnect) may have reconnected
            # while we slept; never replace a healthy connection.
            if self._should_run and not self._connected:
                await self._connect()
        
        self._reconnect_task = asyncio.create_task(reconnect_after_delay())
    
    async def _read_loop(self, reader=None):
        """Main loop for reading AIS data from one TCP connection.

        `reader` pins the loop to the connection it was started for. If the
        manager has since moved to a new connection, this loop exits quietly
        instead of reporting a disconnect or scheduling a reconnect."""
        logger.info("Starting AIS read loop")
        reader = reader or self._reader

        while self._should_run and self._connected and self._reader is reader and reader:
            try:
                # Read a line using asyncio (non-blocking)
                try:
                    line_bytes = await asyncio.wait_for(
                        reader.readline(),
                        timeout=30.0  # 30 second timeout for each line
                    )
                    
                    if reader is not self._reader:
                        break  # superseded by a newer connection
                    if not line_bytes:
                        # Empty read = connection closed by remote
                        logger.warning("AIS connection closed by remote host (EOF)")
                        self._connected = False
                        await self._broadcast_status("disconnected", "Connection closed by remote host")
                        await self._schedule_reconnect()
                        break
                    
                    line = line_bytes.decode('ascii', errors='ignore').strip()
                    self._last_data_time = datetime.now(timezone.utc)
                    
                    if line:
                        await self._process_line(line)
                        
                except asyncio.TimeoutError:
                    # No data for 30 seconds, check if connection is stale
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
            except Exception as e:
                if reader is not self._reader:
                    break  # our own close of a superseded connection
                logger.error(f"Error in AIS read loop: {e}")
                self._connected = False
                await self._broadcast_status("error", "AIS feed: read error")
                await self._schedule_reconnect()
                break
        
        logger.info("AIS read loop ended")
    
    async def _apply_static_to_active(self, mmsi: str, static: dict):
        """Copy newly decoded static data onto an active vessel and push the update."""
        vessel = active_vessels.get(mmsi)
        if vessel is None or isinstance(vessel, dict):
            return
        changed = False
        for field in ("name", "ship_type", "length", "width", "draught", "destination", "callsign", "imo", "eta"):
            value = static.get(field)
            if value in (None, "", 0) or not hasattr(vessel, field):
                continue
            if getattr(vessel, field) != value:
                setattr(vessel, field, value)
                changed = True
        if changed:
            await self._broadcast_vessel_update(prepare_vessel_for_output(vessel, ""))

    async def _process_line(self, line: str):
        """Process a single NMEA/AIS line."""
        # NOTE: No global user_mmsi - each subscriber tracks their own MMSI
        
        # Broadcast raw line to debug subscribers
        await broadcast_raw_line(line)
        
        # Log raw data for debugging (first 100 chars)
        if len(line) > 5:
            logger.debug(f"Raw NMEA: {line[:100]}")
        
        # Get config MMSI (used for GPS data from this connection)
        config_mmsi = self._config.get("user_mmsi", "") if self._config else ""
        boat_name = self._config.get("boat_name", "") if self._config else ""
        
        # First try to parse as GPS (for user's own position)
        gps_data = parse_nmea_gps(line)
        if gps_data and config_mmsi:
            # Update vessel from GPS data - stored by MMSI
            rm = estimate_river_mile(gps_data['lat'], gps_data['lon'])
            heading = heading_with_track(config_mmsi, rm, gps_data['speed'], gps_data['course'], gps_data['lat'], gps_data['lon'])
            
            # Get name from cache or settings
            vessel_name = boat_name
            if config_mmsi in vessel_static_cache:
                vessel_name = vessel_static_cache[config_mmsi].get('name', boat_name)
            
            checkin_now = datetime.now(timezone.utc)
            vessel = VesselPosition(
                mmsi=config_mmsi,
                name=vessel_name,
                lat=gps_data['lat'],
                lon=gps_data['lon'],
                speed=gps_data['speed'],
                course=gps_data['course'],
                river_mile=rm,
                heading=heading,
                timestamp=checkin_now,
                last_ais_checkin=checkin_now.isoformat(),
                is_user_vessel=True,  # Will be recalculated per-session
                vessel_type='recreational',
            )
            
            # Store keyed by MMSI - completely isolated
            active_vessels[config_mmsi] = vessel
            
            # Throttle GPS updates (send every 5th)
            self._gps_update_count += 1
            if self._gps_update_count % 5 == 0:
                # Broadcast to all subscribers - each will get is_user_vessel based on their session
                v_dict = prepare_vessel_for_output(vessel, config_mmsi)
                v_dict['source'] = 'GPS'
                await self._broadcast_vessel_update(v_dict)
            return
        
        # Then try to parse as AIS
        vessel_data = parse_nmea_ais(line)
        if vessel_data is None and line.startswith('!AIVDM'):
            logger.debug(f"Failed to parse AIVDM: {line[:80]}")
        await self.ingest_vessel_data(vessel_data, source="feed")

    async def ingest_vessel_data(self, vessel_data, source: str = "feed"):
        """Store one decoded AIS report and push it to viewers.

        Shared by every AIS source (the phone/relay TCP feed and aisstream.io)
        so filtering, naming, lock tracking and broadcasting behave the same.
        `source` is recorded per vessel for source-coverage comparisons."""
        config_mmsi = self._config.get("user_mmsi", "") if self._config else ""

        if vessel_data and vessel_data.get('mmsi'):
            mmsi_parsed = vessel_data['mmsi']
            # Drop filtered/blocked MMSIs IMMEDIATELY after parsing (before logging
            # or touching active_vessels). This keeps test/noise beacons like the
            # Boat Beacon UK test signal (2339005) out of the active set and logs.
            if is_mmsi_blocked(mmsi_parsed):
                logger.debug(f"Dropped filtered MMSI {mmsi_parsed} (pre-store)")
                return
            logger.debug(f"Parsed AIS vessel: MMSI={mmsi_parsed}, lat={vessel_data.get('lat')}, lon={vessel_data.get('lon')}")
        elif vessel_data:
            logger.debug(f"Parsed AIS but no MMSI: {vessel_data}")
        
        if vessel_data and vessel_data.get('mmsi'):
            mmsi_parsed = vessel_data['mmsi']
            
            # Skip filtered/blocked MMSI (defense-in-depth; first check above
            # already handled this path, but kept for safety).
            if is_mmsi_blocked(mmsi_parsed):
                return
            
            # Filter out vessels not on Upper Mississippi (e.g., Illinois River)
            # Only filter if we have actual position data (some AIS messages are static data without position)
            lat = vessel_data.get('lat')
            lon = vessel_data.get('lon')
            
            # Static data message (type 5 / 24): no position. The name is already
            # in the in-memory cache; persist it so it survives restarts.
            if lat is None or lon is None:
                if vessel_data.get('_persist_to_db') and vessel_data.get('name'):
                    try:
                        await repos.vessels.save_vessel_name(
                            mmsi=mmsi_parsed,
                            name=vessel_data['name'],
                            ship_type=vessel_data.get('ship_type'),
                            source="AIS",
                        )
                    except Exception as e:
                        logger.error(f"Failed to persist vessel name to DB: {e}")
                # A vessel already on the map got its position before its name:
                # fill the name in now instead of waiting for its next position.
                await self._apply_static_to_active(mmsi_parsed, vessel_data)
                return
            
            # Own ship: an !AIVDO sentence carries this boat's MMSI. If the
            # feed has no MMSI configured yet, adopt it so the position shows
            # as "your vessel" without any manual setup.
            is_own = bool(vessel_data.get('is_own_vessel')) or (bool(config_mmsi) and mmsi_parsed == config_mmsi)
            if vessel_data.get('is_own_vessel') and self._config is not None and not config_mmsi:
                self._config['user_mmsi'] = mmsi_parsed
                config_mmsi = mmsi_parsed
                logger.info(f"Own vessel identified from !AIVDO: MMSI {mmsi_parsed}")

            # Main-channel filtering for OTHER vessels: excludes targets on
            # tributaries such as the St. Croix and Illinois River so they do not
            # affect Mississippi lock timing, traffic ahead, trip planning, or
            # speed-to-beat. Never drop the user's own boat (e.g. in a marina).
            if not is_own and not is_on_upper_mississippi(lat, lon):
                filter_stats["filtered"] += 1
                logger.debug(f"Filtered vessel {mmsi_parsed} - not on Mississippi main channel (lat={lat}, lon={lon})")
                return
            filter_stats["passed"] += 1
            
            # Calculate river mile and heading
            rm = estimate_river_mile(lat, lon)
            heading = heading_with_track(
                mmsi_parsed, rm,
                vessel_data['speed'],
                vessel_data['course'] if vessel_data.get('course_valid', True) else None,
                lat, lon,
            )
            
            # Preserve existing name if new data doesn't have one
            vessel_name = vessel_data.get('name', '')
            if not vessel_name and mmsi_parsed in active_vessels:
                vessel_name = active_vessels[mmsi_parsed].name
            
            # NOTE: is_user_vessel is determined PER-SESSION when sending to subscribers
            # Here we just store the raw data keyed by MMSI
            
            checkin_now = datetime.now(timezone.utc)
            vessel = VesselPosition(
                mmsi=mmsi_parsed,
                name=vessel_name,
                lat=vessel_data['lat'],
                lon=vessel_data['lon'],
                speed=vessel_data['speed'],
                course=vessel_data['course'],
                river_mile=rm,
                heading=heading,
                timestamp=checkin_now,
                last_ais_checkin=checkin_now.isoformat(),
                is_user_vessel=False,  # Will be set per-session when broadcasting
                vessel_type=vessel_data.get('vessel_type', 'unknown'),
                ship_type=vessel_data.get('ship_type'),
                length=vessel_data.get('length'),
                width=vessel_data.get('width'),
                draught=vessel_data.get('draught'),
                is_tow=vessel_data.get('is_tow', False),
                barge_count=vessel_data.get('barge_count'),
                tow_config=vessel_data.get('tow_config'),
                estimated_lockage_time=vessel_data.get('estimated_lockage_time'),
                turn_rate=vessel_data.get('turn_rate'),
                nav_status=vessel_data.get('nav_status'),
                nav_status_text=vessel_data.get('nav_status_text'),
                destination=vessel_data.get('destination'),
                callsign=vessel_data.get('callsign'),
                imo=vessel_data.get('imo'),
                eta=vessel_data.get('eta'),
            )
            
            # Store vessel keyed by MMSI - completely isolated
            active_vessels[vessel.mmsi] = vessel
            # Live AIS now outranks typed-in/phone/simulated positions for it.
            _live_ais.record_position(vessel.mmsi, checkin_now)

            # First real AIS vessel from the live feed → record the event so the
            # /api/vessels endpoint can hide demo vessels in 'auto' mode.
            _record_live_ais_event(vessel.mmsi)
            _record_source_sighting(source, vessel.mmsi, vessel.name)
            
            # Track vessel passage through locks
            await track_vessel_lock_passage(vessel.model_dump())
            # Also run the AIS-inferred dwell detector for lockage events
            await track_ais_inferred_lockage(vessel.model_dump())
            
            # Persist vessel name to database if we got one from AIS
            if vessel_data.get('name') and vessel_data.get('_persist_to_db'):
                try:
                    await repos.vessels.save_vessel_name(
                        mmsi=mmsi_parsed,
                        name=vessel_data['name'],
                        ship_type=vessel_data.get('ship_type'),
                        source="AIS"
                    )
                except Exception as e:
                    logger.error(f"Failed to persist vessel name to DB: {e}")
            
            # Broadcast update to all subscribers - use prepare_vessel_for_output for clean data
            v_dict = prepare_vessel_for_output(vessel, vessel.mmsi)
            v_dict['source'] = 'AIS'
            await self._broadcast_vessel_update(v_dict)
    
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
        """Broadcast vessel update to all subscribers, marking user's vessel for each."""
        disconnected = []
        vessel_mmsi = vessel_dict.get('mmsi', '')
        feed_mmsi = (self._config or {}).get('user_mmsi', '')

        for ws, user_info in list(self._subscribers.items()):
            try:
                # Create copy with user-specific is_user_vessel flag. An admin
                # with no MMSI of their own (the feed owner, e.g. on the Pi) sees
                # the feed's boat as theirs; nobody else does (session isolation).
                user_vessel_dict = vessel_dict.copy()
                user_mmsi = user_info.get('mmsi', '') or (feed_mmsi if user_info.get('admin') else '')
                user_vessel_dict['is_user_vessel'] = (vessel_mmsi == user_mmsi)
                
                await ws.send_json({"type": "vessel_update", "vessel": user_vessel_dict})
            except Exception:
                disconnected.append(ws)
        
        for ws in disconnected:
            self._subscribers.pop(ws, None)
    
    async def subscribe(self, websocket: WebSocket, user_mmsi: str = "", boat_name: str = "",
                        show_feed_address: bool = False):
        """Add a WebSocket client as a subscriber with their MMSI. The feed's
        IP:port (the admin's phone/receiver) is only shown to admins."""
        self._subscribers[websocket] = {"mmsi": user_mmsi, "boat_name": boat_name, "admin": show_feed_address}
        logger.info(f"WebSocket subscribed (MMSI: {user_mmsi}). Total subscribers: {len(self._subscribers)}")

        # Send current status
        if self._connected:
            await websocket.send_json({
                "type": "connected",
                "message": (f"Connected to {self._config['ip_address']}:{self._config['port']}"
                            if self._config and show_feed_address else "Connected to AIS feed")
            })
        else:
            await websocket.send_json({
                "type": "disconnected",
                "message": "Not connected to AIS feed"
            })
        
        # Send current vessel list - mark user's vessel (or the feed's own boat)
        mark_mmsi = user_mmsi or (self._config or {}).get('user_mmsi', '')
        vessels = []
        for mmsi, vessel in active_vessels.items():
            v_dict = prepare_vessel_for_output(vessel, mark_mmsi)
            vessels.append(v_dict)
        await websocket.send_json({"type": "vessels", "vessels": vessels})
    
    async def unsubscribe(self, websocket: WebSocket):
        """Remove a WebSocket client from subscribers."""
        if websocket in self._subscribers:
            user_info = self._subscribers.pop(websocket)
            logger.info(f"WebSocket unsubscribed (MMSI: {user_info.get('mmsi', 'unknown')}). Total subscribers: {len(self._subscribers)}")
    
    async def disconnect(self):
        """Disconnect from AIS feed and stop all tasks."""
        logger.info("Disconnecting AIS connection manager...")
        self._should_run = False
        
        # Cancel tasks
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
        
        # Close connection
        await self._close_connection()
        
        # Notify subscribers
        await self._broadcast_status("disconnected", "Disconnected from AIS feed")
        
        logger.info("AIS connection manager disconnected")


# Global singleton instance
ais_manager = AISConnectionManager()

# Models
class ConnectionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ip_address: str
    port: int = 5353
    user_mmsi: str
    boat_name: str = ""

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
    last_ais_checkin: Optional[str] = None  # ISO timestamp of most recent AIS/GPS position check-in
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
    # Where the status came from: "district_page" (official open/closed table)
    # or "recent_lockage" (USACE reported a completed lockage recently).
    status_source: Optional[str] = None

# Store active vessels
active_vessels: Dict[str, VesselPosition] = {}
# REMOVED: global user_mmsi - This was causing session bleed
# Each session now explicitly passes its MMSI for all operations


def calculate_next_lock_eta(river_mile: float, heading_direction: str, speed_knots: float) -> dict:
    """
    Calculate the next lock and ETA based on vessel position, direction, and speed.
    
    Args:
        river_mile: Current river mile position
        heading_direction: 'northbound'/'upriver' or 'southbound'/'downriver'
        speed_knots: Current speed in knots
    
    Returns:
        dict with next_lock_id, next_lock_name, next_lock_rm, distance_miles, eta_minutes
    """
    if not river_mile or not speed_knots or speed_knots < 0.1:
        return None
    
    # Normalize direction
    going_upriver = heading_direction in ['northbound', 'upriver', 'upstream']
    
    # Find the next lock in the direction of travel
    next_lock = None
    next_lock_id = None
    min_distance = float('inf')
    
    for lock_id, lock_info in LOCKS.items():
        lock_rm = lock_info["river_mile"]
        
        if going_upriver:
            # Looking for locks with HIGHER river mile (upriver/north)
            if lock_rm > river_mile:
                distance = lock_rm - river_mile
                if distance < min_distance:
                    min_distance = distance
                    next_lock = lock_info
                    next_lock_id = lock_id
        else:
            # Looking for locks with LOWER river mile (downriver/south)
            if lock_rm < river_mile:
                distance = river_mile - lock_rm
                if distance < min_distance:
                    min_distance = distance
                    next_lock = lock_info
                    next_lock_id = lock_id
    
    if not next_lock:
        return None
    
    # Calculate ETA
    # Speed is in knots, distance is in river miles (statute miles)
    # Convert knots to mph: 1 knot = 1.15078 mph
    speed_mph = speed_knots * 1.15078
    
    if speed_mph < 0.1:
        return None
    
    eta_hours = min_distance / speed_mph
    eta_minutes = int(eta_hours * 60)
    
    return {
        "next_lock_id": next_lock_id,
        "next_lock_name": next_lock["name"],
        "next_lock_rm": next_lock["river_mile"],
        "distance_miles": round(min_distance, 1),
        "eta_minutes": eta_minutes,
        "eta_display": f"{eta_minutes // 60}h {eta_minutes % 60}m" if eta_minutes >= 60 else f"{eta_minutes}m"
    }


def prepare_vessel_for_output(vessel, session_mmsi: str = None) -> dict:
    """
    Prepare a vessel for API output, enriching with USACE data or clearing stale barge info.
    
    This is the SINGLE SOURCE OF TRUTH for vessel data output.
    All endpoints and WebSocket broadcasts should use this function.
    
    CRITICAL: session_mmsi determines which vessel gets is_user_vessel=True.
    Each session sees ONLY their own vessel highlighted.
    
    Rules:
    - If USACE data exists: use authoritative barge count from USACE
    - If NO USACE data: clear ALL barge-related fields to None
    - Never show estimated/default barge counts
    - Always calculate ETA to next lock based on direction
    
    Args:
        vessel: Can be a VesselPosition model or a dict (for demo vessels)
        session_mmsi: The MMSI of the session user
    """
    # Handle both Pydantic models and dicts
    if hasattr(vessel, 'model_dump'):
        v_dict = vessel.model_dump()
        if v_dict.get('timestamp') and hasattr(v_dict['timestamp'], 'isoformat'):
            v_dict['timestamp'] = v_dict['timestamp'].isoformat()
        if v_dict.get('last_ais_checkin') and hasattr(v_dict['last_ais_checkin'], 'isoformat'):
            v_dict['last_ais_checkin'] = v_dict['last_ais_checkin'].isoformat()
    else:
        v_dict = dict(vessel)  # Copy the dict
        if v_dict.get('timestamp') and hasattr(v_dict['timestamp'], 'isoformat'):
            v_dict['timestamp'] = v_dict['timestamp'].isoformat()
        if v_dict.get('last_ais_checkin') and hasattr(v_dict['last_ais_checkin'], 'isoformat'):
            v_dict['last_ais_checkin'] = v_dict['last_ais_checkin'].isoformat()

    # Backward-compatible fallback: older/demo vessel objects may only have timestamp.
    if not v_dict.get('last_ais_checkin') and v_dict.get('timestamp'):
        v_dict['last_ais_checkin'] = v_dict['timestamp']
    
    # Get vessel MMSI
    vessel_mmsi = v_dict.get('mmsi', '')
    vessel_name = v_dict.get('name', '')
    
    # CRITICAL: Set is_user_vessel based on session MMSI match
    # This is the KEY to session isolation!
    if session_mmsi:
        v_dict['is_user_vessel'] = (str(vessel_mmsi) == str(session_mmsi))
    else:
        v_dict['is_user_vessel'] = False
    
    # Calculate ETA to next lock (for all vessels with position, direction, and speed)
    river_mile = v_dict.get('river_mile')
    heading_direction = v_dict.get('heading_direction') or v_dict.get('heading')
    speed = v_dict.get('speed', 0)
    
    if river_mile and heading_direction and speed:
        eta_info = calculate_next_lock_eta(river_mile, heading_direction, speed)
        if eta_info:
            v_dict['next_lock'] = eta_info
        else:
            v_dict['next_lock'] = None
    else:
        v_dict['next_lock'] = None
    
    # Skip USACE enrichment for demo vessels (they already have the data)
    if v_dict.get('is_demo'):
        return v_dict
    
    # Check USACE for authoritative barge data
    usace_info = get_usace_vessel_info(mmsi=vessel_mmsi, vessel_name=vessel_name)
    
    if usace_info and usace_info.get('num_barges') is not None:
        # USACE data available - use authoritative barge count
        bc = usace_info['num_barges']
        v_dict['barge_count'] = bc
        v_dict['is_tow'] = bc > 0 or v_dict.get('is_tow', False)
        v_dict['usace_source'] = True
        v_dict['usace_lock'] = usace_info.get('lock_id')
        v_dict['usace_status'] = usace_info.get('status')
        v_dict.update(_in_lock_fields(usace_info, v_dict))

        # Calculate lockage time from actual barge count
        if bc <= 6:
            v_dict['estimated_lockage_time'] = 30
        elif bc <= 9:
            v_dict['estimated_lockage_time'] = 45
        else:
            v_dict['estimated_lockage_time'] = 90 + (bc - 9) * 5
        v_dict['is_double_lockage'] = bc > 9
        
        # Estimate tow config from barge count
        if bc > 0:
            if bc <= 6:
                v_dict['tow_config'] = f"2x{(bc+1)//2}"
            elif bc <= 9:
                v_dict['tow_config'] = f"3x{(bc+2)//3}"
            else:
                v_dict['tow_config'] = f"3x{(bc+2)//3}+"
        else:
            v_dict['tow_config'] = None
    else:
        # NO USACE data - CLEAR ALL barge-related fields
        # This prevents stale data from being shown
        v_dict['barge_count'] = None
        v_dict['tow_config'] = None
        v_dict['estimated_lockage_time'] = None
        v_dict['is_double_lockage'] = False
        v_dict['usace_source'] = False
        v_dict['usace_lock'] = None
        v_dict['usace_status'] = None
        v_dict.update(_in_lock_fields(None, None) if v_dict.get('is_tow')
                      else _recreational_in_lock_fields(v_dict))
        # Keep is_tow based on AIS data (ship type, name patterns)

    return v_dict


# A boat USACE shows mid-lockage is drawn "in the lock" only if its own
# position agrees (a stale queue row must not pin a boat that has moved on).
IN_LOCK_MAX_MI = 1.0
# Pleasure boats can't be matched to a USACE row (they're logged as anonymous
# "RECREATIONAL VESSEL"), so a stopped pleasure boat right at a lock where a
# recreational lockage is under way is taken to be in it. Stopped tows logged
# at the lock (waiting or locking) sit 0.08-0.31 mi from the lock point in
# vessel_history; speed under 1.5 kn.
REC_IN_LOCK_MAX_MI = 0.31
REC_IN_LOCK_MAX_KN = 1.5
_IN_LOCK_OFF = {"in_lock": False, "in_lock_id": None, "in_lock_since": None, "in_lock_cut": None}


def _miles_between(lat1, lon1, lat2, lon2) -> float:
    p = math.radians
    a = (math.sin(p(lat2 - lat1) / 2) ** 2
         + math.cos(p(lat1)) * math.cos(p(lat2)) * math.sin(p(lon2 - lon1) / 2) ** 2)
    return 2 * 3958.8 * math.asin(math.sqrt(a))


def _lock_distance_mi(vessel: dict, lock: dict) -> Optional[float]:
    """Distance from a vessel to a lock: river miles when both are known,
    otherwise straight-line from its AIS position (river_mile is often unset)."""
    try:
        if vessel.get("river_mile") is not None and lock.get("river_mile") is not None:
            return abs(float(vessel["river_mile"]) - float(lock["river_mile"]))
        if vessel.get("lat") is not None and vessel.get("lon") is not None and lock.get("lat") is not None:
            return _miles_between(float(vessel["lat"]), float(vessel["lon"]), float(lock["lat"]), float(lock["lon"]))
    except (TypeError, ValueError):
        pass
    return None


def _locking_fields(info: dict) -> dict:
    started = _usace_lockages.parse_time(info.get("sol_date"), info.get("timezone"))
    return {"in_lock": True, "in_lock_id": info.get("lock_id"),
            "in_lock_since": started.isoformat() if started else None,
            "in_lock_cut": int(info.get("cuts_completed") or 0) + 1}


def _in_lock_fields(usace_info: Optional[dict], vessel: Optional[dict]) -> dict:
    """in_lock / in_lock_id / in_lock_since / in_lock_cut for the map, from the
    USACE queue: lockage started (start-of-lockage logged) and not finished."""
    if not usace_info or usace_info.get("status") != "locking":
        return dict(_IN_LOCK_OFF)
    lock = LOCKS.get(usace_info.get("lock_id")) or {}
    d = _lock_distance_mi(vessel or {}, lock)
    if d is not None and d > IN_LOCK_MAX_MI:
        return dict(_IN_LOCK_OFF)
    return _locking_fields(usace_info)


def _recreational_in_lock_fields(vessel: dict) -> dict:
    """A pleasure boat stopped at a lock whose USACE queue shows a recreational
    lockage in progress."""
    try:
        if float(vessel.get("speed") or 0) > REC_IN_LOCK_MAX_KN:
            return dict(_IN_LOCK_OFF)
    except (TypeError, ValueError):
        return dict(_IN_LOCK_OFF)
    for infos in usace_lock_rows.values():
        for info in infos:
            if info.get("status") != "locking" or "RECREATIONAL" not in str(info.get("vessel_name", "")).upper():
                continue
            d = _lock_distance_mi(vessel, LOCKS.get(info.get("lock_id")) or {})
            if d is not None and d <= REC_IN_LOCK_MAX_MI:
                return _locking_fields(info)
    return dict(_IN_LOCK_OFF)


def estimate_tow_info(vessel_data: dict) -> dict:
    """
    Identify if a vessel is a tow based on AIS data.
    
    IMPORTANT: We do NOT estimate barge counts anymore.
    Barge counts ONLY come from USACE LPMS data.
    
    Ship type codes (AIS):
    - 30: Fishing
    - 31-32: Towing
    - 60-69: Passenger
    - 70-79: Cargo
    - 80-89: Tanker
    """
    ship_type = vessel_data.get('ship_type', 0)
    name = (vessel_data.get('shipname', '') or vessel_data.get('name', '') or '').upper()
    
    is_tow = False
    
    # Check if it's a towing vessel by ship type
    if ship_type in [31, 32, 52]:  # Towing, Towing and length > 200m, Tug
        is_tow = True
    
    # Check name for tow indicators
    tow_keywords = ['M/V', 'MV ', 'CAPT', 'MISS', 'TUG', 'TOWBOAT', 'BARGE', 'PUSH', 'SIR ']
    if any(kw in name for kw in tow_keywords):
        is_tow = True
    
    # NO DEFAULT BARGE COUNTS - only USACE data provides this
    return {
        'is_tow': is_tow,
        'barge_count': None,  # ONLY from USACE
        'tow_config': None,   # ONLY from USACE
        'estimated_lockage_time': None,  # ONLY from USACE
        'is_double_lockage': False
    }


# The USACE lock queue service allows 5 requests per minute; above that it
# answers HTTP 200 with a JSON "Rate limit exceeded" body instead of XML.
# A background worker therefore walks the locks one at a time (USACE_SPACING_S
# apart, ~6 min per full pass) and keeps the latest rows per lock; request
# handlers only read that cache and never call USACE themselves.
USACE_SPACING_S = float(os.environ.get("USACE_SPACING_SECONDS", "13"))
usace_lock_rows: Dict[str, list] = {}       # lock_no -> active (waiting/locking) vessel infos
usace_lock_fetched_at: Dict[str, datetime] = {}


class UsaceRateLimited(Exception):
    pass


def _normalize_vessel_name(vessel_name: str) -> str:
    normalized = vessel_name.upper().replace('-', ' ').replace('/', ' ').strip()
    for prefix in ['M/V ', 'MV ', 'CAPT ', 'SIR ', 'MISS ']:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized


def _rebuild_usace_indexes() -> None:
    by_mmsi, by_name = {}, {}
    for infos in usace_lock_rows.values():
        for info in infos:
            if info.get("mmsi"):
                by_mmsi[info["mmsi"]] = info
            name = info.get("vessel_name")
            if name:
                by_name[_normalize_vessel_name(name)] = info
                by_name[name.upper()] = info
                # The forms get_usace_vessel_info used to find by scanning every
                # name per AIS boat: punctuation-normalized, and minus one prefix.
                un = name.upper().replace('-', ' ').replace('/', ' ').strip()
                by_name.setdefault(un, info)
                for prefix in ('M/V ', 'MV ', 'CAPT ', 'SIR ', 'MISS '):
                    if un.startswith(prefix):
                        by_name.setdefault(un[len(prefix):], info)
    usace_lock_queue_cache["data"] = by_mmsi
    usace_lock_queue_cache["data_by_name"] = by_name
    usace_lock_queue_cache["last_updated"] = datetime.now(timezone.utc)


def now_utc_floor() -> datetime:
    return datetime.min.replace(tzinfo=timezone.utc)


async def fetch_usace_lock(client, lock_no: str) -> int:
    """Fetch one lock's queue: refresh its active vessels and store completed lockages.

    Returns the number of active vessels. Raises UsaceRateLimited when USACE
    refuses the request."""
    import xml.etree.ElementTree as ET

    url = f"https://ndc.ops.usace.army.mil/ords/lockqueue_xml?in_river=MI&in_lock={lock_no}"
    response = await client.get(url)
    text = (response.text or "").strip()
    if response.status_code == 429 or "rate limit" in text[:200].lower():
        raise UsaceRateLimited(text[:120])
    if response.status_code != 200 or text.startswith("{"):
        logger.warning(f"USACE lock {lock_no}: HTTP {response.status_code} {text[:120]}")
        return len(usace_lock_rows.get(lock_no, []))

    rows = []
    if "<ROW>" in text:
        try:
            rows = ET.fromstring(text).findall('.//ROW')
        except ET.ParseError:
            logger.warning(f"USACE lock {lock_no}: unparseable XML")
            return len(usace_lock_rows.get(lock_no, []))

    # The feed also lists the lock's completed lockages (~30 days back).
    await _store_usace_lockages(rows, lock_no)

    def val(row, tag):
        el = row.find(tag)
        return el.text.strip() if el is not None and el.text else None

    lock_id = usace_lock_id(lock_no)

    # USACE reports each cut of a multi-cut (double) lockage as it finishes.
    # A pending row whose vessel already has a completed cut with the same
    # arrival time is therefore mid-lockage, not waiting.
    done_cuts = {}
    for row in rows:
        if val(row, 'END_OF_LOCKAGE'):
            key = (val(row, 'VESSEL_NO') or val(row, 'VESSEL_NAME'), val(row, 'ARRIVAL_DATE'))
            done_cuts.setdefault(key, []).append(val(row, 'SOL_DATE'))

    active = []
    for row in rows:
        sol, eol = val(row, 'SOL_DATE'), val(row, 'END_OF_LOCKAGE')
        if eol:
            # Completed: history only. Applying its barge count to the vessel
            # now would be stale.
            continue
        prior = done_cuts.get((val(row, 'VESSEL_NO') or val(row, 'VESSEL_NAME'), val(row, 'ARRIVAL_DATE')), [])
        if prior and not sol:
            sol = min((p for p in prior if p), key=lambda t: _usace_lockages.parse_time(t, val(row, 'TIMEZONE')) or now_utc_floor(),
                      default=None)
        try:
            num_barges = int(val(row, 'NUM_BARGES')) if val(row, 'NUM_BARGES') else None
        except ValueError:
            num_barges = None
        active.append({
            'vessel_name': val(row, 'VESSEL_NAME'),
            'vessel_no': val(row, 'VESSEL_NO'),
            'num_barges': num_barges,
            'direction': val(row, 'DIRECTION'),
            'lock_no': lock_no,
            'lock_id': lock_id,
            'arrival_date': val(row, 'ARRIVAL_DATE'),
            'sol_date': sol,
            'end_of_lockage': None,
            'status': 'locking' if sol else 'waiting',
            'cuts_completed': len(prior),
            'mmsi': val(row, 'MMSI'),
            'timezone': val(row, 'TIMEZONE'),
            'source': 'USACE_LPMS',
        })
    usace_lock_rows[lock_no] = active
    usace_lock_fetched_at[lock_no] = datetime.now(timezone.utc)
    _rebuild_usace_indexes()
    try:  # survive restarts: the worker needs ~6 min to revisit every lock
        await db.usace_queue.update_one(
            {"lock_no": lock_no},
            {"$set": {"rows": active, "fetched_at": usace_lock_fetched_at[lock_no]}},
            upsert=True,
        )
    except Exception as e:
        logger.debug(f"Could not persist USACE queue for lock {lock_no}: {e}")
    return len(active)


async def load_usace_queue_snapshot(max_age_minutes: int = 30) -> int:
    """Reload each lock's last queue at startup so the lock board isn't empty
    until the worker's first pass completes. Skips stale snapshots."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    loaded = 0
    try:
        async for doc in db.usace_queue.find({}, {"_id": 0}):
            fetched = doc.get("fetched_at")
            if fetched is not None and fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            if not fetched or fetched < cutoff or doc.get("lock_no") in usace_lock_rows:
                continue
            usace_lock_rows[doc["lock_no"]] = doc.get("rows") or []
            usace_lock_fetched_at[doc["lock_no"]] = fetched
            loaded += 1
        if loaded:
            _rebuild_usace_indexes()
    except Exception as e:
        logger.warning(f"Could not load USACE queue snapshot: {e}")
    return loaded


async def fetch_usace_lock_queue_data():
    """Current USACE queue data {mmsi: vessel_info}, as last fetched by the worker.

    Never calls USACE (see usace_refresh_task); safe to use in request handlers."""
    return usace_lock_queue_cache.get("data") or {}


# USACE lock numbers -> RiverWatch lock ids (26/27 have names in LOCKS).
_USACE_NAMED_LOCKS = {"26": "melvin_price", "27": "chain_of_rocks", "55": "lock_5a"}  # USACE codes 5A as "55"


def usace_lock_id(lock_no) -> str:
    lock_no = str(lock_no).strip().lstrip("0") or "0"   # USACE pads 1-9: "02" -> lock_2
    return _USACE_NAMED_LOCKS.get(lock_no) or f"lock_{lock_no.lower()}"


def lockage_for_output(record: dict) -> dict:
    """A lockage_history document ready for the API: lock name, UTC timestamps,
    and single/double cut info even for records written before `cuts` existed."""
    out = dict(record)
    out.pop("_id", None)
    out.setdefault("lock_name", (LOCKS.get(out.get("lock_id")) or {}).get("name"))
    cuts = out.get("cuts") or (2 if out.get("is_double_lockage") else 1)
    out["cuts"] = cuts
    out["is_double_lockage"] = cuts > 1
    for key, value in list(out.items()):
        if isinstance(value, datetime):
            # Mongo returns naive UTC; say so, or browsers read it as local time.
            out[key] = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    return out


_usace_stored: Dict[str, Dict[str, str]] = {}   # lock_id -> {record key: record signature}


async def _store_usace_lockages(rows, lock_no: str) -> int:
    """Upsert completed lockages from one lock's queue feed into lockage_history."""
    lock_id = usace_lock_id(lock_no)
    lock_name = (LOCKS.get(lock_id) or {}).get("name")
    # The feed repeats ~30 days of completed lockages on every fetch (median
    # ~220 rows per lock, every 13 s): only write rows that are new or changed
    # since this process last stored them, in one bulk write.
    seen = _usace_stored.setdefault(lock_id, {})
    ops, sigs = [], {}
    for record in _usace_lockages.completed_lockages(rows, lock_id, lock_name):
        key = _usace_lockages.record_key(record)
        k = repr(sorted(key.items(), key=lambda kv: kv[0]))
        sig = repr(sorted(record.items(), key=lambda kv: kv[0]))
        if seen.get(k) == sig:
            continue
        ops.append(UpdateOne(key, {"$set": record}, upsert=True))
        sigs[k] = sig
    if not ops:
        return 0
    try:
        await db.lockage_history.bulk_write(ops, ordered=False)
    except Exception as e:
        logger.warning(f"Could not store USACE lockages for {lock_id}: {e}")
        return 0
    seen.update(sigs)
    if len(seen) > 5000:   # the feed only carries ~30 days; keep the map bounded
        for old in list(seen)[:len(seen) - 4000]:
            seen.pop(old, None)
    return len(ops)


def get_usace_vessel_info(mmsi: str = None, vessel_name: str = None) -> Optional[dict]:
    """
    Get USACE lock queue info for a vessel by MMSI or name.
    Returns barge count and other data from the authoritative USACE source.
    
    IMPORTANT: Only returns data for vessels ACTIVELY at a lock (waiting or locking).
    Completed lockages are filtered out to prevent stale barge counts from
    being displayed for vessels that have moved on.
    """
    def is_valid_active_lockage(info: dict) -> bool:
        """Check if this is an active lockage record we should use."""
        if not info:
            return False
        # Only use waiting or locking records - skip completed
        status = info.get('status')
        if status == 'completed':
            return False
        return True
    
    # Try MMSI first
    if mmsi and usace_lock_queue_cache.get("data"):
        info = usace_lock_queue_cache["data"].get(mmsi)
        if info and is_valid_active_lockage(info):
            return info
    
    # Fall back to name matching
    if vessel_name and usace_lock_queue_cache.get("data_by_name"):
        data_by_name = usace_lock_queue_cache["data_by_name"]
        
        # Normalize the search name: uppercase, replace hyphens with spaces
        search_name = vessel_name.upper().replace('-', ' ').replace('/', ' ').strip()
        
        # Direct lookup with normalized name
        if search_name in data_by_name:
            info = data_by_name[search_name]
            if is_valid_active_lockage(info):
                return info
        
        # Try without common prefixes
        search_without_prefix = search_name
        for prefix in ['M/V ', 'MV ', 'CAPT ', 'SIR ', 'MISS ']:
            if search_name.startswith(prefix):
                search_without_prefix = search_name[len(prefix):]
                break
        
        if search_without_prefix in data_by_name:
            info = data_by_name[search_without_prefix]
            if is_valid_active_lockage(info):
                return info
        
        # (The normalized and prefix-less forms are indexed in _rebuild_usace_indexes;
        # this used to scan every queue name for every AIS boat without a match.)
    
    return None


_LOCK_NAME_RE = re.compile(
    r"\b(?:LOCK|L\s*&\s*D|L/D)\s*(?:AND\s+DAM\s*|&\s*DAM\s*)?(?:NO\.?\s*|#\s*)?(\d{1,2})\s*(A)?\b"
)


def match_lock_name(text: str) -> Optional[str]:
    """
    Map a USACE table label ("Lock and Dam 14", "L&D 5A", "Lock No. 1",
    "Melvin Price Locks and Dam") to our lock id. Whole-number matching only:
    the old substring test matched "1" inside "Lock 14".
    """
    if not text:
        return None
    t = text.upper()
    if "MELVIN PRICE" in t or "MEL PRICE" in t:
        return "melvin_price" if "melvin_price" in LOCKS else None
    if "CHAIN OF ROCKS" in t or "CHAINS OF ROCKS" in t:
        return "chain_of_rocks" if "chain_of_rocks" in LOCKS else None
    m = _LOCK_NAME_RE.search(t)
    if not m:
        return None
    lock_id = f"lock_{int(m.group(1))}{'a' if m.group(2) else ''}"
    return lock_id if lock_id in LOCKS else None


RECENT_LOCKAGE_OPEN_HOURS = 4
QUIET_LOOKBACK_DAYS = 30


def lockage_gap_note(last_exit: Optional[datetime], count: int, now: datetime,
                     lookback_days: int = QUIET_LOOKBACK_DAYS) -> Optional[str]:
    """A note for a lock with no official status whose USACE lockages have
    stopped for far longer than its usual spacing (e.g. Lock 1, Nov 2026: none
    in 17 days, other locks within a day). Never claims the lock is closed -
    USACE seasonal closures, reduced hours and outages look the same here."""
    if last_exit is None:
        return f"No lockages reported by USACE in {lookback_days} days - may be closed or on reduced hours; call the lock"
    if last_exit.tzinfo is None:
        last_exit = last_exit.replace(tzinfo=timezone.utc)
    gap_h = (now - last_exit).total_seconds() / 3600
    usual_h = lookback_days * 24 / max(count, 1)
    if gap_h < max(24.0, 6 * usual_h):
        return None
    gap = f"{int(gap_h // 24)} days" if gap_h >= 48 else f"{int(gap_h)} h"
    per_day = count / lookback_days
    usual = f"usually ~{per_day:.0f} a day" if per_day >= 1 else f"usually ~{per_day * 7:.0f} a week"
    return f"No lockages reported by USACE in {gap} ({usual}) - may be closed or on reduced hours; call the lock"


async def _infer_status_from_recent_lockages(lock_status_data: Dict[str, "LockStatus"]) -> None:
    unknown = [lid for lid, st in lock_status_data.items() if st.status == "UNKNOWN"]
    if not unknown:
        return
    since = datetime.now(timezone.utc) - timedelta(hours=RECENT_LOCKAGE_OPEN_HOURS)
    try:
        latest = await db.lockage_history.aggregate([
            {"$match": {"lock_id": {"$in": unknown}, "source": "usace_lpms", "exit_time": {"$gte": since}}},
            {"$group": {"_id": "$lock_id", "last": {"$max": "$exit_time"}}},
        ]).to_list(None)
    except Exception as e:
        logger.warning(f"Could not infer lock status from lockages: {e}")
        return
    for row in latest:
        st = lock_status_data.get(row["_id"])
        if st is None:
            continue
        last = row["last"] if row["last"].tzinfo else row["last"].replace(tzinfo=timezone.utc)
        st.status = "OPEN"
        st.status_source = "recent_lockage"
        st.closure_info = f"Lockage completed {int((datetime.now(timezone.utc) - last).total_seconds() // 60)} min ago (USACE)"

    # Still unknown: flag locks whose lockages have stopped unusually long ago
    # Only locks the USACE worker has actually fetched: before that, silence
    # in lockage_history would mean nothing (e.g. right after a fresh deploy).
    fetched = {usace_lock_id(k) for k in usace_lock_fetched_at}
    still = [lid for lid in unknown if lock_status_data[lid].status == "UNKNOWN" and lid in fetched]
    if not still:
        return
    now = datetime.now(timezone.utc)
    try:
        rows = await db.lockage_history.aggregate([
            {"$match": {"lock_id": {"$in": still}, "source": "usace_lpms",
                        "exit_time": {"$gte": now - timedelta(days=QUIET_LOOKBACK_DAYS)}}},
            {"$group": {"_id": "$lock_id", "last": {"$max": "$exit_time"}, "n": {"$sum": 1}}},
        ]).to_list(None)
    except Exception as e:
        logger.warning(f"Could not check lockage gaps: {e}")
        return
    seen = {r["_id"]: r for r in rows}
    for lid in still:
        r = seen.get(lid)
        note = lockage_gap_note(r["last"] if r else None, r["n"] if r else 0, now)
        if note:
            lock_status_data[lid].status_source = "lockage_gap"
            lock_status_data[lid].closure_info = note


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
        async with httpx.AsyncClient(timeout=30.0, headers=OUTBOUND_HEADERS) as client:
            # Try the MVR lock status page for basic open/closed status
            mvp_url = "https://www.mvp.usace.army.mil/Missions/Navigation/Locks-Dams/"
            
            # Default is UNKNOWN, never OPEN: if the status page can't be read we
            # must not tell a boater a lock is open.
            for lock_id, lock_data in LOCKS.items():
                lock_status_data[lock_id] = LockStatus(
                    lock_id=lock_id,
                    status="UNKNOWN",
                    avg_wait_minutes=None,
                    upbound_queue=0,
                    downbound_queue=0,
                    vessels_in_queue=[],
                    last_updated=datetime.now(timezone.utc).isoformat()
                )

            # MVR lock status page (Rock Island District) for open/closed status
            try:
                mvr_url = "https://www.mvr.usace.army.mil/missions/navigation/lock-status/"
                response = await client.get(mvr_url, follow_redirects=True)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    for table in soup.find_all('table'):
                        for row in table.find_all('tr'):
                            cells = row.find_all(['td', 'th'])
                            if len(cells) < 3:
                                continue
                            lock_id = match_lock_name(cells[0].get_text(" ", strip=True))
                            if not lock_id:
                                continue
                            status_cell = cells[2].get_text(" ", strip=True)
                            upper = status_cell.upper()
                            if "CLOSED" in upper:
                                lock_status_data[lock_id].status = "CLOSED"
                                lock_status_data[lock_id].closure_info = status_cell
                            elif "RESTRICT" in upper:
                                lock_status_data[lock_id].status = "RESTRICTED"
                                lock_status_data[lock_id].closure_info = status_cell
                            elif "OPEN" in upper:
                                lock_status_data[lock_id].status = "OPEN"
                            lock_status_data[lock_id].status_source = "district_page"
                            logger.debug(f"USACE status for {lock_id}: {status_cell}")
            except Exception as e:
                logger.warning(f"Could not fetch MVR lock status: {e}")

        # Locks the district status page doesn't cover (St. Paul 1-10, St. Louis
        # 24-27) stay UNKNOWN unless USACE itself reported a completed lockage
        # there recently - positive evidence the lock is operating. Never
        # assume OPEN without evidence.
        await _infer_status_from_recent_lockages(lock_status_data)

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
        
        async with httpx.AsyncClient(timeout=30.0, headers=OUTBOUND_HEADERS) as client:
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


_AVERAGES_CACHE: Dict[str, object] = {"at": None, "data": None}
_LAST_LOCKAGE_CACHE: Dict[str, object] = {"at": None, "data": None}
BOARD_INPUT_CACHE_SECONDS = 60


def _fresh(cache: dict, now: datetime) -> bool:
    return cache["at"] is not None and (now - cache["at"]).total_seconds() < BOARD_INPUT_CACHE_SECONDS


async def get_lockage_averages(lock_id: str = None) -> Dict[str, dict]:
    """All locks' averages are cached for a minute: every lock board call needs
    them, and a trip plan / departure options call the board once per lock per
    departure time (75 calls: 1.9 s, 151 Mongo reads before this). Callers
    must not mutate the result."""
    if lock_id is not None:
        return await _compute_lockage_averages(lock_id)
    now = datetime.now(timezone.utc)
    if not _fresh(_AVERAGES_CACHE, now):
        _AVERAGES_CACHE.update(at=now, data=await _compute_lockage_averages(None))
    return _AVERAGES_CACHE["data"]


async def _last_lockage_by_lock(now: datetime) -> Dict[str, datetime]:
    """Latest completed lockage per lock (60 days back), cached for a minute."""
    if _fresh(_LAST_LOCKAGE_CACHE, now):
        return _LAST_LOCKAGE_CACHE["data"]
    last_by_lock = {}
    try:
        rows = await db.lockage_history.aggregate([
            # Long window: a quiet lock (e.g. L1 late in the season) should still
            # say when it last locked, not look like it has no history.
            {"$match": {"recorded_at": {"$gte": now - timedelta(days=60)}}},
            {"$group": {"_id": "$lock_id", "last": {"$max": "$exit_time"}}},
        ]).to_list(None)
        for r in rows:
            if r.get("last"):
                last_by_lock[r["_id"]] = r["last"] if r["last"].tzinfo else r["last"].replace(tzinfo=timezone.utc)
    except Exception as e:
        logger.warning(f"Lock board: could not read last lockages: {e}")
        return last_by_lock
    _LAST_LOCKAGE_CACHE.update(at=now, data=last_by_lock)
    return last_by_lock


async def _compute_lockage_averages(lock_id: str = None) -> Dict[str, dict]:
    """
    Calculate running averages for lockage times based on historical data.
    Returns averages for tows vs recreational vessels, plus wait times.
    Uses baseline data from USACE historical statistics plus any observed passages.
    """
    # Lock-specific BASELINE ESTIMATES (hand-entered planning figures informed by
    # USACE LPMS summaries / Iowa DOT studies; not measurements). Every value
    # derived from them is flagged is_baseline=True so the UI can label it as an
    # estimate; observed passages replace them as they accumulate.
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
    
    records = await db.lockage_history.find(
        query, {"_id": 0, "lock_id": 1, "direction": 1, "lockage_duration_minutes": 1,
                "wait_time_minutes": 1, "is_tow": 1, "cuts": 1, "is_double_lockage": 1, "in_progress": 1}
    ).to_list(None)
    # A double lockage with a cut still to go would count as a short single.
    records = [r for r in records if not r.get("in_progress")]
    
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
                             "tow_waits": [], "rec_waits": [], "all_waits": [],
                             "single_times": [], "double_times": []}
        
        duration = record.get("lockage_duration_minutes")
        wait = record.get("wait_time_minutes")
        
        if duration and duration > 0:
            lock_data[key]["all_times"].append(duration)
            cuts = record.get("cuts") or (2 if record.get("is_double_lockage") else 1)
            lock_data[key]["double_times" if cuts > 1 else "single_times"].append(duration)
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
        
        # Locks 26/27 use named ids in LOCKS
        lid = {26: "melvin_price", 27: "chain_of_rocks"}.get(lock_num, f"lock_{lock_num}")
        
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
        singles = [t for d in ("upbound", "downbound") for t in lock_data.get(f"{lid}_{d}", {}).get("single_times", [])]
        doubles = [t for d in ("upbound", "downbound") for t in lock_data.get(f"{lid}_{d}", {}).get("double_times", [])]
        averages[lid]["cuts"] = {
            # Observed only (no baseline): None until there is data.
            "avg_single_lockage_minutes": round(sum(singles) / len(singles), 1) if singles else None,
            "avg_double_lockage_minutes": round(sum(doubles) / len(doubles), 1) if doubles else None,
            "single_count": len(singles),
            "double_count": len(doubles),
            "double_share": round(len(doubles) / (len(singles) + len(doubles)), 2) if (singles or doubles) else None,
        }
        averages[lid]["combined"] = {
            "avg_tow_lockage_minutes": round(avg_tow, 1),
            "avg_recreational_lockage_minutes": round(avg_rec, 1),
            "avg_tow_wait_minutes": round(avg_tow_wait, 1),
            "avg_recreational_wait_minutes": round(avg_rec_wait, 1),
            "tow_sample_count": len(all_tow_times),
            "rec_sample_count": len(all_rec_times),
            "is_baseline": len(all_tow_times) == 0 and len(all_rec_times) == 0
        }
        # Callers read the combined figures at the lock's top level
        # (avg_tow_lockage_minutes, sample_count, ...); they used to get None
        # and fall back to fixed guesses.
        all_times = all_tow_times + all_rec_times
        averages[lid].update(averages[lid]["combined"])
        averages[lid].update(averages[lid]["cuts"])
        averages[lid]["sample_count"] = len(all_times)
        averages[lid]["avg_lockage_minutes"] = round(sum(all_times) / len(all_times), 1) if all_times else None
        
        # For backwards compatibility, also set top-level values
        averages[lid]["avg_tow_lockage_minutes"] = round(avg_tow, 1)
        averages[lid]["avg_recreational_lockage_minutes"] = round(avg_rec, 1)
        averages[lid]["avg_tow_wait_minutes"] = round(avg_tow_wait, 1)
        averages[lid]["avg_recreational_wait_minutes"] = round(avg_rec_wait, 1)
        averages[lid]["sample_count"] = len(all_tow_times) + len(all_rec_times)

    # Learned lockage minutes / double chance by barge count (lock_board).
    tables = await _barge_tables()
    for lid in averages:
        if lid in tables:
            averages[lid]["by_barges"] = tables[lid]

    return averages


BARGE_TABLE_DAYS = 30
_barge_table_cache: Dict[str, object] = {"at": None, "value": {}}


async def _barge_tables() -> Dict[str, dict]:
    """Per-lock learned barge tables from the last BARGE_TABLE_DAYS of USACE
    tow lockages, refreshed every 6 h."""
    now = datetime.now(timezone.utc)
    if _barge_table_cache["at"] and now - _barge_table_cache["at"] < timedelta(hours=6):
        return _barge_table_cache["value"]
    try:
        rows = await db.lockage_history.find(
            {"source": "usace_lpms", "is_tow": True,
             "exit_time": {"$gte": (now - timedelta(days=BARGE_TABLE_DAYS)).replace(tzinfo=None)}},
            {"_id": 0, "lock_id": 1, "is_tow": 1, "barge_count": 1, "cuts": 1,
             "lockage_duration_minutes": 1, "in_progress": 1}).to_list(None)
    except Exception as e:
        logger.warning(f"Could not load lockage history for barge tables: {e}")
        return _barge_table_cache["value"]
    river = _lock_board.river_barge_stats(rows)
    by_lock: Dict[str, list] = {}
    for r in rows:
        by_lock.setdefault(r.get("lock_id"), []).append(r)
    value = {lid: _lock_board.lock_barge_table(rs, river) for lid, rs in by_lock.items() if lid}
    _barge_table_cache.update(at=now, value=value)
    return value


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
    
    if not mmsi or river_mile is None:
        return
    # Only a moving vessel can START an approach; a stopped vessel (e.g. sitting
    # in the chamber) still advances an existing passage toward "cleared".
    moving = heading in ("northbound", "southbound")

    now = datetime.now(timezone.utc)
    per_vessel = vessel_lock_tracking.setdefault(mmsi, {})

    for lock_id, lock_info in LOCKS.items():
        lock_rm = lock_info["river_mile"]
        distance_to_lock = river_mile - lock_rm  # positive = upstream (higher RM) of the lock
        abs_distance = abs(distance_to_lock)
        tracking = per_vessel.get(lock_id)

        if tracking is None:
            if not moving:
                continue
            if heading == "southbound" and 0 < distance_to_lock <= LOCK_APPROACH_DISTANCE:
                direction = "downbound"
            elif heading == "northbound" and -LOCK_APPROACH_DISTANCE <= distance_to_lock < 0:
                direction = "upbound"
            else:
                continue
            per_vessel[lock_id] = {
                "state": "approaching",
                "direction": direction,
                "arrival_time": now,
                "vessel_name": vessel.get("name", "Unknown"),
                "is_tow": is_tow,
                "barge_count": vessel.get("barge_count", 0),
            }
            logger.info(f"Vessel {mmsi} ({vessel.get('name', 'Unknown')}) approaching {lock_id} ({direction})")
            continue

        state = tracking.get("state")
        tracked_direction = tracking.get("direction")
        age_minutes = (now - tracking.get("arrival_time", now)).total_seconds() / 60

        # Give up on passages that never complete (applies to BOTH states; the
        # old ordering meant a stuck in_chamber entry lived forever).
        if age_minutes > 240:
            logger.warning(f"Abandoning stale lock tracking for {mmsi} at {lock_id} ({state})")
            del per_vessel[lock_id]
            continue

        if state == "approaching":
            if abs_distance <= LOCK_CHAMBER_DISTANCE:
                tracking["state"] = "in_chamber"
                tracking["entry_time"] = now
                tracking["wait_time_minutes"] = age_minutes
                logger.info(f"Vessel {mmsi} entering {lock_id} chamber (waited {age_minutes:.1f} min)")
            elif (tracked_direction == "downbound" and distance_to_lock > LOCK_APPROACH_DISTANCE * 1.5) or \
                 (tracked_direction == "upbound" and distance_to_lock < -LOCK_APPROACH_DISTANCE * 1.5):
                del per_vessel[lock_id]  # turned back
            elif (tracked_direction == "downbound" and distance_to_lock < -LOCK_CHAMBER_DISTANCE) or \
                 (tracked_direction == "upbound" and distance_to_lock > LOCK_CHAMBER_DISTANCE):
                del per_vessel[lock_id]  # went past without a usable chamber fix
            continue

        if state == "in_chamber":
            cleared = (
                (tracked_direction == "downbound" and distance_to_lock < -LOCK_CLEARED_DISTANCE) or
                (tracked_direction == "upbound" and distance_to_lock > LOCK_CLEARED_DISTANCE)
            )
            if cleared:
                tracking["state"] = "cleared"
                tracking["exit_time"] = now
                tracking["lockage_duration_minutes"] = (now - tracking["entry_time"]).total_seconds() / 60
                tracking["total_time_minutes"] = age_minutes
                await save_lockage_record(lock_id, tracking)
                logger.info(f"Vessel {mmsi} cleared {lock_id}: lockage={tracking['lockage_duration_minutes']:.1f}min, "
                            f"wait={tracking['wait_time_minutes']:.1f}min")
                del per_vessel[lock_id]

    if not per_vessel:
        vessel_lock_tracking.pop(mmsi, None)


async def save_lockage_record(lock_id: str, tracking: dict):
    """Save a completed lockage record to the database."""
    try:
        record = {
            "lock_id": lock_id,
            "vessel_name": tracking.get("vessel_name", "Unknown"),
            "mmsi": tracking.get("mmsi"),
            "direction": tracking.get("direction"),
            "arrival_time": tracking.get("arrival_time"),
            "entry_time": tracking.get("entry_time"),
            "exit_time": tracking.get("exit_time"),
            "wait_time_minutes": round(tracking.get("wait_time_minutes", 0), 1),
            "lockage_duration_minutes": round(tracking.get("lockage_duration_minutes", 0), 1),
            "total_time_minutes": round(tracking.get("total_time_minutes", 0), 1),
            "is_tow": tracking.get("is_tow", False),
            "barge_count": tracking.get("barge_count", 0),
            "source": tracking.get("source", "ais_state_machine"),
            "confidence": tracking.get("confidence", "medium"),
            "recorded_at": datetime.now(timezone.utc)
        }
        
        await db.lockage_history.insert_one(record)
        logger.info(f"📊 Saved lockage record for {lock_id}: {record['vessel_name']} - {record['lockage_duration_minutes']}min lockage, {record['wait_time_minutes']}min wait (source={record['source']})")
        
    except Exception as e:
        logger.error(f"Error saving lockage record: {e}")


async def track_ais_inferred_lockage(vessel: dict):
    """
    Dwell-based lockage detector.

    Opens a session when a vessel is within ±LOCK_DWELL_DISTANCE_RM of a lock
    AND moving slower than LOCK_DWELL_MAX_SPEED_KT. Closes the session and
    writes a `lockage_history` record (source="ais_inferred", confidence="medium")
    when the vessel leaves the dwell zone or accelerates above the speed
    threshold, provided the session lasted at least LOCK_DWELL_MIN_SECONDS.

    This complements `track_vessel_lock_passage` (which is approach-based) and
    is much less likely to mislabel transient passes as lockages.
    """
    mmsi = vessel.get("mmsi")
    river_mile = vessel.get("river_mile")
    speed_kt = vessel.get("speed")

    if not mmsi or river_mile is None or speed_kt is None:
        return

    now = datetime.now(timezone.utc)
    heading = (vessel.get("heading") or "").lower()
    direction = None
    if heading in ("northbound", "upriver", "upstream"):
        direction = "upbound"
    elif heading in ("southbound", "downriver", "downstream"):
        direction = "downbound"

    for lock_id, lock_info in LOCKS.items():
        lock_rm = lock_info["river_mile"]
        delta_rm = abs(river_mile - lock_rm)
        key = (mmsi, lock_id)

        in_zone = delta_rm <= LOCK_DWELL_DISTANCE_RM
        moving_slow = speed_kt <= LOCK_DWELL_MAX_SPEED_KT
        session = ais_dwell_sessions.get(key)

        # Open a new session?
        if in_zone and moving_slow and session is None:
            ais_dwell_sessions[key] = {
                "start_time": now,
                "last_seen": now,
                "vessel_name": vessel.get("name", f"MMSI {mmsi}"),
                "direction_at_entry": direction,
                "is_tow": vessel.get("is_tow", False),
                "barge_count": vessel.get("barge_count", 0),
                "min_distance_rm": delta_rm,
            }
            continue

        # Update an open session
        if session is not None:
            session["last_seen"] = now
            session["min_distance_rm"] = min(session["min_distance_rm"], delta_rm)
            session["last_direction"] = direction or session.get("last_direction")

            exited = delta_rm > LOCK_DWELL_EXIT_DISTANCE_RM
            sped_up = speed_kt > (LOCK_DWELL_MAX_SPEED_KT + 0.3)  # small hysteresis
            if exited or sped_up:
                duration = (session["last_seen"] - session["start_time"]).total_seconds()
                if duration >= LOCK_DWELL_MIN_SECONDS:
                    record_payload = {
                        "vessel_name": session.get("vessel_name", f"MMSI {mmsi}"),
                        "mmsi": mmsi,
                        "direction": session.get("last_direction") or session.get("direction_at_entry"),
                        "arrival_time": session["start_time"],
                        "entry_time": session["start_time"],
                        "exit_time": session["last_seen"],
                        "wait_time_minutes": 0,
                        "lockage_duration_minutes": duration / 60.0,
                        "total_time_minutes": duration / 60.0,
                        "is_tow": session.get("is_tow", False),
                        "barge_count": session.get("barge_count", 0),
                        "source": "ais_inferred",
                        "confidence": "medium",
                        "min_distance_rm": round(session["min_distance_rm"], 3),
                    }
                    try:
                        await save_lockage_record(lock_id, record_payload)
                    except Exception as e:
                        logger.warning(f"[ais-dwell] failed to save record for {lock_id}/{mmsi}: {e}")
                ais_dwell_sessions.pop(key, None)


def estimate_river_mile(lat: float, lon: float) -> Optional[float]:
    """
    Official river mile for a position, by snapping it to the USACE sailing
    line (services/river_geometry.py). Returns None when the position is not
    on the Mississippi (off-river, or nearer a tributary channel).
    """
    return _river_geo.river_mile(lat, lon)


def river_mile_to_coords(rm: float) -> tuple:
    """Point on the sailing line at river mile `rm` (falls back to the lock table)."""
    hit = _river_geo.coords_for_mile(rm)
    if hit is not None:
        return hit
    return _river_mile_to_coords(rm)


# Recent river miles per vessel: [(time, rm), ...] within TRACK_WINDOW.
_rm_track: Dict[str, list] = {}
TRACK_WINDOW = timedelta(minutes=15)
TRACK_MIN_MOVE_MI = 0.2


TRACK_MAX_MPH = 30.0


def heading_with_track(mmsi: Optional[str], rm: Optional[float], speed, course,
                       lat: float = None, lon: float = None, now: Optional[datetime] = None) -> str:
    """Direction of travel, preferring the vessel's own track over one compass reading.

    A single course is fragile at river bends (at RM 823 the channel briefly
    runs east-northeast, so a southerly course reads as upbound) and noisy at
    low speed. When the vessel's river mile has moved at least
    TRACK_MIN_MOVE_MI within TRACK_WINDOW, the sign of that movement decides;
    otherwise fall back to course against the local river bearing."""
    base = determine_heading(speed, course, lat, lon)
    if not mmsi or rm is None or base == "stationary":
        if mmsi and base == "stationary":
            _rm_track.pop(str(mmsi), None)
        return base
    now = now or datetime.now(timezone.utc)
    hist = _rm_track.setdefault(str(mmsi), [])
    if hist:
        # A jump no boat could make (manual repositioning, a GPS glitch) is not
        # travel: restart the track so it can't flip the direction for 15 min.
        dt_h = max((now - hist[-1][0]).total_seconds() / 3600, 0.0)
        if abs(float(rm) - hist[-1][1]) > TRACK_MAX_MPH * dt_h + 0.5:
            hist.clear()
    hist.append((now, float(rm)))
    while hist and now - hist[0][0] > TRACK_WINDOW:
        hist.pop(0)
    del hist[:-30]
    delta = hist[-1][1] - hist[0][1]
    if abs(delta) >= TRACK_MIN_MOVE_MI:
        return "northbound" if delta > 0 else "southbound"
    return base


def determine_heading(speed: float, course: float, lat: float = None, lon: float = None) -> str:
    """
    'northbound' = upbound (toward higher river mile), 'southbound' = downbound.

    Uses the river's LOCAL direction at (lat, lon). Compass course alone is wrong
    wherever the river runs east-west (it flows WEST through the Quad Cities).
    """
    return _river_geo.heading_label(speed, course, lat, lon)

def calculate_eta_to_lock(vessel_rm: float, vessel_speed_knots: float, heading: str, lock_rm: float) -> Optional[float]:
    """Calculate ETA in minutes to reach a lock. Returns None if vessel moving away."""
    # A boat off the main channel has no river mile; one such boat used to
    # 500 race-analysis and trip-plan for every user.
    if vessel_rm is None or lock_rm is None or vessel_speed_knots is None or vessel_speed_knots < 0.1:
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
    if competitor_eta_minutes is None or competitor_eta_minutes <= 0 or user_rm is None or target_lock_rm is None:
        return None
    
    distance_rm = abs(user_rm - target_lock_rm)
    
    # Check if user is heading toward the lock
    if user_heading == "northbound" and user_rm >= target_lock_rm:
        return None  # User past the lock going north
    elif user_heading == "southbound" and user_rm <= target_lock_rm:
        return None  # User past the lock going south
    
    # Required speed in MPH to arrive with enough buffer before competitor
    # Buffer time ensures user can complete lockage before tow arrives
    # If the tow arrives within the buffer there is no achievable speed: return
    # None (callers treat that as "can't arrive first") instead of dividing by
    # a 1-minute floor, which produced speeds of hundreds of mph.
    target_time_minutes = competitor_eta_minutes - buffer_minutes
    if target_time_minutes <= 0:
        return None
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

_ais_assembler = NmeaFragmentAssembler()


def vessel_data_from_decoded(decoded: dict, is_own_vessel: bool = False) -> Optional[dict]:
    """Turn one decoded AIS message (pyais field names) into RiverWatch vessel data.

    Shared by the NMEA parser and by sources that deliver already-decoded
    messages (aisstream.io), so every source gets the same static-data cache,
    tow detection and USACE enrichment. Returns None when the message yields
    nothing to store."""
    global vessel_static_cache
    if 'mmsi' not in decoded:
        return None
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

            # Static-only messages (5, 24) carry no position: hand the
            # name back so the caller can persist it to the database.
            if msg_type in (5, 24) and static_data.get('name'):
                return {
                    'mmsi': mmsi,
                    'name': static_data['name'],
                    'ship_type': static_data.get('ship_type'),
                    '_static_only': True,
                    '_persist_to_db': True,
                }

    # Handle position messages (Type 1,2,3,18,19)
    if msg_type in [1, 2, 3, 18, 19]:
        lat = decoded.get('lat')
        lon = decoded.get('lon')

        # Filter invalid positions
        if lat is None or lon is None:
            return None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        if lat == 91.0 or lon == 181.0:  # AIS "not available" values
            return None
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
            'speed': clean_sog(decoded.get('speed')),  # knots; 102.3 = n/a
            'course': clean_cog(decoded.get('course')) or 0.0,
            'course_valid': clean_cog(decoded.get('course')) is not None,
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

        # First check USACE lock queue data for authoritative barge count
        mmsi = vessel.get('mmsi', '')
        usace_info = get_usace_vessel_info(mmsi) if mmsi else None

        if usace_info and usace_info.get('num_barges') is not None:
            # Use USACE authoritative data
            vessel['barge_count'] = usace_info['num_barges']
            vessel['is_tow'] = usace_info['num_barges'] > 0
            vessel['usace_source'] = True
            vessel['usace_lock'] = usace_info.get('lock_id')
            vessel['usace_status'] = usace_info.get('status')

            # Calculate lockage time from barge count
            bc = usace_info['num_barges']
            if bc <= 6:
                vessel['estimated_lockage_time'] = 30
            elif bc <= 9:
                vessel['estimated_lockage_time'] = 45
            else:
                vessel['estimated_lockage_time'] = 90 + (bc - 9) * 5
            vessel['is_double_lockage'] = bc > 9

            # Estimate tow config from barge count
            if bc > 0:
                if bc <= 6:
                    vessel['tow_config'] = f"2x{(bc+1)//2}"
                elif bc <= 9:
                    vessel['tow_config'] = f"3x{(bc+2)//3}"
                else:
                    vessel['tow_config'] = f"3x{(bc+2)//3}+"

            logger.debug(f"Using USACE data for {mmsi}: {usace_info['num_barges']} barges")

            # (persisted once below, with or without USACE data)
        else:
            # NO USACE data - use AIS-based tow detection only
            # IMPORTANT: Clear any stale barge data - only show if USACE confirms
            tow_info = estimate_tow_info(vessel)
            vessel.update(tow_info)
            # Explicitly ensure no stale data
            vessel['barge_count'] = None
            vessel['tow_config'] = None
            vessel['estimated_lockage_time'] = None
            vessel['is_double_lockage'] = False
            vessel['usace_source'] = False
            vessel['usace_lock'] = None
            vessel['usace_status'] = None

        # Persist vessel sighting (even without USACE for tracking)
        asyncio.create_task(persist_vessel_sighting(vessel))

        return vessel
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
                    # Multi-sentence messages (type 5 static/voyage data) arrive
                    # as 2 lines; wait until all fragments are in.
                    fragments = _ais_assembler.feed(line)
                    if not fragments:
                        continue
                    msg = decode(*fragments, error_if_checksum_invalid=True)
                    decoded = msg.asdict()
                    
                    result = vessel_data_from_decoded(decoded, is_own_vessel)
                    if result is not None:
                        return result
                        
                except Exception as e:
                    logger.debug(f"Failed to parse AIS message: {e}")
                    continue
    except Exception as e:
        logger.error(f"AIS parsing error: {e}")
    return None

# API Routes
# Version identifier for debugging deployment issues
CODE_VERSION = "2026-01-20-fix-completed-lockages"

@api_router.get("/")
async def root():
    return {
        "message": "AIS Vessel Tracker API", 
        "status": "online",
        "code_version": CODE_VERSION,
        "fix_applied": "Filter out completed lockages from USACE cache"
    }

@api_router.get("/locks", response_model=List[LockInfo])
async def get_locks():
    """Get all lock positions."""
    return [
        LockInfo(id=k, name=v["name"], river_mile=v["river_mile"], lat=v["lat"], lon=v["lon"], phone=v.get("phone"))
        for k, v in LOCKS.items()
    ]

# Lock-to-lock transit times learned from USACE history (services/transits.py),
# refreshed hourly. Backtest: median arrival error 0.72 h (downbound 0.55 h).
_TRANSIT_ORDER = _transits.lock_order(LOCKS)
_transit_cache = {"stats": None, "at": None}


TRANSIT_HISTORY_DAYS = 120


async def get_transit_stats() -> dict:
    now = datetime.now(timezone.utc)
    if _transit_cache["stats"] is not None and _transit_cache["at"] and now - _transit_cache["at"] < timedelta(hours=1):
        return _transit_cache["stats"]
    try:
        # Last TRANSIT_HISTORY_DAYS only (the query had no bound and grew forever),
        # and the learning runs off the event loop (~80 ms now, linear in history).
        rows = await db.lockage_history.find(
            {"source": "usace_lpms", "in_progress": {"$ne": True},
             "arrival_time": {"$gte": (now - timedelta(days=TRANSIT_HISTORY_DAYS)).replace(tzinfo=None)}},
            {"_id": 0, "mmsi": 1, "usace_vessel_no": 1, "lock_id": 1, "direction": 1, "barge_count": 1,
             "arrival_time": 1, "exit_time": 1, "is_recreational": 1},
        ).to_list(None)

        def learn():
            s = _transits.transit_stats(_transits.transit_samples(rows, _TRANSIT_ORDER))
            s.update(_transits.dwell_stats(rows))
            s.update(_transits.continuation_stats(rows, _TRANSIT_ORDER))
            return s
        stats = await asyncio.to_thread(learn)
        _transit_cache["stats"] = stats
        _transit_cache["at"] = now
    except Exception as e:
        logger.warning(f"Could not learn transit times: {e}")
        _transit_cache["stats"] = _transit_cache["stats"] or {}
    return _transit_cache["stats"]


_APPROACHING_CACHE: Dict[str, object] = {"at": None, "data": None}
APPROACHING_CACHE_SECONDS = 60


async def approaching_by_lock(now: datetime) -> Dict[str, list]:
    """Vessels predicted to reach each lock next, from their last USACE lockage.

    Cached for a minute: every lock board request needs it, and a trip plan
    asks the board once per lock ahead. Lockages only change every few
    minutes (USACE worker cycle)."""
    at = _APPROACHING_CACHE["at"]
    if at is not None and (now - at).total_seconds() < APPROACHING_CACHE_SECONDS:
        return _APPROACHING_CACHE["data"]
    data = await _approaching_by_lock(now)
    _APPROACHING_CACHE.update(at=now, data=data)
    return data


async def _approaching_by_lock(now: datetime) -> Dict[str, list]:
    stats = await get_transit_stats()
    if not stats:
        return {}
    try:
        recent = await db.lockage_history.find(
            {"source": "usace_lpms", "exit_time": {"$gte": now - timedelta(hours=36)}},
            {"_id": 0},
        ).to_list(None)
    except Exception as e:
        logger.warning(f"Could not read recent lockages: {e}")
        return {}
    for r in recent:
        for k in ("exit_time", "arrival_time", "entry_time"):
            if isinstance(r.get(k), datetime) and r[k].tzinfo is None:
                r[k] = r[k].replace(tzinfo=timezone.utc)
    out = {}
    for lid in _TRANSIT_ORDER:
        present = set()
        for lock_no, infos in usace_lock_rows.items():
            if usace_lock_id(lock_no) == lid:
                for v in infos:
                    present.update(x for x in (v.get("mmsi"), v.get("vessel_no")) if x)
        arrivals = _transits.predicted_arrivals(lid, _TRANSIT_ORDER, stats, recent, present, now)
        lock_rm = LOCKS[lid]["river_mile"]
        for a in arrivals:
            seg_from = LOCKS.get(a["segment_from"], {}).get("river_mile")
            seg_to = LOCKS.get(a["segment_to"], {}).get("river_mile")
            a["est_river_mile"] = (round(seg_from + (seg_to - seg_from) * a["segment_progress"], 1)
                                   if seg_from is not None and seg_to is not None else None)
            a["via_lock_name"] = LOCKS.get(a["via_lock"], {}).get("name") if a.get("via_lock") else None
            a["from_lock_name"] = LOCKS.get(a["from_lock"], {}).get("name")
            for k in ("left_at", "eta", "eta_earliest", "eta_latest"):
                a[k] = a[k].isoformat()
        out[lid] = arrivals
    return out


# ---------------------------------------------------------------------------
# Wait-estimate calibration that keeps learning (services/calibration.py).
# Nightly: refit on the last 30 days of USACE lockages, score new vs current
# on the same held-out recent days, adopt only if it is more accurate and
# within sanity bounds. Every attempt is recorded in db.wait_calibration.
# ---------------------------------------------------------------------------
RECALIBRATE_EVERY = timedelta(hours=24)


def _apply_calibration(model: dict, fitted_on: str, test_mae: dict) -> None:
    _lock_board.CALIBRATION["tow"] = dict(model["tow"])
    _lock_board.CALIBRATION["recreational"] = dict(model["recreational"])
    _lock_board.CALIBRATION["fitted_on"] = fitted_on
    _lock_board.CALIBRATION["test_mae_minutes"] = dict(test_mae)


async def load_adopted_calibration() -> bool:
    try:
        doc = await db.wait_calibration.find_one({"adopted": True}, sort=[("ran_at", -1)])
    except Exception as e:
        logger.warning(f"Could not load wait calibration: {e}")
        return False
    try:  # likely-wait ranges: from the latest run that learned them
        rdoc = await db.wait_calibration.find_one({"ranges.kind": {"$exists": True}}, {"ranges": 1},
                                                  sort=[("ran_at", -1)])
        if rdoc:
            _lock_board.CALIBRATION["tow_ranges"] = rdoc["ranges"]
    except Exception as e:
        logger.warning(f"Could not load wait ranges: {e}")
    if not doc or not doc.get("model"):
        return False
    _apply_calibration(doc["model"], doc.get("fitted_on", ""), doc.get("test_mae_minutes", {}))
    logger.info(f"Wait model: using calibration learned {doc.get('ran_at')} ({doc.get('reason')})")
    return True


async def recalibrate_wait_model() -> dict:
    now = datetime.now(timezone.utc)
    rows = await db.lockage_history.find(
        {"source": "usace_lpms", "in_progress": {"$ne": True}, "arrival_time": {"$gte": now - timedelta(days=30)}},
        {"_id": 0, "lock_id": 1, "direction": 1, "barge_count": 1, "cuts": 1, "is_tow": 1, "is_recreational": 1,
         "arrival_time": 1, "entry_time": 1, "exit_time": 1, "wait_time_minutes": 1, "lockage_duration_minutes": 1},
    ).to_list(None)
    current = {"tow": dict(_lock_board.CALIBRATION["tow"]),
               "recreational": dict(_lock_board.CALIBRATION["recreational"])}
    report = await asyncio.to_thread(_calibration.recalibrate, rows, current)
    doc = {"ran_at": now, "adopted": bool(report.get("adopt")), **{k: v for k, v in report.items() if k != "adopt"}}
    if report.get("adopt"):
        fitted_on = f"{report['history_from']:%Y-%m-%d}..{report['split_at']:%Y-%m-%d}, {report['train']} USACE lockages"
        test_mae = {"tow": report["new_score"]["tow"].get("mae"),
                    "recreational": report["new_score"]["recreational"].get("mae")}
        doc.update({"fitted_on": fitted_on, "test_mae_minutes": test_mae})
        _apply_calibration(report["model"], fitted_on, test_mae)
    if report.get("ranges"):
        # Learned every run (for the model now in use), adopted or not.
        _lock_board.CALIBRATION["tow_ranges"] = report["ranges"]
    try:
        await db.wait_calibration.insert_one(doc)
    except Exception as e:
        logger.warning(f"Could not record wait calibration run: {e}")
    logger.info(f"Wait model recalibration: {'ADOPTED' if doc['adopted'] else 'kept current'} - {report.get('reason')}")
    return doc


async def wait_model_learning_task():
    await asyncio.sleep(20 * 60)  # let the USACE worker refresh history first
    while True:
        try:
            await recalibrate_wait_model()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"Wait model recalibration failed: {e}")
        try:
            await asyncio.sleep(RECALIBRATE_EVERY.total_seconds())
        except asyncio.CancelledError:
            return


@api_router.get("/admin/wait-model")
async def admin_wait_model(request: Request, runs: int = 10):
    """Current wait-estimate calibration and the latest learning runs (admin)."""
    await require_admin(request)
    docs = await db.wait_calibration.find({}, {"_id": 0}).sort("ran_at", -1).limit(max(1, min(runs, 50))).to_list(None)
    for d in docs:
        for k, v in list(d.items()):
            if isinstance(v, datetime):
                d[k] = v.isoformat()
    return {"current": _lock_board.CALIBRATION, "runs": docs}


# ---------------------------------------------------------------------------
# Arrival predictions that keep learning (services/arrival_learning.py).
# Every few minutes each lock's predicted arrivals are logged; every few hours
# they are scored against USACE arrivals and the AIS ETA correction refit
# (adopted only if it beats the current one on held-out boat trips).
# ---------------------------------------------------------------------------
ARRIVAL_SNAPSHOT_EVERY = timedelta(minutes=5)
ARRIVAL_RELEARN_EVERY = timedelta(hours=6)


async def snapshot_arrival_predictions(now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    approaching = await approaching_by_lock(now)
    live = _live_positions(now)
    barges = await _recent_barges([v["mmsi"] for v in live])
    docs = []
    for lid in LOCKS:
        appr = []
        for a in approaching.get(lid, []):
            try:
                appr.append({**a, "eta": datetime.fromisoformat(a["eta"])})
            except (KeyError, TypeError, ValueError):
                continue
        at_lock = [x for lock_no, rows in usace_lock_rows.items() if usace_lock_id(lock_no) == lid
                   for v in rows for x in (v.get("mmsi"), v.get("vessel_name"))]
        merged = _live_arrivals.merge_live_arrivals(lid, _LOCK_RMS, appr, live, now,
                                                    at_lock=at_lock, barges_by_mmsi=barges)
        docs.extend(_arrival_learning.snapshot_docs(lid, merged, now))
    if docs:
        await db.arrival_predictions.insert_many(docs)
    return len(docs)


async def load_adopted_arrival_factor() -> None:
    try:
        doc = await db.arrival_calibration.find_one({"adopted": True}, sort=[("ran_at", -1)])
    except Exception as e:
        logger.warning(f"Could not load arrival calibration: {e}")
        return
    if doc and doc.get("fitted_factor"):
        _live_arrivals.AIS_ETA_FACTOR = float(doc["fitted_factor"])
        logger.info(f"AIS arrival ETAs: factor {_live_arrivals.AIS_ETA_FACTOR} learned {doc.get('ran_at')}")


async def relearn_arrivals() -> dict:
    now = datetime.now(timezone.utc)
    preds = await db.arrival_predictions.find({"made_at": {"$gte": now - timedelta(days=30)}},
                                              {"_id": 0}).to_list(None)
    for p in preds:
        for k in ("made_at", "predicted_eta"):
            if isinstance(p.get(k), datetime) and p[k].tzinfo is None:
                p[k] = p[k].replace(tzinfo=timezone.utc)
    since = min((p["made_at"] for p in preds), default=now) - timedelta(hours=1)
    arrivals = await db.lockage_history.find(
        {"source": "usace_lpms", "arrival_time": {"$gte": since.replace(tzinfo=None)}},
        {"_id": 0, "lock_id": 1, "mmsi": 1, "vessel_name": 1, "arrival_time": 1}).to_list(None)
    for a in arrivals:
        if isinstance(a.get("arrival_time"), datetime) and a["arrival_time"].tzinfo is None:
            a["arrival_time"] = a["arrival_time"].replace(tzinfo=timezone.utc)
    def learn():   # off the event loop: grows with logged predictions (~7k/day)
        s = _arrival_learning.score(preds, arrivals, now)
        return s, _arrival_learning.fit_ais_factor(s, _live_arrivals.AIS_ETA_FACTOR), _arrival_learning.summarize(s)
    scored, report, accuracy = await asyncio.to_thread(learn)
    doc = {"ran_at": now, "logged_predictions": len(preds), "scored": len(scored),
           "accuracy": accuracy,
           "adopted": bool(report.pop("adopt")), **report}
    if doc["adopted"]:
        _live_arrivals.AIS_ETA_FACTOR = float(report["fitted_factor"])
    try:
        await db.arrival_calibration.insert_one(dict(doc))
    except Exception as e:
        logger.warning(f"Could not record arrival calibration run: {e}")
    logger.info(f"Arrival learning: {'ADOPTED' if doc['adopted'] else 'kept current'} - {doc.get('reason')}")
    return doc


async def arrival_learning_task():
    await asyncio.sleep(90)  # let the USACE worker and the AIS feed fill in
    last_learn = None
    while True:
        try:
            now = datetime.now(timezone.utc)
            await snapshot_arrival_predictions(now)
            if last_learn is None or now - last_learn >= ARRIVAL_RELEARN_EVERY:
                await relearn_arrivals()
                last_learn = now
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"Arrival learning failed: {e}")
        try:
            await asyncio.sleep(ARRIVAL_SNAPSHOT_EVERY.total_seconds())
        except asyncio.CancelledError:
            return


def _jsonable(d: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items() if k != "_id"}


@api_router.get("/admin/arrival-model")
async def admin_arrival_model(request: Request, runs: int = 10):
    """How accurate arrival predictions have been, and the learned AIS ETA
    correction (admin)."""
    await require_admin(request)
    docs = await db.arrival_calibration.find({}, {"_id": 0}).sort("ran_at", -1).limit(max(1, min(runs, 50))).to_list(None)
    return {"ais_eta_factor": _live_arrivals.AIS_ETA_FACTOR,
            "logged_predictions": await db.arrival_predictions.estimated_document_count(),
            "runs": [_jsonable(d) for d in docs]}


@api_router.post("/admin/arrival-model/relearn")
async def admin_relearn_arrivals(request: Request):
    """Score logged predictions and refit now (admin). Adopts only if better."""
    await require_admin(request)
    return _jsonable(await relearn_arrivals())


# ---------------------------------------------------------------------------
# Daily Traffic Report (services/traffic_report.py): a Central-time day of lock
# traffic from USACE lockage records, as JSON / HTML / CSV / ready-to-send .eml,
# and optionally emailed each morning (services/report_mailer.py).
# ---------------------------------------------------------------------------
REPORT_MAX_AGE_DAYS = 30  # lockage_history keeps about 30 days of USACE rows
_report_email_me_last: Dict[str, datetime] = {}
_long_single_cache: Dict[str, object] = {"at": None, "value": {}}


async def _long_single_thresholds() -> Dict[str, float]:
    """Per-lock 'unusually long single' cut-off, learned from the last 30 days
    of one-cut tow lockages at that lock; refreshed every 6 h."""
    now = datetime.now(timezone.utc)
    if _long_single_cache["at"] and now - _long_single_cache["at"] < timedelta(hours=6):
        return _long_single_cache["value"]
    history = await db.lockage_history.find(
        {"source": "usace_lpms", "is_tow": True, "cuts": 1,
         "exit_time": {"$gte": (now - timedelta(days=30)).replace(tzinfo=None)}},
        {"_id": 0, "lock_id": 1, "is_tow": 1, "cuts": 1, "lockage_duration_minutes": 1, "in_progress": 1}
    ).to_list(None)
    value = _traffic_report.long_single_thresholds(history)
    _long_single_cache.update(at=now, value=value)
    return value


async def build_traffic_report(day) -> dict:
    start, end = _traffic_report.day_bounds_utc(day)
    prior_days = 7
    fields = {"_id": 0, "lock_id": 1, "vessel_name": 1, "mmsi": 1, "direction": 1, "barge_count": 1,
              "is_tow": 1, "is_recreational": 1, "arrival_time": 1, "entry_time": 1, "exit_time": 1,
              "wait_time_minutes": 1, "lockage_duration_minutes": 1, "in_progress": 1, "cuts": 1,
              "cut_times": 1}
    naive = lambda t: t.astimezone(timezone.utc).replace(tzinfo=None)
    rows = await db.lockage_history.find(
        {"source": "usace_lpms", "exit_time": {"$gte": naive(start), "$lt": naive(end)}}, fields).to_list(None)
    prior = await db.lockage_history.find(
        {"source": "usace_lpms",
         "exit_time": {"$gte": naive(start - timedelta(days=prior_days)), "$lt": naive(start)}},
        {"_id": 0, "lock_id": 1, "in_progress": 1}).to_list(None)
    now = datetime.now(timezone.utc)
    statuses = None
    if (_traffic_report.central_today(now) - day).days <= 1:  # status is "now": only beside recent days
        statuses = {s["lock_id"]: s for s in await db.lock_status.find(
            {}, {"_id": 0, "lock_id": 1, "status": 1, "closure_info": 1}).to_list(100) if s.get("lock_id")}
    return _traffic_report.build_report(day, rows, prior, LOCKS, statuses, prior_days=prior_days, now=now,
                                        long_single_min=await _long_single_thresholds())


def _report_day(date_str: Optional[str]):
    today = _traffic_report.central_today()
    if not date_str:
        return today - timedelta(days=1)
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    if day > today or (today - day).days > REPORT_MAX_AGE_DAYS:
        raise HTTPException(status_code=400, detail=f"Reports cover the last {REPORT_MAX_AGE_DAYS} days")
    return day


@api_router.get("/reports/traffic")
async def get_traffic_report(date: Optional[str] = None, format: str = "json", download: bool = False):
    """Daily Traffic Report for a Central-time day (default: yesterday).
    format=json|html|csv|eml; download=true sends it as a file."""
    report = await build_traffic_report(_report_day(date))
    fmt = (format or "json").lower()
    if fmt == "json":
        return report
    if fmt == "html":
        body, media = _traffic_report.render_html(report, app_url=_report_mailer.app_url()), "text/html; charset=utf-8"
    elif fmt == "csv":
        body, media = _traffic_report.render_csv(report), "text/csv; charset=utf-8"
    elif fmt == "tows":  # every tow and light boat: one row per lockage
        body, media = _traffic_report.render_tows_csv(report), "text/csv; charset=utf-8"
    elif fmt == "eml":
        body, media = _traffic_report.render_eml(report, app_url=_report_mailer.app_url()), "message/rfc822"
        download = True
    else:
        raise HTTPException(status_code=400, detail="format must be json, html, csv, tows or eml")
    headers = {"Cache-Control": "no-store"}
    if download:
        name = (f"riverwatch-tows-{report['date']}.csv" if fmt == "tows"
                else _traffic_report.filename(report, fmt))
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return Response(content=body, media_type=media, headers=headers)


@api_router.get("/reports/traffic/subscription")
async def get_report_subscription(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    sub = user.get("report_subscription") or {}
    return {"daily_email": bool(sub.get("daily_email")), "email": user.get("email"),
            "email_available": _report_mailer.configured(), "send_hour_central": _report_mailer.send_hour()}


@api_router.put("/reports/traffic/subscription")
async def set_report_subscription(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json()
    daily = bool((body or {}).get("daily_email"))
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"report_subscription": {"daily_email": daily,
                                                                "updated_at": datetime.now(timezone.utc)}}})
    return {"daily_email": daily, "email_available": _report_mailer.configured()}


async def _email_report(report: dict, to: str) -> None:
    msg = _traffic_report.build_email(report, to=to, sender=_report_mailer.sender(),
                                      app_url=_report_mailer.app_url())
    await asyncio.to_thread(_report_mailer.send, msg)


@api_router.post("/reports/traffic/email-me")
async def email_me_traffic_report(request: Request, date: Optional[str] = None):
    """Email a report to the signed-in user's own address (needs SMTP set up)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not _report_mailer.configured():
        raise HTTPException(status_code=503, detail="Email isn't set up on this server. Download the report instead.")
    if not user.get("email"):
        raise HTTPException(status_code=400, detail="Your account has no email address")
    last = _report_email_me_last.get(user["user_id"])
    now = datetime.now(timezone.utc)
    if last and now - last < timedelta(minutes=1):
        raise HTTPException(status_code=429, detail="Just sent one - try again in a minute")
    _report_email_me_last[user["user_id"]] = now
    report = await build_traffic_report(_report_day(date))
    try:
        await _email_report(report, user["email"])
    except Exception as e:
        logger.error(f"[REPORT] email to {user['user_id']} failed: {e}")
        raise HTTPException(status_code=502, detail="The mail server refused the message")
    return {"sent_to": user["email"], "date": report["date"]}


async def send_daily_reports(now: Optional[datetime] = None) -> int:
    """Email yesterday's report to subscribers who haven't had it yet."""
    if not _report_mailer.configured():
        return 0
    now = now or datetime.now(timezone.utc)
    local = _traffic_report.to_central(now)
    if local.hour < _report_mailer.send_hour():
        return 0
    day = local.date() - timedelta(days=1)
    subs = await db.users.find({"report_subscription.daily_email": True},
                               {"_id": 0, "user_id": 1, "email": 1}).to_list(None)
    report, sent = None, 0
    for u in subs:
        if not u.get("email"):
            continue
        key = {"date": day.isoformat(), "user_id": u["user_id"]}
        if await db.report_sends.find_one(key):
            continue
        report = report or await build_traffic_report(day)
        try:
            await _email_report(report, u["email"])
        except Exception as e:
            logger.error(f"[REPORT] daily email to {u['user_id']} failed: {e}")
            continue
        await db.report_sends.insert_one({**key, "sent_at": now})
        sent += 1
    if sent:
        logger.info(f"[REPORT] emailed the {day} traffic report to {sent} subscriber(s)")
    return sent


async def daily_report_task():
    if not _report_mailer.configured():
        logger.info("Daily traffic report email off (REPORT_SMTP_HOST / REPORT_EMAIL_FROM not set)")
        return
    while True:
        try:
            await send_daily_reports()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"Daily report task failed: {e}")
        try:
            await asyncio.sleep(600)
        except asyncio.CancelledError:
            return


@api_router.post("/admin/wait-model/recalibrate")
async def admin_recalibrate(request: Request):
    """Run a recalibration now (admin). Adopts only if more accurate."""
    await require_admin(request)
    doc = await recalibrate_wait_model()
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in doc.items() if k != "_id"}


@api_router.get("/locks/board")
async def get_lock_board(from_rm: Optional[float] = None, direction: Optional[str] = None,
                         scope: str = "all", sort: str = "river", limit: Optional[int] = None,
                         lock_id: Optional[str] = None, arrive_in: Optional[float] = None,
                         mmsi: Optional[str] = None):
    """Lock-first view: every lock's status, queue, estimated wait and typical
    lockage times, from USACE data (works without any AIS feed).

    arrive_in (minutes) adds wait_at_arrival: the wait for a boat getting there
    then, counting boats expected first - USACE-based predictions corrected by
    live AIS (services/live_arrivals.py). mmsi is the asking boat, never
    counted ahead of itself.

    from_rm + direction (upbound|downbound) + scope=ahead: only the locks in
    front of the boat, nearest first. sort=delay: longest estimated wait first.
    """
    direction = direction or None   # "?direction=" means unknown
    if direction not in (None, "upbound", "downbound"):
        raise HTTPException(status_code=400, detail="direction must be upbound or downbound")
    now = datetime.now(timezone.utc)
    fetched_by_lock = _usace_fetched_by_lock()
    status_data = await fetch_usace_lock_status()
    averages = await get_lockage_averages()

    # Latest completed lockage per lock
    last_by_lock = await _last_lockage_by_lock(now)

    # Active queue rows from the USACE worker, by lock id
    queue_by_lock = {}
    for lock_no, infos in usace_lock_rows.items():
        queue_by_lock[usace_lock_id(lock_no)] = infos

    locks = [{"lock_id": lid, **info} for lid, info in LOCKS.items()]
    approaching = await approaching_by_lock(now)
    ordered = _lock_board.locks_in_view(locks, from_rm, direction, scope)
    if lock_id:  # one lock (e.g. the Lock Timing panel's target lock)
        if lock_id not in LOCKS:
            raise HTTPException(status_code=404, detail="Unknown lock")
        ordered = [lk for lk in locks if lk["lock_id"] == lock_id]

    def when(text, tz):
        return _usace_lockages.parse_time(text, tz)

    board = []
    live, live_barges = None, {}
    for lk in ordered:
        lid = lk["lock_id"]
        typical = _typical_for(averages.get(lid, {}))
        locking, waiting = _queue_entries(lid, queue_by_lock.get(lid, []), now)
        waits = _lock_board.predict_waits(lid, locking, waiting, typical, direction, now)
        wait_at_arrival = None
        if arrive_in is not None and 0 <= arrive_in <= 24 * 60:
            # Wait for a boat arriving in `arrive_in` minutes: simulate the queue
            # forward, including vessels predicted to get there first.
            appr = []
            for a in approaching.get(lid, []):
                try:
                    appr.append({**a, "eta": datetime.fromisoformat(a["eta"])})
                except (KeyError, TypeError, ValueError):
                    continue
            if live is None:   # once per request, not once per lock
                live = _live_positions(now)
                live_barges = await _recent_barges([v["mmsi"] for v in live])
            appr = _live_arrivals.merge_live_arrivals(
                lid, _LOCK_RMS, appr, live, now, own_mmsi=mmsi,
                at_lock=[x for e in locking + waiting for x in (e.get("mmsi"), e.get("vessel_name"))],
                barges_by_mmsi=live_barges)
            wait_at_arrival = _lock_board.predict_waits_at(
                lid, locking, waiting, appr, typical, now + timedelta(minutes=arrive_in), now, direction=direction)
            wait_at_arrival["arrive_in_minutes"] = round(arrive_in)

        st = status_data.get(lid)
        last = last_by_lock.get(lid)

        def out(e, position=None):
            o = dict(e)
            for k in ("arrived_at", "started_at"):
                if o.get(k):
                    o[k] = o[k].isoformat()
            if e.get("arrived_at"):
                o["waiting_minutes"] = round((now - e["arrived_at"]).total_seconds() / 60)
            if position is not None:
                o["position"] = position
            return o

        board.append({
            "lock_id": lid,
            "name": lk.get("name"),
            "river_mile": lk.get("river_mile"),
            "phone": lk.get("phone"),
            "distance_mi": round(abs(lk["river_mile"] - from_rm), 1) if from_rm is not None else None,
            "status": st.status if st else "UNKNOWN",
            "status_source": st.status_source if st else None,
            "closure_info": st.closure_info if st else None,
            # Calibrated against USACE history (scripts/backtest_waits.py)
            "wait_estimate_minutes": waits["tow"],
            # Middle 60% of outcomes at this lock, learned nightly (None until then)
            "wait_range_minutes": waits.get("tow_range"),
            "wait_estimate_recreational_minutes": waits["recreational"],
            "wait_range_recreational_minutes": waits.get("recreational_range"),
            "queue_minutes": waits["queue_minutes"],
            "wait_at_arrival": wait_at_arrival,
            "queue_count": len(locking) + len(waiting),
            "locking": [out(e) for e in locking],
            "waiting": [out(e, i + 1) for i, e in enumerate(waiting)],
            "last_lockage_minutes_ago": round((now - last).total_seconds() / 60) if last else None,
            # Predicted from each vessel's last USACE lockage + learned transit times
            "approaching": approaching.get(lid, [])[:6],
            "typical": {k: v for k, v in typical.items() if k != "by_barges"},  # table stays server-side
            "queue_data_at": fetched_by_lock.get(lid),
            # Waits from a queue older than ~20 min are labelled, not shown as current
            **({"queue_age_minutes": None, "queue_stale": False} if lid in USACE_NO_DATA_LOCKS
               else _health.queue_freshness(fetched_by_lock.get(lid), now)),
        })
    for row in board:
        if isinstance(row["queue_data_at"], datetime):
            row["queue_data_at"] = row["queue_data_at"].isoformat()

    if sort == "delay":
        board.sort(key=lambda r: -(r["wait_estimate_minutes"] or 0))
    if limit:
        board = board[:max(1, min(int(limit), 40))]
    return {
        "generated_at": now.isoformat(),
        "from_rm": from_rm,
        "direction": direction,
        "scope": scope,
        "wait_model": {
            "fitted_on": _lock_board.CALIBRATION["fitted_on"],
            "typical_error_minutes": _lock_board.CALIBRATION["test_mae_minutes"],
        },
        "usace": _health.usace_summary(fetched_by_lock, LOCKS, now, USACE_NO_DATA_LOCKS),
        "locks": board,
    }


_LOCK_RMS = {lid: info["river_mile"] for lid, info in LOCKS.items()}


def _live_positions(now: datetime) -> List[dict]:
    """Live AIS boats (no demo boats) for services/live_arrivals.py."""
    out = []
    for mmsi, v in list(active_vessels.items()):
        # active_vessels holds models (AIS) and dicts (simulated / demo boats);
        # a simulated boat on the map used to crash the lock board here.
        g = v.get if isinstance(v, dict) else (lambda k, d=None, _v=v: getattr(_v, k, d))
        if _is_demo_vessel(v, str(mmsi)) or g("is_simulated") or g("river_mile") is None:
            continue  # demo and simulated boats aren't real traffic
        if g("is_user_vessel") or g("vessel_type") == "recreational":
            continue  # account boats (phone / manual / parked) have no ship type and counted as tows
        out.append({"mmsi": str(mmsi), "name": g("name"), "river_mile": g("river_mile"), "speed": g("speed"),
                    "heading": g("heading"), "ship_type": g("ship_type"),
                    "timestamp": g("last_ais_checkin") or g("timestamp")})
    return out


async def _recent_barges(mmsis: List[str]) -> Dict[str, int]:
    """Barge count from each boat's latest USACE lockage (AIS doesn't carry it)."""
    if not mmsis:
        return {}
    try:
        rows = await db.lockage_history.aggregate([
            {"$match": {"mmsi": {"$in": mmsis}, "source": "usace_lpms", "barge_count": {"$ne": None}}},
            {"$sort": {"recorded_at": -1}},
            {"$group": {"_id": "$mmsi", "barges": {"$first": "$barge_count"}}},
        ]).to_list(None)
        return {r["_id"]: r["barges"] for r in rows}
    except Exception as e:
        logger.warning(f"Could not read barge counts: {e}")
        return {}


# Locks USACE publishes no queue for (none since 5A was found under code "55").
USACE_NO_DATA_LOCKS: tuple = ()


def _usace_fetched_by_lock() -> Dict[str, datetime]:
    return {usace_lock_id(n): t for n, t in usace_lock_fetched_at.items()}


def _typical_for(avg: dict) -> dict:
    return {
        "avg_single_lockage_minutes": avg.get("avg_single_lockage_minutes"),
        "avg_double_lockage_minutes": avg.get("avg_double_lockage_minutes"),
        "avg_recreational_lockage_minutes": avg.get("avg_recreational_lockage_minutes"),
        "avg_tow_wait_minutes": avg.get("avg_tow_wait_minutes"),
        "avg_recreational_wait_minutes": avg.get("avg_recreational_wait_minutes"),
        "double_share": avg.get("double_share"),
        "by_barges": avg.get("by_barges"),
        "sample_count": avg.get("sample_count", 0),
        "is_baseline": avg.get("is_baseline", True),
    }


def _queue_entries(lid: str, rows: list, now: datetime):
    """USACE queue rows -> (locking, waiting) as the lock board models them."""
    locking, waiting = [], []
    for v in rows:
        tz = v.get("timezone")
        entry = {
            "vessel_name": v.get("vessel_name"),
            "mmsi": v.get("mmsi"),
            "key": _wait_log.key_of(v),
            "direction": {"U": "upbound", "D": "downbound"}.get(v.get("direction") or "", v.get("direction")),
            "barges": v.get("num_barges"),
            "needs_double": _lock_board.needs_double(lid, v.get("num_barges")) or bool(v.get("cuts_completed")),
            "cuts_completed": v.get("cuts_completed") or 0,
            "arrived_at": _usace_lockages.parse_time(v.get("arrival_date"), tz),
        }
        if v.get("status") == "locking":
            entry["started_at"] = _usace_lockages.parse_time(v.get("sol_date"), tz)
            locking.append(entry)
        else:
            waiting.append(entry)
    waiting.sort(key=lambda e: e["arrived_at"] or now)
    return locking, waiting


# --- Live wait-prediction log (services/wait_log.py) ---------------------------
_wait_logged: set = set()
_accuracy_cache: dict = {}


async def log_wait_predictions(now: Optional[datetime] = None) -> int:
    """Log the board's estimate for each boat that just joined a lock queue."""
    now = now or datetime.now(timezone.utc)
    averages = await get_lockage_averages()
    docs = []
    for lock_no, rows in list(usace_lock_rows.items()):
        lid = usace_lock_id(lock_no)
        if lid not in LOCKS or not rows:
            continue
        typical = _typical_for(averages.get(lid, {}))
        locking, waiting = _queue_entries(lid, rows, now)
        predict = lambda lk, ahead, d, _l=lid, _t=typical: _lock_board.predict_waits(_l, lk, ahead, _t, d, now)
        docs += _wait_log.arrival_docs(lid, locking, waiting, predict, _wait_logged, now)
    for d in docs:
        _wait_logged.add((d["lock_id"], d["key"], d["arrived_at"]))
        try:
            await db.wait_predictions.update_one(
                {"lock_id": d["lock_id"], "key": d["key"], "arrived_at": d["arrived_at"]},
                {"$setOnInsert": d}, upsert=True)
        except Exception as e:
            logger.warning(f"[ACCURACY] could not log a wait prediction: {e}")
    if len(_wait_logged) > 20000:
        cutoff = now - timedelta(hours=2)
        _wait_logged.difference_update({k for k in _wait_logged if k[2] < cutoff})
    return len(docs)


async def wait_logging_task():
    while True:
        try:
            await asyncio.sleep(120)
            await log_wait_predictions()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[ACCURACY] wait logging failed: {e}")


def _utc_dt(t):
    return t.replace(tzinfo=timezone.utc) if t is not None and t.tzinfo is None else t


@api_router.get("/accuracy")
async def accuracy(days: int = 30):
    """Public: live wait predictions vs what USACE recorded, arrival-time
    accuracy, and the latest held-out test of the wait model. No user data;
    pleasure boats are not named."""
    days = max(1, min(int(days), 120))
    now = datetime.now(timezone.utc)
    hit = _accuracy_cache.get(days)
    if hit and now - hit[0] < timedelta(minutes=10):
        return hit[1]
    since = now - timedelta(days=days)
    preds = await db.wait_predictions.find({"arrived_at": {"$gte": since}}, {"_id": 0}).to_list(None)
    for p in preds:
        p["arrived_at"] = _utc_dt(p["arrived_at"])
    keys = list({p["key"] for p in preds})
    lockages = await db.lockage_history.find(
        {"source": "usace_lpms", "arrival_time": {"$gte": since - timedelta(hours=1)},
         "$or": [{"usace_vessel_no": {"$in": keys}}, {"vessel_name": {"$in": keys}}]},
        {"_id": 0, "lock_id": 1, "usace_vessel_no": 1, "vessel_name": 1, "arrival_time": 1,
         "wait_time_minutes": 1, "is_recreational": 1}).to_list(None) if keys else []
    for r in lockages:
        r["arrival_time"] = _utc_dt(r["arrival_time"])
    scored = await asyncio.to_thread(_wait_log.score, preds, lockages)
    names = {lid: info.get("name", lid) for lid, info in LOCKS.items()}
    waits = _wait_log.report(scored, names)
    waits["logged"] = len(preds)
    waits["since"] = min((p["arrived_at"] for p in preds), default=None)
    waits["since"] = waits["since"].isoformat() if waits["since"] else None
    arr = await db.arrival_calibration.find_one({}, {"_id": 0, "ran_at": 1, "accuracy": 1}, sort=[("ran_at", -1)])
    model = await db.wait_calibration.find_one({"adopted": True}, {"_id": 0, "ran_at": 1, "reason": 1, "test": 1,
                                                                   "new_score": 1}, sort=[("ran_at", -1)])
    out = {
        "days": days, "generated_at": now.isoformat(), "waits": waits,
        "arrivals": (arr or {}).get("accuracy"),
        "arrivals_checked_at": _utc_dt(arr["ran_at"]).isoformat() if arr else None,
        "model_test": {"ran_at": _utc_dt(model["ran_at"]).isoformat(), "test_lockages": model.get("test"),
                       "score": model.get("new_score")} if model else None,
    }
    _accuracy_cache[days] = (now, out)
    return out

# --- Season log: a light track of users' own boats (services/season_log.py) -----
_owned_mmsis: tuple = (None, set())
_track_last: Dict[str, tuple] = {}


async def _owned_mmsi_set() -> set:
    global _owned_mmsis
    now = datetime.now(timezone.utc)
    at, owned = _owned_mmsis
    if at is None or now - at > timedelta(minutes=5):
        owned = set(str(m) for m in await db.users.distinct("vessels.mmsi") if m)
        _owned_mmsis = (now, owned)
    return owned


async def _record_track_point(v: dict) -> None:
    """One point per ~0.25 river mile (or 30 min) for boats on an account.
    Simulated and parked-at-home positions are skipped."""
    try:
        mmsi = str(v.get("mmsi") or "")
        rm = v.get("river_mile")
        if not mmsi or rm is None or v.get("is_simulated") or v.get("parked"):
            return
        if mmsi in user_vessel_simulation and user_vessel_simulation[mmsi].get("enabled"):
            return
        if mmsi not in await _owned_mmsi_set():
            return
        now = datetime.now(timezone.utc)
        if not _season_log.due(_track_last.get(mmsi), float(rm), now):
            return
        _track_last[mmsi] = (now, float(rm))
        await db.boat_tracks.insert_one({"mmsi": mmsi, "t": now, "rm": float(rm), "lat": v.get("lat"),
                                         "lon": v.get("lon"), "speed": v.get("speed")})
    except Exception as e:
        logger.debug(f"[TRACK] could not record: {e}")


@api_router.get("/me/season")
async def my_season(request: Request, year: Optional[int] = None):
    """Season log for each boat on the signed-in account."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    year = year or _traffic_report.to_central(datetime.now(timezone.utc)).year
    start = datetime(year, 1, 1, 6, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, 6, tzinfo=timezone.utc)
    locks = [(lid, info["river_mile"], info.get("name", lid)) for lid, info in LOCKS.items()]
    boats = []
    for v in (user.get("vessels") or []):
        mmsi = str(v.get("mmsi") or "")
        if not mmsi:
            continue
        pts = await db.boat_tracks.find({"mmsi": mmsi, "t": {"$gte": start, "$lt": end}},
                                        {"_id": 0, "t": 1, "rm": 1}).sort("t", 1).to_list(None)
        summary = await asyncio.to_thread(_season_log.summarize, pts, locks)
        boats.append({"mmsi": mmsi, "boat_name": v.get("boat_name"), **summary})
    return {"year": year, "boats": boats}
# --- Marinas along the river (OpenStreetMap, services/marinas.py) ---------------
_marinas_cache: list = []


async def refresh_marinas(force: bool = False) -> int:
    """Load marinas from the DB; re-fetch from OpenStreetMap weekly."""
    global _marinas_cache
    meta = await db.settings.find_one({"_id": "marinas_meta"}) or {}
    fetched = meta.get("fetched_at")
    if fetched is not None and fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    fresh = fetched and datetime.now(timezone.utc) - fetched < timedelta(days=_marinas.REFRESH_DAYS)
    if fresh and not force:
        _marinas_cache = await db.marinas.find({}, {"_id": 0}).to_list(None)
        return len(_marinas_cache)
    try:
        async with httpx.AsyncClient(timeout=120.0, headers=OUTBOUND_HEADERS) as client:
            r = await client.post(_marinas.OVERPASS_URL, data={"data": _marinas.QUERY})
            r.raise_for_status()
            elements = r.json().get("elements", [])
        snap = lambda lat, lon: _river_geo.river_mile(lat, lon, max_offset_mi=_marinas.MAX_OFFSET_MI)
        docs = await asyncio.to_thread(_marinas.parse, elements, snap)
    except Exception as e:
        logger.warning(f"[MARINAS] OpenStreetMap fetch failed: {e}")
        _marinas_cache = await db.marinas.find({}, {"_id": 0}).to_list(None)
        return len(_marinas_cache)
    if docs:
        await db.marinas.delete_many({})
        await db.marinas.insert_many([dict(d) for d in docs])
        await db.settings.update_one({"_id": "marinas_meta"},
                                     {"$set": {"fetched_at": datetime.now(timezone.utc), "count": len(docs)}},
                                     upsert=True)
        _marinas_cache = docs
        logger.info(f"[MARINAS] {len(docs)} marinas on the river from OpenStreetMap")
    return len(_marinas_cache)


async def marinas_task():
    while True:
        try:
            await refresh_marinas()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[MARINAS] refresh failed: {e}")
        try:
            await asyncio.sleep(12 * 3600)
        except asyncio.CancelledError:
            return


@api_router.get("/marinas")
async def list_marinas(from_rm: Optional[float] = None, to_rm: Optional[float] = None):
    """Marinas / fuel docks on the river, optionally between two river miles
    (listed in travel order from -> to)."""
    rows = _marinas_cache
    if from_rm is not None and to_rm is not None:
        rows = _marinas.between(rows, from_rm, to_rm)
    return {"marinas": rows, "credit": _marinas.OSM_CREDIT,
            "add_url": "https://www.openstreetmap.org/"}

# --- AIS feed health: uptime history and outage alerts ------------------------
_feed_samples: "deque" = deque()
_feed_uptime: dict = {}
_feed_alerted = False
_feed_last_ok: Optional[datetime] = None  # last minute the feed was up (persisted)
_feed_alerted_from: Optional[datetime] = None


def _feed_summary(samples, now: datetime) -> dict:
    out = _health.uptime_summary(samples, now)
    if out["down_since"] and _feed_last_ok and _feed_last_ok.isoformat() < out["down_since"]:
        out["down_since"] = _feed_last_ok.isoformat()  # outage began before this run of samples
    return out


def _feed_alert_message(kind: str, down_from: datetime, now: datetime, to: str) -> EmailMessage:
    start = _traffic_report.to_central(down_from).strftime("%b %d %I:%M %p").replace(" 0", " ")
    msg = EmailMessage()
    msg["From"] = _report_mailer.sender()
    msg["To"] = to
    if kind == "down":
        msg["Subject"] = f"River Watch: live AIS feed down since {start} CT"
        body = ("The live AIS feed has sent nothing since " + start + " Central. Tow positions "
                "are not updating; lock queues and waits from USACE are unaffected.\n\n"
                "Check that the Boat Beacon device is on, on Wi-Fi, and not asleep.")
    else:
        mins = int((now - down_from).total_seconds() // 60)
        msg["Subject"] = f"River Watch: live AIS feed back after {mins} min"
        body = f"The live AIS feed is sending again (down from {start} Central, about {mins} minutes)."
    url = _report_mailer.app_url()
    msg.set_content(body + (f"\n\n{url}" if url else ""))
    return msg


async def _send_feed_alert(kind: str, down_from: datetime, now: datetime) -> None:
    logger.warning(f"[FEED] live AIS feed {'down since ' + down_from.isoformat() if kind == 'down' else 'back up'}")
    if not _report_mailer.configured():
        return
    admins = await db.users.find({"$or": [{"is_admin": True}, {"is_super_admin": True}],
                                  "email": {"$nin": [None, ""]}}, {"_id": 0, "email": 1}).to_list(50)
    for a in admins:
        try:
            await asyncio.to_thread(_report_mailer.send, _feed_alert_message(kind, down_from, now, a["email"]))
        except Exception as e:
            logger.error(f"[FEED] alert email failed: {e}")


async def feed_monitor_task():
    """One up/down sample a minute while a feed is configured: uptime for the
    health check and the app's banner, plus an email to admins when an outage
    passes 15 minutes and when it ends (only if SMTP is set up)."""
    global _feed_alerted, _feed_uptime, _feed_last_ok, _feed_alerted_from
    now = datetime.now(timezone.utc)
    try:
        rows = await db.feed_samples.find({"t": {"$gte": now - timedelta(days=7)}}, {"_id": 0}) \
            .sort("t", 1).to_list(None)
        _feed_samples.extend((r["t"].replace(tzinfo=timezone.utc) if r["t"].tzinfo is None else r["t"], r["ok"])
                             for r in rows)
        state = await db.feed_state.find_one({"_id": "ais"}) or {}
        if state.get("last_ok"):
            t = state["last_ok"]
            _feed_last_ok = t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
        _feed_uptime = _feed_summary(list(_feed_samples), now)
    except Exception as e:
        logger.warning(f"[FEED] could not load uptime history: {e}")
    while True:
        try:
            await asyncio.sleep(_health.SAMPLE_SECONDS)
            now = datetime.now(timezone.utc)
            if ais_manager.config is None:
                continue
            ok = _health.ais_summary(True, ais_manager.is_connected, ais_manager._last_data_time,
                                     now)["status"] == "ok"
            _feed_samples.append((now, ok))
            while _feed_samples and _feed_samples[0][0] < now - timedelta(days=7):
                _feed_samples.popleft()
            await db.feed_samples.insert_one({"t": now, "ok": ok})
            if ok:
                _feed_last_ok = now
                await db.feed_state.update_one({"_id": "ais"}, {"$set": {"last_ok": now}}, upsert=True)
            samples = list(_feed_samples)
            _feed_uptime = _feed_summary(samples, now)
            down_from = datetime.fromisoformat(_feed_uptime["down_since"]) if _feed_uptime["down_since"] else None
            kind = _health.alert_due(down_from, _feed_alerted, now)
            if kind == "down":
                _feed_alerted, _feed_alerted_from = True, down_from
                await _send_feed_alert("down", down_from, now)
            elif kind == "up":
                _feed_alerted = False
                await _send_feed_alert("up", _feed_alerted_from or now, now)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[FEED] monitor failed: {e}")


@api_router.get("/health")
async def health(response: Response):
    """Public health check for uptime monitors: database reachable, USACE data
    age, live AIS feed. 503 only when the database is down; stale USACE data
    reports "degraded". Exposes no feed addresses or user data."""
    now = datetime.now(timezone.utc)
    try:
        await asyncio.wait_for(db.command("ping"), timeout=3)
        database_ok = True
    except Exception:
        database_ok = False
    usace = _health.usace_summary(_usace_fetched_by_lock(), LOCKS, now, USACE_NO_DATA_LOCKS)
    ais = _health.ais_summary(ais_manager.config is not None, ais_manager.is_connected,
                              ais_manager._last_data_time, now)
    status = _health.overall(database_ok, usace)
    if status == "down":
        response.status_code = 503
    return {"status": status, "time": now.isoformat(), "database": "ok" if database_ok else "down",
            "usace": usace, "ais_feed": {**ais, **_feed_uptime}}


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
            "status_source": status.status_source,
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


@api_router.get("/locks/{lock_id}/details")
async def get_lock_details(lock_id: str):
    """
    Get comprehensive lock details including:
    - Basic info (name, location, phone)
    - Current USACE status (open/closed/restricted)
    - Wait time predictions based on queue
    - Current vessels waiting/locking
    - Historical average lockage times
    - Recent lockage history
    """
    if lock_id not in LOCKS:
        return {"error": "Invalid lock ID"}
    
    lock_info = LOCKS[lock_id]
    
    # Fetch all relevant data in parallel
    status_data = await fetch_usace_lock_status()
    status = status_data.get(lock_id, LockStatus(lock_id=lock_id, status="UNKNOWN"))
    
    # Get lock queue data for vessels at this lock
    queue_data = await fetch_usace_lock_queue_data()
    vessels_at_lock = [
        v for v in queue_data.values() 
        if v.get('lock_id') == lock_id and v.get('status') in ('waiting', 'locking')
    ]
    
    # Sort by arrival time
    vessels_at_lock.sort(key=lambda v: v.get('arrival_date') or '')
    
    # Separate by status and direction
    vessels_waiting_up = [v for v in vessels_at_lock if v.get('status') == 'waiting' and v.get('direction') == 'U']
    vessels_waiting_down = [v for v in vessels_at_lock if v.get('status') == 'waiting' and v.get('direction') == 'D']
    vessels_locking = [v for v in vessels_at_lock if v.get('status') == 'locking']
    
    # Get lockage time averages
    averages = await get_lockage_averages(lock_id)
    lock_averages = averages.get(lock_id, {})
    
    # Calculate wait time prediction
    tow_lockage_time = lock_averages.get('avg_tow_lockage_minutes') or 45
    rec_lockage_time = lock_averages.get('avg_recreational_lockage_minutes') or 20
    
    # Estimate wait time based on queue
    # Tows take priority, then recreational boats go through together
    estimated_wait_minutes = 0
    if vessels_locking:
        # Currently locking vessel - estimate remaining time
        locking_vessel = vessels_locking[0]
        if locking_vessel.get('num_barges') and locking_vessel['num_barges'] > 0:
            estimated_wait_minutes += tow_lockage_time // 2  # Assume halfway done
        else:
            estimated_wait_minutes += rec_lockage_time // 2
    
    # Add time for each vessel ahead in queue
    for v in vessels_at_lock:
        if v.get('status') == 'waiting':
            if v.get('num_barges') and v['num_barges'] > 0:
                # Tow - check for double lockage
                if v['num_barges'] > 9:
                    estimated_wait_minutes += tow_lockage_time * 2  # Double lockage
                else:
                    estimated_wait_minutes += tow_lockage_time
            else:
                estimated_wait_minutes += rec_lockage_time
    
    # Get recent lockage history from database
    recent_lockages = []
    try:
        recent = await db.lockage_history.find(
            {"lock_id": lock_id},
            {"_id": 0}
        ).sort("recorded_at", -1).limit(10).to_list(10)
        recent_lockages = [lockage_for_output(r) for r in recent]
    except Exception as e:
        logger.warning(f"Failed to fetch lockage history for {lock_id}: {e}")
    
    # Calculate prediction confidence
    sample_count = lock_averages.get('sample_count', 0)
    is_baseline = lock_averages.get('combined', {}).get('is_baseline', True)
    prediction_confidence = "low" if is_baseline else ("medium" if sample_count < 20 else "high")
    
    return {
        "lock_id": lock_id,
        "name": lock_info["name"],
        "river_mile": lock_info["river_mile"],
        "lat": lock_info["lat"],
        "lon": lock_info["lon"],
        "phone": lock_info.get("phone"),
        
        # Current status
        "status": status.status,
        "closure_info": status.closure_info,
        "last_updated": status.last_updated,
        
        # Queue info
        "upbound_queue": status.upbound_queue or len(vessels_waiting_up),
        "downbound_queue": status.downbound_queue or len(vessels_waiting_down),
        "total_queue": len(vessels_at_lock),
        
        # Wait time prediction
        "estimated_wait_minutes": round(estimated_wait_minutes),
        "usace_avg_wait_minutes": status.avg_wait_minutes,
        "prediction_confidence": prediction_confidence,
        
        # Vessels at lock
        "vessels_locking": [{
            "name": v.get('vessel_name'),
            "mmsi": v.get('mmsi'),
            "num_barges": v.get('num_barges'),
            "direction": v.get('direction'),
            "arrival_date": v.get('arrival_date'),
            "sol_date": v.get('sol_date')
        } for v in vessels_locking],
        "vessels_waiting": [{
            "name": v.get('vessel_name'),
            "mmsi": v.get('mmsi'),
            "num_barges": v.get('num_barges'),
            "direction": v.get('direction'),
            "arrival_date": v.get('arrival_date'),
            "position": i + 1
        } for i, v in enumerate(vessels_at_lock) if v.get('status') == 'waiting'],
        
        # Average times
        "avg_tow_lockage_minutes": lock_averages.get('avg_tow_lockage_minutes'),
        "avg_recreational_lockage_minutes": lock_averages.get('avg_recreational_lockage_minutes'),
        "avg_tow_wait_minutes": lock_averages.get('avg_tow_wait_minutes'),
        "avg_recreational_wait_minutes": lock_averages.get('avg_recreational_wait_minutes'),
        "avg_single_lockage_minutes": lock_averages.get('avg_single_lockage_minutes'),
        "avg_double_lockage_minutes": lock_averages.get('avg_double_lockage_minutes'),
        "single_count": lock_averages.get('single_count'),
        "double_count": lock_averages.get('double_count'),
        "double_share": lock_averages.get('double_share'),
        "is_baseline_data": is_baseline,
        "sample_count": sample_count,
        
        # Recent history
        "recent_lockages": recent_lockages[:5]
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
            "avg_single_lockage_minutes": lock_averages.get("avg_single_lockage_minutes"),
            "avg_double_lockage_minutes": lock_averages.get("avg_double_lockage_minutes"),
            "single_count": lock_averages.get("single_count"),
            "double_count": lock_averages.get("double_count"),
            "double_share": lock_averages.get("double_share"),
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
    # Recent lockages: USACE-reported (lock queue feed) plus passages River
    # Watch observed itself via AIS lock-passage tracking.
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent = await db.lockage_history.find(
        {"lock_id": lock_id, "recorded_at": {"$gte": cutoff}}, {"_id": 0}
    ).sort("recorded_at", -1).to_list(50)
    lockage_data = {lock_id: [lockage_for_output(r) for r in recent]}
    
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


# =============================================
# USGS WATER CONDITIONS API
# =============================================

import httpx

# Cache for USGS data (refreshes every 15 minutes)
usgs_cache = {}
usgs_cache_time = {}
USGS_CACHE_DURATION = 900  # 15 minutes

# Cache for NWS NWPS hydrograph data (refreshes every 15 minutes)
nws_cache: dict = {}
nws_cache_time: dict = {}
NWS_CACHE_DURATION = 900

async def fetch_nws_gauge_data(nwsli: str) -> dict:
    """
    Fetch observed stage + forecast + per-gauge flood categories from the
    NWS National Water Prediction Service (NWPS) for a given NWSLI gauge ID.
    """
    cache_key = f"nws_{nwsli}"
    now = datetime.now(timezone.utc)

    cached_at = nws_cache_time.get(cache_key)
    if cached_at and (now - cached_at).total_seconds() < NWS_CACHE_DURATION:
        return nws_cache[cache_key]

    result = {
        "nwsli": nwsli,
        "name": None,
        "stage": None,
        "stage_unit": "ft",
        "flood_category": "normal",
        "forecast": None,
        "categories": {},
        "error": None,
    }

    try:
        url = f"https://api.water.noaa.gov/nwps/v1/gauges/{nwsli}"
        async with httpx.AsyncClient(timeout=15.0, headers=OUTBOUND_HEADERS) as client:
            response = await client.get(url)
            if response.status_code != 200:
                result["error"] = f"NWS HTTP {response.status_code}"
            else:
                payload = response.json()
                result["name"] = payload.get("name")
                observed = (payload.get("status") or {}).get("observed") or {}
                if observed.get("primary") is not None:
                    try:
                        result["stage"] = round(float(observed["primary"]), 2)
                    except (TypeError, ValueError):
                        pass
                if observed.get("primaryUnit"):
                    result["stage_unit"] = observed["primaryUnit"]
                if observed.get("floodCategory"):
                    cat = observed["floodCategory"]
                    # NWPS uses "no_flooding", "action", "minor", "moderate", "major"
                    mapping = {
                        "no_flooding": "normal",
                        "action": "action",
                        "minor": "flood",
                        "moderate": "moderate",
                        "major": "major",
                    }
                    result["flood_category"] = mapping.get(cat, cat)

                flood = payload.get("flood") or {}
                cats = flood.get("categories") or {}
                # Normalize NWPS naming -> our names
                for nws_key, our_key in (("action", "action"), ("minor", "flood"),
                                          ("moderate", "moderate"), ("major", "major")):
                    stage_val = (cats.get(nws_key) or {}).get("stage")
                    if stage_val is not None and stage_val != -9999:
                        result["categories"][our_key] = stage_val

                # Build short forecast (next ~6 points)
                fc_payload = payload.get("forecast") or {}
                fc_data = fc_payload.get("data") if isinstance(fc_payload, dict) else None
                if isinstance(fc_data, list):
                    forecast_points = []
                    for point in fc_data[:6]:
                        try:
                            forecast_points.append({
                                "time": point.get("validTime"),
                                "stage_ft": float(point.get("primary")),
                            })
                        except (TypeError, ValueError):
                            continue
                    if forecast_points:
                        result["forecast"] = forecast_points
    except Exception as e:
        logger.error(f"Error fetching NWS data for {nwsli}: {e}")
        result["error"] = str(e)

    nws_cache[cache_key] = result
    nws_cache_time[cache_key] = now
    return result


async def fetch_usgs_water_data(site_id: str) -> dict:
    """
    Fetch real-time water conditions from USGS Water Services API.
    
    Parameters fetched:
    - 00065: Gage height (feet)
    - 00060: Discharge (cubic feet per second)  
    - 00010: Water temperature (Celsius)
    
    Also fetches forecast data from NOAA AHPS.
    """
    cache_key = f"usgs_{site_id}"
    now = datetime.now(timezone.utc)
    
    # Check cache
    if cache_key in usgs_cache:
        cache_age = (now - usgs_cache_time.get(cache_key, now)).total_seconds()
        if cache_age < USGS_CACHE_DURATION:
            return usgs_cache[cache_key]
    
    result = {
        "site_id": site_id,
        "timestamp": now.isoformat(),
        "gage_height_ft": None,
        "discharge_cfs": None,
        "water_temp_c": None,
        "water_temp_f": None,
        "current_speed_mph": None,
        "flood_stage": "normal",
        "forecast": None,
        "error": None
    }
    
    try:
        # Fetch current conditions from USGS
        url = f"https://waterservices.usgs.gov/nwis/iv/?format=json&sites={site_id}&parameterCd=00065,00060,00010&siteStatus=active"
        
        async with httpx.AsyncClient(timeout=15.0, headers=OUTBOUND_HEADERS) as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                time_series = data.get('value', {}).get('timeSeries', [])
                
                for ts in time_series:
                    param_code = ts.get('variable', {}).get('variableCode', [{}])[0].get('value', '')
                    values = ts.get('values', [{}])[0].get('value', [])
                    
                    if values:
                        latest = values[-1]  # Most recent value
                        value = float(latest.get('value', 0))
                        
                        if param_code == '00065':  # Gage height
                            result['gage_height_ft'] = round(value, 2)
                        elif param_code == '00060':  # Discharge
                            result['discharge_cfs'] = round(value, 0)
                            # Estimate current speed from discharge (rough approximation)
                            # Assuming average channel width ~2000ft, depth ~15ft for Upper Miss
                            # Speed (fps) ≈ discharge / (width * depth)
                            # This is a rough estimate - actual varies by location
                            estimated_fps = value / (2000 * 15)
                            result['current_speed_mph'] = round(estimated_fps * 0.681818, 1)  # fps to mph
                        elif param_code == '00010':  # Water temp
                            result['water_temp_c'] = round(value, 1)
                            result['water_temp_f'] = round(value * 9/5 + 32, 1)
                
                # Determine flood stage
                if result['gage_height_ft'] and site_id in FLOOD_STAGES:
                    stages = FLOOD_STAGES[site_id]
                    height = result['gage_height_ft']
                    if height >= stages['major']:
                        result['flood_stage'] = 'major'
                    elif height >= stages['moderate']:
                        result['flood_stage'] = 'moderate'
                    elif height >= stages['flood']:
                        result['flood_stage'] = 'flood'
                    elif height >= stages['action']:
                        result['flood_stage'] = 'action'
                    else:
                        result['flood_stage'] = 'normal'
                        
    except Exception as e:
        logger.error(f"Error fetching USGS data for {site_id}: {e}")
        result['error'] = str(e)
    
    # Try to fetch forecast data from NOAA AHPS
    try:
        # NOAA AHPS forecast endpoint (XML)
        # Map USGS site to NWS location ID
        nws_locations = {
            "05331000": "STPM5",   # St. Paul
            "05344500": "PREW3",   # Prescott
            "05378500": "WINM5",   # Winona
            "05389500": "MCGI4",   # McGregor
            "05420500": "CLNI4",   # Clinton
            "05474500": "KEOI4",   # Keokuk
            "05587450": "GRFI2",   # Grafton
            "07010000": "EADM7",   # St. Louis
        }
        
        if site_id in nws_locations:
            nws_id = nws_locations[site_id]
            forecast_url = f"https://water.weather.gov/ahps2/hydrograph_to_xml.php?gage={nws_id}&output=xml"
            
            async with httpx.AsyncClient(timeout=10.0, headers=OUTBOUND_HEADERS) as client:
                forecast_resp = await client.get(forecast_url)
                
                if forecast_resp.status_code == 200:
                    # Parse basic forecast info from XML
                    import re
                    xml_text = forecast_resp.text
                    
                    # Extract forecast values (simplified parsing)
                    forecasts = []
                    forecast_matches = re.findall(
                        r'<forecast>.*?<valid[^>]*>([^<]+)</valid>.*?<primary[^>]*>([^<]+)</primary>.*?</forecast>',
                        xml_text, re.DOTALL
                    )
                    
                    for valid_time, value in forecast_matches[:6]:  # Next 6 forecasts
                        try:
                            forecasts.append({
                                "time": valid_time.strip(),
                                "stage_ft": float(value)
                            })
                        except:
                            pass
                    
                    if forecasts:
                        result['forecast'] = forecasts
                        
    except Exception as e:
        logger.debug(f"Could not fetch forecast for {site_id}: {e}")
    
    # Cache result
    usgs_cache[cache_key] = result
    usgs_cache_time[cache_key] = now
    
    return result


@api_router.get("/water-conditions/{lock_id}")
async def get_water_conditions_for_lock(lock_id: str):
    """
    Get water conditions (level, temp, current) for a specific lock.
    Uses the lock's authoritative station from /app/backend/lock_stations.py
    and ONLY applies that station's thresholds. Reference stations are returned
    alongside (no threshold cross-application) for audit/comparison.

    Response shape (per the data-accuracy audit):
        official:  {station_id, station_name, source, river_mile,
                    distance_from_lock_miles, measurement_type, value,
                    units, datum, observed_at, thresholds, threshold_source,
                    status, status_explanation, raw, data_url, source_url}
        references: [ ...same shape... ]

    Backwards-compatible legacy fields are still surfaced at the top level
    (`conditions`, `gauge`, `flood_stages`) so older clients keep working.
    """
    if lock_id not in LOCKS:
        raise HTTPException(status_code=404, detail="Invalid lock ID")

    from services.water_station_service import get_water_conditions as _structured_water
    structured = await _structured_water(lock_id)
    if "error" in structured:
        return {"lock_id": lock_id, "error": structured["error"]}

    official = structured["official"]
    raw = official.get("raw") or {}

    # Reference station data is kept in a separate `reference_conditions`
    # block. We intentionally do NOT merge reference discharge / current
    # speed into the official conditions object: those readings live on a
    # different datum and don't describe Lock {lock_id}'s flow.
    reference_conditions = []
    for ref in structured.get("references", []):
        rraw = ref.get("raw") or {}
        reference_conditions.append({
            "station_id": ref.get("station_id"),
            "station_name": ref.get("station_name"),
            "source": ref.get("source"),
            "value": ref.get("value"),
            "units": ref.get("units"),
            "observed_at": ref.get("observed_at"),
            "datum": ref.get("datum"),
            "distance_from_lock_miles": ref.get("distance_from_lock_miles"),
            "raw": rraw,
            "note": ref.get("note"),
            "fetch_method": ref.get("fetch_method"),
            "source_status": ref.get("source_status"),
        })

    legacy_flood_status = (
        official.get("status")
        if official.get("status") in ("normal", "action", "flood", "moderate", "major")
        else None
    )

    # `official_current` summarises just the headline reading + state.
    official_current = {
        "station_id": official.get("station_id"),
        "station_name": official.get("station_name"),
        "value": official.get("value"),
        "units": official.get("units"),
        "measurement_type": official.get("measurement_type"),
        "observed_at": official.get("observed_at"),
        "status": official.get("status"),
        "status_explanation": official.get("status_explanation"),
        "available": official.get("value") is not None,
        "unavailable_reason": (
            None if official.get("value") is not None
            else (official.get("fetch_error") or "Official stage unavailable")
        ),
        "fetch_method": official.get("fetch_method"),
        "fallback_used": official.get("fallback_used", False),
        "source_status": official.get("source_status"),
    }

    payload = {
        "lock_id": lock_id,
        "lock_name": structured["lock_name"],
        "lock_river_mile": structured["lock_river_mile"],
        # NEW structured shape
        "official": official,
        "official_current": official_current,
        "references": structured.get("references", []),
        "reference_conditions": reference_conditions,
        "selection_reason": structured.get("selection_reason"),
        "fetched_at": structured.get("fetched_at"),
        # LEGACY shape - kept so older modal builds keep rendering. Only
        # data sourced from the official station is allowed in here.
        "gauge": {
            "site_id": official["station_id"],
            "name": official["station_name"],
            "river_mile": official.get("river_mile"),
            "distance_from_lock": official.get("distance_from_lock_miles"),
            "source": official.get("source"),
            "datum": official.get("datum"),
        },
        "conditions": {
            "timestamp": official.get("observed_at"),
            "gage_height_ft": raw.get("gage_height_ft") if official.get("measurement_type") == "gage_height" else None,
            "river_stage_ft": raw.get("river_stage_ft") if official.get("measurement_type") == "river_stage" else None,
            "water_temp_f": raw.get("water_temp_f"),
            "water_temp_c": raw.get("water_temp_c"),
            "discharge_cfs": raw.get("discharge_cfs"),
            "current_speed_mph": None,  # computed below from OFFICIAL discharge only
            "flood_stage": legacy_flood_status,
            "status_explanation": official.get("status_explanation"),
            "source_status": official.get("source_status"),
            "fetch_method": official.get("fetch_method"),
            "fallback_used": official.get("fallback_used", False),
            "from_reference": False,
        },
        "flood_stages": official.get("thresholds") or {},
        "threshold_source": official.get("threshold_source"),
    }

    # Only derive current_speed_mph from the OFFICIAL discharge. Never mix
    # reference-station discharge into the official conditions block.
    discharge = raw.get("discharge_cfs")
    if discharge:
        fps = discharge / (2000 * 15)
        payload["conditions"]["current_speed_mph"] = round(fps * 0.681818, 1)

    return payload


@api_router.get("/locks/{lock_id}/water-condition-debug")
async def get_water_condition_debug(lock_id: str):
    """
    Diagnostic view of the water-condition station mapping for `lock_id`.

    Returns the selected official station, any alternate (reference)
    stations, raw fetched values, thresholds with source citation, source
    URLs, and why this station was selected.
    """
    if lock_id not in LOCKS:
        raise HTTPException(status_code=404, detail="Invalid lock ID")
    from services.water_station_service import get_debug as _debug_water
    return await _debug_water(lock_id)


@api_router.get("/water-conditions")
async def get_all_water_conditions():
    """Get water conditions for all locks using each lock's own NWS gauge."""
    results = {}
    for lock_id, cfg in LOCK_GAUGES.items():
        if lock_id not in LOCKS:
            continue
        nws = await fetch_nws_gauge_data(cfg["nwsli"])
        stage = nws.get("stage")
        category = nws.get("flood_category") or "normal"
        if category == "normal" and stage is not None:
            thresholds = cfg["stages"]
            if stage >= thresholds.get("major", float("inf")):
                category = "major"
            elif stage >= thresholds.get("moderate", float("inf")):
                category = "moderate"
            elif stage >= thresholds.get("flood", float("inf")):
                category = "flood"
            elif stage >= thresholds.get("action", float("inf")):
                category = "action"
        results[lock_id] = {
            "gauge_name": nws.get("name") or cfg["name"],
            "nwsli": cfg["nwsli"],
            "gage_height_ft": stage,
            "datum": cfg["datum"],
            "flood_stage": category,
        }
    return results


@api_router.get("/usace/lock-queue")
async def get_usace_lock_queue():
    """Get current USACE lock queue data (vessels with barge counts)."""
    data = await fetch_usace_lock_queue_data()
    return {
        "vessel_count": len(data),
        "last_updated": usace_lock_queue_cache["last_updated"].isoformat() if usace_lock_queue_cache["last_updated"] else None,
        "vessels": list(data.values())
    }


@api_router.post("/usace/refresh", dependencies=[Depends(require_admin)])
async def refresh_usace_data():
    """USACE queue data status. Refreshing is continuous (one lock every
    USACE_SPACING_S, within USACE's 5-requests-per-minute limit), so this
    reports the current state rather than forcing a burst of requests."""
    data = await fetch_usace_lock_queue_data()
    oldest = min(usace_lock_fetched_at.values()) if usace_lock_fetched_at else None
    return {
        "success": True,
        "vessel_count": len(data),
        "locks_fetched": len(usace_lock_fetched_at),
        "oldest_lock_data": oldest.isoformat() if oldest else None,
        "message": f"USACE data: {len(data)} vessels in queues; refreshed continuously",
    }


@api_router.get("/usace/vessel/{mmsi}")
async def get_usace_vessel(mmsi: str):
    """Get USACE lock queue info for a specific vessel by MMSI."""
    data = await fetch_usace_lock_queue_data()
    vessel_info = data.get(mmsi)
    if vessel_info:
        return {"found": True, "vessel": vessel_info}
    return {"found": False, "message": f"Vessel {mmsi} not found in USACE lock queue data"}


@api_router.post("/lockage/record", dependencies=[Depends(require_admin)])
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


@api_router.get("/debug/state", dependencies=[Depends(require_admin)])
async def get_debug_state():
    """Get current application state for debugging."""
    return {
        "demo_vessels_active": demo_vessels_active,
        "active_vessels_count": len(active_vessels),
        "active_vessel_mmsis": list(active_vessels.keys()),
        "vessel_cache_count": len(vessel_static_cache),
        "cached_vessel_names": {k: v.get('name', 'unnamed') for k, v in vessel_static_cache.items()},
        "filtered_mmsis": list(FILTERED_MMSI),
    }


@api_router.get("/debug/performance", dependencies=[Depends(require_admin)])
async def get_performance_stats():
    """Get performance statistics for monitoring."""
    cache_stats = await get_cache_stats()
    return {
        "active_vessels": len(active_vessels),
        "vessel_cache_entries": vessel_cache.count,
        "caches": cache_stats,
        "websocket_connections": len(ais_manager._subscribers),
        "ais_connected": ais_manager.is_connected,
        "demo_vessels_active": demo_vessels_active
    }


@api_router.get("/lockage/tracking")
async def get_lockage_tracking():
    """Get current vessel lock passage tracking state."""
    tracking_info = {}
    for mmsi, locks in vessel_lock_tracking.items():
        if locks:
            tracking_info[mmsi] = {}
            for lock_id, data in locks.items():
                tracking_info[mmsi][lock_id] = {
                    "state": data.get("state"),
                    "direction": data.get("direction"),
                    "vessel_name": data.get("vessel_name"),
                    "is_tow": data.get("is_tow"),
                    "arrival_time": data.get("arrival_time").isoformat() if data.get("arrival_time") else None,
                    "entry_time": data.get("entry_time").isoformat() if data.get("entry_time") else None,
                    "wait_time_minutes": round(data.get("wait_time_minutes", 0), 1) if data.get("wait_time_minutes") else None,
                }
    
    return {
        "vessels_being_tracked": len(tracking_info),
        "tracking": tracking_info
    }


@api_router.get("/lockage/history")
async def get_lockage_history(lock_id: str = None, days: int = 7):
    """Get recent lockage history from the database."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    query = {"recorded_at": {"$gte": cutoff}}
    if lock_id:
        query["lock_id"] = lock_id
    
    records = await db.lockage_history.find(query, {"_id": 0}).sort("recorded_at", -1).to_list(100)
    
    # Convert datetime objects to ISO strings
    for record in records:
        for key in ["arrival_time", "entry_time", "exit_time", "recorded_at"]:
            if record.get(key) and isinstance(record[key], datetime):
                record[key] = record[key].isoformat()
    
    return {
        "count": len(records),
        "records": records
    }


@api_router.get("/vessels/sightings")
async def get_vessel_sightings(days: int = 30, usace_only: bool = False):
    """
    Get historical vessel sightings from the database.
    
    Args:
        days: Number of days to look back (default 30)
        usace_only: If true, only return sightings with USACE data
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    query = {"timestamp": {"$gte": cutoff}}
    if usace_only:
        query["usace_source"] = True
    
    sightings = await db.vessel_sightings.find(query, {"_id": 0}).sort("timestamp", -1).to_list(500)
    
    # Convert datetime objects
    for record in sightings:
        for key in ["timestamp", "first_seen"]:
            if record.get(key) and isinstance(record[key], datetime):
                record[key] = record[key].isoformat()
    
    return {
        "count": len(sightings),
        "sightings": sightings
    }


@api_router.get("/vessels/history/{mmsi}")
async def get_vessel_history(mmsi: str, days: int = 30):
    """
    Get historical sightings for a specific vessel.
    Includes all USACE data records (barge counts, lock positions, etc.)
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Get historical records with USACE data
    records = await db.vessel_history.find(
        {"mmsi": mmsi, "recorded_at": {"$gte": cutoff}},
        {"_id": 0}
    ).sort("recorded_at", -1).to_list(200)
    
    # Convert datetime objects
    for record in records:
        for key in ["timestamp", "recorded_at"]:
            if record.get(key) and isinstance(record[key], datetime):
                record[key] = record[key].isoformat()
    
    # Get current sighting
    current = await db.vessel_sightings.find_one({"mmsi": mmsi}, {"_id": 0})
    if current:
        for key in ["timestamp", "first_seen"]:
            if current.get(key) and isinstance(current[key], datetime):
                current[key] = current[key].isoformat()
    
    # Lockages this vessel made (USACE-reported and AIS-detected), newest first
    lockages = await db.lockage_history.find(
        {"mmsi": mmsi, "recorded_at": {"$gte": cutoff}}, {"_id": 0}
    ).sort("recorded_at", -1).to_list(100)
    lockages = [lockage_for_output(lk) for lk in lockages]

    return {
        "mmsi": mmsi,
        "current": current,
        "history_count": len(records),
        "history": records,
        "lockage_history": lockages,
    }


@api_router.get("/vessels/stats")
async def get_vessel_stats():
    """Get summary statistics of vessel sightings and USACE data."""
    # Total unique vessels seen
    total_vessels = await db.vessel_sightings.count_documents({})
    
    # Vessels with USACE data
    usace_vessels = await db.vessel_sightings.count_documents({"usace_source": True})
    
    # Tows tracked
    tows_tracked = await db.vessel_sightings.count_documents({"is_tow": True})
    
    # Historical USACE records
    history_count = await db.vessel_history.count_documents({})
    
    # Get recent tow activity (last 7 days)
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_tows = await db.vessel_history.find(
        {"recorded_at": {"$gte": seven_days_ago}, "is_tow": True},
        {"_id": 0, "mmsi": 1, "name": 1, "barge_count": 1, "usace_lock": 1}
    ).sort("recorded_at", -1).to_list(50)
    
    return {
        "total_vessels_seen": total_vessels,
        "vessels_with_usace_data": usace_vessels,
        "tows_tracked": tows_tracked,
        "historical_usace_records": history_count,
        "recent_tow_activity": recent_tows
    }


@api_router.get("/lockage/stats")
async def get_lockage_stats():
    """Get summary statistics of recorded lockages."""
    # Count total records
    total_count = await db.lockage_history.count_documents({})
    
    # Get records from last 7 days
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_count = await db.lockage_history.count_documents({"recorded_at": {"$gte": seven_days_ago}})
    
    # Get averages by lock
    pipeline = [
        {"$match": {"recorded_at": {"$gte": seven_days_ago}}},
        {"$group": {
            "_id": "$lock_id",
            "count": {"$sum": 1},
            "avg_lockage": {"$avg": "$lockage_duration_minutes"},
            "avg_wait": {"$avg": "$wait_time_minutes"},
            "max_wait": {"$max": "$wait_time_minutes"}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    stats_by_lock = await db.lockage_history.aggregate(pipeline).to_list(50)
    
    return {
        "total_records": total_count,
        "records_last_7_days": recent_count,
        "by_lock": [
            {
                "lock_id": s["_id"],
                "count": s["count"],
                "avg_lockage_minutes": round(s["avg_lockage"], 1) if s["avg_lockage"] else None,
                "avg_wait_minutes": round(s["avg_wait"], 1) if s["avg_wait"] else None,
                "max_wait_minutes": round(s["max_wait"], 1) if s["max_wait"] else None
            }
            for s in stats_by_lock
        ]
    }


@api_router.post("/connection/test", dependencies=[Depends(require_user)])
async def test_connection(config: ConnectionConfig):
    """Test that an AIS TCP feed is reachable (non-blocking)."""
    err = await asyncio.to_thread(validate_feed_target, config.ip_address, config.port)
    if err:
        return {"success": False, "message": err}
    try:
        _r, w = await asyncio.wait_for(asyncio.open_connection(config.ip_address, config.port), timeout=5)
        w.close()
        try:
            await w.wait_closed()
        except Exception:
            pass
        return {"success": True, "message": "Connection successful"}
    except ConnectionRefusedError:
        return {"success": False, "message": "Connection refused - Boat Beacon may not be running or the IP is unreachable from this server."}
    except asyncio.TimeoutError:
        return {"success": False, "message": "Connection timed out - check the IP address and ensure Boat Beacon TCP server is enabled."}
    except OSError as e:
        return {"success": False, "message": f"Connection failed: {e.strerror or e}"}


@api_router.get("/connection/status", dependencies=[Depends(require_user)])
async def get_connection_status():
    """Get the current AIS connection status."""
    return ais_manager.get_status()


@api_router.post("/connection/reconnect", dependencies=[Depends(require_user)])
async def reconnect_ais():
    """Force reconnection to the AIS feed."""
    if not ais_manager.config:
        return {"success": False, "message": "No connection configured"}
    
    config = ais_manager.config
    await ais_manager.configure(
        config["ip_address"],
        config["port"],
        config.get("user_mmsi", ""),
        config.get("boat_name", "")
    )
    return {"success": True, "message": "Reconnection initiated"}

@api_router.post("/connection/start", dependencies=[Depends(require_user)])
async def start_connection(config: ConnectionConfig):
    """Start the AIS connection with the given configuration.

    Also persists the config to the `settings` collection under key
    `last_connection_config` so the connection is auto-restored on backend
    restart (important for the Pi where the systemd service may restart
    overnight and we don't want the user to re-enter the phone IP)."""
    err = await asyncio.to_thread(validate_feed_target, config.ip_address, config.port)
    if err:
        raise HTTPException(status_code=400, detail=err)
    await ais_manager.configure(
        config.ip_address,
        config.port,
        config.user_mmsi,
        getattr(config, "boat_name", "") or ""
    )

    # Persist for auto-restore on reboot.
    try:
        await db.settings.update_one(
            {"key": "last_connection_config"},
            {"$set": {
                "value": json.dumps({
                    "ip_address": config.ip_address,
                    "port": config.port,
                    "user_mmsi": config.user_mmsi,
                    "boat_name": getattr(config, "boat_name", "") or "",
                }),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"Failed to persist last_connection_config: {e}")

    return {"success": True, "message": f"Connection started to {config.ip_address}:{config.port}"}


@api_router.post("/connection/stop", dependencies=[Depends(require_user)])
async def stop_connection():
    """Stop the AIS connection (manual disconnect from Settings page)."""
    await ais_manager.disconnect()
    return {"success": True, "message": "AIS connection stopped"}


# =============================================================================
# NMEA INGEST ENDPOINT (push-based relay)
# =============================================================================
# Lets a local relay script (e.g. /app/scripts/ais_relay.py) POST raw NMEA
# lines over plain HTTPS. The VM's cloud backend cannot dial back into a
# user's LAN (private RFC1918), so the relay pushes here instead.
#
# Request body:
#   {
#     "user_mmsi": "367123450",
#     "boat_name": "MY BOAT",          (optional)
#     "lines": ["$GPRMC,...", "!AIVDM,...", ...]
#   }
#
# Response: {"accepted": N, "echoed": M}
@api_router.post("/ais/ingest")
async def ingest_nmea(payload: dict, request: Request):
    """Accept a batch of raw NMEA lines from a local relay and process them
    through the same pipeline used by the live TCP feed.

    The relay is identity-free: AIS sentences already contain MMSI, and GPS
    sentences get attributed to whichever MMSI is configured on the AIS
    manager (set when the dashboard user clicks Connect)."""
    if not _ingest_token_ok(request):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Ingest-Token")
    lines = payload.get("lines") or []
    if not isinstance(lines, list):
        raise HTTPException(status_code=400, detail="`lines` must be a list of NMEA strings")
    if len(lines) > 2000:
        raise HTTPException(status_code=413, detail="Too many lines in one batch (max 2000)")

    # Mark the manager as "connected" via push so /api/connection/status
    # and the UI reflect a live feed even without a TCP dial-in.
    if not ais_manager._config:
        ais_manager._config = {
            "ip_address": "push://relay",
            "port": 0,
            "user_mmsi": "",
            "boat_name": "",
        }
    ais_manager._connected = True
    ais_manager._last_data_time = datetime.now(timezone.utc)

    accepted = 0
    for raw in lines:
        if not isinstance(raw, str):
            continue
        line = raw.strip()
        if not line or len(line) > 300:  # NMEA sentences are <= 82 chars; allow slack
            continue
        try:
            await ais_manager._process_line(line)
            accepted += 1
        except Exception as e:
            logger.warning(f"ingest_nmea: failed to process line: {e}")

    return {
        "accepted": accepted,
        "received": len(lines),
        "subscriber_count": ais_manager.subscriber_count,
        "last_data_time": ais_manager._last_data_time.isoformat() if ais_manager._last_data_time else None,
    }


@api_router.get("/vessel-cache")
async def get_vessel_cache():
    """Get cached vessel static data (names, dimensions, etc.)"""
    return {
        "cached_vessels": len(vessel_static_cache),
        "cache": vessel_static_cache
    }


# Serve the one-click Windows relay launcher. We bake the script's
# base64 contents into this file so it works inside the backend container
# without needing the scripts/ directory mounted.
from fastapi.responses import FileResponse as _FileResponse, Response as _Response  # noqa: E402
import base64 as _b64  # noqa: E402

def _generate_relay_bat(vm_url: str) -> bytes:
    """Build RIVERWATCH.bat dynamically with the requested VM URL baked in.
    The embedded PowerShell relay is the HTTPS-push version."""
    ps1 = """[CmdletBinding()]
param(
    [string]$BoatBeaconIp   = $(if ($env:BOAT_BEACON_IP)   { $env:BOAT_BEACON_IP }   else { "192.168.0.25" }),
    [int]   $BoatBeaconPort = $(if ($env:BOAT_BEACON_PORT) { [int]$env:BOAT_BEACON_PORT } else { 5353 }),
    [string]$VmUrl          = $(if ($env:VM_URL)           { $env:VM_URL }           else { "__VM_URL__" }),
    [string]$IngestToken    = $(if ($env:AIS_INGEST_TOKEN) { $env:AIS_INGEST_TOKEN } else { "__INGEST_TOKEN__" }),
    [double]$BatchSeconds   = 1.0,
    [int]   $MaxBatchLines  = 200
)
$ErrorActionPreference = "Stop"
$VmUrl = $VmUrl.TrimEnd('/')
$IngestUrl = "$VmUrl/api/ais/ingest"
function Write-Log([string]$msg) { Write-Host ("[" + (Get-Date).ToString("HH:mm:ss") + "] " + $msg) }
Write-Log "River Watch NMEA Relay -> $IngestUrl"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
$buffer = New-Object System.Collections.Generic.List[string]
$lock = New-Object Object
$stats = [pscustomobject]@{ LinesRead=0; LinesSent=0; BatchesSent=0; Errors=0 }
function Send-Batch([System.Collections.Generic.List[string]]$lines) {
    $body = @{ lines = @($lines) } | ConvertTo-Json -Compress
    try {
        $resp = Invoke-RestMethod -Uri $IngestUrl -Method Post -ContentType "application/json" -Body $body -TimeoutSec 15 -Headers @{ "X-Ingest-Token" = $IngestToken }
        $stats.BatchesSent++; $stats.LinesSent += $lines.Count
        if ($stats.BatchesSent -le 3 -or ($stats.BatchesSent % 30) -eq 0) {
            Write-Log ("POST -> 200  accepted={0}/{1}  total_sent={2}" -f $resp.accepted, $resp.received, $stats.LinesSent)
        }
        return $true
    } catch { $stats.Errors++; Write-Log ("POST FAILED: " + $_.Exception.Message); return $false }
}
$client = $null; $stream = $null; $reader = $null
$lastFlush = Get-Date
try {
    while ($true) {
        if (-not $client -or -not $client.Connected) {
            try {
                Write-Log "Connecting to Boat Beacon @ ${BoatBeaconIp}:${BoatBeaconPort} ..."
                $client = New-Object System.Net.Sockets.TcpClient
                $client.ReceiveTimeout = 30000; $client.SendTimeout = 10000
                $iar = $client.BeginConnect($BoatBeaconIp, $BoatBeaconPort, $null, $null)
                if (-not $iar.AsyncWaitHandle.WaitOne(10000)) { throw "Boat Beacon connect timeout" }
                $client.EndConnect($iar)
                $stream = $client.GetStream(); $stream.ReadTimeout = 30000
                $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::ASCII)
                Write-Log "Boat Beacon connected. Streaming NMEA..."
            } catch { $stats.Errors++; Write-Log ("Connect failed: " + $_.Exception.Message + " - retry 5s"); Start-Sleep 5; continue }
        }
        try {
            $line = $reader.ReadLine()
            if ($null -eq $line) { Write-Log "Boat Beacon closed connection."; try { $client.Close() } catch {}; $client = $null; Start-Sleep 2; continue }
            $line = $line.Trim()
            if ($line.Length -gt 0) {
                [System.Threading.Monitor]::Enter($lock); try { $buffer.Add($line) | Out-Null; $stats.LinesRead++ } finally { [System.Threading.Monitor]::Exit($lock) }
                if ($stats.LinesRead -le 5) { Write-Log ("NMEA: " + $line.Substring(0, [Math]::Min(90, $line.Length))) }
            }
        } catch [System.IO.IOException] { $stats.Errors++; Write-Log ("Read error: " + $_.Exception.Message); try { $client.Close() } catch {}; $client = $null; Start-Sleep 2; continue }
        $age = ((Get-Date) - $lastFlush).TotalSeconds
        if ($age -ge $BatchSeconds) {
            $toSend = $null
            [System.Threading.Monitor]::Enter($lock)
            try {
                if ($buffer.Count -gt 0) {
                    $take = [Math]::Min($buffer.Count, $MaxBatchLines)
                    $toSend = New-Object System.Collections.Generic.List[string]
                    for ($i = 0; $i -lt $take; $i++) { $toSend.Add($buffer[$i]) | Out-Null }
                    $buffer.RemoveRange(0, $take)
                }
            } finally { [System.Threading.Monitor]::Exit($lock) }
            if ($toSend -and $toSend.Count -gt 0) {
                if (-not (Send-Batch $toSend)) {
                    [System.Threading.Monitor]::Enter($lock); try { $buffer.InsertRange(0, $toSend) } finally { [System.Threading.Monitor]::Exit($lock) }
                    Start-Sleep 2
                }
            }
            $lastFlush = Get-Date
        }
    }
} finally {
    foreach ($d in @($reader, $stream, $client)) { if ($d) { try { $d.Dispose() } catch {} } }
}
""".replace("__VM_URL__", vm_url).replace("__INGEST_TOKEN__", os.environ.get("AIS_INGEST_TOKEN", ""))

    b64 = _b64.b64encode(ps1.encode("utf-8")).decode("ascii")
    chunks = [b64[i:i+200] for i in range(0, len(b64), 200)]
    echo_lines = "\r\n".join([f"echo {c}" for c in chunks])

    bat = (
        "@echo off\r\n"
        f'set "VM_URL={vm_url}"\r\n'
        'set "BOAT_BEACON_IP=192.168.0.25"\r\n'
        'set "BOAT_BEACON_PORT=5353"\r\n'
        "setlocal enabledelayedexpansion\r\n"
        "title River Watch Relay\r\n"
        "echo ================================================================\r\n"
        "echo   River Watch Relay (HTTPS push)\r\n"
        "echo   Beacon : %BOAT_BEACON_IP%:%BOAT_BEACON_PORT%\r\n"
        "echo   VM URL : %VM_URL%\r\n"
        "echo ================================================================\r\n"
        'set "RELAY_PS1=%TEMP%\\riverwatch-relay.ps1"\r\n'
        'set "RELAY_B64=%TEMP%\\riverwatch-relay.b64"\r\n'
        '> "%RELAY_B64%" (\r\n'
        "echo -----BEGIN CERTIFICATE-----\r\n"
        f"{echo_lines}\r\n"
        "echo -----END CERTIFICATE-----\r\n"
        ")\r\n"
        'certutil -decode -f "%RELAY_B64%" "%RELAY_PS1%" >nul\r\n'
        'if not exist "%RELAY_PS1%" ( echo ERROR: failed to write relay script. & pause & exit /b 1 )\r\n'
        'powershell -NoProfile -ExecutionPolicy Bypass -File "%RELAY_PS1%" '
        '-BoatBeaconIp "%BOAT_BEACON_IP%" -BoatBeaconPort %BOAT_BEACON_PORT% -VmUrl "%VM_URL%"\r\n'
        "echo Relay exited. Press any key.\r\n"
        "pause >nul\r\n"
        "endlocal\r\n"
    )
    return bat.encode("utf-8")


# Admin only: the generated script embeds AIS_INGEST_TOKEN, and anyone can
# register an account. With the token they could push fake AIS for any boat.
@api_router.get("/relay/download", dependencies=[Depends(require_admin)])
async def download_relay_bat(request: Request):
    """Return a freshly-generated RIVERWATCH.bat that points at THIS VM."""
    # Use the Host header so the .bat always targets whatever URL the client used
    host = request.headers.get("host") or "127.0.0.1"
    scheme = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
    vm_url = f"{scheme}://{host}"
    content = _generate_relay_bat(vm_url)
    return _Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="RIVERWATCH.bat"'},
    )


@api_router.get("/install/tarball")
async def download_install_tarball():
    """Return the tarball bundle of the latest backend/frontend/scripts changes."""
    path = "/app/dist/riverwatch-update.tar.gz"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Install bundle not built on server")
    return _FileResponse(
        path,
        media_type="application/gzip",
        filename="riverwatch-update.tar.gz",
    )


@api_router.get("/install/bootstrap")
async def download_install_bootstrap():
    """Return the one-shot installer shell script."""
    path = "/app/dist/install.sh"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Installer not built on server")
    return _FileResponse(
        path,
        media_type="text/x-shellscript",
        filename="install.sh",
    )

@api_router.get("/river-mile-to-coords/{rm}")
async def convert_rm_to_coords(rm: float):
    """Convert a river mile to approximate lat/lon coordinates."""
    lat, lon = river_mile_to_coords(rm)
    # Also return the estimated RM back (for verification)
    estimated_rm = estimate_river_mile(lat, lon)
    up = _river_geo.channel_bearing_at_mile(rm)
    return {
        "river_mile": rm,
        "lat": lat,
        "lon": lon,
        "estimated_rm_back": estimated_rm,
        # Course to steer for each direction here (the river isn't north-south)
        "upbound_course": up,
        "downbound_course": None if up is None else round((up + 180) % 360, 1),
    }

@api_router.post("/vessel-cache/{mmsi}")
async def set_vessel_name(mmsi: str, data: dict, user: dict = Depends(require_user)):
    """
    Manually set a vessel name in the cache.
    This persists to MongoDB and is shared across all users/sessions, so
    only the boat's owner (or an admin) may name it.
    """
    _require_owner(user, mmsi)
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
    await repos.vessels.save_vessel_name(
        mmsi=mmsi,
        name=data.get('name'),
        ship_type=data.get('ship_type'),
        source="user"
    )
    logger.info(f"Saved vessel name to database: MMSI {mmsi} = {data.get('name')}")
    
    # Also update active vessel if present
    if mmsi in active_vessels:
        vessel = active_vessels[mmsi]
        # Handle both dict and Pydantic model
        if isinstance(vessel, dict):
            if data.get('name'):
                vessel['name'] = data['name']
            if data.get('ship_type') is not None:
                vessel['ship_type'] = data['ship_type']
        else:
            # Pydantic model
            if data.get('name'):
                vessel.name = data['name']
            if data.get('ship_type') is not None:
                vessel.ship_type = data['ship_type']
    
    return {"success": True, "cached": vessel_static_cache.get(mmsi), "persisted": True}

async def load_vessel_names_from_db():
    """Load all persisted vessel names from MongoDB on startup."""
    global vessel_static_cache
    
    try:
        vessels = await repos.vessels.get_all_vessel_names()
        
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
    """Get all tracked vessels, enriched with USACE lock queue data.

    NOTE: This endpoint has no session context, so `is_user_vessel` is always
    False here. Use `/api/session/{mmsi}/vessels` to get per-session highlighting.
    """
    vessels = []
    # Hide demo vessels when live AIS has been received (auto mode)
    suppress_demo = _should_suppress_demo_vessels()
    for mmsi, vessel in active_vessels.items():
        # Skip filtered/blocked MMSI
        if is_mmsi_blocked(mmsi):
            continue
        # Hide demo vessels once real AIS has started flowing
        if suppress_demo and _is_demo_vessel(vessel, mmsi):
            continue
        # Use centralized helper to ensure clean data output
        # IMPORTANT: pass None for session_mmsi so is_user_vessel=False for all.
        v_dict = prepare_vessel_for_output(vessel, None)
        vessels.append(v_dict)
    return vessels

@api_router.get("/session/{session_mmsi}/race-analysis/{lock_id}")
async def get_session_race_analysis(session_mmsi: str, lock_id: str, request: Request = None, buffer_minutes: int = 20,
                                    max_speed_mph: float = 25.0):
    """
    Get race analysis for a specific session (MMSI) and lock.
    
    CRITICAL: This endpoint is EXPLICITLY scoped to a session.
    Each session gets race analysis calculated for THEIR vessel.
    
    Args:
        session_mmsi: The session's MMSI (their vessel)
        lock_id: Target lock ID
        buffer_minutes: Minutes of buffer needed before a commercial tow arrives
    """
    session_mmsi = str(session_mmsi).strip()
    await _check_session_owner(request, session_mmsi)
    
    # Validate session
    if not session_mmsi:
        raise HTTPException(status_code=400, detail="Session MMSI required")
    
    logger.info(f"[SESSION:{session_mmsi}] Race analysis requested for {lock_id}")
    
    # Distance threshold - don't warn about vessels more than 100 miles from USER
    MAX_THREAT_DISTANCE = 100.0
    
    if lock_id not in LOCKS:
        raise HTTPException(status_code=404, detail="Invalid lock ID")
    
    lock = LOCKS[lock_id]
    lock_rm = lock["river_mile"]
    
    # Find THIS SESSION's vessel - completely isolated
    user_vessel = None
    user_rm = None
    if session_mmsi and session_mmsi in active_vessels:
        user_vessel = prepare_vessel_for_output(active_vessels[session_mmsi], session_mmsi)
        user_rm = user_vessel.get('river_mile') or estimate_river_mile(user_vessel['lat'], user_vessel['lon'])
    
    # Find competitors heading toward this lock
    competitors = []
    for mmsi, vessel in active_vessels.items():
        if mmsi == session_mmsi:
            continue

        # Skip other users' simulated vessels (orphan "Your Vessel" entries from
        # prior sessions). Demo tows are is_demo=True without is_simulated and
        # remain eligible as competitors.
        if isinstance(vessel, dict) and vessel.get('is_simulated') and vessel.get('is_user_vessel'):
            continue

        # Handle both Pydantic models and dicts (demo vessels are dicts)
        if hasattr(vessel, 'river_mile'):
            # Pydantic model
            vessel_rm = vessel.river_mile or estimate_river_mile(vessel.lat, vessel.lon)
            vessel_speed = vessel.speed
            vessel_heading = vessel.heading or determine_heading(vessel.speed, vessel.course, vessel.lat, vessel.lon)
            vessel_course = vessel.course
        else:
            # Dict (demo vessels)
            vessel_rm = vessel.get('river_mile') or estimate_river_mile(vessel.get('lat'), vessel.get('lon'))
            vessel_speed = vessel.get('speed', 0)
            vessel_heading = vessel.get('heading') or vessel.get('heading_direction') or determine_heading(vessel.get('speed', 0), vessel.get('course', 0), vessel.get('lat'), vessel.get('lon'))
            vessel_course = vessel.get('course', 0)
        
        eta = calculate_eta_to_lock(
            vessel_rm,
            vessel_speed,
            vessel_heading,
            lock_rm
        )
        
        if eta is not None and eta > 0:
            # Use prepare_vessel_for_output for clean data
            v_dict = prepare_vessel_for_output(vessel, None)  # another boat: never "yours"
            v_dict['eta_minutes'] = eta
            
            # Calculate distance from this competitor TO THE LOCK (for bi-directional filtering)
            v_dict['distance_to_lock'] = round(abs(vessel_rm - lock_rm), 1) if vessel_rm else None
            
            # Calculate distance from USER to this competitor (for display)
            if user_rm and vessel_rm:
                v_dict['distance_from_user'] = round(abs(user_rm - vessel_rm), 1)
            else:
                v_dict['distance_from_user'] = None
                
            competitors.append(v_dict)
    
    # Sort by ETA
    competitors.sort(key=lambda x: x.get('eta_minutes', float('inf')))
    
    # Calculate analysis if user vessel exists
    analysis = None
    if user_vessel and user_rm:
        user_heading = user_vessel.get('heading', 'southbound')
        user_distance = abs(user_rm - lock_rm)
        user_speed_knots = user_vessel.get('speed', 0)
        user_speed_mph = user_speed_knots * 1.15078
        
        user_eta = calculate_eta_to_lock(user_rm, user_speed_knots, user_heading, lock_rm)

        # If the user's vessel is stopped, do not calculate impossible "speed to beat"
        # values. A stopped vessel obviously cannot beat traffic to the lock, and the
        # frontend should not display panic values like 888 MPH.
        user_stopped_for_timing = (
            user_speed_mph < 0.5
            or user_heading == "stationary"
            or user_eta is None
        )
        # Already at the lock (approach wall / chamber): nobody still on the
        # way can get there first - they queue behind you. Boats already
        # waiting are in the wait estimate. (Seen: "Traffic Ahead: MARY J,
        # ETA 437 min" while REBOOT sat at Lock 4.)
        user_at_lock = user_distance <= _lock_board.AT_LOCK_MI and user_speed_knots < _lock_board.SLOW_KNOTS
        # Stopped with no direction of travel (e.g. at its home berth): not
        # headed for any lock, so nothing to race. (Seen: "Traffic Ahead:
        # ITASCA" for REBOOT sitting in its slip.)
        user_parked = (not user_at_lock and user_speed_mph < 0.5
                       and user_heading not in ('northbound', 'southbound'))

        # Find most threatening competitor
        # LOGIC: Any vessel heading TOWARD the lock is a potential competitor,
        # regardless of which side of the lock they're on (bi-directional).
        # The competitors list already only contains vessels with valid ETAs
        # (i.e., vessels heading toward the lock - calculate_eta_to_lock returns None for vessels moving away)
        threat = None
        required_speed = None
        can_beat = True
        
        for comp in ([] if (user_at_lock or user_parked) else competitors):
            comp_eta = comp.get('eta_minutes')
            comp_distance_to_lock = comp.get('distance_to_lock')
            
            # Skip if this competitor is more than 100 miles from the LOCK
            # (using distance to lock, not distance from user, for bi-directional logic)
            if comp_distance_to_lock is not None and comp_distance_to_lock > MAX_THREAT_DISTANCE:
                continue
            
            # Check if this competitor will arrive before user (with buffer)
            # Competitors are already sorted by ETA, so first valid one is the biggest threat
            if comp_eta and (user_stopped_for_timing or user_eta is None or comp_eta < user_eta + buffer_minutes):
                # User needs to arrive buffer_minutes BEFORE the tow to get through first.
                # If stopped, keep the traffic threat but suppress impossible speed math.
                threat = comp

                if user_stopped_for_timing:
                    required_speed = None
                    can_beat = False
                else:
                    required_speed = calculate_required_speed(user_rm, user_heading, lock_rm, comp_eta, buffer_minutes)
                    if required_speed is None or required_speed > max_speed_mph:
                        can_beat = False
                break
        
        analysis = {
            "user_distance_to_lock": round(user_distance, 1),
            "user_eta_minutes": user_eta,
            "user_current_speed_mph": round(user_speed_mph, 1),
            "threatening_vessel": threat,
            "required_speed_mph": required_speed,
            "can_beat_at_25mph": can_beat,          # legacy key: evaluated at max_speed_mph
            "can_beat_at_max_speed": can_beat,
            "max_speed_mph": max_speed_mph,
            "buffer_minutes": buffer_minutes,
            "timing_paused": user_stopped_for_timing,
            "timing_paused_reason": ("at_lock" if user_at_lock else "stopped") if user_stopped_for_timing else None,
            "user_at_lock": user_at_lock,
            "user_parked": user_parked,
        }
    
    return RaceAnalysis(
        user_vessel=user_vessel,
        target_lock=lock_id,
        target_lock_name=lock["name"],
        target_lock_rm=lock["river_mile"],
        competitors=competitors,
        analysis=analysis
    )


# Legacy race analysis endpoint - requires mmsi query param
@api_router.get("/race-analysis/{lock_id}")
async def get_race_analysis_legacy(lock_id: str, request: Request, mmsi: str = None, buffer_minutes: int = 20,
                                   max_speed_mph: float = 25.0):
    """
    LEGACY: Get race analysis for a lock.
    
    DEPRECATED: Use GET /session/{mmsi}/race-analysis/{lock_id} instead.
    """
    if not mmsi:
        raise HTTPException(status_code=400, detail="mmsi query parameter required. Use GET /session/{mmsi}/race-analysis/{lock_id}")
    
    return await get_session_race_analysis(mmsi, lock_id, request, buffer_minutes, max_speed_mph)


# =============================================================================
# TRIP PLAN - Chain Race Analysis Across Multiple Locks Ahead
# =============================================================================
DEPARTURE_OFFSETS = [0, 30, 60, 120, 240]


_lock_notes_cache: tuple = (None, {})


async def _lock_notes() -> Dict[str, str]:
    """Planning warnings per lock: closed / restricted (district page) or no
    USACE lockages for far longer than usual (lockage_gap_note). Read from the
    stored lock status, cached for a minute."""
    global _lock_notes_cache
    now = datetime.now(timezone.utc)
    at, notes = _lock_notes_cache
    if at and now - at < timedelta(seconds=60):
        return notes
    notes = {}
    try:
        async for s in db.lock_status.find({}, {"_id": 0, "lock_id": 1, "status": 1, "closure_info": 1,
                                                 "status_source": 1}):
            info = s.get("closure_info")
            if info and (s.get("status") in ("CLOSED", "RESTRICTED") or s.get("status_source") == "lockage_gap"):
                notes[s["lock_id"]] = info
    except Exception as e:
        logger.warning(f"Could not read lock notes: {e}")
    _lock_notes_cache = (now, notes)
    return notes

@api_router.get("/session/{session_mmsi}/departure-options")
async def get_departure_options(session_mmsi: str, direction: str, request: Request = None, cruise_mph: float = 15.0,
                                destination_rm: Optional[float] = None, max_locks: int = 5):
    """For a boat that is stopped (the trip plan needs it under way): leave now,
    in 30 min, 1 h, 2 h or 4 h - expected wait at each lock when you'd get
    there (same model as the trip plan, incl. tows predicted to arrive) and
    when you'd finish. `best` is the option with the least time at locks."""
    session_mmsi = str(session_mmsi).strip()
    await _check_session_owner(request, session_mmsi)
    if direction not in ("upbound", "downbound"):
        raise HTTPException(status_code=400, detail="direction must be upbound or downbound")
    speed = max(1.0, min(float(cruise_mph or 15.0), 60.0))
    max_locks = max(1, min(int(max_locks or 5), 15))
    v = active_vessels.get(session_mmsi)
    if v is None:
        return {"session_mmsi": session_mmsi, "start_rm": None, "options": [], "best": None, "locks": []}
    vd = prepare_vessel_for_output(v, session_mmsi)
    start_rm = vd.get('river_mile') or estimate_river_mile(vd.get('lat'), vd.get('lon'))
    if start_rm is None:
        return {"session_mmsi": session_mmsi, "start_rm": None, "options": [], "best": None, "locks": []}

    order = sorted(LOCKS.items(), key=lambda kv: kv[1]['river_mile'], reverse=(direction == "downbound"))
    chain = []
    for lid, ldata in order:
        if not _lock_board.lock_is_ahead(ldata['river_mile'], start_rm, direction, 0.0):
            continue
        if destination_rm is not None and ((direction == "downbound" and ldata['river_mile'] < destination_rm)
                                           or (direction == "upbound" and ldata['river_mile'] > destination_rm)):
            break
        chain.append((lid, ldata))
    chain = chain[:max_locks]

    lock_averages = await get_lockage_averages()
    user_barges = vd.get('barge_count')
    user_is_tow = bool(vd.get('is_tow') or (user_barges or 0) > 0)

    async def wait_at(lid: str, arrive_in: float) -> Optional[float]:
        try:
            board = await get_lock_board(direction=direction, lock_id=lid,
                                         arrive_in=arrive_in if arrive_in <= 24 * 60 else None,
                                         mmsi=session_mmsi)
        except Exception as e:
            logger.warning(f"Departure options: no wait estimate for {lid}: {e}")
            return None
        row = (board.get("locks") or [None])[0]
        if not row:
            return None
        w = row.get("wait_at_arrival")
        if w:
            return w["tow"] if user_is_tow else w["recreational"]
        return row["wait_estimate_minutes"] if user_is_tow else row["wait_estimate_recreational_minutes"]

    def own_lockage(lid: str) -> float:
        return _lock_board.expected_lockage_minutes(lid, user_barges if user_is_tow else None,
                                                    lock_averages.get(lid, {}))

    legs, prev = [], start_rm
    for lid, ldata in chain:
        legs.append({"lock_id": lid, "distance_mi": abs(ldata['river_mile'] - prev)})
        prev = ldata['river_mile']
    tail = abs(destination_rm - prev) if destination_rm is not None else 0.0
    options = await _trip_timeline.departure_options(legs, speed * 1.0, DEPARTURE_OFFSETS, wait_at, own_lockage, tail)
    notes = await _lock_notes()
    best = (min(range(len(options)), key=lambda i: (options[i]["time_at_locks_minutes"], options[i]["depart_in_minutes"]))
            if options and chain else None)
    return {
        "session_mmsi": session_mmsi, "direction": direction, "cruise_mph": speed,
        "start_rm": round(float(start_rm), 1), "destination_rm": destination_rm,
        "locks": [{"lock_id": lid, "name": ld.get("name"), "river_mile": ld.get("river_mile"),
                   "note": notes.get(lid)} for lid, ld in chain],
        "options": options, "best": best,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@api_router.get("/session/{session_mmsi}/trip-plan")
async def get_session_trip_plan(
    session_mmsi: str,
    request: Request = None,
    destination_rm: Optional[float] = None,
    buffer_minutes: int = 20,
    max_locks: int = 5,
    max_speed_mph: float = 25.0,
):
    """
    Compute a multi-lock trip plan for a session's vessel.

    For each lock the user will encounter (in their heading direction), this
    returns the race-to-beat status against the most threatening commercial
    tow targeting that same lock.

    Query params:
    - destination_rm: Optional river mile to stop the chain at (otherwise
      uses end of river in heading direction).
    - buffer_minutes: Minutes of buffer required before a competing tow.
    - max_locks: Max number of locks to include in the chain (1-15).

    Status values per leg:
    - "clear":     no threatening vessel within 100 mi of the lock
    - "on_pace":   tow detected but user already on pace at current speed
    - "speed_up":  beatable but user must increase speed (still <= 25 mph)
    - "cant_beat": required speed exceeds 25 mph max
    - "no_data":   insufficient info (no speed/heading) to compute
    """
    session_mmsi = str(session_mmsi).strip()
    await _check_session_owner(request, session_mmsi)
    if not session_mmsi:
        raise HTTPException(status_code=400, detail="Session MMSI required")

    max_locks = max(1, min(int(max_locks or 5), 15))
    MAX_THREAT_DISTANCE = 100.0
    USER_MAX_MPH = max(1.0, min(float(max_speed_mph or 25.0), 80.0))

    # Find the user vessel
    if session_mmsi not in active_vessels:
        return {
            "session_mmsi": session_mmsi,
            "user_vessel": None,
            "heading": None,
            "destination_rm": destination_rm,
            "legs": [],
            "summary": {
                "total_distance_mi": 0,
                "cumulative_eta_minutes": None,
                "legs_count": 0,
                "cant_beat_count": 0,
                "speed_up_count": 0,
                "clear_count": 0,
                "overall_status": "no_user",
            },
        }

    user_vessel = prepare_vessel_for_output(active_vessels[session_mmsi], session_mmsi)
    user_rm = user_vessel.get('river_mile') or estimate_river_mile(user_vessel.get('lat'), user_vessel.get('lon'))
    user_speed_knots = user_vessel.get('speed') or 0
    user_speed_mph = user_speed_knots * 1.15078
    user_heading = user_vessel.get('heading') or determine_heading(user_speed_knots, user_vessel.get('course'), user_vessel.get('lat'), user_vessel.get('lon'))

    # Build ordered chain of locks ahead of the user in heading direction.
    locks_sorted = sorted(LOCKS.items(), key=lambda kv: kv[1]['river_mile'])
    # Per-lock lockage times, so a competitor that will already be through the
    # lock when the user arrives isn't flagged as a threat.
    lock_averages = await get_lockage_averages()
    chain: List[tuple] = []  # list of (lock_id, lock_dict)
    # A boat stopped at a lock still has that lock ahead (lock_is_ahead).
    if user_heading == 'northbound':
        # River miles increase northbound: locks ahead in ascending order.
        for lid, ldata in locks_sorted:
            if _lock_board.lock_is_ahead(ldata['river_mile'], user_rm or 0, user_heading, user_speed_knots):
                if destination_rm is not None and ldata['river_mile'] > destination_rm:
                    break
                chain.append((lid, ldata))
    elif user_heading == 'southbound':
        # River miles decrease southbound: locks ahead in descending order.
        for lid, ldata in reversed(locks_sorted):
            if _lock_board.lock_is_ahead(ldata['river_mile'], user_rm or 0, user_heading, user_speed_knots):
                if destination_rm is not None and ldata['river_mile'] < destination_rm:
                    break
                chain.append((lid, ldata))
    else:
        # Stationary or unknown - no chain
        chain = []

    chain = chain[:max_locks]

    # Time at each lock (wait when you get there + your lockage) pushes every
    # later lock back; services/trip_timeline.py.
    user_barges = user_vessel.get('barge_count')
    user_is_tow = bool(user_vessel.get('is_tow') or (user_barges or 0) > 0)
    board_direction = {'northbound': 'upbound', 'southbound': 'downbound'}.get(user_heading)
    wait_ranges: Dict[str, Optional[list]] = {}  # lock -> learned "likely" wait range

    async def _wait_when_there(lid: str, arrive_in: float) -> Optional[float]:
        try:
            board = await get_lock_board(from_rm=None, direction=board_direction, scope="all", sort="river",
                                         limit=None, lock_id=lid,
                                         arrive_in=arrive_in if arrive_in <= 24 * 60 else None,
                                         mmsi=session_mmsi)
        except Exception as e:
            logger.warning(f"Trip plan: no wait estimate for {lid}: {e}")
            return None
        row = (board.get("locks") or [None])[0]
        if not row:
            return None
        w = row.get("wait_at_arrival")
        if w:
            wait_ranges[lid] = w.get("tow_range") if user_is_tow else w.get("recreational_range")
            return w["tow"] if user_is_tow else w["recreational"]
        wait_ranges[lid] = row.get("wait_range_minutes") if user_is_tow else row.get("wait_range_recreational_minutes")
        return row["wait_estimate_minutes"] if user_is_tow else row["wait_estimate_recreational_minutes"]

    def _own_lockage(lid: str) -> float:
        return _lock_board.expected_lockage_minutes(lid, user_barges if user_is_tow else None,
                                                    lock_averages.get(lid, {}))

    timeline = []
    if chain and user_rm is not None and user_heading in ('northbound', 'southbound'):
        prev = user_rm
        timeline_legs = []
        for lid, ldata in chain:
            timeline_legs.append({"lock_id": lid, "distance_mi": abs(ldata['river_mile'] - prev)})
            prev = ldata['river_mile']
        timeline = await _trip_timeline.schedule(timeline_legs, user_speed_mph, _wait_when_there, _own_lockage)
    timeline_by_lock = {t["lock_id"]: t for t in timeline}

    # Build per-leg analysis
    lock_notes = await _lock_notes()
    legs = []
    cumulative_eta = 0.0 if user_speed_mph > 0 else None
    cant_beat_count = 0
    speed_up_count = 0
    clear_count = 0
    last_rm = user_rm

    for lid, ldata in chain:
        lock_rm = ldata['river_mile']
        leg_distance = round(abs((last_rm or lock_rm) - lock_rm), 1)

        travel_only_eta = calculate_eta_to_lock(user_rm, user_speed_knots, user_heading, lock_rm) if user_rm else None
        tl = timeline_by_lock.get(lid)
        # Arrival counting the time spent at earlier locks
        user_eta = tl["arrive_minutes"] if tl else travel_only_eta
        at_earlier_locks = tl["time_at_earlier_locks_minutes"] if tl else 0

        # Find threatening competitor for THIS lock (bi-directional). None if
        # the boat is already at this lock: later arrivals queue behind it.
        at_this_lock = (user_rm is not None and abs(user_rm - lock_rm) <= _lock_board.AT_LOCK_MI
                        and user_speed_knots < _lock_board.SLOW_KNOTS)
        threat = None
        threat_eta = None
        required_speed = None
        for mmsi, vessel in ([] if at_this_lock else list(active_vessels.items())):
            if mmsi == session_mmsi:
                continue
            # Skip other users' simulated vessels (they are not real commercial traffic).
            # These can show up as "Your Vessel" orphans from prior test sessions.
            if isinstance(vessel, dict):
                if vessel.get('is_simulated') and vessel.get('is_user_vessel'):
                    continue
            if hasattr(vessel, 'river_mile'):
                vessel_rm = vessel.river_mile or estimate_river_mile(vessel.lat, vessel.lon)
                vessel_speed = vessel.speed
                vessel_heading = vessel.heading or determine_heading(vessel.speed, vessel.course, vessel.lat, vessel.lon)
            else:
                vessel_rm = vessel.get('river_mile') or estimate_river_mile(vessel.get('lat'), vessel.get('lon'))
                vessel_speed = vessel.get('speed', 0)
                vessel_heading = vessel.get('heading') or vessel.get('heading_direction') or determine_heading(vessel.get('speed', 0), vessel.get('course', 0), vessel.get('lat'), vessel.get('lon'))

            eta = calculate_eta_to_lock(vessel_rm, vessel_speed, vessel_heading, lock_rm)
            if eta is None or eta <= 0:
                continue

            # Ignore competitors too far from the lock
            if vessel_rm is not None and abs(vessel_rm - lock_rm) > MAX_THREAT_DISTANCE:
                continue

            # Only a competitor still at the lock (arriving or locking) when the
            # user gets there can delay them. One that arrives and locks through
            # well before the user is not a threat.
            comp_barges = getattr(vessel, 'barge_count', None) if not isinstance(vessel, dict) else vessel.get('barge_count')
            comp_is_tow = getattr(vessel, 'is_tow', False) if not isinstance(vessel, dict) else vessel.get('is_tow', False)
            lock_avg = lock_averages.get(lid, {})
            if comp_barges:
                comp_lockage = _lock_board.expected_lockage_minutes(lid, comp_barges, lock_avg)
            elif comp_is_tow:
                comp_lockage = float(lock_avg.get('avg_tow_lockage_minutes') or _lock_board.DEFAULT_SINGLE)
            else:
                comp_lockage = float(lock_avg.get('avg_recreational_lockage_minutes') or _lock_board.DEFAULT_LIGHT)
            if user_eta is not None and user_eta >= eta + comp_lockage:
                continue
            # Earliest competitor wins; user needs to arrive buffer_minutes before them
            if user_eta is None or eta < user_eta + buffer_minutes:
                if threat_eta is None or eta < threat_eta:
                    v_dict = prepare_vessel_for_output(vessel, None)  # another boat: never "yours"
                    v_dict['eta_minutes'] = eta
                    v_dict['distance_to_lock'] = round(abs(vessel_rm - lock_rm), 1) if vessel_rm else None
                    v_dict['expected_lockage_minutes'] = round(comp_lockage)
                    # Minutes the user would wait for this vessel to clear the lock
                    v_dict['expected_delay_minutes'] = (
                        round(max(0.0, eta + comp_lockage - user_eta)) if user_eta is not None else None
                    )
                    threat = v_dict
                    threat_eta = eta
                    # Time spent at earlier locks isn't available for travel
                    required_speed = calculate_required_speed(user_rm, user_heading, lock_rm,
                                                              eta - at_earlier_locks, buffer_minutes)

        # Determine status
        if user_rm is None or user_speed_knots < 0.1 or user_heading not in ('northbound', 'southbound'):
            status = 'no_data'
        elif threat is None:
            status = 'clear'
            clear_count += 1
        elif required_speed is None:
            # Can't compute required speed - treat as can't beat
            status = 'cant_beat'
            cant_beat_count += 1
        elif required_speed > USER_MAX_MPH:
            status = 'cant_beat'
            cant_beat_count += 1
        elif required_speed > user_speed_mph + 0.5:
            status = 'speed_up'
            speed_up_count += 1
        else:
            status = 'on_pace'
            clear_count += 1

        legs.append({
            "lock_id": lid,
            "lock_name": ldata['name'],
            "note": lock_notes.get(lid),
            "lock_rm": lock_rm,
            "leg_distance_mi": leg_distance,
            "user_eta_minutes": user_eta,
            "travel_only_eta_minutes": travel_only_eta,
            # Expected at this lock: the wait when you get there + your lockage
            "expected_wait_minutes": tl["wait_minutes"] if tl else None,
            "expected_wait_range_minutes": wait_ranges.get(lid) if tl else None,
            "expected_lockage_minutes": tl["lockage_minutes"] if tl else None,
            "depart_eta_minutes": tl["depart_minutes"] if tl else None,
            "threatening_vessel": threat,
            "required_speed_mph": required_speed,
            "expected_delay_minutes": (threat or {}).get('expected_delay_minutes'),
            "status": status,
            "buffer_minutes": buffer_minutes,
        })

        if cumulative_eta is not None and user_eta is not None:
            cumulative_eta = user_eta  # Each user_eta already from current position
        last_rm = lock_rm

    # Total distance is from user position to the final lock in the chain (if any)
    total_distance = 0.0
    if chain and user_rm is not None:
        total_distance = round(abs(chain[-1][1]['river_mile'] - user_rm), 1)

    # Overall status: worst of the chain
    if cant_beat_count > 0:
        overall = 'cant_beat'
    elif speed_up_count > 0:
        overall = 'speed_up'
    elif clear_count > 0:
        overall = 'clear'
    else:
        overall = 'no_data'

    return {
        "session_mmsi": session_mmsi,
        "user_vessel": user_vessel,
        "user_rm": user_rm,
        "user_speed_mph": round(user_speed_mph, 1),
        "heading": user_heading,
        "destination_rm": destination_rm,
        "legs": legs,
        "summary": {
            "total_distance_mi": total_distance,
            # Through the last lock: travel + waits + lockages
            "cumulative_eta_minutes": ((legs[-1]["depart_eta_minutes"] or legs[-1]["user_eta_minutes"])
                                       if legs else None),
            "time_at_locks_minutes": (sum((t["wait_minutes"] + t["lockage_minutes"]) for t in timeline)
                                      if timeline else None),
            "legs_count": len(legs),
            "cant_beat_count": cant_beat_count,
            "speed_up_count": speed_up_count,
            "clear_count": clear_count,
            "overall_status": overall,
            "max_speed_mph": USER_MAX_MPH,
        },
    }


@api_router.post("/set-user-mmsi")
async def set_user_mmsi_legacy(data: dict, user: dict = Depends(require_user)):
    """
    LEGACY: Set the user's MMSI number.
    
    DEPRECATED: Sessions are now created automatically when connecting.
    This endpoint just creates/updates a session.
    """
    mmsi = data.get("mmsi", "")
    if not mmsi:
        raise HTTPException(status_code=400, detail="mmsi required")
    # Marks the live vessel as a user boat for everyone, so owner/admin only.
    _require_owner(user, mmsi)

    # Create session for this MMSI
    session_manager.create_session(mmsi)
    
    # Update vessel if already tracked
    if mmsi in active_vessels:
        active_vessels[mmsi].is_user_vessel = True
    
    logger.info(f"[SESSION:{mmsi}] Session created via set-user-mmsi")
    
    return {"success": True, "mmsi": mmsi}


@api_router.get("/sessions", dependencies=[Depends(require_admin)])
async def get_active_sessions():
    """
    Get list of active sessions (for debugging/admin).
    
    Shows which MMSIs have active WebSocket connections.
    """
    sessions = session_manager.get_active_sessions()
    return {
        "total_sessions": len(sessions),
        "sessions": sessions
    }


@api_router.get("/session/{session_mmsi}/vessels")
async def get_vessels_for_session(session_mmsi: str):
    """
    Get all vessels with is_user_vessel correctly set for this session.
    
    CRITICAL: Each session sees their own vessel highlighted.
    """
    session_mmsi = str(session_mmsi).strip()
    if not session_mmsi:
        raise HTTPException(status_code=400, detail="Session MMSI required")
    
    vessels = []
    for mmsi, vessel in active_vessels.items():
        if is_mmsi_blocked(mmsi):
            continue
        # EXPLICIT: is_user_vessel is TRUE only if vessel MMSI matches session MMSI
        v_dict = prepare_vessel_for_output(vessel, session_mmsi)
        v_dict["is_user_vessel"] = (mmsi == session_mmsi)
        vessels.append(v_dict)
    
    logger.info(f"[SESSION:{session_mmsi}] Returned {len(vessels)} vessels")
    return vessels


_user_owns_mmsi = _user_settings.owns_mmsi
_NOT_YOUR_BOAT = "Add this MMSI to your account (Settings > Your Vessel) first"


def _require_owner(user: dict, mmsi: str) -> None:
    if not _user_owns_mmsi(user, mmsi):
        raise HTTPException(status_code=403, detail=_NOT_YOUR_BOAT)


async def _check_session_owner(request: Request, mmsi: str) -> None:
    """Per-boat planning views answer only for the caller's own boat (they mark
    it is_user_vessel and show its simulation). No-login installs skip this."""
    if request is None or not _api_access.login_required():
        return  # internal call, or a no-login install
    user = await get_current_user(request)
    if user and not _user_owns_mmsi(user, str(mmsi)):
        raise HTTPException(status_code=403, detail=_NOT_YOUR_BOAT)


@api_router.post("/session/{session_mmsi}/position")
async def update_session_position(session_mmsi: str, data: dict, user: dict = Depends(require_user)):
    """
    Update position for a specific session (MMSI).
    
    CRITICAL: This endpoint is EXPLICITLY scoped to a session.
    Updating position for MMSI 338414076 will NEVER affect MMSI 367555123.
    
    Position can come from:
    - Browser Geolocation API
    - Manual lat/lon entry
    - External GPS source
    """
    # Validate session MMSI
    if not session_mmsi or len(session_mmsi) < 5:
        raise HTTPException(status_code=400, detail="Valid session MMSI required")
    
    session_mmsi = str(session_mmsi).strip()
    # Only the boat's owner (or an admin) may move it on everyone's map.
    if not _user_owns_mmsi(user, session_mmsi):
        raise HTTPException(status_code=403, detail="Add this MMSI to your account before sharing its position")
    # Its own transponder outranks anything typed in (admins included).
    ais_refusal = _live_ais.refusal(session_mmsi)
    if ais_refusal:
        raise HTTPException(status_code=409, detail=ais_refusal)

    lat = data.get("lat")
    lon = data.get("lon")
    speed = data.get("speed", 0)  # knots
    course = data.get("course", 0)
    source = data.get("source", "manual")  # "geolocation", "manual", "external"
    
    if lat is None or lon is None:
        raise HTTPException(status_code=400, detail="lat and lon required")
    
    logger.info(f"[SESSION:{session_mmsi}] Position update via {source}: lat={lat:.4f}, lon={lon:.4f}")
    
    # Create or get session
    session_manager.create_session(session_mmsi)
    session_manager.update_session_activity(session_mmsi)
    
    # Get boat name from session settings
    boat_name = data.get("name") or "Your Vessel"
    user_settings = await db.user_settings.find_one(_user_settings.read_filter(session_mmsi, user), {"_id": 0})
    if user_settings and user_settings.get("settings", {}).get("boat_name"):
        boat_name = user_settings["settings"]["boat_name"]
    elif session_mmsi in vessel_static_cache:
        boat_name = vessel_static_cache[session_mmsi].get("name", boat_name)
    
    # Calculate river mile and heading
    rm = estimate_river_mile(lat, lon)
    heading = heading_with_track(session_mmsi, rm, speed, course, lat, lon)
    
    # Create or update vessel for THIS SESSION ONLY
    vessel = VesselPosition(
        mmsi=session_mmsi,
        name=boat_name,
        lat=lat,
        lon=lon,
        speed=speed,
        course=course,
        river_mile=rm,
        heading=heading,
        is_user_vessel=True,  # Will be recalculated per-session when sent to clients
        vessel_type="recreational",
    )
    
    # Store in active_vessels keyed by THIS session's MMSI
    active_vessels[session_mmsi] = vessel
    
    logger.info(f"[SESSION:{session_mmsi}] Position stored: RM={rm}, speed={speed}")
    
    # Persist vessel sighting to database
    v_dict = prepare_vessel_for_output(vessel, session_mmsi)
    v_dict['source'] = source
    asyncio.create_task(persist_vessel_sighting(v_dict))
    # Push to everyone watching, not just the phone that sent it.
    await ais_manager._broadcast_vessel_update(v_dict)
    
    # Also persist position to user's account if they have this vessel
    asyncio.create_task(persist_vessel_position_to_user(session_mmsi, {
        "lat": lat,
        "lon": lon,
        "speed": speed,
        "course": course,
        "river_mile": rm,
        "heading_direction": heading,
        "last_position_update": datetime.now(timezone.utc).isoformat()
    }))
    
    return {"success": True, "session_mmsi": session_mmsi, "vessel": v_dict}


# Legacy endpoint - redirects to session-based endpoint
@api_router.post("/user-position")
async def update_user_position_legacy(data: dict, user: dict = Depends(require_user)):
    """
    LEGACY: Update user's vessel position.
    
    DEPRECATED: Use POST /session/{mmsi}/position instead.
    This endpoint requires mmsi in the request body.
    """
    mmsi = data.get("mmsi")
    if not mmsi:
        raise HTTPException(status_code=400, detail="mmsi required in request body. Use POST /session/{mmsi}/position instead.")
    
    return await update_session_position(mmsi, data, user)


@api_router.get("/settings")
async def get_settings(mmsi: str = None, user: dict = Depends(require_user)):
    """Get saved settings. If mmsi provided, get this user's settings for it."""
    if mmsi:
        user_settings = await db.user_settings.find_one(_user_settings.read_filter(mmsi, user), {"_id": 0})
        if user_settings:
            return user_settings.get("settings", {})
        # Fall back to defaults
        return {}

    # Server-wide defaults; the admin's own boat/feed keys only for admins.
    settings = await db.settings.find({}, {"_id": 0}).to_list(100)
    return _user_settings.visible_global_settings({s["key"]: s["value"] for s in settings}, user)

@api_router.post("/settings")
async def save_settings(data: dict, user: dict = Depends(require_admin)):
    """Save server-wide settings (admins). If mmsi in data, save as the
    admin's own settings for that boat."""
    mmsi = data.pop("mmsi", None) if isinstance(data, dict) else None

    if mmsi:
        # Save user-specific settings
        await db.user_settings.update_one(
            _user_settings.write_filter(mmsi, user),
            {
                "$set": {
                    "mmsi": mmsi,
                    "user_id": user["user_id"],
                    "settings": data,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )
        logger.info(f"Saved settings for user MMSI: {mmsi}")
        return {"success": True, "mmsi": mmsi}
    
    # Legacy: save global settings
    for key, value in data.items():
        await db.settings.update_one(
            {"key": key},
            {"$set": {"value": value, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True
        )
    return {"success": True}


@api_router.get("/user/{mmsi}/settings")
async def get_user_settings(mmsi: str, user: dict = Depends(require_user)):
    """This user's settings for a boat (by MMSI). Another account's settings
    for the same MMSI are never returned."""
    user_settings = await db.user_settings.find_one(_user_settings.read_filter(mmsi, user), {"_id": 0})
    if user_settings:
        return {
            "mmsi": mmsi,
            "settings": user_settings.get("settings", {}),
            "updated_at": user_settings.get("updated_at")
        }
    return {"mmsi": mmsi, "settings": {}, "updated_at": None}


@api_router.post("/user/{mmsi}/settings")
async def save_user_settings(mmsi: str, data: dict, user: dict = Depends(require_user)):
    """Save this user's settings for a boat (by MMSI)."""
    await db.user_settings.update_one(
        _user_settings.write_filter(mmsi, user),
        {
            "$set": {
                "mmsi": mmsi,
                "user_id": user["user_id"],
                "settings": data,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    logger.info(f"Saved settings for user MMSI: {mmsi}")
    return {"success": True, "mmsi": mmsi}

# Blocked MMSI Management
@api_router.get("/blocked-mmsi")
async def get_blocked_mmsi():
    """Get list of user-blocked MMSIs."""
    blocked = await repos.blocked_mmsi.get_all_blocked()
    return {
        "blocked": blocked,
        "system_filtered": list(FILTERED_MMSI)
    }

@api_router.post("/blocked-mmsi", dependencies=[Depends(require_admin)])
async def add_blocked_mmsi(data: dict):
    """Add an MMSI to the block list."""
    global user_blocked_mmsi
    
    mmsi = str(data.get("mmsi", "")).strip()
    reason = data.get("reason", "User blocked")
    
    if not mmsi:
        return {"success": False, "error": "MMSI required"}
    
    # Add to database
    await repos.blocked_mmsi.block_mmsi(mmsi, reason)
    
    # Add to in-memory set
    user_blocked_mmsi.add(mmsi)
    
    # Remove from active vessels if present
    if mmsi in active_vessels:
        del active_vessels[mmsi]
        logger.info(f"Removed blocked vessel {mmsi} from active vessels")
    
    logger.info(f"Blocked MMSI {mmsi}: {reason}")
    return {"success": True, "mmsi": mmsi}

@api_router.delete("/blocked-mmsi/{mmsi}", dependencies=[Depends(require_admin)])
async def remove_blocked_mmsi(mmsi: str):
    """Remove an MMSI from the block list."""
    global user_blocked_mmsi
    
    # Remove from database
    success = await repos.blocked_mmsi.unblock_mmsi(mmsi)
    
    # Remove from in-memory set
    user_blocked_mmsi.discard(mmsi)
    
    if success:
        logger.info(f"Unblocked MMSI {mmsi}")
        return {"success": True, "mmsi": mmsi}
    else:
        return {"success": False, "error": "MMSI not found in block list"}


@api_router.get("/filter-config")
async def get_filter_config():
    """Get the current vessel filtering configuration."""
    from config import UPPER_MISSISSIPPI_BOUNDS, ILLINOIS_RIVER_EXCLUSION
    return {
        "upper_mississippi_bounds": UPPER_MISSISSIPPI_BOUNDS,
        "illinois_river_exclusion": ILLINOIS_RIVER_EXCLUSION,
        "description": "Vessels outside Upper Mississippi bounds or in Illinois River zone are filtered out"
    }


async def load_blocked_mmsi():
    """Load user-blocked MMSIs from database on startup."""
    global user_blocked_mmsi
    blocked = await repos.blocked_mmsi.get_all_blocked()
    user_blocked_mmsi = {item["mmsi"] for item in blocked}
    logger.info(f"Loaded {len(user_blocked_mmsi)} blocked MMSIs from database")

def is_mmsi_blocked(mmsi: str) -> bool:
    """Check if an MMSI is blocked (system or user)."""
    return mmsi in FILTERED_MMSI or mmsi in user_blocked_mmsi

_WS_REFUSED = object()


async def _websocket_user_or_close(websocket: WebSocket):
    """The signed-in user for a WebSocket handshake (None if login isn't
    required and nobody is signed in), or _WS_REFUSED after rejecting an
    anonymous handshake (HTTP 403, policy-violation close code)."""
    try:
        user = await get_current_user(websocket)
    except Exception:
        user = None
    if user is None and _api_access.login_required():
        await websocket.close(code=1008)
        return _WS_REFUSED
    return user


# WebSocket for real-time AIS data
# Note: We register both paths - /ws/ais for local and /api/ws/ais for production
# The /api prefix is needed because Kubernetes ingress routes /api/* to backend
@app.websocket("/ws/ais")
@app.websocket("/api/ws/ais")
async def websocket_ais(websocket: WebSocket):
    """
    WebSocket endpoint for real-time AIS data streaming.
    
    Uses the singleton AISConnectionManager - all clients share ONE TCP connection.
    Each client tracks their own MMSI for per-user vessel highlighting.
    """
    # Same session cookie/Bearer token as the REST API. Signed-in only (the
    # stream carries users' own boats); who is asking also decides whether
    # their "this is my boat, named X" is written for everyone.
    ws_user = await _websocket_user_or_close(websocket)
    if ws_user is _WS_REFUSED:
        return
    await websocket.accept()
    logger.info("WebSocket client connected to /ws/ais")
    subscribed = False
    client_mmsi = ""  # Track this client's MMSI
    client_boat_name = ""
    
    try:
        while True:
            # Receive config or commands from client
            data = await websocket.receive_text()
            msg = json.loads(data)
            logger.debug(f"WebSocket received action: {msg.get('action')}")
            
            if msg.get("action") == "connect":
                ip = msg.get("ip_address")
                port = msg.get("port", 5353)
                client_mmsi = msg.get("user_mmsi", "")
                client_boat_name = msg.get("boat_name", "")
                
                # The TCP feed is shared by every viewer and owned by the server
                # (set via POST /api/connection/start, restored on restart).
                # Opening a dashboard only subscribes: a viewer's stale browser
                # config must never re-point the live feed for everyone. The
                # ip_address/port fields older clients send are ignored.
                current = ais_manager.config or {}
                if ip and (current.get("ip_address") != ip or current.get("port") != port):
                    logger.info(
                        f"WebSocket connect asked for {ip}:{port}; keeping server feed "
                        f"{current.get('ip_address')}:{current.get('port')} (change it in Settings)"
                    )
                if client_mmsi and _user_owns_mmsi(ws_user, client_mmsi):
                    session_manager.create_session(client_mmsi)
                    if client_boat_name:
                        vessel_static_cache[client_mmsi] = {"name": client_boat_name, "is_user": True}
                elif client_mmsi and client_boat_name:
                    # Highlighting still follows client_mmsi (only this viewer
                    # sees it); the shared name cache does not.
                    logger.info(f"WebSocket: not naming {client_mmsi} - not on this viewer's account")

                # Subscribe this WebSocket with user's MMSI for per-user vessel tracking
                if not subscribed:
                    await ais_manager.subscribe(websocket, client_mmsi, client_boat_name,
                                                show_feed_address=_user_settings.is_admin(ws_user))
                    subscribed = True
                    logger.info(f"WebSocket subscribed to AIS updates (MMSI: {client_mmsi})")
                else:
                    # Update existing subscription with new MMSI if changed
                    ais_manager._subscribers[websocket] = {**ais_manager._subscribers.get(websocket, {}),
                                                          "mmsi": client_mmsi, "boat_name": client_boat_name}
                    logger.info(f"Updated subscription MMSI: {client_mmsi}")
                    
            elif msg.get("action") == "disconnect":
                # Just unsubscribe from updates - don't close the shared connection
                if subscribed:
                    await ais_manager.unsubscribe(websocket)
                    subscribed = False
                await websocket.send_json({"type": "disconnected", "message": "Unsubscribed from AIS feed"})
                
            elif msg.get("action") == "get_vessels":
                vessels = []
                for mmsi, vessel in active_vessels.items():
                    # Use client's MMSI to mark their vessel
                    v_dict = prepare_vessel_for_output(vessel, client_mmsi)
                    vessels.append(v_dict)
                await websocket.send_json({"type": "vessels", "vessels": vessels})
                
            elif msg.get("action") == "status":
                # Return current connection status
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

# Store raw data subscribers for broadcasting
raw_data_subscribers: set = set()

# WebSocket for raw NMEA data streaming (debug/diagnostic tool)
@app.websocket("/ws/raw")
@app.websocket("/api/ws/raw")
async def websocket_raw(websocket: WebSocket):
    """
    WebSocket endpoint for streaming raw NMEA data for debugging.
    Clients connect here to see every line received from the AIS TCP feed.
    Signed-in only, like the rest of the API.
    """
    if await _websocket_user_or_close(websocket) is _WS_REFUSED:
        return
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
    
    # Generate simulated AIS position report (Message Type 1)
    # Format: !AIVDM,1,1,,A,<payload>,0*<checksum>
    # For simplicity, we'll create a readable pseudo-NMEA that shows the data
    
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
    
    # Generate simulated GPRMC (GPS position)
    gprmc_body = f"GPRMC,{time_str}.00,A,{lat_nmea},{lat_dir},{lon_nmea},{lon_dir},{speed_knots:.1f},{course:.1f},{date_str},,,A"
    gprmc_checksum = generate_nmea_checksum(gprmc_body)
    gprmc_sentence = f"${gprmc_body}*{gprmc_checksum}"
    
    # Generate simulated AIS VDM (simplified - shows MMSI and position in comment format)
    # Real AIS is binary encoded, but for demo we'll use a readable format
    aivdm_comment = f"!AIVDM,1,1,,A,DEMO:{mmsi}:LAT{lat:.4f}:LON{lon:.4f}:SPD{speed_knots:.1f}:CRS{course:.0f},0*00"
    
    # Broadcast both sentences
    await broadcast_raw_line(f"[DEMO] {gprmc_sentence}")
    await broadcast_raw_line(f"[DEMO] {aivdm_comment}")


# =============================================================================
# TRIPS - Create / Save / Load planned trips
# =============================================================================
class TripCreate(BaseModel):
    name: str
    start_rm: Optional[float] = None
    end_rm: Optional[float] = None
    heading: Optional[str] = None   # "northbound" | "southbound"
    departure_time: Optional[str] = None  # ISO 8601 string
    notes: Optional[str] = None
    locks: Optional[List[str]] = None  # ordered lock ids the trip traverses


def _trip_doc_to_public(doc: dict) -> dict:
    """Strip Mongo internals + ensure JSON-safe fields."""
    if not doc:
        return {}
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


@api_router.post("/trips")
async def create_trip(trip: TripCreate, request: Request):
    """Create a new saved trip for the current user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    name = (trip.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Trip name is required")

    now = datetime.now(timezone.utc)
    doc = {
        "trip_id": f"trip_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "name": name,
        "start_rm": trip.start_rm,
        "end_rm": trip.end_rm,
        "heading": trip.heading,
        "departure_time": trip.departure_time,
        "notes": (trip.notes or "").strip(),
        "locks": list(trip.locks or []),
        "created_at": now,
        "updated_at": now,
    }
    await db.trips.insert_one(doc)
    return _trip_doc_to_public(doc)


@api_router.get("/trips")
async def list_trips(request: Request):
    """List the current user's saved trips, newest first."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    cursor = db.trips.find(
        {"user_id": user["user_id"]},
        {"_id": 0},
    ).sort("created_at", -1)
    trips = []
    async for doc in cursor:
        for k in ("created_at", "updated_at"):
            v = doc.get(k)
            if isinstance(v, datetime):
                doc[k] = v.isoformat()
        trips.append(doc)
    return {"trips": trips, "count": len(trips)}


@api_router.get("/trips/{trip_id}")
async def get_trip(trip_id: str, request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    doc = await db.trips.find_one(
        {"trip_id": trip_id, "user_id": user["user_id"]},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Trip not found")
    for k in ("created_at", "updated_at"):
        v = doc.get(k)
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


@api_router.put("/trips/{trip_id}")
async def update_trip(trip_id: str, trip: TripCreate, request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    update_fields = {
        "name": (trip.name or "").strip(),
        "start_rm": trip.start_rm,
        "end_rm": trip.end_rm,
        "heading": trip.heading,
        "departure_time": trip.departure_time,
        "notes": (trip.notes or "").strip(),
        "locks": list(trip.locks or []),
        "updated_at": datetime.now(timezone.utc),
    }
    if not update_fields["name"]:
        raise HTTPException(status_code=400, detail="Trip name is required")
    result = await db.trips.update_one(
        {"trip_id": trip_id, "user_id": user["user_id"]},
        {"$set": update_fields},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Trip not found")
    doc = await db.trips.find_one(
        {"trip_id": trip_id, "user_id": user["user_id"]},
        {"_id": 0},
    )
    for k in ("created_at", "updated_at"):
        v = doc.get(k)
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


@api_router.delete("/trips/{trip_id}")
async def delete_trip(trip_id: str, request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    result = await db.trips.delete_one(
        {"trip_id": trip_id, "user_id": user["user_id"]},
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Trip not found")
    return {"deleted": trip_id}




# =============================================================================
# SHARE MY TRIP - public, expiring links to one boat's position and ETA
# (services/trip_share.py). The public view answers without sign-in
# (/api/public/ is in api_access.PUBLIC_PREFIXES) and returns only the fields
# trip_share.public_payload allows: no MMSI, owner, or other boats.
# =============================================================================
import time as _time  # noqa: E402
from services import trip_share as _trip_share  # noqa: E402


class ShareCreate(BaseModel):
    mmsi: str
    hours: Optional[int] = Field(default=_trip_share.DEFAULT_HOURS, ge=_trip_share.MIN_HOURS, le=_trip_share.MAX_HOURS)
    destination_rm: Optional[float] = Field(default=None, ge=0, le=2000)


_share_rate = _trip_share.RateLimiter(limit=30, window_s=60.0)
_share_cache: Dict[str, tuple] = {}   # token -> (monotonic time, payload)
_SHARE_CACHE_S = 20.0
_SHARE_NOT_FOUND = "This trip link has expired or was turned off"


def _own_boat_entry(user: dict, mmsi: str) -> Optional[dict]:
    """The boat on this account's own list. No admin override: a share puts
    the boat's position on a public link, so only its owner may create one."""
    for v in (user.get("vessels") or []):
        if isinstance(v, dict) and str(v.get("mmsi")) == str(mmsi).strip():
            return v
    return None


@api_router.post("/share")
async def create_trip_share(body: ShareCreate, user: dict = Depends(require_user)):
    """Create a public link to one of your boats (expires in 1-72 h)."""
    mmsi = str(body.mmsi or "").strip()
    entry = _own_boat_entry(user, mmsi)
    if not mmsi or entry is None:
        raise HTTPException(status_code=403, detail=_NOT_YOUR_BOAT)
    now = datetime.now(timezone.utc)
    active = await db.trip_shares.count_documents(
        {"user_id": user["user_id"], "revoked": False, "expires_at": {"$gt": now}})
    if active >= _trip_share.MAX_ACTIVE_PER_USER:
        raise HTTPException(status_code=400, detail="Too many active trip links; stop one first")
    doc = _trip_share.new_share(mmsi, user["user_id"], body.hours, body.destination_rm,
                                entry.get("boat_name"), now=now)
    await db.trip_shares.insert_one(dict(doc))
    logger.info(f"[SHARE] {user['user_id']} shared {mmsi} for {body.hours} h")
    return _trip_share.owner_view(doc)


@api_router.get("/share")
async def list_trip_shares(user: dict = Depends(require_user)):
    """Your active trip links."""
    now = datetime.now(timezone.utc)
    cursor = db.trip_shares.find(
        {"user_id": user["user_id"], "revoked": False, "expires_at": {"$gt": now}}, {"_id": 0},
    ).sort("created_at", -1).limit(50)
    shares = [_trip_share.owner_view(d) async for d in cursor if _trip_share.is_active(d, now)]
    return {"shares": shares}


@api_router.delete("/share/{token}")
async def revoke_trip_share(token: str, user: dict = Depends(require_user)):
    """Stop sharing: the link answers 404 from now on."""
    res = await db.trip_shares.update_one(
        {"token": str(token), "user_id": user["user_id"]}, {"$set": {"revoked": True}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Trip link not found")
    _share_cache.pop(str(token), None)
    return {"revoked": True}


async def _shared_boat_view(doc: dict) -> dict:
    mmsi = doc["mmsi"]
    vessel = active_vessels.get(mmsi)
    v_out, plan = None, None
    if vessel is not None:
        v_out = prepare_vessel_for_output(vessel, None)
        if v_out.get("river_mile") is None and v_out.get("lat") is not None:
            v_out["river_mile"] = estimate_river_mile(v_out.get("lat"), v_out.get("lon"))
        dest = doc.get("destination_rm")
        try:
            # Internal call (request=None): ownership was checked when the
            # link was created and is re-checked on every view.
            plan = await get_session_trip_plan(mmsi, request=None, destination_rm=dest,
                                               max_locks=15 if dest is not None else 1)
        except Exception as e:
            logger.warning(f"[SHARE] trip plan for a shared boat failed: {e}")
            plan = None
    locks = [(ld.get("name"), ld.get("river_mile")) for ld in LOCKS.values()]
    return _trip_share.public_payload(doc.get("boat_name"), v_out, plan, locks,
                                      destination_rm=doc.get("destination_rm"),
                                      expires_at=doc.get("expires_at"))


@api_router.get("/public/share/{token}")
async def get_public_trip_share(token: str):
    """PUBLIC: where a shared boat is and when it should arrive."""
    token = str(token or "")
    if not token or len(token) > 64:
        raise HTTPException(status_code=404, detail=_SHARE_NOT_FOUND)
    if not _share_rate.allow(token):
        raise HTTPException(status_code=429, detail="Too many requests; try again in a minute",
                            headers={"Retry-After": "60"})
    doc = await db.trip_shares.find_one({"token": token}, {"_id": 0})
    if not _trip_share.is_active(doc):
        _share_cache.pop(token, None)
        raise HTTPException(status_code=404, detail=_SHARE_NOT_FOUND)
    # The boat must still be on the account that shared it.
    owner = await db.users.find_one({"user_id": doc.get("user_id"), "vessels.mmsi": doc.get("mmsi")}, {"_id": 1})
    if not owner:
        raise HTTPException(status_code=404, detail=_SHARE_NOT_FOUND)
    hit = _share_cache.get(token)
    now_m = _time.monotonic()
    if hit and now_m - hit[0] < _SHARE_CACHE_S:
        return hit[1]
    payload = await _shared_boat_view(doc)
    if len(_share_cache) > 2000:
        _share_cache.clear()
    _share_cache[token] = (now_m, payload)
    return payload


@api_router.post("/debug/inject-nmea", dependencies=[Depends(require_admin)])
async def inject_test_nmea(request: Request):
    """
    Inject a test NMEA sentence to verify the raw data pipeline is working.
    Useful for debugging when you're not sure if:
    - The WebSocket connection to browser is working
    - The AIS TCP connection to Boat Beacon is working
    """
    body = await request.json()
    sentence = body.get("sentence", "!AIVDM,1,1,,A,TEST_SENTENCE_FROM_DEBUG_ENDPOINT,0*00")
    
    # Broadcast to all raw data subscribers
    await broadcast_raw_line(f"[TEST] {sentence}")
    
    return {
        "success": True,
        "message": "Test sentence broadcasted",
        "sentence": sentence,
        "subscriber_count": len(raw_data_subscribers)
    }


@api_router.get("/debug/raw-subscribers", dependencies=[Depends(require_admin)])
async def get_raw_subscribers():
    """Check how many clients are subscribed to raw NMEA data."""
    return {
        "subscriber_count": len(raw_data_subscribers),
        "ais_connected": ais_manager.is_connected,
        "ais_config": ais_manager.get_status().get("config"),
        "last_data_time": ais_manager.get_status().get("last_data_time")
    }


def _generate_phone_localhost_relay_script(vm_url: str) -> bytes:
    """Build an Android/Termux relay for Boat Beacon localhost TCP output."""
    ingest_url = vm_url.rstrip("/") + "/api/ais/ingest"

    script = r"""#!/data/data/com.termux/files/usr/bin/bash
set -u

BOAT_BEACON_HOST="${BOAT_BEACON_HOST:-127.0.0.1}"
BOAT_BEACON_PORT="${BOAT_BEACON_PORT:-5353}"
INGEST_URL="__INGEST_URL__"
INGEST_TOKEN="${AIS_INGEST_TOKEN:-__INGEST_TOKEN__}"
BATCH_SECONDS="${BATCH_SECONDS:-1}"
MAX_BATCH_LINES="${MAX_BATCH_LINES:-200}"

log() {
  printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().rstrip("\n")))'
}

send_batch() {
  local tmpfile="$1"
  local count
  count=$(wc -l < "$tmpfile" | tr -d ' ')

  if [ "$count" = "0" ]; then
    return 0
  fi

  local lines_json
  local line
  local escaped
  local first

  lines_json="["
  first=1

  while IFS= read -r line || [ -n "$line" ]; do
    escaped=$(printf '%s' "$line" | json_escape)

    if [ "$first" = "1" ]; then
      lines_json="$lines_json$escaped"
      first=0
    else
      lines_json="$lines_json,$escaped"
    fi
  done < "$tmpfile"

  lines_json="$lines_json]"
  body="{\"lines\":$lines_json}"

  if curl -fsS -X POST "$INGEST_URL" \
      -H "Content-Type: application/json" \
      -H "X-Ingest-Token: $INGEST_TOKEN" \
      --data "$body" >/tmp/riverwatch-phone-relay-response.json 2>/tmp/riverwatch-phone-relay-error.log; then
    log "POST ok: $count line(s)"
    : > "$tmpfile"
    return 0
  else
    log "POST failed: $(cat /tmp/riverwatch-phone-relay-error.log 2>/dev/null)"
    return 1
  fi
}

log "RiverWatch Phone Localhost Relay"
log "Boat Beacon source: $BOAT_BEACON_HOST:$BOAT_BEACON_PORT"
log "RiverWatch ingest: $INGEST_URL"

if ! need_cmd python3; then
  log "python3 not found. Installing..."
  pkg install -y python || {
    log "ERROR: Could not install python. Run: pkg install python"
    exit 1
  }
fi

if ! need_cmd curl; then
  log "curl not found. Installing..."
  pkg install -y curl || {
    log "ERROR: Could not install curl. Run: pkg install curl"
    exit 1
  }
fi

if ! need_cmd nc; then
  log "netcat not found. Installing..."
  pkg install -y netcat-openbsd || pkg install -y busybox || {
    log "ERROR: Could not install netcat. Run: pkg install netcat-openbsd"
    exit 1
  }
fi

batch_file="/tmp/riverwatch-phone-nmea-batch.txt"
: > "$batch_file"

while true; do
  log "Connecting to Boat Beacon localhost feed..."
  log "If this loops, confirm Boat Beacon is outputting TCP/NMEA on 127.0.0.1:5353."

  last_flush="$(date +%s)"

  nc "$BOAT_BEACON_HOST" "$BOAT_BEACON_PORT" | while IFS= read -r line || [ -n "$line" ]; do
    line="$(printf '%s' "$line" | tr -d '\r')"

    if [ -z "$line" ]; then
      continue
    fi

    printf '%s\n' "$line" >> "$batch_file"

    current_count=$(wc -l < "$batch_file" | tr -d ' ')
    if [ "$current_count" -ge "$MAX_BATCH_LINES" ]; then
      send_batch "$batch_file" || true
    fi

    now="$(date +%s)"
    elapsed=$((now - last_flush))

    if [ "$elapsed" -ge "$BATCH_SECONDS" ]; then
      send_batch "$batch_file" || true
      last_flush="$now"
    fi
  done

  send_batch "$batch_file" || true
  log "Boat Beacon connection closed or failed. Retrying in 5 seconds..."
  sleep 5
done
"""

    script = script.replace("__INGEST_URL__", ingest_url).replace("__INGEST_TOKEN__", os.environ.get("AIS_INGEST_TOKEN", ""))
    return script.encode("utf-8")


@api_router.get("/relay/phone-localhost/download", dependencies=[Depends(require_admin)])  # embeds AIS_INGEST_TOKEN
async def download_phone_localhost_relay(request: Request):
    """Return an Android/Termux relay script for Boat Beacon localhost TCP output."""
    host = request.headers.get("host") or "127.0.0.1"
    scheme = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
    vm_url = f"{scheme}://{host}"
    content = _generate_phone_localhost_relay_script(vm_url)
    return _Response(
        content=content,
        media_type="text/x-shellscript",
        headers={"Content-Disposition": 'attachment; filename="riverwatch-phone-localhost-relay.sh"'},
    )


async def require_login_unless_public(request: Request) -> None:
    """Router-wide: every /api route needs a session unless it's on the short
    public list (services/api_access.py). Runs inside CORS, so a 401 still
    carries CORS headers."""
    if request.method == "OPTIONS" or not _api_access.login_required():
        return
    if _api_access.is_public(request.url.path):
        return
    if not await get_current_user(request):
        raise HTTPException(status_code=401, detail="Not authenticated")


# Include the router in the main app
app.include_router(api_router, dependencies=[Depends(require_login_unless_public)])

# River Traffic Planning routes (Trip Planner, Lock Queue, Meetings, Bottlenecks)
try:
    from routes.planning import router as planning_router
    app.include_router(planning_router, prefix="/api", dependencies=[Depends(require_login_unless_public)])
    logger.info("Traffic Planning routes loaded at /api/planning/*")
except ImportError as e:
    logger.error(f"Failed to load planning routes: {e}")

# AIS scanner proxy routes (forwards to ais-relay:8088)
try:
    from routes.ais_scan import router as ais_scan_router
    # LAN scans and upstream selection: signed-in users only.
    app.include_router(ais_scan_router, prefix="/api", dependencies=[Depends(require_user)])
    logger.info("AIS Scanner proxy routes loaded at /api/ais-scan/*")
except ImportError as e:
    logger.error(f"Failed to load ais-scan routes: {e}")

# CORS: When credentials are used, specific origins must be listed (not '*').
# A wildcard together with credentials would let ANY website make signed-in
# requests and read the responses, so '*' disables credentialed CORS.
cors_origins = get_cors_origins()
_cors_credentials = "*" not in cors_origins
if not _cors_credentials:
    logger.warning("CORS_ORIGINS='*': credentialed cross-origin requests are disabled. "
                   "List explicit origins to allow a separate frontend origin.")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=_cors_credentials,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Demo vessel simulation for testing
DEMO_VESSELS_ENABLED = True  # Set to False to disable demo vessels

DEMO_VESSELS = {
    "demo_tow_1": {
        "mmsi": "DEMO001",
        "name": "M/V DELTA QUEEN",
        "ship_type": 70,  # Cargo
        "is_tow": True,
        "barge_count": 12,
        "tow_config": "3x4",
        "usace_source": True,
        "start_rm": 830.0,  # Start north of Lock 2 (815.2), heading downstream
        "direction": "downstream",
        "speed_knots": 4.5,  # ~5 mph downstream
        "estimated_lockage_time": 45,
        "is_double_lockage": True,
    },
    "demo_tow_2": {
        "mmsi": "DEMO002", 
        "name": "M/V RIVER RUNNER",
        "ship_type": 70,
        "is_tow": True,
        "barge_count": 6,
        "tow_config": "2x3",
        "usace_source": True,
        "start_rm": 800.0,  # Start south of Lock 2 (815.2), heading upstream
        "direction": "upstream",
        "speed_knots": 3.0,  # ~3.5 mph upstream (slower against current)
        "estimated_lockage_time": 30,
        "is_double_lockage": False,
    }
}

demo_vessel_positions = {}  # Track current positions

async def simulate_demo_vessels():
    """Background task to simulate demo vessel movement."""
    global demo_vessel_positions, demo_vessels_active
    
    if not DEMO_VESSELS_ENABLED:
        return
    
    # Initialize positions
    for vessel_id, config in DEMO_VESSELS.items():
        demo_vessel_positions[vessel_id] = config["start_rm"]
    
    logger.info(f"Demo vessel simulation started with {len(DEMO_VESSELS)} vessels")
    
    while True:
        try:
            await asyncio.sleep(10)  # Update every 10 seconds
            
            # Skip if demo vessels are disabled, or hidden because real AIS
            # traffic is flowing (RIVERWATCH_DEMO_VESSELS_MODE=auto).
            if not demo_vessels_active or _should_suppress_demo_vessels():
                # Remove demo vessels if present
                for vessel_id, config in DEMO_VESSELS.items():
                    mmsi = config["mmsi"]
                    if mmsi in active_vessels:
                        del active_vessels[mmsi]
                continue
            
            for vessel_id, config in DEMO_VESSELS.items():
                mmsi = config["mmsi"]
                
                # Skip paused vessels (manual control mode)
                if mmsi in demo_vessels_paused:
                    continue
                
                current_rm = demo_vessel_positions[vessel_id]
                speed_mph = config["speed_knots"] * 1.15078
                
                # Calculate movement (river miles per 10 seconds)
                # Speed is mph, so movement = speed * (10/3600) hours
                movement = speed_mph * (10 / 3600)
                
                if config["direction"] == "downstream":
                    new_rm = current_rm - movement
                    course = 180  # South
                    heading_dir = "southbound"
                    direction_display = "downriver"
                    # Wrap around if past Lock 27
                    if new_rm < 185:
                        new_rm = 847.0
                else:
                    new_rm = current_rm + movement
                    course = 0  # North
                    heading_dir = "northbound"
                    direction_display = "upriver"
                    # Wrap around if past Lock 1
                    if new_rm > 847:
                        new_rm = 185.0
                
                demo_vessel_positions[vessel_id] = new_rm
                
                # Calculate lat/lon from river mile
                lat, lon = _river_mile_to_coords(new_rm)
                
                # Find nearest lock
                nearest_lock = None
                min_dist = float('inf')
                for lock_id, lock_info in LOCKS.items():
                    dist = abs(lock_info["river_mile"] - new_rm)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_lock = lock_id
                
                # Create vessel entry with direction info
                vessel = {
                    "mmsi": config["mmsi"],
                    "name": vessel_static_cache.get(config["mmsi"], {}).get("name") or config["name"],  # Use cached name if renamed
                    "lat": lat,
                    "lon": lon,
                    "speed": config["speed_knots"],
                    "course": course,
                    "heading": heading_dir,  # String: 'northbound' or 'southbound' for race analysis
                    "heading_direction": heading_dir,
                    "direction": direction_display,  # 'upriver' or 'downriver'
                    "ship_type": vessel_static_cache.get(config["mmsi"], {}).get("ship_type") or config["ship_type"],  # Use cached type if changed
                    "nav_status": 0,  # Under way using engine
                    "river_mile": round(new_rm, 1),
                    "is_tow": config["is_tow"],
                    "barge_count": config["barge_count"],
                    "tow_config": config["tow_config"],
                    "usace_source": config["usace_source"],
                    "usace_lock": nearest_lock,
                    "usace_status": "in_transit",
                    "estimated_lockage_time": config["estimated_lockage_time"],
                    "is_double_lockage": config["is_double_lockage"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "is_demo": True,  # Mark as demo vessel
                }
                
                # Store in active_vessels
                active_vessels[config["mmsi"]] = vessel
                
                # Generate simulated NMEA and broadcast to raw data subscribers
                await broadcast_demo_nmea(config["mmsi"], lat, lon, config["speed_knots"], course)
                
                # Persist to database
                asyncio.create_task(persist_vessel_sighting(vessel))
            
        except asyncio.CancelledError:
            logger.info("Demo vessel simulation stopped")
            break
        except Exception as e:
            logger.error(f"Error in demo vessel simulation: {e}")
            await asyncio.sleep(30)


async def simulate_user_vessels():
    """Move users' simulated boats every 10 s. Its own task: it used to run
    inside the demo-vessel loop, which skips everything while demo boats are
    off or hidden behind live AIS - so a simulated boat froze in place as soon
    as real traffic showed up."""
    lock_miles = sorted(float(l["river_mile"]) for l in LOCKS.values() if l.get("river_mile") is not None)
    while True:
        try:
            await asyncio.sleep(10)
            now = datetime.now(timezone.utc)
            for mmsi, sim in list(user_vessel_simulation.items()):
                if not sim.get('enabled'):
                    continue
                before = sim.get('river_mile')
                _user_sim.step(sim, lock_miles, 10, now)
                await _update_simulated_user_vessel(mmsi, sim)
                if sim.get('holding') and before != sim.get('river_mile'):
                    logger.info(f"[USER SIM] {mmsi}: stopped at the lock at RM {sim['river_mile']} until {sim.get('hold_until')}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in user vessel simulation: {e}")
            await asyncio.sleep(30)


@app.on_event("startup")
async def startup_event():
    """Load settings, blocked MMSIs, and vessel names from database on startup."""
    # NOTE: No global user_mmsi - sessions are created per-connection
    
    # Load blocked MMSIs
    await load_blocked_mmsi()
    
    await _ensure_indexes(db)

    # Load persisted vessel names (shared across all users)
    await load_vessel_names_from_db()

    # Optional second AIS source: aisstream.io (needs AISSTREAM_API_KEY).
    global _aisstream_task
    if _aisstream.api_key():
        _aisstream_task = asyncio.create_task(_aisstream.run(
            vessel_data_from_decoded,
            ais_manager.ingest_vessel_data,
            vessel_static_cache,
            ais_manager._apply_static_to_active,
        ))
    
    await load_adopted_calibration()
    asyncio.create_task(wait_model_learning_task())
    # Arrival predictions: log, score against USACE, learn the AIS ETA correction
    await load_adopted_arrival_factor()
    asyncio.create_task(arrival_learning_task())
    asyncio.create_task(daily_report_task())
    asyncio.create_task(feed_monitor_task())
    asyncio.create_task(wait_logging_task())
    asyncio.create_task(marinas_task())

    restored = await load_usace_queue_snapshot()
    if restored:
        logger.info(f"Restored USACE queues for {restored} locks from the last run")

    # USACE lock queues + lockage history: refreshed continuously in the
    # background, one lock at a time (USACE allows 5 requests per minute).
    asyncio.create_task(usace_refresh_task())
    
    # Start demo vessel simulation
    if DEMO_VESSELS_ENABLED:
        asyncio.create_task(simulate_demo_vessels())
    # Users' own simulated boats move regardless of demo boats / live AIS.
    asyncio.create_task(simulate_user_vessels())

    # Periodic stale-vessel pruning (removes leftover test/injected MMSIs)
    asyncio.create_task(stale_vessel_sweep_task())
    # Boats parked at their home berth live only in memory; without this a
    # restart (every deploy) left them off the map.
    asyncio.create_task(_park_all_at_home())
    # Auto-restore last AIS connection (so the Pi reconnects to the phone
    # automatically after a reboot without the user re-entering the IP).
    try:
        doc = await db.settings.find_one({"key": "last_connection_config"}, {"_id": 0})
        if doc and doc.get("value"):
            saved = json.loads(doc["value"])
            ip = saved.get("ip_address")
            port = int(saved.get("port") or 5353)
            mmsi = saved.get("user_mmsi", "") or ""
            boat = saved.get("boat_name", "") or ""
            if ip and ip not in ("ais-relay", "push://relay"):
                logger.info(f"Auto-restoring AIS connection to {ip}:{port} (mmsi={mmsi})")
                asyncio.create_task(ais_manager.configure(ip, port, mmsi, boat))
            else:
                logger.info(f"Skipping AIS auto-restore (ip={ip!r} is stale/non-routable)")
    except Exception as e:
        logger.warning(f"Failed to auto-restore AIS connection: {e}")


async def usace_refresh_task():
    """Walk the Upper Mississippi locks forever, one USACE request at a time."""
    passes = 0
    async with httpx.AsyncClient(timeout=30.0, headers=OUTBOUND_HEADERS) as client:
        while True:
            total = 0
            for lock_no in UPPER_MISS_LOCKS:
                while True:
                    try:
                        total += await fetch_usace_lock(client, lock_no)
                        break
                    except UsaceRateLimited:
                        logger.info(f"USACE rate limit hit at lock {lock_no}; pausing 65 s")
                        await asyncio.sleep(65)
                    except asyncio.CancelledError:
                        return
                    except Exception as e:
                        logger.warning(f"USACE lock {lock_no} fetch failed: {e}")
                        break
                try:
                    await asyncio.sleep(USACE_SPACING_S)
                except asyncio.CancelledError:
                    return
            passes += 1
            logger.info(f"USACE pass {passes} complete: {total} vessels waiting/locking across {len(usace_lock_fetched_at)} locks")

@app.on_event("shutdown")
async def shutdown_db_client():
    """Clean up resources on shutdown."""
    if _aisstream_task and not _aisstream_task.done():
        _aisstream_task.cancel()
    # Close HTTP client pool
    await close_http_client()
    # Close MongoDB connection
    client.close()
    logger.info("Server shutdown complete")
