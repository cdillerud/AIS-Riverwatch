# River Watch Backend - Traffic Planning Routes
#
# Endpoints under /api/planning/* powering the River Traffic Planning UI.
# Includes: trip planner, lock queue, meeting predictor, bottleneck forecast.

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from datetime import datetime, timezone
import logging

from config import LOCKS
from services.planning_service import (
    compute_trip_plan,
    build_lock_queue,
    predict_meetings,
    forecast_bottlenecks,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/planning", tags=["Planning"])


class TripPlanRequest(BaseModel):
    origin_rm: float = Field(..., description="Starting river mile")
    destination_rm: float = Field(..., description="Destination river mile")
    etd: Optional[str] = Field(None, description="ISO timestamp for departure (defaults to now)")
    base_speed_knots: Optional[float] = Field(None, description="Planned speed in knots; if omitted and mmsi provided, recent AIS speed is used")
    mmsi: Optional[str] = Field(None, description="Optional vessel MMSI for prefilling speed")


def _get_active_vessels() -> Dict:
    try:
        from server import active_vessels
        return active_vessels
    except Exception:
        return {}


def _get_usace_queue_data() -> Optional[Dict]:
    try:
        from server import usace_lock_queue_cache
        return usace_lock_queue_cache.get("data") or {}
    except Exception:
        return None


async def _get_history_by_lock() -> Dict[str, List[Dict]]:
    try:
        from server import db
        # Pull last 20 records per lock by aggregation; fall back to one query
        cursor = db.lockage_history.find(
            {"duration_minutes": {"$ne": None}},
            {"_id": 0, "lock_id": 1, "duration_minutes": 1, "completed_at": 1},
        ).sort("completed_at", -1).limit(500)
        rows = await cursor.to_list(length=500)
        grouped: Dict[str, List[Dict]] = {}
        for r in rows:
            lid = r.get("lock_id")
            if not lid:
                continue
            grouped.setdefault(lid, []).append(r)
        # Keep only most recent 5 per lock (cursor already sorted desc)
        for lid in list(grouped.keys()):
            grouped[lid] = grouped[lid][:5]
        return grouped
    except Exception as e:
        logger.error(f"[planning] history lookup failed: {e}")
        return {}


@router.post("/trip")
async def plan_trip(body: TripPlanRequest):
    """Compute a multi-leg trip plan with lock waits and per-segment ETAs."""
    if body.origin_rm == body.destination_rm:
        raise HTTPException(status_code=400, detail="origin and destination cannot be equal")

    speed = body.base_speed_knots
    speed_source = "user"
    if not speed and body.mmsi:
        # Try to pull recent AIS speed for this MMSI
        active = _get_active_vessels()
        vessel = active.get(body.mmsi)
        if vessel:
            spd = vessel.get("speed") if isinstance(vessel, dict) else getattr(vessel, "speed", None)
            if spd and spd > 0:
                speed = float(spd)
                speed_source = "ais"
    if not speed:
        speed = 8.0
        speed_source = "default"

    etd = body.etd or datetime.now(timezone.utc).isoformat()
    queue_data = _get_usace_queue_data()
    history_by_lock = await _get_history_by_lock()

    plan = compute_trip_plan(
        origin_rm=body.origin_rm,
        destination_rm=body.destination_rm,
        etd_iso=etd,
        base_speed_knots=speed,
        queue_cache_data=queue_data,
        history_by_lock=history_by_lock,
    )
    plan["speed_source"] = speed_source
    if body.mmsi:
        plan["mmsi"] = body.mmsi
    return plan


@router.get("/lock-queue/{lock_id}")
async def lock_queue(lock_id: str, lookahead_hours: float = Query(6.0, ge=0.5, le=24.0)):
    """Ordered list of vessels approaching a specific lock within the lookahead window."""
    if lock_id not in LOCKS:
        raise HTTPException(status_code=404, detail=f"Unknown lock {lock_id}")
    active = _get_active_vessels()
    return build_lock_queue(lock_id, active, lookahead_hours=lookahead_hours)


@router.get("/meetings")
async def meetings(lookahead_hours: float = Query(4.0, ge=0.5, le=12.0)):
    """Predicted head-on and overtaking encounters within the next `lookahead_hours`."""
    active = _get_active_vessels()
    encounters = predict_meetings(active, lookahead_hours=lookahead_hours)
    return {
        "encounters": encounters,
        "count": len(encounters),
        "lookahead_hours": lookahead_hours,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/bottlenecks")
async def bottlenecks(hours: float = Query(6.0, ge=1.0, le=24.0)):
    """Forecast lock congestion in the next `hours`."""
    active = _get_active_vessels()
    queue_data = _get_usace_queue_data()
    history = await _get_history_by_lock()
    forecast = forecast_bottlenecks(
        active_vessels=active,
        queue_cache_data=queue_data,
        history_by_lock=history,
        hours=hours,
    )
    return {
        "forecast": forecast,
        "hours": hours,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/locks")
async def planning_locks():
    """Helper endpoint returning lock list sorted upstream → downstream for the Trip Planner UI."""
    rows = []
    for lid, l in LOCKS.items():
        rows.append({"lock_id": lid, "name": l["name"], "river_mile": l["river_mile"]})
    rows.sort(key=lambda x: x["river_mile"], reverse=True)
    return {"locks": rows}
