# River Watch Backend - Vessel Routes
# API endpoints for vessel data and session management

from fastapi import APIRouter, HTTPException, Request
from typing import Optional
import logging

from services.vessel_service import (
    vessel_cache, prepare_vessel_for_output, 
    estimate_river_mile, determine_heading,
    calculate_eta_to_lock, calculate_required_speed
)
from config import LOCKS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Vessels"])


def get_db():
    """Get database reference."""
    from database import db
    return db


def get_active_vessels():
    """Get active vessels dict from server module."""
    from server import active_vessels
    return active_vessels


@router.get("/vessels")
async def get_vessels():
    """Get all active vessels."""
    active_vessels = get_active_vessels()
    vessels = []
    for mmsi, vessel in active_vessels.items():
        v_dict = prepare_vessel_for_output(vessel, mmsi)
        vessels.append(v_dict)
    return vessels


@router.get("/session/{session_mmsi}/vessels")
async def get_vessels_for_session(session_mmsi: str):
    """Get vessels for a specific session (excludes session's own vessel)."""
    session_mmsi = str(session_mmsi).strip()
    active_vessels = get_active_vessels()
    
    vessels = []
    for mmsi, vessel in active_vessels.items():
        v_dict = prepare_vessel_for_output(vessel, mmsi)
        # Mark user's vessel
        if mmsi == session_mmsi:
            v_dict['is_user_vessel'] = True
        vessels.append(v_dict)
    
    return vessels


@router.post("/session/{session_mmsi}/position")
async def update_session_position(session_mmsi: str, data: dict):
    """Update position for a session's vessel."""
    from server import active_vessels, VesselData
    from datetime import datetime, timezone
    
    session_mmsi = str(session_mmsi).strip()
    if not session_mmsi:
        raise HTTPException(status_code=400, detail="Session MMSI required")
    
    lat = data.get('lat')
    lon = data.get('lon')
    
    if lat is None or lon is None:
        raise HTTPException(status_code=400, detail="lat and lon required")
    
    # Calculate river mile if not provided
    river_mile = data.get('river_mile')
    if river_mile is None:
        river_mile = estimate_river_mile(lat, lon)
    
    # Determine heading if not provided
    speed = data.get('speed', 0)
    course = data.get('course', 0)
    heading = data.get('heading')
    if not heading:
        heading = determine_heading(speed, course)
    
    # Create/update vessel data
    vessel_data = {
        'mmsi': session_mmsi,
        'name': data.get('name', 'Your Vessel'),
        'lat': lat,
        'lon': lon,
        'speed': speed,
        'course': course,
        'river_mile': river_mile,
        'heading': heading,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'is_user_vessel': True,
        'vessel_type': 'recreational',
        'ship_type': data.get('ship_type'),
        'length': data.get('length'),
        'width': data.get('width'),
        'draught': data.get('draught'),
        'barge_count': None,
        'tow_config': None,
        'is_tow': False,
        'estimated_lockage_time': None,
        'heading_true': None,
        'turn_rate': None,
        'nav_status': None,
        'nav_status_text': None,
        'destination': data.get('destination'),
        'callsign': None,
        'imo': None,
        'eta': None,
        'is_double_lockage': False,
        'usace_source': False,
        'usace_lock': None,
        'usace_status': None,
        'source': 'manual'
    }
    
    # Calculate next lock info
    next_lock = _calculate_next_lock(river_mile, heading, speed)
    vessel_data['next_lock'] = next_lock
    
    # Store in active vessels
    active_vessels[session_mmsi] = vessel_data
    
    # Also cache
    await vessel_cache.set(session_mmsi, vessel_data)
    
    logger.info(f"[SESSION:{session_mmsi}] Position updated: RM {river_mile}, {heading}")
    
    return {
        "success": True,
        "session_mmsi": session_mmsi,
        "vessel": vessel_data
    }


def _calculate_next_lock(river_mile: float, heading: str, speed: float) -> Optional[dict]:
    """Calculate next lock based on position and heading."""
    if not river_mile:
        return None
    
    next_lock = None
    next_lock_id = None
    min_distance = float('inf')
    
    for lock_id, lock_info in LOCKS.items():
        lock_rm = lock_info["river_mile"]
        distance = abs(river_mile - lock_rm)
        
        # Check if heading toward this lock
        if heading == "northbound" and lock_rm > river_mile:
            if distance < min_distance:
                min_distance = distance
                next_lock = lock_info
                next_lock_id = lock_id
        elif heading == "southbound" and lock_rm < river_mile:
            if distance < min_distance:
                min_distance = distance
                next_lock = lock_info
                next_lock_id = lock_id
    
    if not next_lock:
        return None
    
    # Calculate ETA
    eta_minutes = None
    if speed and speed > 0.1:
        speed_mph = speed * 1.15078
        eta_minutes = int((min_distance / speed_mph) * 60)
    
    # Format ETA display
    eta_display = None
    if eta_minutes:
        if eta_minutes >= 60:
            hours = eta_minutes // 60
            mins = eta_minutes % 60
            eta_display = f"{hours}h {mins}m"
        else:
            eta_display = f"{eta_minutes}m"
    
    return {
        "next_lock_id": next_lock_id,
        "next_lock_name": next_lock["name"],
        "next_lock_rm": next_lock["river_mile"],
        "distance_miles": round(min_distance, 1),
        "eta_minutes": eta_minutes,
        "eta_display": eta_display
    }


@router.get("/session/{session_mmsi}/race-analysis/{lock_id}")
async def get_session_race_analysis(session_mmsi: str, lock_id: str, buffer_minutes: int = 20):
    """Get race analysis for a specific session and lock."""
    from server import active_vessels, RaceAnalysis
    
    session_mmsi = str(session_mmsi).strip()
    if not session_mmsi:
        raise HTTPException(status_code=400, detail="Session MMSI required")
    
    if lock_id not in LOCKS:
        raise HTTPException(status_code=404, detail="Invalid lock ID")
    
    lock = LOCKS[lock_id]
    lock_rm = lock["river_mile"]
    
    # Distance threshold for threats
    MAX_THREAT_DISTANCE = 100.0
    
    # Find user's vessel
    user_vessel = None
    user_rm = None
    if session_mmsi in active_vessels:
        user_vessel = prepare_vessel_for_output(active_vessels[session_mmsi], session_mmsi)
        user_rm = user_vessel.get('river_mile') or estimate_river_mile(
            user_vessel.get('lat'), user_vessel.get('lon')
        )
    
    # Find competitors heading toward this lock
    competitors = []
    for mmsi, vessel in active_vessels.items():
        if mmsi == session_mmsi:
            continue
        
        # Get vessel data
        if hasattr(vessel, 'river_mile'):
            vessel_rm = vessel.river_mile or estimate_river_mile(vessel.lat, vessel.lon)
            vessel_speed = vessel.speed
            vessel_heading = vessel.heading or determine_heading(vessel.speed, vessel.course)
        else:
            vessel_rm = vessel.get('river_mile') or estimate_river_mile(
                vessel.get('lat'), vessel.get('lon')
            )
            vessel_speed = vessel.get('speed', 0)
            vessel_heading = (
                vessel.get('heading') or 
                vessel.get('heading_direction') or 
                determine_heading(vessel.get('speed', 0), vessel.get('course', 0))
            )
        
        # Calculate ETA to lock
        eta = calculate_eta_to_lock(vessel_rm, vessel_speed, vessel_heading, lock_rm)
        
        if eta is not None and eta > 0:
            v_dict = prepare_vessel_for_output(vessel, mmsi)
            v_dict['eta_minutes'] = eta
            v_dict['distance_to_lock'] = round(abs(vessel_rm - lock_rm), 1) if vessel_rm else None
            
            if user_rm and vessel_rm:
                v_dict['distance_from_user'] = round(abs(user_rm - vessel_rm), 1)
            else:
                v_dict['distance_from_user'] = None
            
            competitors.append(v_dict)
    
    # Sort by ETA
    competitors.sort(key=lambda x: x.get('eta_minutes', float('inf')))
    
    # Calculate analysis
    analysis = None
    if user_vessel and user_rm:
        user_heading = user_vessel.get('heading', 'southbound')
        user_distance = abs(user_rm - lock_rm)
        user_speed_knots = user_vessel.get('speed', 0)
        user_speed_mph = user_speed_knots * 1.15078
        
        user_eta = calculate_eta_to_lock(user_rm, user_speed_knots, user_heading, lock_rm)
        
        # Find most threatening competitor (bi-directional)
        threat = None
        required_speed = None
        can_beat = True
        
        for comp in competitors:
            comp_eta = comp.get('eta_minutes')
            comp_distance_to_lock = comp.get('distance_to_lock')
            
            # Skip if too far from lock
            if comp_distance_to_lock is not None and comp_distance_to_lock > MAX_THREAT_DISTANCE:
                continue
            
            # Check if competitor will arrive before user
            if comp_eta and (user_eta is None or comp_eta < user_eta + buffer_minutes):
                threat = comp
                required_speed = calculate_required_speed(
                    user_rm, user_heading, lock_rm, comp_eta, buffer_minutes
                )
                if required_speed and required_speed > 25:
                    can_beat = False
                break
        
        analysis = {
            "user_distance_to_lock": round(user_distance, 1),
            "user_eta_minutes": user_eta,
            "user_current_speed_mph": round(user_speed_mph, 1),
            "threatening_vessel": threat,
            "required_speed_mph": required_speed,
            "can_beat_at_25mph": can_beat,
            "max_speed_mph": 25,
            "buffer_minutes": buffer_minutes
        }
    
    return RaceAnalysis(
        user_vessel=user_vessel,
        target_lock=lock_id,
        target_lock_name=lock["name"],
        target_lock_rm=lock["river_mile"],
        competitors=competitors,
        analysis=analysis
    )


@router.get("/sessions")
async def get_active_sessions():
    """Get list of active sessions."""
    active_vessels = get_active_vessels()
    sessions = []
    for mmsi, vessel in active_vessels.items():
        if isinstance(vessel, dict) and vessel.get('is_user_vessel'):
            sessions.append({
                "mmsi": mmsi,
                "name": vessel.get('name', 'Unknown'),
                "river_mile": vessel.get('river_mile'),
                "heading": vessel.get('heading')
            })
    return {"sessions": sessions}
