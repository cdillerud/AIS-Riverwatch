"""
Where a user's own boat sits when nothing live says otherwise.

A boat can have a home berth (its slip) on the account. When it isn't being
simulated and hasn't reported a real position (phone GPS, manual entry, AIS)
recently, it is shown parked there, stopped. A real position newer than
STALE_AFTER wins; anything older is "back at the slip".

Before this, page load put the boat at its last saved fix with that fix's
speed - e.g. REBOOT frozen at RM 808 "doing 6 mph" from a days-old update.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

STALE_AFTER = timedelta(hours=6)


def _aware(ts) -> Optional[datetime]:
    if not ts:
        return None
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def position_to_show(vessel_info: dict, now: datetime) -> Tuple[Optional[dict], str]:
    """(position, source) for a boat from the account: source is "last"
    (recent real fix, as reported), "home" (parked at its berth) or "none".
    A "last" fix that is stale but has no berth to fall back on is returned
    stopped (speed 0), since it isn't moving now as far as we know."""
    last = vessel_info.get("last_position") or {}
    home = vessel_info.get("home_berth") or {}
    has_last = last.get("lat") is not None and last.get("lon") is not None
    has_home = home.get("lat") is not None and home.get("lon") is not None
    seen = _aware(last.get("last_position_update"))
    fresh = has_last and seen is not None and now - seen <= STALE_AFTER

    if fresh:
        return dict(last), "last"
    if has_home:
        return {"lat": home["lat"], "lon": home["lon"], "river_mile": home.get("river_mile"),
                "speed": 0.0, "course": 0.0, "heading_direction": "stationary"}, "home"
    if has_last:
        return {**last, "speed": 0.0, "heading_direction": "stationary"}, "last"
    return None, "none"
