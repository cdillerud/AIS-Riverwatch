# River Watch Backend - Lock Models
from pydantic import BaseModel
from typing import Optional, List


class LockInfo(BaseModel):
    """Basic lock information."""
    id: str
    name: str
    river_mile: float
    location: str


class LockStatus(BaseModel):
    """Lock operational status from USACE."""
    lock_id: str
    name: str
    status: str = "unknown"  # open, closed, restricted, unknown
    queue_upbound: int = 0
    queue_downbound: int = 0
    vessels_in_queue: List[dict] = []
    last_update: Optional[str] = None
    delay_minutes: Optional[int] = None
    restriction_reason: Optional[str] = None


class LockageRecord(BaseModel):
    """Record of a vessel passing through a lock."""
    lock_id: str
    vessel_name: str
    mmsi: Optional[str] = None
    direction: str  # "upstream" or "downstream"
    arrival_time: Optional[str] = None
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    duration_minutes: Optional[float] = None
    is_tow: bool = False
    barge_count: int = 0
    recorded_at: Optional[str] = None


class RaceAnalysis(BaseModel):
    """Analysis of race to a lock against commercial traffic."""
    target_lock: str
    target_lock_name: str
    user_vessel_mmsi: str
    user_vessel_name: Optional[str] = None
    user_distance_miles: Optional[float] = None
    user_current_speed: Optional[float] = None
    user_eta_minutes: Optional[float] = None
    competitors: List[dict] = []
    required_speed_mph: Optional[float] = None
    can_beat_traffic: bool = True
    alert_level: str = "clear"  # clear, warning, critical
    recommendation: Optional[str] = None
