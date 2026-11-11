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


def typical_for(records: List[dict], river: Optional[dict] = None) -> dict:
    """Per-lock averages, defined as in get_lockage_averages; with `river`
    (lock_board.river_barge_stats) also the lock's learned barge table."""
    def mean(xs):
        return sum(xs) / len(xs) if xs else None
    singles = [r["lockage_duration_minutes"] for r in records if (r.get("cuts") or 1) <= 1 and r["lockage_duration_minutes"] > 0]
    doubles = [r["lockage_duration_minutes"] for r in records if (r.get("cuts") or 1) > 1 and r["lockage_duration_minutes"] > 0]
    rec = [r["lockage_duration_minutes"] for r in records if not r.get("is_tow") and r["lockage_duration_minutes"] > 0]
    out = {"avg_single_lockage_minutes": mean(singles), "avg_double_lockage_minutes": mean(doubles),
           "avg_recreational_lockage_minutes": mean(rec)}
    if river is not None:
        out["by_barges"] = lock_board.lock_barge_table(records, river)
    return out


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


def build_samples(rows: List[dict], split, learned_barges: bool = True) -> List[dict]:
    """One sample per lockage: raw queue estimates at arrival and the actual wait.
    learned_barges: lockage minutes / double chance per barge count learned from
    the training rows (False: the old >9-barge rule, for comparison)."""
    rows = [r for r in rows if r.get("arrival_time") and r.get("entry_time") and r.get("exit_time")
            and not r.get("in_progress")]
    if not rows:
        return []
    by_lock = defaultdict(list)
    for r in rows:
        by_lock[r["lock_id"]].append(r)
    start = min(r["arrival_time"] for r in rows)
    river = lock_board.river_barge_stats(r for r in rows if r["arrival_time"] < split) if learned_barges else None
    samples = []
    for lock_id, lock_rows in by_lock.items():
        train_rows = [r for r in lock_rows if r["arrival_time"] < split]
        typical = typical_for(train_rows or lock_rows, river)
        train_waits = sorted(r["wait_time_minutes"] for r in train_rows) or [0]
        for target in lock_rows:
            if target["arrival_time"] < start + timedelta(hours=12):
                continue  # queue state before the data starts is unknown
            locking, waiting = state_at(lock_rows, target)
            t = target["arrival_time"]
            same = [w for w in waiting if w["direction"] == target.get("direction")]
            v0 = float(lock_board.estimate_wait(lock_id, locking, waiting, typical, t))
            feats = lock_board.queue_features(
                lock_id, locking, waiting, typical, target.get("direction"), v0,
                lock_board.estimate_wait(lock_id, locking, [], typical, t),
                own_double=lock_board.double_chance(lock_id, target.get("barge_count"), typical))
            samples.append({
                **feats,
                "lock_id": lock_id, "train": t < split,
                "actual": float(target["wait_time_minutes"]),
                "recreational": bool(target.get("is_recreational")),
                "queue": len(waiting), "locking": len(locking),
                "v0": v0,
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


def _solve(X, y, ridge=1.0):
    """Ridge-regularised least squares via normal equations (no intercept penalty)."""
    n = len(X[0])
    A = [[sum(r[i] * r[j] for r in X) + (ridge if i == j and i > 0 else 0.0) for j in range(n)] for i in range(n)]
    B = [sum(r[i] * yy for r, yy in zip(X, y)) for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda k: abs(A[k][i]))
        A[i], A[p], B[i], B[p] = A[p], A[i], B[p], B[i]
        if not A[i][i]:
            continue
        for k in range(i + 1, n):
            f = A[k][i] / A[i][i]
            for j in range(i, n):
                A[k][j] -= f * A[i][j]
            B[k] -= f * B[i]
    out = [0.0] * n
    for i in reversed(range(n)):
        out[i] = (B[i] - sum(A[i][j] * out[j] for j in range(i + 1, n))) / A[i][i] if A[i][i] else 0.0
    return out


def fit_l1(X, y, iters=30, ridge=1.0):
    """Least absolute deviations via iteratively reweighted least squares:
    fits the median, so rare multi-hour waits don't drag the estimate."""
    w = [1.0] * len(y)
    coef = None
    for _ in range(iters):
        sw = [wi ** 0.5 for wi in w]
        coef = _solve([[xi * s for xi in x] for x, s in zip(X, sw)], [yi * s for yi, s in zip(y, sw)], ridge)
        w = [1.0 / max(abs(yi - sum(c * xi for c, xi in zip(coef, x))), 1.0) for x, yi in zip(X, y)]
    return coef


def fit_tow_features(train: List[dict]) -> dict:
    """Tow model v2: L1 fit on queue features plus a per-lock effect.
    Backtest 2026-11-10 (20 days fit / 10 test): MAE 43.0 vs 46.7 for v1."""
    tows = [s for s in train if not s["recreational"]]
    locks = sorted({s["lock_id"] for s in tows})
    names = lock_board.TOW_FEATURES
    X = [[1.0] + [float(s[k]) for k in names] + [1.0 if s["lock_id"] == l else 0.0 for l in locks[1:]] for s in tows]
    coef = fit_l1(X, [s["actual"] for s in tows])
    return {
        "kind": "l1_features",
        "coef": {"intercept": round(coef[0], 2), **{k: round(c, 3) for k, c in zip(names, coef[1:1 + len(names)])}},
        "lock_effects": {locks[0]: 0.0, **{l: round(c, 2) for l, c in zip(locks[1:], coef[1 + len(names):])}},
    }


def fit_recreational(train: List[dict]) -> dict:
    """Recreational wait: L1 (median) fit of intercept + slope * same-direction
    queue. Pleasure-boat waits are mostly 0 with a few long ones; least squares
    let those pull every estimate up (5.7 + 0.09q). Backtest 2026-11-11 on the
    last third of 699 USACE recreational lockages: MAE 8.3 -> 6.4 min."""
    recs = [s for s in train if s["recreational"]]
    if len(recs) < 10:
        ra, rb = fit_linear([s["v2"] for s in recs], [s["actual"] for s in recs])
    else:
        ra, rb = fit_l1([[1.0, float(s["v2"])] for s in recs], [s["actual"] for s in recs], ridge=0.0)
    return {"intercept": round(max(0.0, ra), 1), "slope": round(max(0.0, rb), 3)}


def fit_model(train: List[dict]) -> dict:
    return {
        "tow": fit_tow_features(train),
        "recreational": fit_recreational(train),
    }


def predict(model: dict, s: dict) -> float:
    if s["recreational"]:
        r = model["recreational"]
        return max(0.0, r["intercept"] + r["slope"] * s["v2"])
    return lock_board.tow_wait(s, model)


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
    tow = model["tow"]
    if tow.get("kind") == "l1_features":
        c = tow["coef"]
        checks = {"tow.intercept": (c["intercept"], -30.0, 120.0), "tow.v0": (c["v0"], 0.2, 3.0)}
        checks.update({f"tow.{k}": (c[k], -90.0, 120.0) for k in lock_board.TOW_FEATURES if k != "v0"})
        checks.update({f"tow.lock_effects.{l}": (v, -150.0, 150.0) for l, v in tow.get("lock_effects", {}).items()})
        for key, (v, lo, hi) in checks.items():
            if not lo <= v <= hi:
                return f"{key}={v} outside [{lo}, {hi}]"
        r = model["recreational"]
        for key, v in (("recreational.intercept", r["intercept"]), ("recreational.slope", r["slope"])):
            lo, hi = BOUNDS[key]
            if not lo <= v <= hi:
                return f"{key}={v} outside [{lo}, {hi}]"
        return None
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
    fitted = fit_model(train)
    problem = within_bounds(fitted)
    if problem:
        return {**report, "adopt": False, "model": fitted, "reason": f"fit rejected: {problem}"}
    fitted_score, current_score = score(fitted, test), score(current, test)
    # Tows and pleasure boats are judged separately: pleasure boats are ~12% of
    # lockages, so a real gain for them vanished inside the combined MAE.
    model, changed = {}, []
    for part in ("tow", "recreational"):
        new_mae, cur_mae = fitted_score[part].get("mae"), current_score[part].get("mae")
        if new_mae is not None and cur_mae is not None and new_mae <= cur_mae - MIN_IMPROVEMENT_MINUTES:
            model[part] = fitted[part]
            changed.append(f"{part} MAE {cur_mae} -> {new_mae}")
        else:
            model[part] = current[part]
    new_score = score(model, test)
    report.update({"model": model, "fitted": fitted, "new_score": new_score, "current_score": current_score})
    if not changed:
        return {**report, "adopt": False,
                "reason": f"no improvement (MAE {fitted_score['all']['mae']} vs current {current_score['all']['mae']})"}
    return {**report, "adopt": True, "reason": f"{'; '.join(changed)} min on {len(test)} recent lockages"}
