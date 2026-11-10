"""
Wait-estimate calibration learned from USACE lockage history.

Shared by scripts/backtest_waits.py (offline analysis) and the server's
nightly recalibration job. For every historical lockage, the lock's state at
the moment that vessel arrived is rebuilt (who was mid-lockage, who was
already waiting) and run through the raw queue estimate; the calibration maps
that raw estimate onto real waits, separately for tows and recreational boats.

Model (same shape as services/lock_board.CALIBRATION):
    tow:          intercept + slope * queue_minutes   (empty lock: empty_lock)
    recreational: intercept + slope * same-direction queue minutes
"""
import statistics
from collections import defaultdict
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from services import lock_board

TRAIN_FRACTION = 2 / 3
MIN_SAMPLES = 1000
MIN_IMPROVEMENT_MINUTES = 0.5   # don't churn the model over noise
# Guardrails: a fit outside these is treated as a data problem, not adopted.
BOUNDS = {
    "tow.intercept": (0.0, 120.0), "tow.slope": (0.3, 3.0), "tow.empty_lock": (0.0, 90.0),
    "recreational.intercept": (0.0, 90.0), "recreational.slope": (0.0, 1.5),
}


def typical_for(records: List[dict]) -> dict:
    """Per-lock averages, defined as in get_lockage_averages."""
    def mean(xs):
        return sum(xs) / len(xs) if xs else None
    singles = [r["lockage_duration_minutes"] for r in records if (r.get("cuts") or 1) <= 1 and r["lockage_duration_minutes"] > 0]
    doubles = [r["lockage_duration_minutes"] for r in records if (r.get("cuts") or 1) > 1 and r["lockage_duration_minutes"] > 0]
    rec = [r["lockage_duration_minutes"] for r in records if not r.get("is_tow") and r["lockage_duration_minutes"] > 0]
    return {"avg_single_lockage_minutes": mean(singles), "avg_double_lockage_minutes": mean(doubles),
            "avg_recreational_lockage_minutes": mean(rec)}


def state_at(lock_rows: List[dict], target: dict) -> Tuple[list, list]:
    """Vessels locking / waiting at the lock when `target` arrived."""
    t = target["arrival_time"]
    locking, waiting = [], []
    for r in lock_rows:
        if r is target:
            continue
        if r["entry_time"] <= t < r["exit_time"]:
            locking.append({"barges": r.get("barge_count"), "started_at": r["entry_time"],
                            "recreational": bool(r.get("is_recreational")), "direction": r.get("direction")})
        elif r["arrival_time"] < t < r["entry_time"]:
            waiting.append({"barges": r.get("barge_count"),
                            "recreational": bool(r.get("is_recreational")), "direction": r.get("direction")})
    return locking, waiting


def build_samples(rows: List[dict], split) -> List[dict]:
    """One sample per lockage: raw queue estimates at arrival and the actual wait."""
    rows = [r for r in rows if r.get("arrival_time") and r.get("entry_time") and r.get("exit_time")
            and not r.get("in_progress")]
    if not rows:
        return []
    by_lock = defaultdict(list)
    for r in rows:
        by_lock[r["lock_id"]].append(r)
    start = min(r["arrival_time"] for r in rows)
    samples = []
    for lock_id, lock_rows in by_lock.items():
        train_rows = [r for r in lock_rows if r["arrival_time"] < split]
        typical = typical_for(train_rows or lock_rows)
        train_waits = sorted(r["wait_time_minutes"] for r in train_rows) or [0]
        for target in lock_rows:
            if target["arrival_time"] < start + timedelta(hours=12):
                continue  # queue state before the data starts is unknown
            locking, waiting = state_at(lock_rows, target)
            t = target["arrival_time"]
            same = [w for w in waiting if w["direction"] == target.get("direction")]
            samples.append({
                "lock_id": lock_id, "train": t < split,
                "actual": float(target["wait_time_minutes"]),
                "recreational": bool(target.get("is_recreational")),
                "queue": len(waiting), "locking": len(locking),
                "v0": float(lock_board.estimate_wait(lock_id, locking, waiting, typical, t)),
                "v1": float(lock_board.estimate_wait(lock_id, locking, [w for w in waiting if not w["recreational"]], typical, t)),
                "v2": float(lock_board.estimate_wait(lock_id, locking, same, typical, t)),
                "lock_median": float(train_waits[len(train_waits) // 2]),
            })
    return samples


def fit_linear(xs, ys) -> Tuple[float, float]:
    """Least-squares y = a + b*x with b >= 0."""
    n = len(xs)
    if n < 10:
        return 0.0, 1.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return my, 0.0
    b = max(0.0, sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx)
    return my - b * mx, b


def fit_model(train: List[dict]) -> dict:
    tows = [s for s in train if not s["recreational"]]
    recs = [s for s in train if s["recreational"]]
    # Tow line fit on every lockage: compared out of sample on 30 days, this
    # beat fitting on tows only (45.7 min) or busy locks only (47.4 min).
    ta, tb = fit_linear([s["v0"] for s in train], [s["actual"] for s in train])
    empty = sorted(s["actual"] for s in tows if not s["queue"] and not s["locking"]) or [0.0]
    ra, rb = fit_linear([s["v2"] for s in recs], [s["actual"] for s in recs])
    return {
        "tow": {"intercept": round(ta, 1), "slope": round(tb, 3), "empty_lock": float(empty[len(empty) // 2])},
        "recreational": {"intercept": round(ra, 1), "slope": round(rb, 3)},
    }


def predict(model: dict, s: dict) -> float:
    if s["recreational"]:
        r = model["recreational"]
        return max(0.0, r["intercept"] + r["slope"] * s["v2"])
    t = model["tow"]
    if not s["queue"] and not s["locking"]:
        return t["empty_lock"]
    return max(0.0, t["intercept"] + t["slope"] * s["v0"])


def metrics(pairs) -> dict:
    errs = [p - a for p, a in pairs]
    if not errs:
        return {"n": 0}
    abs_errs = [abs(e) for e in errs]
    return {
        "n": len(pairs),
        "mae": round(statistics.mean(abs_errs), 1),
        "median_abs_error": round(statistics.median(abs_errs), 1),
        "bias": round(statistics.mean(errs), 1),
        "within_30": round(sum(1 for e in abs_errs if e <= 30) / len(abs_errs), 2),
        "within_60": round(sum(1 for e in abs_errs if e <= 60) / len(abs_errs), 2),
    }


def score(model: dict, samples: List[dict]) -> dict:
    return {
        "all": metrics([(predict(model, s), s["actual"]) for s in samples]),
        "tow": metrics([(predict(model, s), s["actual"]) for s in samples if not s["recreational"]]),
        "recreational": metrics([(predict(model, s), s["actual"]) for s in samples if s["recreational"]]),
    }


def within_bounds(model: dict) -> Optional[str]:
    for key, (lo, hi) in BOUNDS.items():
        group, field = key.split(".")
        v = model[group][field]
        if not lo <= v <= hi:
            return f"{key}={v} outside [{lo}, {hi}]"
    return None


def recalibrate(rows: List[dict], current: dict) -> dict:
    """Fit on the earlier part of `rows`, score new vs current on the later part.

    Returns a report with `adopt` True only if there is enough data, the fit is
    within bounds and it beats the current model's overall MAE out of sample."""
    rows = [r for r in rows if r.get("arrival_time")]
    if not rows:
        return {"adopt": False, "reason": "no history"}
    start = min(r["arrival_time"] for r in rows)
    end = max(r["arrival_time"] for r in rows)
    split = start + (end - start) * TRAIN_FRACTION
    samples = build_samples(rows, split)
    train = [s for s in samples if s["train"]]
    test = [s for s in samples if not s["train"]]
    report = {"samples": len(samples), "train": len(train), "test": len(test),
              "history_from": start, "history_to": end, "split_at": split}
    if len(train) < MIN_SAMPLES or len(test) < MIN_SAMPLES // 4:
        return {**report, "adopt": False, "reason": f"not enough samples ({len(train)} train / {len(test)} test)"}
    model = fit_model(train)
    new_score, current_score = score(model, test), score(current, test)
    report.update({"model": model, "new_score": new_score, "current_score": current_score})
    problem = within_bounds(model)
    if problem:
        return {**report, "adopt": False, "reason": f"fit rejected: {problem}"}
    if new_score["all"]["mae"] > current_score["all"]["mae"] - MIN_IMPROVEMENT_MINUTES:
        return {**report, "adopt": False,
                "reason": f"no improvement (MAE {new_score['all']['mae']} vs current {current_score['all']['mae']})"}
    return {**report, "adopt": True,
            "reason": f"MAE {current_score['all']['mae']} -> {new_score['all']['mae']} min on {len(test)} recent lockages"}
