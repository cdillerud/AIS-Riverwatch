# River Watch Backend - Vessel Service
# Centralized vessel data management with caching

from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
import logging
import asyncio
from functools import lru_cache

logger = logging.getLogger(__name__)

# In-memory vessel storage with TTL-based cache
class VesselCache:
    """Thread-safe vessel cache with automatic cleanup."""
    
    def __init__(self, ttl_seconds: int = 300):
        self._vessels: Dict[str, dict] = {}
        self._timestamps: Dict[str, datetime] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._name_cache: Dict[str, str] = {}  # MMSI -> vessel name
    
    async def get(self, mmsi: str) -> Optional[dict]:
        """Get vessel by MMSI."""
        async with self._lock:
            if mmsi not in self._vessels:
                return None
            # Check TTL
            ts = self._timestamps.get(mmsi)
            if ts and (datetime.now(timezone.utc) - ts).total_seconds() > self._ttl:
                del self._vessels[mmsi]
                del self._timestamps[mmsi]
                return None
            return self._vessels.get(mmsi)
    
    async def set(self, mmsi: str, vessel: dict) -> None:
        """Store vessel data."""
        async with self._lock:
            self._vessels[mmsi] = vessel
            self._timestamps[mmsi] = datetime.now(timezone.utc)
            # Cache name if available
            if vessel.get('name'):
                self._name_cache[mmsi] = vessel['name']
    
    async def get_all(self) -> Dict[str, dict]:
        """Get all active vessels."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            # Filter out expired entries
            active = {}
            expired = []
            for mmsi, vessel in self._vessels.items():
                ts = self._timestamps.get(mmsi)
                if ts and (now - ts).total_seconds() <= self._ttl:
                    active[mmsi] = vessel
                else:
                    expired.append(mmsi)
            # Cleanup expired
            for mmsi in expired:
                del self._vessels[mmsi]
                if mmsi in self._timestamps:
                    del self._timestamps[mmsi]
            return active
    
    async def delete(self, mmsi: str) -> None:
        """Remove vessel from cache."""
        async with self._lock:
            self._vessels.pop(mmsi, None)
            self._timestamps.pop(mmsi, None)
    
    async def clear(self) -> None:
        """Clear all cached vessels."""
        async with self._lock:
            self._vessels.clear()
            self._timestamps.clear()
    
    def get_name(self, mmsi: str) -> Optional[str]:
        """Get cached vessel name (sync, for quick lookups)."""
        return self._name_cache.get(mmsi)
    
    def set_name(self, mmsi: str, name: str) -> None:
        """Cache vessel name."""
        self._name_cache[mmsi] = name
    
    @property
    def count(self) -> int:
        """Get number of cached vessels."""
        return len(self._vessels)


# Global vessel cache instance
vessel_cache = VesselCache(ttl_seconds=300)  # 5 min TTL


def prepare_vessel_for_output(vessel: Any, mmsi: str) -> dict:
    """
    Convert vessel data to a clean dictionary for API output.
    Handles both Pydantic models and plain dicts.
    """
    if hasattr(vessel, 'model_dump'):
        # Pydantic v2
        v_dict = vessel.model_dump()
    elif hasattr(vessel, 'dict'):
        # Pydantic v1
        v_dict = vessel.dict()
    else:
        # Already a dict
        v_dict = dict(vessel)
    
    # Ensure MMSI is set
    v_dict['mmsi'] = mmsi
    
    # Remove MongoDB _id if present
    v_dict.pop('_id', None)
    
    # Add cached name if not present
    if not v_dict.get('name'):
        cached_name = vessel_cache.get_name(mmsi)
        if cached_name:
            v_dict['name'] = cached_name
    
    return v_dict


def estimate_river_mile(lat: float, lon: float) -> float:
    """Estimate river mile from GPS coordinates using interpolation."""
    from config import RIVER_MILE_POINTS
    
    if not lat or not lon:
        return 0.0
    
    # Find the two closest reference points
    closest = None
    second_closest = None
    
    for ref_lat, ref_lon, ref_rm in RIVER_MILE_POINTS:
        dist = ((lat - ref_lat) ** 2 + (lon - ref_lon) ** 2) ** 0.5
        
        if closest is None or dist < closest[0]:
            second_closest = closest
            closest = (dist, ref_lat, ref_lon, ref_rm)
        elif second_closest is None or dist < second_closest[0]:
            second_closest = (dist, ref_lat, ref_lon, ref_rm)
    
    if closest is None:
        return 0.0
    
    if second_closest is None:
        return closest[3]
    
    # Linear interpolation between the two closest points
    total_dist = closest[0] + second_closest[0]
    if total_dist == 0:
        return closest[3]
    
    weight1 = 1 - (closest[0] / total_dist)
    weight2 = 1 - (second_closest[0] / total_dist)
    
    interpolated_rm = (closest[3] * weight1 + second_closest[3] * weight2) / (weight1 + weight2)
    
    return round(interpolated_rm, 1)


def determine_heading(speed: float, course: float) -> str:
    """Determine if vessel is heading upstream or downstream based on course."""
    if speed is None or speed < 0.5:
        return "stationary"
    
    if course is None:
        return "unknown"
    
    # On the Upper Mississippi, upstream is generally north (270-90 degrees)
    # and downstream is generally south (90-270 degrees)
    if 270 <= course <= 360 or 0 <= course < 90:
        return "northbound"
    else:
        return "southbound"


def calculate_eta_to_lock(
    vessel_rm: float, 
    vessel_speed_knots: float, 
    heading: str, 
    lock_rm: float
) -> Optional[float]:
    """Calculate ETA in minutes to reach a lock. Returns None if vessel moving away."""
    if vessel_speed_knots < 0.1:
        return None
    
    distance_rm = abs(vessel_rm - lock_rm)
    
    # Check if vessel is moving toward the lock
    if heading == "northbound" and vessel_rm < lock_rm:
        pass  # Moving toward lock
    elif heading == "southbound" and vessel_rm > lock_rm:
        pass  # Moving toward lock
    elif heading == "stationary":
        return None
    else:
        return None  # Moving away
    
    # Convert speed from knots to mph (1 knot = 1.15078 mph)
    speed_mph = vessel_speed_knots * 1.15078
    
    if speed_mph > 0:
        eta_minutes = (distance_rm / speed_mph) * 60
        return round(eta_minutes, 1)
    return None


def calculate_required_speed(
    user_rm: float, 
    user_heading: str, 
    target_lock_rm: float, 
    competitor_eta_minutes: float, 
    buffer_minutes: float = 20
) -> Optional[float]:
    """Calculate required speed in MPH to beat competitor to lock."""
    if competitor_eta_minutes is None or competitor_eta_minutes <= 0:
        return None
    
    distance_rm = abs(user_rm - target_lock_rm)
    
    # Check if user is heading toward the lock
    if user_heading == "northbound" and user_rm >= target_lock_rm:
        return None
    elif user_heading == "southbound" and user_rm <= target_lock_rm:
        return None
    
    # Required speed to arrive with buffer before competitor
    target_time_minutes = max(competitor_eta_minutes - buffer_minutes, 1)
    required_mph = (distance_rm / target_time_minutes) * 60
    
    return round(required_mph, 1)
