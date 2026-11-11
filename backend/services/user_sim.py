"""
Simulated movement of a user's own boat (Settings > Simulation, Quick Test).

One step per tick: move along the river at the set speed; when the boat
reaches a lock, hold it there stopped for `lock_dwell_minutes` (wait plus
lockage) before it carries on - so lock arrival, "at lock" and passage logic
can be tested end to end instead of the boat gliding through at 8 knots.
lock_dwell_minutes = 0 turns the stops off.
"""
from datetime import datetime, timedelta
from typing import Iterable, Optional

KNOTS_TO_MPH = 1.15078
DEFAULT_LOCK_DWELL_MINUTES = 20.0
RIVER_MIN, RIVER_MAX = 180.0, 860.0


def _parse(ts) -> Optional[datetime]:
    if ts is None or isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(ts)


def step(sim: dict, lock_miles: Iterable[float], seconds: float, now: datetime) -> dict:
    """Advance `sim` (mutated and returned) by `seconds`."""
    if not sim.get("enabled"):
        return sim

    hold_until = _parse(sim.get("hold_until"))
    if hold_until is not None:
        if now < hold_until:
            sim["holding"] = True
            return sim
        sim["hold_until"] = None
    sim["holding"] = False

    speed_knots = float(sim.get("speed_knots") or 0)
    if speed_knots < 0.1:
        return sim

    rm = float(sim.get("river_mile", 815.0))
    down = sim.get("heading", "southbound") == "southbound"
    moved = speed_knots * KNOTS_TO_MPH * seconds / 3600.0
    new_rm = rm - moved if down else rm + moved
    new_rm = max(RIVER_MIN, min(RIVER_MAX, new_rm))

    dwell = sim.get("lock_dwell_minutes", DEFAULT_LOCK_DWELL_MINUTES)
    dwell = DEFAULT_LOCK_DWELL_MINUTES if dwell is None else float(dwell)
    if dwell > 0:
        last_lock = sim.get("last_lock_mile")
        # Locks strictly ahead of where we were and reached this tick.
        crossed = [m for m in lock_miles
                   if (new_rm <= m < rm if down else rm < m <= new_rm) and m != last_lock]
        if crossed:
            lock_mile = max(crossed) if down else min(crossed)  # the first one reached
            sim["river_mile"] = lock_mile
            sim["last_lock_mile"] = lock_mile
            sim["hold_until"] = (now + timedelta(minutes=dwell)).isoformat()
            sim["holding"] = True
            return sim

    sim["river_mile"] = new_rm
    return sim
