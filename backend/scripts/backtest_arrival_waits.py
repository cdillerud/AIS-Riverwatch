"""
Backtest "wait when you get there" (lock_board.predict_waits_at).

For each lockage in the later part of USACE history, step back H minutes
before the vessel arrived and predict its wait using only what was known
then: the lock's queue at that moment and vessels predicted (from earlier
lockages + learned transit times) to arrive before it. Compared with
predicting from the queue at that moment alone ("wait now", ignoring who is
coming), the lock's typical wait, and an oracle that knows the queue at the
moment of arrival.

    python scripts/backtest_arrival_waits.py
"""
import os
import statistics
import sys
from collections import defaultdict
from datetime import timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import LOCKS  # noqa: E402
from services import calibration as C  # noqa: E402
from services import lock_board, transits  # noqa: E402

HORIZONS = (60, 120, 240)


def state_at_time(lock_rows, t, exclude):
    locking, waiting = [], []
    for r in lock_rows:
        if r is exclude:
            continue
        if r["entry_time"] <= t < r["exit_time"]:
            locking.append({"barges": r.get("barge_count"), "started_at": r["entry_time"], "direction": r.get("direction")})
        elif r["arrival_time"] <= t < r["entry_time"]:
            waiting.append({"barges": r.get("barge_count"), "direction": r.get("direction")})
    return locking, waiting


def main():
    import pymongo
    rows = list(pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "riverwatch")].lockage_history.find(
        {"source": "usace_lpms", "in_progress": {"$ne": True}}, {"_id": 0}))
    rows = [r for r in rows if r.get("arrival_time") and r.get("entry_time") and r.get("exit_time")]
    for r in rows:  # Mongo returns naive UTC
        for k in ("arrival_time", "entry_time", "exit_time"):
            if r[k].tzinfo is None:
                r[k] = r[k].replace(tzinfo=timezone.utc)
    order = transits.lock_order(LOCKS)
    start = min(r["arrival_time"] for r in rows)
    end = max(r["arrival_time"] for r in rows)
    split = start + (end - start) * 2 / 3
    train_rows = [r for r in rows if r["exit_time"] < split]
    stats = transits.transit_stats(transits.transit_samples(train_rows, order))
    stats.update(transits.dwell_stats(train_rows))
    max_hops = int(os.environ.get("MAX_HOPS", "1"))
    by_lock = defaultdict(list)
    for r in rows:
        by_lock[r["lock_id"]].append(r)
    typical = {lid: C.typical_for([r for r in rs if r["arrival_time"] < split] or rs) for lid, rs in by_lock.items()}
    lock_median = {}
    for lid, rs in by_lock.items():
        w = sorted(r["wait_time_minutes"] for r in rs if r["arrival_time"] < split) or [0]
        lock_median[lid] = w[len(w) // 2]

    for H in HORIZONS:
        res = defaultdict(list)
        for lid, lock_rows in by_lock.items():
            for target in lock_rows:
                t = target["arrival_time"]
                if t < split or target.get("is_recreational"):
                    continue
                p = t - timedelta(minutes=H)
                key = target.get("mmsi") or target.get("usace_vessel_no")
                known = [r for r in rows if r["exit_time"] <= p]
                present = {r.get("mmsi") or r.get("usace_vessel_no") for r in lock_rows if r["arrival_time"] <= p < r["exit_time"]}
                appr = [a for a in transits.predicted_arrivals(lid, order, stats, [r for r in known if r["exit_time"] >= p - timedelta(hours=36)], present, p, max_hops=max_hops)
                        if (a.get("mmsi") or a.get("vessel_name")) not in (key, target.get("vessel_name"))]
                locking, waiting = state_at_time(lock_rows, p, target)
                ty = typical[lid]
                at_arrival = lock_board.predict_waits_at(lid, locking, waiting, appr, ty, t, p)["tow"]
                now_only = lock_board.predict_waits(lid, locking, waiting, ty, None, p)["tow"]
                o_lock, o_wait = state_at_time(lock_rows, t, target)
                oracle = lock_board.predict_waits(lid, o_lock, o_wait, ty, None, t)["tow"]
                actual = target["wait_time_minutes"]
                res["simulated forward (shipped)"].append((at_arrival, actual))
                res["queue at prediction time"].append((now_only, actual))
                res["lock's typical wait"].append((lock_median[lid], actual))
                res["oracle: queue at arrival"].append((oracle, actual))
        print(f"\n== predicting {H} min before arrival (tows, test period) ==")
        for name, pairs in res.items():
            m = C.metrics(pairs)
            print(f"{name:30} n={m['n']:5} MAE {m['mae']:6} medAE {m['median_abs_error']:6} bias {m['bias']:7} <=60m {m['within_60']}")


if __name__ == "__main__":
    main()
