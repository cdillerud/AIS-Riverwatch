"""
Lock-to-lock transit times learned from USACE lockage history, and predicted
arrivals built on them.

USACE records each vessel's lockage at every lock it passes (with MMSI or
vessel number). Pairing a vessel's exit from one lock with its arrival at the
next lock in the same direction gives real transit times per leg and
direction. A vessel that has just left lock A heading toward lock B is then
expected at B around exit + median transit, before any AIS sees it.

Locks with no USACE data (5A) are skipped, so 5 -> 6 is one leg.
"""
import statistics
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

MAX_TRANSIT_HOURS = 48.0     # longer gaps are layovers, not transits
MIN_SAMPLES = 3
MIN_SIZE_SAMPLES = 5         # per leg x tow-size class before using it


def size_class(barges) -> str:
    """Tow size bucket: bigger tows run slower (backtest: 0.78 h -> 0.72 h median error)."""
    b = barges or 0
    return "light" if b <= 3 else ("medium" if b <= 9 else "large")


def lock_order(locks: Dict[str, dict], skip: Iterable[str] = ("lock_5a",)) -> List[str]:
    """Lock ids north to south (descending river mile)."""
    skip = set(skip)
    return [k for k in sorted(locks, key=lambda k: -locks[k]["river_mile"]) if k not in skip]


def next_lock(order: List[str], lock_id: str, direction: str) -> Optional[str]:
    if lock_id not in order:
        return None
    i = order.index(lock_id)
    j = i + 1 if direction == "downbound" else i - 1
    return order[j] if 0 <= j < len(order) else None


def previous_lock(order: List[str], lock_id: str, direction: str) -> Optional[str]:
    """The lock a vessel heading `direction` passes just before `lock_id`."""
    return next_lock(order, lock_id, "upbound" if direction == "downbound" else "downbound")


def _vessel_key(r: dict) -> Optional[str]:
    return r.get("mmsi") or r.get("usace_vessel_no") or None


def transit_samples(records: Iterable[dict], order: List[str]) -> Dict[tuple, List[float]]:
    """{(from_lock, to_lock, direction): [hours]} plus the same keyed with a
    fourth element, the tow-size class, from completed lockages."""
    by_vessel: Dict[str, List[dict]] = {}
    for r in records:
        if r.get("is_recreational") or r.get("in_progress"):
            continue
        key = _vessel_key(r)
        if key and r.get("exit_time") and r.get("arrival_time"):
            by_vessel.setdefault(key, []).append(r)
    legs: Dict[Tuple[str, str, str], List[float]] = {}
    for rows in by_vessel.values():
        rows.sort(key=lambda r: r["exit_time"])
        for a, b in zip(rows, rows[1:]):
            d = a.get("direction")
            if d not in ("upbound", "downbound") or b.get("direction") != d:
                continue
            if next_lock(order, a["lock_id"], d) != b["lock_id"]:
                continue
            hours = (b["arrival_time"] - a["exit_time"]).total_seconds() / 3600
            if 0 < hours < MAX_TRANSIT_HOURS:
                legs.setdefault((a["lock_id"], b["lock_id"], d), []).append(hours)
                legs.setdefault((a["lock_id"], b["lock_id"], d, size_class(a.get("barge_count"))), []).append(hours)
    return legs


def transit_stats(samples: Dict[tuple, List[float]]) -> Dict[tuple, dict]:
    out = {}
    for key, hours in samples.items():
        if len(hours) < (MIN_SIZE_SAMPLES if len(key) == 4 else MIN_SAMPLES):
            continue
        h = sorted(hours)
        out[key] = {
            "median_h": statistics.median(h),
            "p25_h": h[len(h) // 4],
            "p75_h": h[(3 * len(h)) // 4],
            "n": len(h),
        }
    return out


def predicted_arrivals(lock_id: str, order: List[str], stats: Dict[Tuple[str, str, str], dict],
                       recent: Iterable[dict], present: Iterable[str], now: datetime,
                       lookback_hours: float = 36.0) -> List[dict]:
    """Vessels expected at `lock_id`: their latest USACE lockage was at the
    previous lock in their direction of travel, recently enough that they
    should still be on the way, and they aren't at `lock_id` yet.

    `recent` = completed lockages (any lock) in the last `lookback_hours`.
    `present` = vessel keys already in `lock_id`'s queue or locked through it.
    """
    present = set(present)
    latest: Dict[str, dict] = {}
    for r in recent:
        key = _vessel_key(r)
        if not key or r.get("is_recreational"):
            continue
        if key not in latest or r["exit_time"] > latest[key]["exit_time"]:
            latest[key] = r
    out = []
    for key, r in latest.items():
        d = r.get("direction")
        if d not in ("upbound", "downbound") or key in present:
            continue
        if next_lock(order, r["lock_id"], d) != lock_id:
            continue
        s = stats.get((r["lock_id"], lock_id, d, size_class(r.get("barge_count")))) or stats.get((r["lock_id"], lock_id, d))
        if not s:
            continue
        exit_time = r["exit_time"] if r["exit_time"].tzinfo else r["exit_time"].replace(tzinfo=timezone.utc)
        eta = exit_time + timedelta(hours=s["median_h"])
        latest_eta = exit_time + timedelta(hours=s["p75_h"])
        # Well past the slow end of normal: probably tied off at a fleeting
        # area or turned around - don't keep predicting it.
        if now > latest_eta + timedelta(hours=max(2.0, s["p75_h"] - s["median_h"])):
            continue
        if now - exit_time > timedelta(hours=lookback_hours):
            continue
        out.append({
            "vessel_name": r.get("vessel_name"),
            "mmsi": r.get("mmsi"),
            "direction": d,
            "barges": r.get("barge_count"),
            "from_lock": r["lock_id"],
            "left_at": exit_time,
            "eta": eta,
            "eta_earliest": exit_time + timedelta(hours=s["p25_h"]),
            "eta_latest": latest_eta,
            "overdue": now > eta,
            "transit_samples": s["n"],
            # Share of the typical transit already elapsed (0..1): used to place an
            # estimated position between the two locks.
            "progress": max(0.0, min(0.97, (now - exit_time).total_seconds() / 3600 / s["median_h"])),
        })
    out.sort(key=lambda a: a["eta"])
    return out
