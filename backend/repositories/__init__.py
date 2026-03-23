"""
Database Repository Layer

This module provides a clean interface for all MongoDB operations.
Using the repository pattern keeps database logic separate from business logic.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class VesselRepository:
    """Repository for vessel-related database operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.vessel_names
    
    async def get_vessel_name(self, mmsi: str) -> Optional[Dict]:
        """Get cached vessel name and type by MMSI."""
        try:
            doc = await self.collection.find_one(
                {"mmsi": mmsi},
                {"_id": 0}
            )
            return doc
        except Exception as e:
            logger.error(f"Error getting vessel name for {mmsi}: {e}")
            return None
    
    async def save_vessel_name(
        self, 
        mmsi: str, 
        name: str, 
        ship_type: Optional[int] = None,
        source: str = "AIS"
    ) -> bool:
        """Save or update vessel name in the database."""
        try:
            await self.collection.update_one(
                {"mmsi": mmsi},
                {"$set": {
                    "mmsi": mmsi,
                    "name": name,
                    "ship_type": ship_type,
                    "source": source,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error saving vessel name for {mmsi}: {e}")
            return False
    
    async def get_all_vessel_names(self) -> List[Dict]:
        """Get all cached vessel names."""
        try:
            cursor = self.collection.find({}, {"_id": 0})
            return await cursor.to_list(length=1000)
        except Exception as e:
            logger.error(f"Error getting all vessel names: {e}")
            return []


class UserRepository:
    """Repository for user account operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.user_accounts
    
    async def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user by email address."""
        try:
            doc = await self.collection.find_one(
                {"email": email.lower()},
                {"_id": 0}
            )
            return doc
        except Exception as e:
            logger.error(f"Error getting user by email: {e}")
            return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Get user by their ID."""
        try:
            doc = await self.collection.find_one(
                {"id": user_id},
                {"_id": 0}
            )
            return doc
        except Exception as e:
            logger.error(f"Error getting user by id: {e}")
            return None
    
    async def create_user(self, user_data: Dict) -> bool:
        """Create a new user account."""
        try:
            user_data["email"] = user_data["email"].lower()
            user_data["created_at"] = datetime.now(timezone.utc).isoformat()
            await self.collection.insert_one(user_data)
            return True
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False
    
    async def update_user(self, user_id: str, updates: Dict) -> bool:
        """Update user account fields."""
        try:
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            result = await self.collection.update_one(
                {"id": user_id},
                {"$set": updates}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            return False
    
    async def delete_user(self, user_id: str) -> bool:
        """Delete a user account."""
        try:
            result = await self.collection.delete_one({"id": user_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            return False
    
    async def get_all_users(self, skip: int = 0, limit: int = 100) -> List[Dict]:
        """Get all users with pagination."""
        try:
            cursor = self.collection.find(
                {},
                {"_id": 0, "hashed_password": 0}
            ).skip(skip).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    async def count_users(self) -> int:
        """Count total users."""
        try:
            return await self.collection.count_documents({})
        except Exception as e:
            logger.error(f"Error counting users: {e}")
            return 0


class SessionRepository:
    """Repository for user session operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.sessions
    
    async def create_session(self, session_data: Dict) -> bool:
        """Create a new session."""
        try:
            session_data["created_at"] = datetime.now(timezone.utc).isoformat()
            await self.collection.insert_one(session_data)
            return True
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return False
    
    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by ID."""
        try:
            doc = await self.collection.find_one(
                {"session_id": session_id},
                {"_id": 0}
            )
            return doc
        except Exception as e:
            logger.error(f"Error getting session: {e}")
            return None
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        try:
            result = await self.collection.delete_one({"session_id": session_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False
    
    async def delete_user_sessions(self, user_id: str) -> int:
        """Delete all sessions for a user."""
        try:
            result = await self.collection.delete_many({"user_id": user_id})
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error deleting user sessions: {e}")
            return 0


class TrafficWatchRepository:
    """Repository for traffic watch point operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.traffic_watch_points
    
    async def save_watch_point(self, user_id: str, watch_point: Dict) -> bool:
        """Save or update a user's watch point."""
        try:
            await self.collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "user_id": user_id,
                    "watch_point": watch_point,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error saving watch point: {e}")
            return False
    
    async def get_watch_point(self, user_id: str) -> Optional[Dict]:
        """Get a user's watch point."""
        try:
            doc = await self.collection.find_one(
                {"user_id": user_id},
                {"_id": 0}
            )
            return doc.get("watch_point") if doc else None
        except Exception as e:
            logger.error(f"Error getting watch point: {e}")
            return None


class LockPassageRepository:
    """Repository for tracking vessel passages through locks."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.lock_passages
    
    async def record_passage(
        self, 
        mmsi: str, 
        lock_id: str, 
        direction: str,
        vessel_name: Optional[str] = None
    ) -> bool:
        """Record a vessel passage through a lock."""
        try:
            await self.collection.insert_one({
                "mmsi": mmsi,
                "lock_id": lock_id,
                "direction": direction,
                "vessel_name": vessel_name,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            return True
        except Exception as e:
            logger.error(f"Error recording lock passage: {e}")
            return False
    
    async def get_recent_passages(
        self, 
        lock_id: str, 
        hours: int = 24,
        limit: int = 50
    ) -> List[Dict]:
        """Get recent passages through a lock."""
        try:
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            
            cursor = self.collection.find(
                {
                    "lock_id": lock_id,
                    "timestamp": {"$gte": cutoff}
                },
                {"_id": 0}
            ).sort("timestamp", -1).limit(limit)
            
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error getting recent passages: {e}")
            return []


class SettingsRepository:
    """Repository for application settings."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.app_settings
    
    async def get_settings(self) -> Dict:
        """Get global application settings."""
        try:
            doc = await self.collection.find_one(
                {"type": "global"},
                {"_id": 0}
            )
            return doc or {}
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return {}
    
    async def save_settings(self, settings: Dict) -> bool:
        """Save global application settings."""
        try:
            await self.collection.update_one(
                {"type": "global"},
                {"$set": {**settings, "type": "global"}},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return False
    
    async def update_last_connection(self, ip: str, port: int) -> bool:
        """Update last used connection settings."""
        try:
            await self.collection.update_one(
                {"type": "global"},
                {"$set": {
                    "last_ip": ip,
                    "last_port": port,
                    "last_connection_time": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error updating connection settings: {e}")
            return False


class UserSettingsRepository:
    """Repository for per-user settings (by MMSI)."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.user_settings
    
    async def get_settings(self, mmsi: str) -> Optional[Dict]:
        """Get settings for a specific MMSI."""
        try:
            doc = await self.collection.find_one(
                {"mmsi": mmsi},
                {"_id": 0}
            )
            return doc
        except Exception as e:
            logger.error(f"Error getting user settings for {mmsi}: {e}")
            return None
    
    async def save_settings(self, mmsi: str, settings: Dict) -> bool:
        """Save or update settings for a specific MMSI."""
        try:
            settings["mmsi"] = mmsi
            settings["updated_at"] = datetime.now(timezone.utc).isoformat()
            await self.collection.update_one(
                {"mmsi": mmsi},
                {"$set": settings},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error saving user settings for {mmsi}: {e}")
            return False


class BlockedMMSIRepository:
    """Repository for blocked MMSI list."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.blocked_mmsi
    
    async def get_all_blocked(self) -> List[Dict]:
        """Get all blocked MMSIs."""
        try:
            cursor = self.collection.find({}, {"_id": 0})
            return await cursor.to_list(length=100)
        except Exception as e:
            logger.error(f"Error getting blocked MMSIs: {e}")
            return []
    
    async def block_mmsi(self, mmsi: str, reason: Optional[str] = None) -> bool:
        """Block an MMSI."""
        try:
            await self.collection.update_one(
                {"mmsi": mmsi},
                {"$set": {
                    "mmsi": mmsi,
                    "reason": reason,
                    "blocked_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error blocking MMSI {mmsi}: {e}")
            return False
    
    async def unblock_mmsi(self, mmsi: str) -> bool:
        """Unblock an MMSI."""
        try:
            result = await self.collection.delete_one({"mmsi": mmsi})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error unblocking MMSI {mmsi}: {e}")
            return False


# Repository factory
class RepositoryFactory:
    """Factory for creating repository instances."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._vessels: Optional[VesselRepository] = None
        self._users: Optional[UserRepository] = None
        self._sessions: Optional[SessionRepository] = None
        self._traffic_watch: Optional[TrafficWatchRepository] = None
        self._lock_passages: Optional[LockPassageRepository] = None
        self._settings: Optional[SettingsRepository] = None
        self._user_settings: Optional[UserSettingsRepository] = None
        self._blocked_mmsi: Optional[BlockedMMSIRepository] = None
    
    @property
    def vessels(self) -> VesselRepository:
        if self._vessels is None:
            self._vessels = VesselRepository(self.db)
        return self._vessels
    
    @property
    def users(self) -> UserRepository:
        if self._users is None:
            self._users = UserRepository(self.db)
        return self._users
    
    @property
    def sessions(self) -> SessionRepository:
        if self._sessions is None:
            self._sessions = SessionRepository(self.db)
        return self._sessions
    
    @property
    def traffic_watch(self) -> TrafficWatchRepository:
        if self._traffic_watch is None:
            self._traffic_watch = TrafficWatchRepository(self.db)
        return self._traffic_watch
    
    @property
    def lock_passages(self) -> LockPassageRepository:
        if self._lock_passages is None:
            self._lock_passages = LockPassageRepository(self.db)
        return self._lock_passages
    
    @property
    def settings(self) -> SettingsRepository:
        if self._settings is None:
            self._settings = SettingsRepository(self.db)
        return self._settings
    
    @property
    def user_settings(self) -> UserSettingsRepository:
        if self._user_settings is None:
            self._user_settings = UserSettingsRepository(self.db)
        return self._user_settings
    
    @property
    def blocked_mmsi(self) -> BlockedMMSIRepository:
        if self._blocked_mmsi is None:
            self._blocked_mmsi = BlockedMMSIRepository(self.db)
        return self._blocked_mmsi
