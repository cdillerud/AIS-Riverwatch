# River Watch Backend - Authentication Service
import hashlib
import secrets
import logging
from typing import Optional
from fastapi import Request

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash password with salt using SHA-256."""
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256((salt + password).encode())
    return f"{salt}${hash_obj.hexdigest()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash."""
    try:
        salt, hash_value = hashed.split('$')
        hash_obj = hashlib.sha256((salt + password).encode())
        return hash_obj.hexdigest() == hash_value
    except (ValueError, AttributeError):
        return False


def generate_session_token() -> str:
    """Generate a secure session token."""
    return f"session_{secrets.token_urlsafe(32)}"


async def get_current_user(request: Request, db) -> Optional[dict]:
    """Get the current authenticated user from session token."""
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        return None
    
    # Look up session in database
    session = await db.sessions.find_one({"token": session_token})
    if not session:
        return None
    
    # Check if session is expired (24 hours)
    from datetime import datetime, timezone, timedelta
    if session.get("expires_at"):
        expires_at = session["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        if expires_at < datetime.now(timezone.utc):
            # Session expired, delete it
            await db.sessions.delete_one({"token": session_token})
            return None
    
    # Get user data
    user = await db.user_accounts.find_one({"user_id": session["user_id"]})
    if not user:
        return None
    
    # Remove sensitive fields
    user.pop("_id", None)
    user.pop("hashed_password", None)
    
    return user


async def create_session(user_id: str, db) -> str:
    """Create a new session for a user."""
    from datetime import datetime, timezone, timedelta
    
    token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    
    await db.sessions.insert_one({
        "token": token,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat()
    })
    
    return token


async def delete_session(token: str, db):
    """Delete a session."""
    await db.sessions.delete_one({"token": token})
