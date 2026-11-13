"""
Live wait predictions, logged when a boat joins a lock queue and scored later
against the wait USACE recorded - the honest "we said X, it was Y" record the
public accuracy page shows (the nightly calibration scores the model on
held-out history; this scores what users actually saw).

A boat is logged once, within LOG_WINDOW_MINUTES of its USACE arrival time, so
the logged estimate is close to what the board showed a boat arriving then
(boats already waiting when the server starts are skipped, not back-filled
with a hindsight queue). The queue ahead of it is the boats locking plus those
that arrived before it.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional

LOG_WINDOW_MINUTES = 15
MATCH_MINUTES = 10


def key_of(row: dict) -> str:
    return str(row.get("vessel_no") or row.get("usace_vessel_no") or row.get("vessel_name") or "").strip().upper()


def arrival_docs(lock_id: str, locking: List[dict], waiting: List[dict], predict: Callable[..., dict],
                 logged: set, now: datetime) -> List[dict]:
    """Docs for boats that joined the queue in the last LOG_WINDOW_MINUTES and
    aren't logged yet. `waiting` entries carry arrived_at, direction, key;
    `predict(locking, ahead, direction)` returns lock_board.predict_waits()."""
    out = []
    for i, w in enumerate(waiting):
        at = w.get("arrived_at")
        k = w.get("key")
        if not at or not k or (lock_id, k, at) in logged:
            continue
        if not (timedelta(0) <= now - at <= timedelta(minutes=LOG_WINDOW_MINUTES)):
            continue
        ahead = [o for o in waiting if o is not w and o.get("arrived_at") and o["arrived_at"] < at]
        p = predict(locking, ahead, w.get("direction"))
        out.append({
            "lock_id": lock_id, "key": k, "vessel_name": w.get("vessel_name"), "arrived_at": at,
            "direction": w.get("direction"), "barges": w.get("barges"), "made_at": now,
            "tow": p["tow"], "tow_range": p.get("tow_range"),
            "recreational": p["recreational"], "recreational_range": p.get("recreational_range"),
        })
    return out


def score(predictions: Iterable[dict], lockages: Iterable[dict]) -> List[dict]:
    """Match each prediction to the USACE lockage of the same boat at the same
    lock (arrival within MATCH_MINUTES); the kind (tow / recreational) comes
    from the lockage."""
    by_key: Dict[tuple, List[dict]] = {}
    for r in lockages:
        if r.get("wait_time_minutes") is None or not r.get("arrival_time"):
            continue
        by_key.setdefault((r.get("lock_id"), key_of(r)), []).append(r)
    out = []
    for p in predictions:
        best = None
        for r in by_key.get((p["lock_id"], p["key"]), []):
            gap = abs((r["arrival_time"] - p["arrived_at"]).total_seconds()) / 60
            if gap <= MATCH_MINUTES and (best is None or gap < best[0]):
                best = (gap, r)
        if not best:
            continue
        r = best[1]
        rec = bool(r.get("is_recreational"))
        predicted = p["recreational"] if rec else p["tow"]
        rng = p.get("recreational_range" if rec else "tow_range") or [None, None]
        actual = float(r["wait_time_minutes"])
        lo, hi = rng[0], rng[1]
        out.append({
            "lock_id": p["lock_id"], "kind": "recreational" if rec else "tow",
            "vessel_name": None if rec else (r.get("vessel_name") or p.get("vessel_name")),
            "arrived_at": p["arrived_at"], "predicted": predicted, "actual": actual,
            "error": predicted - actual,
            "in_range": (lo <= actual <= hi) if lo is not None and hi is not None else None,
        })
    return out


def summarize(scored: List[dict]) -> Optional[dict]:
    if not scored:
        return None
    errs = [s["error"] for s in scored]
    absd = [abs(e) for e in errs]
    ranged = [s["in_range"] for s in scored if s["in_range"] is not None]
    n = len(scored)
    return {
        "n": n,
        "mae_minutes": round(sum(absd) / n, 1),
        "median_abs_error_minutes": round(statistics.median(absd), 1),
        "bias_minutes": round(sum(errs) / n, 1),
        "within_15_pct": round(100 * sum(a <= 15 for a in absd) / n),
        "within_30_pct": round(100 * sum(a <= 30 for a in absd) / n),
        "in_range_pct": round(100 * sum(ranged) / len(ranged)) if ranged else None,
    }


def report(scored: List[dict], lock_names: Dict[str, str], recent: int = 15) -> dict:
    """Public accuracy summary: by kind, by lock (tows), and recent examples."""
    by_kind = {k: summarize([s for s in scored if s["kind"] == k]) for k in ("tow", "recreational")}
    by_lock = []
    for lid in sorted({s["lock_id"] for s in scored}):
        sm = summarize([s for s in scored if s["lock_id"] == lid])
        by_lock.append({"lock_id": lid, "lock_name": lock_names.get(lid, lid), **sm})
    by_lock.sort(key=lambda r: -r["n"])
    latest = sorted(scored, key=lambda s: s["arrived_at"], reverse=True)[:recent]
    return {
        "overall": summarize(scored),
        "by_kind": by_kind,
        "by_lock": by_lock,
        "recent": [{**s, "lock_name": lock_names.get(s["lock_id"], s["lock_id"]),
                    "arrived_at": s["arrived_at"].isoformat()} for s in latest],
    }
