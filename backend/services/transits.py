"""
Lock-to-lock transit times learned from USACE lockage history, and predicted
arrivals built on them.

USACE records each vessel's lockage at every lock it passes (with MMSI or
vessel number). Pairing a vessel's exit from one lock with its arrival at the
next lock in the same direction gives real transit times per leg and
direction. A vessel that has just left lock A heading toward lock B is then
expected at B around exit + median transit, before any AIS sees it.

Locks with no USACE data can be skipped (skip=...); 5A is included since its code ("55") was found.

Tested and not used (2026-11-10): river flow. Daily USGS discharge at five
gauges vs 3,646 transits: correlation ~+0.01 both directions (downbound ~4%
faster at high flow). Late-fall flows were moderate; re-check at spring
high water.
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


def lock_order(locks: Dict[str, dict], skip: Iterable[str] = ()) -> List[str]:
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


def dwell_stats(records: Iterable[dict]) -> Dict[tuple, dict]:
    """Time a tow typically spends at a lock (arrival -> exit: wait + lockage),
    keyed ("dwell", lock_id, direction)."""
    by = {}
    for r in records:
        if r.get("is_recreational") or r.get("in_progress") or not (r.get("arrival_time") and r.get("exit_time")):
            continue
        h = (r["exit_time"] - r["arrival_time"]).total_seconds() / 3600
        if 0 <= h < MAX_TRANSIT_HOURS:
            by.setdefault(("dwell", r["lock_id"], r.get("direction")), []).append(h)
    out = {}
    for key, hours in by.items():
        if len(hours) >= MIN_SAMPLES:
            h = sorted(hours)
            out[key] = {"median_h": statistics.median(h), "p25_h": h[len(h) // 4], "p75_h": h[(3 * len(h)) // 4], "n": len(h)}
    return out


MIN_CONTINUE_PROBABILITY = 0.25


def continuation_stats(records: Iterable[dict], order: List[str], data_end: Optional[datetime] = None,
                       window_hours: float = MAX_TRANSIT_HOURS) -> Dict[tuple, dict]:
    """How often a tow leaving lock A in direction d reaches the next lock B
    (same direction, within `window_hours`), keyed ("cont", A, B, d).

    Varies a lot by reach (30 days to 2026-11-10: 82% overall; Lock 2 -> 1
    upbound 0%, Mel Price -> 25 upbound 47%, Lock 14 -> 13 upbound 49% -
    harbors and fleeting areas absorb tows), so predicted arrivals carry it as
    a probability instead of assuming every tow continues."""
    by_vessel: Dict[str, List[dict]] = {}
    for r in records:
        if r.get("is_recreational") or r.get("in_progress"):
            continue
        key = _vessel_key(r)
        if key and r.get("exit_time"):
            by_vessel.setdefault(key, []).append(r)
    if data_end is None:
        data_end = max((r["exit_time"] for rows in by_vessel.values() for r in rows), default=None)
    if data_end is None:
        return {}
    counts: Dict[tuple, List[int]] = {}
    window = timedelta(hours=window_hours)
    for rows in by_vessel.values():
        rows.sort(key=lambda r: r["exit_time"])
        for i, a in enumerate(rows):
            d = a.get("direction")
            if d not in ("upbound", "downbound") or a["exit_time"] > data_end - window:
                continue  # too recent to know whether it continued
            b = next_lock(order, a["lock_id"], d)
            if not b:
                continue
            nxt = rows[i + 1] if i + 1 < len(rows) else None
            went = bool(nxt and nxt["lock_id"] == b and nxt.get("direction") == d
                        and nxt.get("arrival_time") and nxt["arrival_time"] - a["exit_time"] < window)
            c = counts.setdefault(("cont", a["lock_id"], b, d), [0, 0])
            c[0] += went
            c[1] += 1
    return {k: {"p": c[0] / c[1], "n": c[1]} for k, c in counts.items() if c[1] >= 10}


def _leg(stats, a, b, d, barges):
    return stats.get((a, b, d, size_class(barges))) or stats.get((a, b, d))


def predicted_arrivals(lock_id: str, order: List[str], stats: Dict[tuple, dict],
                       recent: Iterable[dict], present: Iterable[str], now: datetime,
                       lookback_hours: float = 36.0, max_hops: int = 1) -> List[dict]:
    """Vessels expected at `lock_id`, from their latest USACE lockage.

    One hop: last lockage at the previous lock in their direction.
    Two hops: last lockage one lock further back; ETA adds the typical time at
    the lock in between (wait + lockage, ("dwell", lock, direction) in
    `stats`) and the second leg. Vessels already at `lock_id` (`present`),
    long overdue, or older than `lookback_hours` are skipped.

    `segment_from`/`segment_to`/`segment_progress` place an estimated
    position along the leg the vessel is on now.

    Default is one hop. Backtested 2026-11-10 (scripts/backtest_arrival_waits.py,
    MAX_HOPS=2): two hops made tow wait predictions much worse (MAE ~92 vs
    ~67 min, biased high) - many tows end their trip or tie off between
    locks, so counting them two locks out adds arrivals that never come."""
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
        a = r["lock_id"]
        b = next_lock(order, a, d)
        if b is None:
            continue
        hops = 1 if b == lock_id else (2 if max_hops >= 2 and next_lock(order, b, d) == lock_id else 0)
        if not hops:
            continue
        barges = r.get("barge_count")
        legs = [_leg(stats, a, b, d, barges)]
        if hops == 2:
            legs += [stats.get(("dwell", b, d)), _leg(stats, b, lock_id, d, barges)]
        if not all(legs):
            continue
        probability = stats.get(("cont", a, b, d), {}).get("p", 1.0)
        if hops == 2:
            probability *= stats.get(("cont", b, lock_id, d), {}).get("p", 1.0)
        if probability < MIN_CONTINUE_PROBABILITY:
            continue
        exit_time = r["exit_time"] if r["exit_time"].tzinfo else r["exit_time"].replace(tzinfo=timezone.utc)
        if now - exit_time > timedelta(hours=lookback_hours):
            continue
        median_h = sum(x["median_h"] for x in legs)
        p25_h = sum(x["p25_h"] for x in legs)
        p75_h = sum(x["p75_h"] for x in legs)
        eta = exit_time + timedelta(hours=median_h)
        latest_eta = exit_time + timedelta(hours=p75_h)
        # Well past the slow end of normal: probably tied off at a fleeting
        # area or turned around - don't keep predicting it.
        if now > latest_eta + timedelta(hours=max(2.0, p75_h - median_h)):
            continue
        elapsed = (now - exit_time).total_seconds() / 3600
        if hops == 1 or elapsed < legs[0]["median_h"]:
            seg = (a, b, elapsed / legs[0]["median_h"])
        elif elapsed < legs[0]["median_h"] + legs[1]["median_h"]:
            seg = (b, b, 0.0)                               # at the lock in between
        else:
            seg = (b, lock_id, (elapsed - legs[0]["median_h"] - legs[1]["median_h"]) / legs[2]["median_h"])
        out.append({
            "vessel_name": r.get("vessel_name"),
            "mmsi": r.get("mmsi"),
            "direction": d,
            "barges": barges,
            "from_lock": a,
            "via_lock": b if hops == 2 else None,
            "hops": hops,
            "left_at": exit_time,
            "eta": eta,
            "eta_earliest": exit_time + timedelta(hours=p25_h),
            "eta_latest": latest_eta,
            "overdue": now > eta,
            "transit_samples": legs[0]["n"],
            # Share of tows on this reach that actually continue to `lock_id`
            "probability": round(probability, 2),
            "progress": max(0.0, min(0.97, elapsed / median_h)),
            "segment_from": seg[0],
            "segment_to": seg[1],
            "segment_progress": max(0.0, min(0.97, seg[2])),
        })
    out.sort(key=lambda x: x["eta"])
    return out
