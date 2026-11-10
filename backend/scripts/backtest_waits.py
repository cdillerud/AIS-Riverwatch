"""
Backtest the lock wait estimate against what actually happened.

For every completed USACE lockage in db.lockage_history, rebuild the lock's
state at the moment that vessel arrived (who was already waiting, who was
mid-lockage), ask an estimator what wait it would have predicted, and compare
with the real wait (start of lockage - arrival).

Calibrated variants are fit on the earlier part of the data and scored on the
later part (time split), so the scores are out-of-sample.

    python scripts/backtest_waits.py            # from backend/, Mongo running
    python scripts/backtest_waits.py --json out.json
"""
import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import lock_board  # noqa: E402

TRAIN_FRACTION = 2 / 3


def load(db_name):
    import pymongo
    coll = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[db_name].lockage_history
    rows = list(coll.find(
        {"source": "usace_lpms", "in_progress": {"$ne": True}},
        {"_id": 0, "lock_id": 1, "vessel_name": 1, "direction": 1, "barge_count": 1, "cuts": 1,
         "is_tow": 1, "is_recreational": 1, "arrival_time": 1, "entry_time": 1, "exit_time": 1,
         "wait_time_minutes": 1, "lockage_duration_minutes": 1},
    ))
    return [r for r in rows if r.get("arrival_time") and r.get("entry_time") and r.get("exit_time")]


def typical_for(records):
    """Per-lock averages, defined the same way as get_lockage_averages."""
    singles = [r["lockage_duration_minutes"] for r in records if (r.get("cuts") or 1) <= 1 and r["lockage_duration_minutes"] > 0]
    doubles = [r["lockage_duration_minutes"] for r in records if (r.get("cuts") or 1) > 1 and r["lockage_duration_minutes"] > 0]
    rec = [r["lockage_duration_minutes"] for r in records if not r.get("is_tow") and r["lockage_duration_minutes"] > 0]
    mean = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
    return {
        "avg_single_lockage_minutes": mean(singles),
        "avg_double_lockage_minutes": mean(doubles),
        "avg_recreational_lockage_minutes": mean(rec),
    }


def state_at(lock_rows, target):
    """Vessels locking / waiting at the moment `target` arrived."""
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


def metrics(pairs):
    errs = [p - a for p, a in pairs]
    abs_errs = [abs(e) for e in errs]
    return {
        "n": len(pairs),
        "mae": round(statistics.mean(abs_errs), 1),
        "median_abs_error": round(statistics.median(abs_errs), 1),
        "bias": round(statistics.mean(errs), 1),
        "within_30": round(sum(1 for e in abs_errs if e <= 30) / len(abs_errs), 2),
        "within_60": round(sum(1 for e in abs_errs if e <= 60) / len(abs_errs), 2),
    }


def fit_linear(xs, ys):
    """Least-squares y = a + b*x (b >= 0)."""
    n = len(xs)
    if n < 10:
        return 0.0, 1.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return my, 0.0
    b = max(0.0, sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx)
    return my - b * mx, b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("DB_NAME", "riverwatch"))
    ap.add_argument("--json", help="write full results to this file")
    args = ap.parse_args()

    rows = load(args.db)
    by_lock = defaultdict(list)
    for r in rows:
        by_lock[r["lock_id"]].append(r)
    start = min(r["arrival_time"] for r in rows)
    end = max(r["arrival_time"] for r in rows)
    split = start + (end - start) * TRAIN_FRACTION

    samples = []  # one per target lockage
    for lock_id, lock_rows in by_lock.items():
        train_rows = [r for r in lock_rows if r["arrival_time"] < split]
        typical = typical_for(train_rows or lock_rows)
        train_waits = sorted(r["wait_time_minutes"] for r in train_rows) or [0]
        lock_median = train_waits[len(train_waits) // 2]
        for target in lock_rows:
            locking, waiting = state_at(lock_rows, target)
            # Skip targets right at the edge of the data (queue state unknown before it).
            if target["arrival_time"] < start + timedelta(hours=12):
                continue
            v0 = lock_board.estimate_wait(lock_id, locking, waiting, typical, target["arrival_time"])
            v1 = lock_board.estimate_wait(lock_id, locking, [w for w in waiting if not w["recreational"]],
                                          typical, target["arrival_time"])
            # Same-direction queue only (locks often alternate directions)
            same = [w for w in waiting if w["direction"] == target.get("direction")]
            v2 = lock_board.estimate_wait(lock_id, locking, same, typical, target["arrival_time"])
            samples.append({
                "lock_id": lock_id, "train": target["arrival_time"] < split,
                "actual": float(target["wait_time_minutes"]),
                "recreational": bool(target.get("is_recreational")),
                "queue": len(waiting), "locking": len(locking),
                "v0": float(v0), "v1": float(v1), "v2": float(v2), "lock_median": float(lock_median),
            })

    train = [s for s in samples if s["train"]]
    test = [s for s in samples if not s["train"]]

    # Calibrated variants, fit on train only: global and per-lock linear on v0
    ga, gb = fit_linear([s["v0"] for s in train], [s["actual"] for s in train])
    per_lock = {}
    for lock_id in by_lock:
        tr = [s for s in train if s["lock_id"] == lock_id]
        per_lock[lock_id] = fit_linear([s["v0"] for s in tr], [s["actual"] for s in tr]) if len(tr) >= 30 else (ga, gb)

    # v5: separate calibrations for tows (on v0) and recreational boats (on the
    # same-direction queue, v2) - pleasure craft are slotted in around tows.
    tow_tr = [s for s in train if not s["recreational"]]
    rec_tr = [s for s in train if s["recreational"]]
    ta, tb = fit_linear([s["v0"] for s in tow_tr], [s["actual"] for s in tow_tr])
    ra, rb = fit_linear([s["v2"] for s in rec_tr], [s["actual"] for s in rec_tr])

    def v5(s):
        return max(0.0, ra + rb * s["v2"]) if s["recreational"] else max(0.0, ta + tb * s["v0"])

    # v6: shipped model. Tows: global calibration on v0 when anything is
    # queued/locking, else the median wait seen with an empty lock;
    # recreational: their own calibration on the same-direction queue.
    empty_tow = sorted(s["actual"] for s in tow_tr if s["queue"] == 0 and s["locking"] == 0) or [0]
    empty_median = empty_tow[len(empty_tow) // 2]

    def v6(s):
        if s["recreational"]:
            return max(0.0, ra + rb * s["v2"])
        if s["queue"] == 0 and s["locking"] == 0:
            return empty_median
        return max(0.0, ga + gb * s["v0"])

    def score(subset):
        return {
            "baseline_zero": metrics([(0.0, s["actual"]) for s in subset]),
            "baseline_lock_median": metrics([(s["lock_median"], s["actual"]) for s in subset]),
            "v0_current": metrics([(s["v0"], s["actual"]) for s in subset]),
            "v1_ignore_recreational_in_queue": metrics([(s["v1"], s["actual"]) for s in subset]),
            "v2_same_direction_queue": metrics([(s["v2"], s["actual"]) for s in subset]),
            "v3_global_linear": metrics([(max(0.0, ga + gb * s["v0"]), s["actual"]) for s in subset]),
            "v4_per_lock_linear": metrics([(max(0.0, per_lock[s["lock_id"]][0] + per_lock[s["lock_id"]][1] * s["v0"]), s["actual"]) for s in subset]),
            "v5_split_tow_rec": metrics([(v5(s), s["actual"]) for s in subset]),
            "v6_shipped": metrics([(v6(s), s["actual"]) for s in subset]),
        }

    result = {
        "records": len(rows), "samples": len(samples), "train": len(train), "test": len(test),
        "split_at": split.isoformat(), "global_fit": {"a": round(ga, 1), "b": round(gb, 3)},
        "tow_fit": {"a": round(ta, 1), "b": round(tb, 3)}, "rec_fit": {"a": round(ra, 1), "b": round(rb, 3)},
        "empty_lock_tow_median": empty_median,
        "test_all": score(test),
        "test_tows": score([s for s in test if not s["recreational"]]),
        "test_recreational": score([s for s in test if s["recreational"]]),
        "test_queue_empty": score([s for s in test if s["queue"] == 0 and s["locking"] == 0]),
        "test_queue_busy": score([s for s in test if s["queue"] >= 2]),
        "per_lock_fit": {k: {"a": round(v[0], 1), "b": round(v[1], 3)} for k, v in sorted(per_lock.items())},
    }
    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2, default=str)

    print(f"{result['records']} lockages, {result['samples']} scored; train {len(train)} / test {len(test)} (split {split:%b %d})")
    for group in ("test_all", "test_tows", "test_recreational", "test_queue_empty", "test_queue_busy"):
        print(f"\n== {group} ==")
        print(f"{'variant':36} {'n':>5} {'MAE':>6} {'medAE':>6} {'bias':>7} {'<=30m':>6} {'<=60m':>6}")
        for name, m in result[group].items():
            print(f"{name:36} {m['n']:>5} {m['mae']:>6} {m['median_abs_error']:>6} {m['bias']:>7} {m['within_30']:>6} {m['within_60']:>6}")
    print(f"\nglobal linear fit: actual ~ {ga:.1f} + {gb:.3f} * v0")
    print(f"tow fit: actual ~ {ta:.1f} + {tb:.3f} * v0   |   recreational fit: actual ~ {ra:.1f} + {rb:.3f} * v2")


if __name__ == "__main__":
    main()
