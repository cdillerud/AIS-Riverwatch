# River Watch Backend - Navigation Service
# Contains river mile calculations and ETA computations
from typing import Optional, Tuple
from config import RIVER_MILE_POINTS


def estimate_river_mile(lat: float, lon: float) -> float:
    """Estimate river mile from GPS coordinates using interpolation."""
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


def river_mile_to_coords(rm: float) -> Tuple[float, float]:
    """Convert river mile to approximate GPS coordinates."""
    # Find the two reference points that bracket this river mile
    points = sorted(RIVER_MILE_POINTS, key=lambda x: x[2], reverse=True)
    
    for i in range(len(points) - 1):
        if points[i][2] >= rm >= points[i + 1][2]:
            # Linear interpolation
            rm_range = points[i][2] - points[i + 1][2]
            if rm_range == 0:
                return (points[i][0], points[i][1])
            
            ratio = (points[i][2] - rm) / rm_range
            lat = points[i][0] + ratio * (points[i + 1][0] - points[i][0])
            lon = points[i][1] + ratio * (points[i + 1][1] - points[i][1])
            return (round(lat, 4), round(lon, 4))
    
    # If outside range, return the closest endpoint
    if rm > points[0][2]:
        return (points[0][0], points[0][1])
    return (points[-1][0], points[-1][1])


def determine_heading(speed: float, course: float) -> str:
    """Determine if vessel is heading upstream or downstream based on course."""
    if speed is None or speed < 0.5:
        return "stationary"
    
    if course is None:
        return "unknown"
    
    # On the Upper Mississippi, upstream is generally north (270-90 degrees)
    # and downstream is generally south (90-270 degrees)
    if 270 <= course <= 360 or 0 <= course < 90:
        return "upstream"
    else:
        return "downstream"


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
