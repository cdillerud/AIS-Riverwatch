# River Watch Backend - Navigation Service
# Contains river mile calculations and ETA computations
from typing import Optional, Tuple
from config import RIVER_MILE_POINTS
from services import river_geometry as _geo


def estimate_river_mile(lat: float, lon: float) -> Optional[float]:
    """Official river mile (snap to USACE sailing line). None if not on the Mississippi."""
    return _geo.river_mile(lat, lon)


def river_mile_to_coords(rm: float) -> Tuple[float, float]:
    """Convert river mile to a point on the sailing line."""
    hit = _geo.coords_for_mile(rm)
    if hit is not None:
        return hit
    points = sorted(RIVER_MILE_POINTS, key=lambda x: x[2], reverse=True)
    if rm > points[0][2]:
        return (points[0][0], points[0][1])
    return (points[-1][0], points[-1][1])


def determine_heading(speed: float, course: float, lat: float = None, lon: float = None) -> str:
    """'upstream' / 'downstream' / 'stationary' / 'unknown', using local river direction."""
    return _geo.heading_label(speed, course, lat, lon, up="upstream", down="downstream")


def calculate_eta_to_lock(
    vessel_rm: float, 
    vessel_speed_knots: float, 
    heading: str, 
    lock_rm: float
) -> Optional[float]:
    """Calculate ETA to a lock in minutes."""
    if vessel_rm is None or vessel_speed_knots is None or vessel_speed_knots < 0.1:
        return None
    
    if heading == "stationary":
        return None
    
    # Calculate distance to lock
    distance = abs(vessel_rm - lock_rm)
    
    # Check if vessel is heading toward or away from the lock
    if heading == "upstream" and vessel_rm < lock_rm:
        # Going upstream toward a higher river mile lock
        pass
    elif heading == "downstream" and vessel_rm > lock_rm:
        # Going downstream toward a lower river mile lock
        pass
    else:
        # Vessel is heading away from the lock
        return None
    
    # Convert speed from knots to mph (1 knot ≈ 1.151 mph)
    speed_mph = vessel_speed_knots * 1.151
    
    if speed_mph < 0.1:
        return None
    
    # Calculate time in hours, then convert to minutes
    time_hours = distance / speed_mph
    return round(time_hours * 60, 1)


def calculate_required_speed(
    user_rm: float, 
    user_heading: str, 
    target_lock_rm: float, 
    competitor_eta_minutes: float, 
    buffer_minutes: float = 20
) -> Optional[float]:
    """Calculate the speed required to beat a competitor to a lock."""
    if user_rm is None or competitor_eta_minutes is None:
        return None
    
    if competitor_eta_minutes <= 0:
        return None  # Competitor is already there
    
    # Calculate distance to lock
    distance = abs(user_rm - target_lock_rm)
    
    # Check if user is heading toward the lock
    if user_heading == "upstream" and user_rm >= target_lock_rm:
        return None  # User is past the lock going upstream
    if user_heading == "downstream" and user_rm <= target_lock_rm:
        return None  # User is past the lock going downstream
    
    # Time available is competitor's ETA minus buffer
    available_time_minutes = competitor_eta_minutes - buffer_minutes
    
    if available_time_minutes <= 0:
        return None  # Not enough time even at maximum speed
    
    # Calculate required speed in mph
    available_time_hours = available_time_minutes / 60
    required_speed_mph = distance / available_time_hours
    
    return round(required_speed_mph, 1)
