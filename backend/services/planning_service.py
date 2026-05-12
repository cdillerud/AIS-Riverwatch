# River Watch Backend - Traffic Planning Service
#
# Provides helpers for the four traffic-planning features:
#   1. Trip Planner: per-leg ETA accounting for lock wait + transit times
#   2. Lock Queue View: ordered list of vessels approaching a lock
#   3. Meeting Predictor: head-on encounters between two AIS vessels
#   4. Bottleneck Forecast: lock congestion in the next N hours
#
# All times in minutes unless stated otherwise.
# Speeds are knots (vessel) or mph (river-mile travel).

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import logging

from config import LOCKS
from services.navigation_service import river_mile_to_coords

logger = logging.getLogger(__name__)

# Conversions
KNOTS_TO_MPH = 1.15078

# Default lockage times (minutes) when no other data is available.
# Single lockage ~30 min, double lockage ~75 min (USACE typical).
DEFAULT_LOCKAGE_MINUTES = 30
DEFAULT_DOUBLE_LOCKAGE_MINUTES = 75

# Bottleneck severity thresholds
SEVERITY_LOW = "low"
SEVERITY_MODERATE = "moderate"
SEVERITY_HIGH = "high"


def sorted_locks() -> List[Tuple[str, float]]:
    """Return [(lock_id, river_mile), ...] sorted descending by RM (upstream first)."""
    return sorted(
        [(lid, lock["river_mile"]) for lid, lock in LOCKS.items()],
        key=lambda x: x[1],
        reverse=True,
    )


def locks_between(start_rm: float, end_rm: float) -> List[Tuple[str, float]]:
    """Return locks strictly between start_rm and end_rm (exclusive), in travel order."""
    lo, hi = sorted([start_rm, end_rm])
    going_down = end_rm < start_rm  # True = traveling downriver (RM decreasing)
    crossed = [(lid, rm) for lid, rm in sorted_locks() if lo < rm < hi]
    # Travel order: downstream → descending RM; upstream → ascending RM
    crossed.sort(key=lambda x: x[1], reverse=going_down)
    return crossed


def estimate_lock_wait_minutes(
    lock_id: str,
    queue_cache_data: Optional[Dict] = None,
    recent_lockages: Optional[List[Dict]] = None,
    direction: str = "upstream",
) -> Dict:
    """
    Estimate the wait time at a lock based on:
      - USACE queue (how many tows are ahead in the same direction)
      - Recent observed lockage durations from history (avg over last 5)
      - Fallback default lockage time

    Returns:
      {
        "wait_minutes": int,        # estimated wait before our vessel enters chamber
        "queue_ahead": int,         # vessels in the queue ahead of us in our direction
        "avg_lockage_minutes": int, # avg duration of a single lockage observed
        "source": str               # "usace+history" | "history" | "default"
      }
    """
    # Pull USACE queue for this lock+direction
    queue_ahead = 0
    if queue_cache_data:
        for _mmsi, info in queue_cache_data.items():
            v_lock = (info.get("lock_id") or info.get("usace_lock") or "").lower()
            v_dir = (info.get("direction") or "").lower()
            if v_lock and lock_id.replace("lock_", "").lower() == v_lock.replace("lock_", "").replace("l", "").lower():
                # Same direction OR unknown direction (count conservatively)
                if direction.lower() in v_dir or "up" in v_dir == "upstream" in direction.lower():
                    queue_ahead += 1
                elif not v_dir:
                    queue_ahead += 1

    # Recent observed durations
    avg_lockage = None
    if recent_lockages:
        durations = [r.get("duration_minutes") for r in recent_lockages if r.get("duration_minutes")]
        if durations:
            avg_lockage = sum(durations) / len(durations)

    if avg_lockage is None:
        avg_lockage = DEFAULT_LOCKAGE_MINUTES
        source = "default"
    elif queue_cache_data:
        source = "usace+history"
    else:
        source = "history"

    wait_minutes = int(round(queue_ahead * avg_lockage))

    return {
        "wait_minutes": wait_minutes,
        "queue_ahead": queue_ahead,
        "avg_lockage_minutes": int(round(avg_lockage)),
        "source": source,
    }


def compute_trip_plan(
    origin_rm: float,
    destination_rm: float,
    etd_iso: str,
    base_speed_knots: float,
    queue_cache_data: Optional[Dict] = None,
    history_by_lock: Optional[Dict[str, List[Dict]]] = None,
) -> Dict:
    """
    Build a per-leg trip plan from origin_rm to destination_rm.

    Args:
      origin_rm, destination_rm: river miles (start and end)
      etd_iso: ISO timestamp of estimated time of departure
      base_speed_knots: planned vessel speed in knots
      queue_cache_data: usace_lock_queue_cache["data"] dict (optional)
      history_by_lock: { lock_id: [lockage_history records] } (optional)
    """
    if base_speed_knots is None or base_speed_knots <= 0:
        base_speed_knots = 8.0  # safe default

    going_down = destination_rm < origin_rm
    direction = "downstream" if going_down else "upstream"
    speed_mph = base_speed_knots * KNOTS_TO_MPH

    try:
        etd = datetime.fromisoformat(etd_iso.replace("Z", "+00:00"))
    except Exception:
        etd = datetime.now(timezone.utc)
    if etd.tzinfo is None:
        etd = etd.replace(tzinfo=timezone.utc)

    crossed = locks_between(origin_rm, destination_rm)

    legs: List[Dict] = []
    cursor_rm = origin_rm
    cursor_time = etd
    total_transit_min = 0.0
    total_wait_min = 0.0

    for lock_id, lock_rm in crossed:
        seg_distance_mi = abs(cursor_rm - lock_rm)
        seg_transit_min = (seg_distance_mi / speed_mph) * 60 if speed_mph > 0 else 0
        arrive_at_lock = cursor_time + timedelta(minutes=seg_transit_min)

        history = history_by_lock.get(lock_id) if history_by_lock else None
        wait_info = estimate_lock_wait_minutes(
            lock_id=lock_id,
            queue_cache_data=queue_cache_data,
            recent_lockages=history,
            direction=direction,
        )

        lockage_time_min = wait_info["avg_lockage_minutes"]
        depart_lock = arrive_at_lock + timedelta(minutes=wait_info["wait_minutes"] + lockage_time_min)

        legs.append({
            "type": "lock",
            "lock_id": lock_id,
            "lock_name": LOCKS[lock_id]["name"],
            "lock_rm": lock_rm,
            "from_rm": cursor_rm,
            "distance_miles": round(seg_distance_mi, 1),
            "transit_minutes": int(round(seg_transit_min)),
            "wait_minutes": wait_info["wait_minutes"],
            "lockage_minutes": lockage_time_min,
            "queue_ahead": wait_info["queue_ahead"],
            "source": wait_info["source"],
            "arrive_at": arrive_at_lock.isoformat(),
            "depart_at": depart_lock.isoformat(),
        })

        total_transit_min += seg_transit_min
        total_wait_min += wait_info["wait_minutes"] + lockage_time_min
        cursor_rm = lock_rm
        cursor_time = depart_lock

    # Final leg to destination
    final_distance = abs(cursor_rm - destination_rm)
    final_transit = (final_distance / speed_mph) * 60 if speed_mph > 0 else 0
    eta = cursor_time + timedelta(minutes=final_transit)

    legs.append({
        "type": "destination",
        "from_rm": cursor_rm,
        "to_rm": destination_rm,
        "distance_miles": round(final_distance, 1),
        "transit_minutes": int(round(final_transit)),
        "arrive_at": eta.isoformat(),
    })

    total_transit_min += final_transit
    total_distance = abs(origin_rm - destination_rm)

    return {
        "origin_rm": origin_rm,
        "destination_rm": destination_rm,
        "direction": direction,
        "base_speed_knots": base_speed_knots,
        "base_speed_mph": round(speed_mph, 1),
        "etd": etd.isoformat(),
        "eta": eta.isoformat(),
        "total_minutes": int(round(total_transit_min + total_wait_min)),
        "total_transit_minutes": int(round(total_transit_min)),
        "total_wait_minutes": int(round(total_wait_min)),
        "total_distance_miles": round(total_distance, 1),
        "lock_count": len(crossed),
        "legs": legs,
    }


def build_lock_queue(
    lock_id: str,
    active_vessels: Dict,
    lookahead_hours: float = 6.0,
) -> Dict:
    """
    Build an ordered queue of vessels approaching a lock.

    Returns vessels with eta_minutes (heading toward lock) and a numeric slot.
    """
    if lock_id not in LOCKS:
        return {"lock_id": lock_id, "error": "unknown lock"}

    lock = LOCKS[lock_id]
    lock_rm = lock["river_mile"]
    horizon_min = lookahead_hours * 60.0

    approaching: List[Dict] = []
    for mmsi, vessel in active_vessels.items():
        if isinstance(vessel, dict):
            rm = vessel.get("river_mile")
            speed = vessel.get("speed", 0) or 0
            heading = (vessel.get("heading_direction") or vessel.get("heading") or "").lower()
            name = vessel.get("name", f"MMSI {mmsi}")
            barge_count = vessel.get("barge_count")
            is_tow = vessel.get("is_tow", False)
        else:
            rm = getattr(vessel, "river_mile", None)
            speed = getattr(vessel, "speed", 0) or 0
            heading = (getattr(vessel, "heading", "") or "").lower()
            name = getattr(vessel, "name", f"MMSI {mmsi}")
            barge_count = getattr(vessel, "barge_count", None)
            is_tow = getattr(vessel, "is_tow", False)

        if rm is None or speed < 0.5:
            continue

        # Heading-toward-lock?
        going_up = heading in ("upstream", "northbound", "upriver")
        going_down = heading in ("downstream", "southbound", "downriver")
        if going_up and rm < lock_rm:
            pass
        elif going_down and rm > lock_rm:
            pass
        else:
            continue

        distance_mi = abs(rm - lock_rm)
        speed_mph = speed * KNOTS_TO_MPH
        if speed_mph < 0.1:
            continue
        eta_min = (distance_mi / speed_mph) * 60
        if eta_min > horizon_min:
            continue

        approaching.append({
            "mmsi": mmsi,
            "name": name,
            "river_mile": rm,
            "speed_knots": round(speed, 1),
            "distance_miles": round(distance_mi, 1),
            "eta_minutes": round(eta_min, 1),
            "direction": "upstream" if going_up else "downstream",
            "is_tow": is_tow,
            "barge_count": barge_count,
        })

    approaching.sort(key=lambda v: v["eta_minutes"])
    for idx, v in enumerate(approaching, start=1):
        v["slot"] = idx

    return {
        "lock_id": lock_id,
        "lock_name": lock["name"],
        "lock_rm": lock_rm,
        "lookahead_hours": lookahead_hours,
        "queue": approaching,
        "queue_size": len(approaching),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def predict_meetings(
    active_vessels: Dict,
    lookahead_hours: float = 4.0,
    min_speed_knots: float = 1.0,
) -> List[Dict]:
    """
    Predict head-on (and overtaking) encounters in the next `lookahead_hours`.

    For each opposing-direction pair, computes the time they pass each other
    on the river-mile axis. Returns soonest first.
    """
    horizon_min = lookahead_hours * 60.0
    movers: List[Dict] = []
    for mmsi, vessel in active_vessels.items():
        if isinstance(vessel, dict):
            rm = vessel.get("river_mile")
            speed = vessel.get("speed", 0) or 0
            heading = (vessel.get("heading_direction") or vessel.get("heading") or "").lower()
            name = vessel.get("name", f"MMSI {mmsi}")
        else:
            rm = getattr(vessel, "river_mile", None)
            speed = getattr(vessel, "speed", 0) or 0
            heading = (getattr(vessel, "heading", "") or "").lower()
            name = getattr(vessel, "name", f"MMSI {mmsi}")

        if rm is None or speed < min_speed_knots:
            continue

        going_up = heading in ("upstream", "northbound", "upriver")
        going_down = heading in ("downstream", "southbound", "downriver")
        if not (going_up or going_down):
            continue

        movers.append({
            "mmsi": str(mmsi),
            "name": name,
            "river_mile": rm,
            "speed_mph": speed * KNOTS_TO_MPH,
            "direction": "upstream" if going_up else "downstream",
        })

    encounters: List[Dict] = []
    for i in range(len(movers)):
        for j in range(i + 1, len(movers)):
            a, b = movers[i], movers[j]
            if a["direction"] == b["direction"]:
                # Overtaking only matters if the faster one is behind in their direction
                same_dir = a["direction"]
                if same_dir == "upstream":
                    lead, trail = (a, b) if a["river_mile"] > b["river_mile"] else (b, a)
                    rel_speed = trail["speed_mph"] - lead["speed_mph"]
                else:
                    lead, trail = (a, b) if a["river_mile"] < b["river_mile"] else (b, a)
                    rel_speed = trail["speed_mph"] - lead["speed_mph"]
                if rel_speed <= 0.1:
                    continue
                gap_mi = abs(lead["river_mile"] - trail["river_mile"])
                t_min = (gap_mi / rel_speed) * 60
                if t_min > horizon_min:
                    continue
                if same_dir == "upstream":
                    meeting_rm = trail["river_mile"] + (trail["speed_mph"] / 60) * t_min
                else:
                    meeting_rm = trail["river_mile"] - (trail["speed_mph"] / 60) * t_min
                encounters.append({
                    "type": "overtake",
                    "vessel_a": {"mmsi": trail["mmsi"], "name": trail["name"]},
                    "vessel_b": {"mmsi": lead["mmsi"], "name": lead["name"]},
                    "meeting_rm": round(meeting_rm, 1),
                    "time_minutes": round(t_min, 1),
                    "direction": same_dir,
                    "advice": f"{trail['name']} overtaking {lead['name']} from astern. Establish 1 whistle (pass on port) or 2 whistle (pass on starboard) per Rule 13.",
                })
            else:
                # Head-on meeting
                up_v = a if a["direction"] == "upstream" else b
                down_v = b if a["direction"] == "upstream" else a
                # Down moves to lower RM, up moves to higher RM. They meet when their RMs coincide.
                if down_v["river_mile"] <= up_v["river_mile"]:
                    # Already passed
                    continue
                closure_speed = up_v["speed_mph"] + down_v["speed_mph"]
                if closure_speed <= 0.1:
                    continue
                gap = down_v["river_mile"] - up_v["river_mile"]
                t_min = (gap / closure_speed) * 60
                if t_min > horizon_min:
                    continue
                meeting_rm = up_v["river_mile"] + (up_v["speed_mph"] / 60) * t_min
                encounters.append({
                    "type": "head_on",
                    "vessel_a": {"mmsi": up_v["mmsi"], "name": up_v["name"], "direction": "upstream"},
                    "vessel_b": {"mmsi": down_v["mmsi"], "name": down_v["name"], "direction": "downstream"},
                    "meeting_rm": round(meeting_rm, 1),
                    "time_minutes": round(t_min, 1),
                    "advice": "Head-on meeting. Standard convention on Upper Miss: downbound vessel has right-of-way (current). Establish passing arrangement on VHF Ch 13.",
                })

    encounters.sort(key=lambda e: e["time_minutes"])
    return encounters


def forecast_bottlenecks(
    active_vessels: Dict,
    queue_cache_data: Optional[Dict] = None,
    history_by_lock: Optional[Dict[str, List[Dict]]] = None,
    hours: float = 6.0,
) -> List[Dict]:
    """
    Forecast lock congestion in the next `hours` window.

    For each lock, count arriving vessels (by ETA from current AIS speeds)
    plus current USACE queue, then estimate cumulative wait.
    """
    forecast: List[Dict] = []
    for lock_id, lock in LOCKS.items():
        # Approaching vessels in window
        queue = build_lock_queue(lock_id, active_vessels, lookahead_hours=hours)["queue"]
        arrivals_up = sum(1 for v in queue if v["direction"] == "upstream")
        arrivals_down = sum(1 for v in queue if v["direction"] == "downstream")
        arrivals_total = arrivals_up + arrivals_down

        # USACE queue currently waiting at this lock
        current_queue = 0
        if queue_cache_data:
            for _m, info in queue_cache_data.items():
                v_lock = (info.get("lock_id") or info.get("usace_lock") or "").lower()
                if not v_lock:
                    continue
                norm = v_lock.replace("lock_", "").replace("l", "").lower()
                lock_norm = lock_id.replace("lock_", "").lower()
                if norm == lock_norm:
                    current_queue += 1

        history = history_by_lock.get(lock_id) if history_by_lock else None
        avg_lockage = DEFAULT_LOCKAGE_MINUTES
        if history:
            durations = [r.get("duration_minutes") for r in history if r.get("duration_minutes")]
            if durations:
                avg_lockage = sum(durations) / len(durations)

        # Estimated congestion (cumulative cycle time / window)
        cumulative_min = (current_queue + arrivals_total) * avg_lockage
        utilization = cumulative_min / (hours * 60.0)

        if utilization >= 0.85:
            severity = SEVERITY_HIGH
        elif utilization >= 0.55:
            severity = SEVERITY_MODERATE
        else:
            severity = SEVERITY_LOW

        forecast.append({
            "lock_id": lock_id,
            "lock_name": lock["name"],
            "lock_rm": lock["river_mile"],
            "current_queue": current_queue,
            "arrivals_in_window": arrivals_total,
            "arrivals_upstream": arrivals_up,
            "arrivals_downstream": arrivals_down,
            "avg_lockage_minutes": int(round(avg_lockage)),
            "cumulative_demand_minutes": int(round(cumulative_min)),
            "utilization": round(utilization, 2),
            "severity": severity,
        })

    forecast.sort(key=lambda x: (-x["utilization"], -x["arrivals_in_window"]))
    return forecast
