"""
Backtest predicted lock arrivals (services/transits.py).

Learns lock-to-lock transit times from the earlier part of USACE history and
predicts, for every later transit, when the vessel would reach the next lock
given only its exit from the previous one. Reports error in hours and how
often the actual arrival fell inside the predicted p25-p75 window.

    python scripts/backtest_arrivals.py
"""
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import LOCKS  # noqa: E402
from services import transits  # noqa: E402

TRAIN_FRACTION = 2 / 3


def main():
    import pymongo
    coll = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "riverwatch")].lockage_history
    rows = list(coll.find({"source": "usace_lpms", "in_progress": {"$ne": True}}, {"_id": 0}))
    order = transits.lock_order(LOCKS)
    start = min(r["arrival_time"] for r in rows)
    end = max(r["arrival_time"] for r in rows)
    split = start + (end - start) * TRAIN_FRACTION

    stats = transits.transit_stats(transits.transit_samples([r for r in rows if r["exit_time"] < split], order))
    test = transits.transit_samples([r for r in rows if r["exit_time"] >= split], order)

    errors, inside, abs_by_dir = [], 0, {"upbound": [], "downbound": []}
    # Score each test transit once, through the same lookup the app uses:
    # leg x tow-size class when there's enough history, else the leg.
    for key, hours in test.items():
        if len(key) != 4:
            continue
        s = stats.get(key) or stats.get(key[:3])
        if not s:
            continue
        for h in hours:
            e = s["median_h"] - h
            errors.append(e)
            abs_by_dir[key[2]].append(abs(e))
            inside += s["p25_h"] <= h <= s["p75_h"]
    n = len(errors)
    abs_e = sorted(abs(e) for e in errors)
    print(f"{len(stats)} legs learned from data before {split:%b %d}; {n} later transits scored")
    print(f"median abs error {statistics.median(abs_e):.2f} h | mean {statistics.mean(abs_e):.2f} h | "
          f"bias {statistics.mean(errors):+.2f} h | within 1 h {sum(1 for e in abs_e if e <= 1) / n:.0%} | "
          f"inside p25-p75 window {inside / n:.0%}")
    for d, v in abs_by_dir.items():
        if v:
            print(f"  {d}: median abs error {statistics.median(v):.2f} h (n={len(v)})")


if __name__ == "__main__":
    main()
