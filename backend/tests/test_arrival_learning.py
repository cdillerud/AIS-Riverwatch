"""Arrival predictions are logged, scored against USACE arrivals, and the AIS
ETA correction is learned only when it beats the current one on held-out trips."""
from datetime import datetime, timedelta, timezone

from services import arrival_learning as L

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def test_snapshot_keeps_future_etas_only():
    arr = [{"mmsi": "1", "vessel_name": "A", "eta": T0 + timedelta(minutes=40), "source": "ais", "distance_mi": 4.0},
           {"mmsi": "2", "vessel_name": "B", "eta": T0 - timedelta(minutes=5)},
           {"mmsi": "3", "vessel_name": "C", "eta": (T0 + timedelta(hours=2)).isoformat()}]
    docs = L.snapshot_docs("lock_3", arr, T0)
    assert [(d["mmsi"], d["predicted_minutes"], d["source"]) for d in docs] == \
        [("1", 40.0, "ais"), ("3", 120.0, "usace_prediction")]


def test_score_matches_by_mmsi_or_name_and_counts_no_shows():
    preds = [
        {"lock_id": "lock_3", "made_at": T0, "predicted_minutes": 30, "source": "ais", "mmsi": "1", "vessel_name": "MARY J"},
        {"lock_id": "lock_3", "made_at": T0, "predicted_minutes": 60, "source": "usace_prediction", "mmsi": None, "vessel_name": "Starfire"},
        {"lock_id": "lock_3", "made_at": T0, "predicted_minutes": 90, "source": "usace_prediction", "mmsi": "9", "vessel_name": "GHOST"},
        {"lock_id": "lock_3", "made_at": T0 + timedelta(hours=20), "predicted_minutes": 20, "source": "ais", "mmsi": "7", "vessel_name": "LATER"},
    ]
    arrivals = [
        {"lock_id": "lock_3", "mmsi": "1", "vessel_name": "MARY J", "arrival_time": T0 + timedelta(minutes=45)},
        {"lock_id": "lock_3", "mmsi": None, "vessel_name": "STARFIRE", "arrival_time": T0 + timedelta(minutes=50)},
        {"lock_id": "lock_4", "mmsi": "9", "vessel_name": "GHOST", "arrival_time": T0 + timedelta(minutes=80)},  # other lock
    ]
    scored = L.score(preds, arrivals, T0 + timedelta(hours=21))
    got = {s["vessel_name"]: s["actual_minutes"] for s in scored}
    assert got == {"MARY J": 45.0, "Starfire": 50.0, "GHOST": None}   # LATER: still pending
    summary = L.summarize(scored)
    assert summary["ais"]["mae_minutes"] == 15.0
    assert summary["usace_prediction"]["no_show_rate"] == 0.5


def _ais_trips(n, slow=1.5, start=T0):
    """n boat trips, 3 snapshots each; real arrival = slow * distance/speed."""
    out = []
    for i in range(n):
        made = start + timedelta(hours=i)
        arrive = made + timedelta(minutes=slow * 40)
        for j, pred in enumerate((40, 30, 20)):
            out.append({"lock_id": "lock_3", "mmsi": str(i), "vessel_name": f"T{i}", "source": "ais",
                        "made_at": made + timedelta(minutes=10 * j), "predicted_minutes": float(pred),
                        "actual_minutes": slow * pred, "actual_arrival": arrive})
    return out


def test_factor_learned_when_it_beats_current_on_held_out_trips():
    r = L.fit_ais_factor(_ais_trips(36), current=1.0)
    assert r["adopt"] and abs(r["fitted_factor"] - 1.5) < 1e-6
    assert r["train_trips"] == 24 and r["test_trips"] == 12   # split by trip, not snapshot


def test_not_adopted_without_enough_trips_or_improvement_or_in_bounds():
    assert not L.fit_ais_factor(_ais_trips(10))["adopt"]                  # too few trips
    assert not L.fit_ais_factor(_ais_trips(36, slow=1.0))["adopt"]        # already right
    r = L.fit_ais_factor(_ais_trips(36, slow=5.0))
    assert not r["adopt"] and "outside" in r["reason"]                    # data problem
    assert not L.fit_ais_factor([])["adopt"]
