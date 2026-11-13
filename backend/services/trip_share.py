"""
"Share my trip": a link family and friends open without signing in.

A boater creates a share for one of their own boats (POST /api/share); the
link /s/<token> then shows where the boat is and when it should arrive, until
it expires (1-72 h) or is revoked. Doubles as a float plan.

Privacy: the public payload is built from an allow-list here
(public_payload). It never carries the MMSI, the owner's email or user id,
or anything about other boats (the trip plan's competing tows are dropped).

Pure logic only (no DB, no server imports) so it can be unit tested.
"""
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

DEFAULT_HOURS = 24
MIN_HOURS, MAX_HOURS = 1, 72
MAX_ACTIVE_PER_USER = 10
KNOTS_TO_MPH = 1.15078

# Same thresholds as lock_board (AT_LOCK_MI / SLOW_KNOTS), repeated so this
# module stays import-free; tests pin them together.
AT_LOCK_MI = 0.25
SLOW_KNOTS = 2.0
STOPPED_KNOTS = 0.5


def new_token() -> str:
    return secrets.token_urlsafe(16)


def clamp_hours(hours) -> int:
    try:
        h = int(round(float(hours)))
    except (TypeError, ValueError):
        return DEFAULT_HOURS
    return max(MIN_HOURS, min(MAX_HOURS, h))


def _utc(dt) -> Optional[datetime]:
    """Mongo hands back naive UTC datetimes; make them comparable."""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def new_share(mmsi: str, user_id: str, hours=None, destination_rm=None, boat_name=None,
              now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    dest = None
    try:
        if destination_rm is not None:
            dest = round(float(destination_rm), 1)
    except (TypeError, ValueError):
        dest = None
    return {
        "token": new_token(),
        "mmsi": str(mmsi).strip(),
        "user_id": user_id,
        "boat_name": (boat_name or "").strip()[:60] or None,
        "destination_rm": dest,
        "created_at": now,
        "expires_at": now + timedelta(hours=clamp_hours(hours if hours is not None else DEFAULT_HOURS)),
        "revoked": False,
    }


def is_active(doc: Optional[dict], now: Optional[datetime] = None) -> bool:
    """Unknown, revoked or expired shares are all just 'not found'."""
    if not doc or doc.get("revoked"):
        return False
    exp = _utc(doc.get("expires_at"))
    if exp is None:
        return False
    return exp > (now or datetime.now(timezone.utc))


def owner_view(doc: dict) -> dict:
    """A share as its owner sees it in GET /api/share (no user_id)."""
    def iso(v):
        v = _utc(v)
        return v.isoformat() if v else None
    return {
        "token": doc.get("token"),
        "mmsi": doc.get("mmsi"),
        "boat_name": doc.get("boat_name"),
        "destination_rm": doc.get("destination_rm"),
        "created_at": iso(doc.get("created_at")),
        "expires_at": iso(doc.get("expires_at")),
    }


def direction_word(heading) -> Optional[str]:
    """River miles grow going north on the Upper Mississippi."""
    h = str(heading or "").lower()
    if h in ("northbound", "upbound", "upriver"):
        return "upriver"
    if h in ("southbound", "downbound", "downriver"):
        return "downriver"
    return None


def lock_at(river_mile, locks: Iterable[Tuple[str, float]]) -> Optional[str]:
    """Name of the lock the boat is at (within AT_LOCK_MI), else None.
    locks: (name, river_mile) pairs."""
    if river_mile is None:
        return None
    best = None
    for name, rm in locks:
        if rm is None:
            continue
        d = abs(float(rm) - float(river_mile))
        if d <= AT_LOCK_MI and (best is None or d < best[0]):
            best = (d, name)
    return best[1] if best else None


def boat_status(speed_knots, at_lock_name: Optional[str]) -> str:
    """underway / stopped / at_lock."""
    s = float(speed_knots or 0)
    if at_lock_name and s < SLOW_KNOTS:
        return "at_lock"
    return "underway" if s >= STOPPED_KNOTS else "stopped"


def destination_eta_minutes(user_rm, speed_mph, heading, destination_rm,
                            legs: Optional[List[dict]] = None) -> Optional[float]:
    """Minutes to the destination: through the locks on the way (their waits
    and lockages, from the trip plan), then the open river past the last one.
    None when stopped, or heading away from the destination."""
    if user_rm is None or destination_rm is None or not speed_mph or speed_mph <= 0:
        return None
    word = direction_word(heading)
    delta = float(destination_rm) - float(user_rm)
    if abs(delta) < 0.05:
        return 0.0
    if (delta > 0 and word != "upriver") or (delta < 0 and word != "downriver"):
        return None
    start_min, start_rm = 0.0, float(user_rm)
    for leg in legs or []:
        rm = leg.get("lock_rm")
        if rm is None:
            continue
        between = min(user_rm, destination_rm) <= rm <= max(user_rm, destination_rm)
        if not between:
            continue
        t = leg.get("depart_eta_minutes")
        if t is None:
            t = leg.get("user_eta_minutes")
        if t is None:
            continue
        start_min, start_rm = float(t), float(rm)
    return round(start_min + abs(float(destination_rm) - start_rm) / speed_mph * 60.0, 1)


def _num(v, nd=1):
    try:
        return None if v is None else round(float(v), nd)
    except (TypeError, ValueError):
        return None


def public_payload(boat_name: Optional[str], vessel: Optional[dict], plan: Optional[dict],
                   locks: Iterable[Tuple[str, float]], destination_rm=None,
                   now: Optional[datetime] = None, expires_at=None) -> dict:
    """Everything /api/public/share/{token} returns, and nothing else.

    vessel: prepare_vessel_for_output() of the shared boat (or None when it
    has no position); plan: the trip-plan response (or None)."""
    now = now or datetime.now(timezone.utc)
    v = vessel or {}
    rm = _num(v.get("river_mile"))
    knots = float(v.get("speed") or 0)
    mph = round(knots * KNOTS_TO_MPH, 1)
    heading_dir = (plan or {}).get("heading") or v.get("heading_direction") or v.get("heading")
    # Compass heading in degrees: AIS true heading, else course over ground
    # (511 / 360 mean "not available" in AIS).
    course = None
    for key in ("heading_true", "course"):
        c = v.get(key)
        if isinstance(c, (int, float)) and 0 <= c < 360:
            course = c
            break
    lock_name = lock_at(rm, locks)
    has_pos = vessel is not None and v.get("lat") is not None and v.get("lon") is not None
    updated = _utc(v.get("last_ais_checkin") or v.get("timestamp"))

    out = {
        "boat_name": boat_name or v.get("name") or "Boat",
        "has_position": has_pos,
        "river_mile": rm,
        "lat": _num(v.get("lat"), 5) if has_pos else None,
        "lon": _num(v.get("lon"), 5) if has_pos else None,
        "speed_mph": mph if has_pos else None,
        "heading": _num(course, 0) if has_pos else None,
        "direction": direction_word(heading_dir) if has_pos and knots >= STOPPED_KNOTS else None,
        "updated_at": updated.isoformat() if updated else None,
        "status": boat_status(knots, lock_name) if has_pos else "unknown",
        "at_lock": lock_name if has_pos and knots < SLOW_KNOTS else None,
        "next_lock": None,
        "destination": None,
        "expires_at": (_utc(expires_at).isoformat() if _utc(expires_at) else None),
        "generated_at": now.isoformat(),
    }

    legs = (plan or {}).get("legs") or []
    if has_pos and legs:
        leg = legs[0]
        eta = leg.get("user_eta_minutes")
        wait_range = leg.get("expected_wait_range_minutes")
        out["next_lock"] = {
            "name": leg.get("lock_name"),
            "river_mile": _num(leg.get("lock_rm")),
            "eta_minutes": _num(eta, 0),
            "eta_at": (now + timedelta(minutes=float(eta))).isoformat() if eta is not None else None,
            "wait_minutes": _num(leg.get("expected_wait_minutes"), 0),
            "wait_range_minutes": ([_num(x, 0) for x in wait_range][:2]
                                   if isinstance(wait_range, (list, tuple)) and len(wait_range) >= 2 else None),
        }

    if destination_rm is not None:
        dest_min = destination_eta_minutes(rm, mph, heading_dir, destination_rm, legs) if has_pos else None
        out["destination"] = {
            "river_mile": _num(destination_rm),
            "eta_minutes": _num(dest_min, 0),
            "eta_at": (now + timedelta(minutes=dest_min)).isoformat() if dest_min is not None else None,
        }
    return out


class RateLimiter:
    """Sliding window, per key, in memory (one process). Good enough to stop a
    shared link being hammered; not a security boundary."""

    def __init__(self, limit: int = 30, window_s: float = 60.0, max_keys: int = 5000):
        self.limit, self.window, self.max_keys = limit, window_s, max_keys
        self._hits: Dict[str, List[float]] = {}

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        cutoff = now - self.window
        hits = [t for t in self._hits.get(key, []) if t > cutoff]
        if len(hits) >= self.limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        if len(self._hits) > self.max_keys:
            for k in [k for k, ts in self._hits.items() if not ts or ts[-1] <= cutoff]:
                self._hits.pop(k, None)
        return True
