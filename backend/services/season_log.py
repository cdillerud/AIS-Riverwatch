"""
Season log for a user's own boat: miles, hours under way, days out, locks
passed and time spent at each lock - from a light track recorded while the
boat moves (a point per ~0.25 river mile, or every 30 min when still).
Simulated positions are never recorded.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Sequence, Tuple

MIN_MILES = 0.25
MAX_QUIET = timedelta(minutes=30)
GAP = timedelta(minutes=45)          # longer silence = the track is broken (phone off)
LOCK_GAP = timedelta(hours=6)        # a lock passage can take hours of waiting
LOCK_RADIUS_MI = 0.6
UNDERWAY_MPH = 2.0


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def due(last: Optional[Tuple[datetime, float]], rm: float, now: datetime) -> bool:
    """Record a point? last = (time, river mile) of the previous point."""
    if last is None:
        return True
    t, last_rm = last
    return abs(rm - last_rm) >= MIN_MILES or now - _utc(t) >= MAX_QUIET


def _central_date(t: datetime):
    return (_utc(t) - timedelta(hours=6)).date()


def summarize(points: Sequence[dict], locks: Iterable[Tuple[str, float, str]]) -> dict:
    """points: [{t, rm}] in time order. locks: (lock_id, river_mile, name)."""
    pts = [p for p in points if p.get("rm") is not None]
    pts.sort(key=lambda p: _utc(p["t"]))
    miles, underway_s, days = 0.0, 0.0, set()
    for a, b in zip(pts, pts[1:]):
        dt = _utc(b["t"]) - _utc(a["t"])
        if dt <= timedelta(0) or dt > GAP:
            continue
        d = abs(b["rm"] - a["rm"])
        mph = d / (dt.total_seconds() / 3600)
        if mph > 40:            # a jump (bad fix), not travel
            continue
        miles += d
        if mph >= UNDERWAY_MPH:
            underway_s += dt.total_seconds()
            days.add(_central_date(b["t"]))
    passages = []
    for lock_id, lrm, name in locks:
        i = 0
        while i < len(pts) - 1:
            a, b = pts[i], pts[i + 1]
            lo, hi = sorted((a["rm"], b["rm"]))
            span = _utc(b["t"]) - _utc(a["t"])
            plausible = timedelta(0) < span <= LOCK_GAP and (hi - lo) / (span.total_seconds() / 3600) <= 40
            if lo < lrm < hi and plausible:
                # time near the lock around this crossing
                s = i
                while s > 0 and abs(pts[s - 1]["rm"] - lrm) <= LOCK_RADIUS_MI:
                    s -= 1
                e = i + 1
                while e < len(pts) - 1 and abs(pts[e + 1]["rm"] - lrm) <= LOCK_RADIUS_MI:
                    e += 1
                start = pts[s] if abs(pts[s]["rm"] - lrm) <= LOCK_RADIUS_MI else a
                end = pts[e] if abs(pts[e]["rm"] - lrm) <= LOCK_RADIUS_MI else b
                minutes = max(0, int((_utc(end["t"]) - _utc(start["t"])).total_seconds() // 60))
                passages.append({"lock_id": lock_id, "name": name, "at": _utc(b["t"]).isoformat(),
                                 "direction": "upbound" if b["rm"] > a["rm"] else "downbound",
                                 "minutes_at_lock": minutes})
                i = e + 1
            else:
                i += 1
    passages.sort(key=lambda p: p["at"], reverse=True)
    return {
        "miles": round(miles, 1),
        "hours_underway": round(underway_s / 3600, 1),
        "days_out": len(days),
        "locks_passed": len(passages),
        "minutes_at_locks": sum(p["minutes_at_lock"] for p in passages),
        "passages": passages[:30],
        "first": _utc(pts[0]["t"]).isoformat() if pts else None,
        "last": _utc(pts[-1]["t"]).isoformat() if pts else None,
    }
