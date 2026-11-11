"""
Learn how good arrival predictions are, and correct them.

"Wait when you get there" depends on who arrives at the lock first. Two
predictors feed it (services/live_arrivals.py):
  ais               boat seen on AIS heading in: ETA = distance / current speed
  usace_prediction  from the boat's last USACE lockage + typical transit times

Neither had ever been checked against what really happened. This module:

1. snapshot_docs()  turns the merged arrival list for a lock into prediction
                    records (logged every few minutes by the server).
2. score()          matches each prediction to the vessel's first USACE
                    arrival at that lock (by MMSI or name) - the ground truth.
                    No arrival within HORIZON = a no-show.
3. fit_ais_factor() learns one correction for AIS ETAs: actual minutes ~=
                    factor * distance/speed (tows slow down approaching a
                    lock). Fit on the older predictions, scored on the newer
                    ones; adopted only if it beats the uncorrected ETA by
                    MIN_IMPROVEMENT on held-out data, with enough samples, and
                    inside sane BOUNDS. Otherwise the factor stays 1.0.
"""
import statistics
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

HORIZON = timedelta(hours=14)
EARLY_SLACK = timedelta(minutes=30)     # USACE may log the arrival a bit before our snapshot
MIN_PRED_MINUTES = 5                    # ratios are meaningless right at the lock
MIN_TRAIN, MIN_TEST = 20, 10            # distinct boat-trips, not snapshots
MIN_IMPROVEMENT = 2.0                   # minutes of MAE
BOUNDS = (0.8, 3.0)
TRAIN_FRACTION = 2 / 3


def _norm(x) -> str:
    return "".join(ch for ch in str(x or "").upper() if ch.isalnum())


def snapshot_docs(lock_id: str, arrivals: Iterable[dict], now: datetime) -> List[dict]:
    out = []
    for a in arrivals:
        eta = a.get("eta")
        if isinstance(eta, str):
            eta = datetime.fromisoformat(eta)
        if not isinstance(eta, datetime):
            continue
        minutes = (eta - now).total_seconds() / 60
        if minutes < 0 or minutes > HORIZON.total_seconds() / 60:
            continue
        out.append({
            "lock_id": lock_id, "made_at": now, "predicted_eta": eta,
            "predicted_minutes": round(minutes, 1),
            "source": a.get("source") or "usace_prediction",
            "mmsi": str(a["mmsi"]) if a.get("mmsi") else None,
            "vessel_name": a.get("vessel_name"),
            "direction": a.get("direction"),
            "distance_mi": a.get("distance_mi"),
            "probability": a.get("probability", 1.0),
        })
    return out


def score(predictions: Iterable[dict], arrivals: Iterable[dict], now: datetime) -> List[dict]:
    """Predictions whose outcome is known, with actual_minutes (None = no-show).
    Predictions younger than HORIZON without an arrival yet are left out."""
    by_lock: Dict[str, List[dict]] = {}
    for a in arrivals:
        if a.get("arrival_time") and a.get("lock_id"):
            by_lock.setdefault(a["lock_id"], []).append(a)
    for rows in by_lock.values():
        rows.sort(key=lambda r: r["arrival_time"])

    scored = []
    for p in predictions:
        made = p["made_at"]
        name = _norm(p.get("vessel_name"))
        hit = None
        for a in by_lock.get(p["lock_id"], []):
            if a["arrival_time"] < made - EARLY_SLACK:
                continue
            if a["arrival_time"] > made + HORIZON:
                break
            if (p.get("mmsi") and a.get("mmsi") and str(a["mmsi"]) == p["mmsi"]) or (name and _norm(a.get("vessel_name")) == name):
                hit = a
                break
        if hit is None and now - made < HORIZON:
            continue  # may still arrive
        actual = None if hit is None else max(0.0, (hit["arrival_time"] - made).total_seconds() / 60)
        scored.append({**p, "actual_minutes": actual, "actual_arrival": hit["arrival_time"] if hit else None})
    return scored


def summarize(scored: List[dict]) -> dict:
    """Accuracy per source: MAE / median error of arrivals, and no-show rate."""
    out = {}
    for src in sorted({s["source"] for s in scored}):
        rows = [s for s in scored if s["source"] == src]
        hits = [s for s in rows if s["actual_minutes"] is not None]
        errs = [s["actual_minutes"] - s["predicted_minutes"] for s in hits]
        out[src] = {
            "predictions": len(rows),
            "arrived": len(hits),
            "no_show_rate": round(1 - len(hits) / len(rows), 3) if rows else None,
            "mae_minutes": round(statistics.mean(abs(e) for e in errs), 1) if errs else None,
            "median_error_minutes": round(statistics.median(errs), 1) if errs else None,
        }
    return out


def fit_ais_factor(scored: List[dict], current: float = 1.0) -> dict:
    """Learn the AIS ETA correction; see module docstring for the adopt rule."""
    rows = [s for s in scored if s["source"] == "ais" and s["actual_minutes"] is not None
            and s["predicted_minutes"] >= MIN_PRED_MINUTES]
    rows.sort(key=lambda s: s["made_at"])
    trips = {}
    for s in rows:
        # one boat reaching one lock once = one trip, however many snapshots it got
        trips.setdefault((s["lock_id"], s.get("mmsi") or _norm(s.get("vessel_name")), s.get("actual_arrival")), []).append(s)
    report = {"samples": len(rows), "trips": len(trips), "current_factor": current, "adopt": False}
    if not rows:
        report["reason"] = "no scored AIS arrivals yet"
        return report
    # Split by trip start time so one boat's snapshots never land on both sides.
    ordered = sorted(trips.values(), key=lambda t: t[0]["made_at"])
    n_train = int(len(ordered) * TRAIN_FRACTION)
    train = [s for t in ordered[:n_train] for s in t]
    test = [s for t in ordered[n_train:] for s in t]
    report.update(train_trips=n_train, test_trips=len(ordered) - n_train)
    if n_train < MIN_TRAIN or len(ordered) - n_train < MIN_TEST:
        report["reason"] = (f"need {MIN_TRAIN}+{MIN_TEST} boat trips scored on AIS; "
                            f"have {n_train}+{len(ordered) - n_train}")
        return report

    def mae(rows_, k):
        return statistics.mean(abs(s["actual_minutes"] - k * s["predicted_minutes"]) for s in rows_)

    factor = statistics.median(s["actual_minutes"] / s["predicted_minutes"] for s in train)
    report.update(fitted_factor=round(factor, 3), test_mae_new=round(mae(test, factor), 1),
                  test_mae_current=round(mae(test, current), 1))
    if not BOUNDS[0] <= factor <= BOUNDS[1]:
        report["reason"] = f"fitted factor {factor:.2f} outside {BOUNDS}: treated as a data problem"
    elif report["test_mae_current"] - report["test_mae_new"] < MIN_IMPROVEMENT:
        report["reason"] = (f"no improvement on held-out trips (MAE {report['test_mae_new']} vs "
                            f"{report['test_mae_current']} min)")
    else:
        report["adopt"] = True
        report["reason"] = (f"held-out MAE {report['test_mae_current']} -> {report['test_mae_new']} min "
                            f"with factor {factor:.2f}")
    return report
