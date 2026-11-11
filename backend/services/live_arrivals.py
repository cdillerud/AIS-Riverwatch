"""
Live AIS positions combined with USACE-based predictions, for "wait when you
get there".

transits.predicted_arrivals() guesses who will reach a lock from each tow's
last USACE lockage and typical travel times. Many of those tows tie off
between locks, which makes the guesses noisy. When the AIS feed covers the
stretch, it has better information:

- A boat under way toward the lock (with no lock in between) is a real
  arrival. Its ETA is distance / current speed and it counts fully.
- A predicted boat that AIS shows is not under way toward the lock is
  dropped. It has tied off, turned, or is still somewhere else.
- A predicted boat that AIS shows stopped within a few miles of the lock is
  about to check in, so it counts as arriving now.
- Pleasure craft (AIS ship type 36/37) and the user's own boat never count.
- Boats USACE already lists at the lock are in the queue itself, so they are
  skipped here (matched by MMSI or name: USACE sometimes has an old MMSI).

Predicted boats AIS hasn't seen are kept: the receiver may not cover them.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

KNOTS_TO_MPH = 1.15078
MOVING_KNOTS = 1.5
MAX_RANGE_MI = 25.0       # beyond this an AIS ETA is no better than the prediction
NEAR_LOCK_MI = 3.0        # tows wait 1-3 mi off the lock
LIVE_MAX_AGE = timedelta(minutes=10)
PLEASURE_TYPES = (36, 37)


def _norm_name(x) -> str:
    return "".join(ch for ch in str(x or "").upper() if ch.isalnum())


def _aware(t):
    if isinstance(t, str):
        t = datetime.fromisoformat(t)
    if isinstance(t, datetime) and t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


def _direction(heading: Optional[str]) -> Optional[str]:
    if heading in ("northbound", "upbound", "upriver"):
        return "upbound"
    if heading in ("southbound", "downbound", "downriver"):
        return "downbound"
    return None


def merge_live_arrivals(lock_id: str, lock_rms: Dict[str, float], predicted: List[dict],
                        live: Iterable[dict], now: datetime, own_mmsi: Optional[str] = None,
                        at_lock: Iterable[str] = (), barges_by_mmsi: Optional[Dict[str, int]] = None) -> List[dict]:
    """Arrivals for `lock_id`: predictions corrected by AIS, plus AIS-only boats.

    `live` items: {mmsi, name, river_mile, speed (knots), heading, ship_type, timestamp}.
    Every returned item has `eta` (datetime), `probability`, and `source`
    ("ais", or "usace_prediction" for a guess AIS hasn't confirmed)."""
    lock_rm = lock_rms[lock_id]
    others = [rm for lid, rm in lock_rms.items() if lid != lock_id]
    at_lock = {str(x) for x in at_lock if x}
    at_lock_names = {_norm_name(x) for x in at_lock} - {""}
    barges_by_mmsi = barges_by_mmsi or {}
    own = str(own_mmsi) if own_mmsi else None

    fresh: Dict[str, dict] = {}
    for v in live:
        mmsi = str(v.get("mmsi") or "")
        ts = _aware(v.get("timestamp"))
        rm = v.get("river_mile")
        if not mmsi or mmsi == own or rm is None or (ts and now - ts > LIVE_MAX_AGE):
            continue
        fresh[mmsi] = v

    def heading_here(v) -> Optional[dict]:
        """ETA info if the boat is under way toward this lock with no lock in between."""
        rm = float(v["river_mile"])
        knots = float(v.get("speed") or 0)
        d = _direction(v.get("heading"))
        if knots < MOVING_KNOTS or d is None:
            return None
        if d == "upbound" and not rm < lock_rm:
            return None
        if d == "downbound" and not rm > lock_rm:
            return None
        lo, hi = sorted((rm, lock_rm))
        if any(lo < o < hi for o in others):
            return None
        dist = abs(lock_rm - rm)
        if dist > MAX_RANGE_MI:
            return None
        return {"direction": d, "distance_mi": round(dist, 1),
                "eta": now + timedelta(hours=dist / (knots * KNOTS_TO_MPH))}

    out: List[dict] = []
    used = set()
    for p in predicted:
        mmsi = str(p.get("mmsi") or "")
        v = fresh.get(mmsi) if mmsi else None
        if v is None:
            out.append({**p, "source": "usace_prediction"})
            continue
        used.add(mmsi)
        h = heading_here(v)
        if h:
            out.append({**p, **h, "probability": 1.0, "source": "ais"})
        elif abs(float(v["river_mile"]) - lock_rm) <= NEAR_LOCK_MI:
            out.append({**p, "eta": now, "probability": 1.0, "source": "ais",
                        "distance_mi": round(abs(float(v["river_mile"]) - lock_rm), 1)})
        # else: AIS shows it isn't coming yet - drop the guess

    for mmsi, v in fresh.items():
        if (mmsi in used or mmsi in at_lock or _norm_name(v.get("name")) in at_lock_names
                or v.get("ship_type") in PLEASURE_TYPES):
            continue
        h = heading_here(v)
        if not h:
            continue
        out.append({"vessel_name": v.get("name"), "mmsi": mmsi, "barges": barges_by_mmsi.get(mmsi),
                    "probability": 1.0, "source": "ais", **h})
    out.sort(key=lambda a: a["eta"])
    return out
