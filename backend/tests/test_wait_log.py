from datetime import datetime, timedelta, timezone

from services import wait_log as W

NOW = datetime(2026, 11, 13, 2, 0, tzinfo=timezone.utc)


def _predict(locking, ahead, direction):
    q = 30 * (len(locking) + len(ahead))
    return {"tow": q + 10, "tow_range": [q, q + 40], "recreational": q // 2, "recreational_range": [0, q]}


def test_logs_only_fresh_arrivals_once_with_the_queue_ahead():
    waiting = [
        {"key": "A", "arrived_at": NOW - timedelta(minutes=40), "direction": "upbound"},   # too old: skipped
        {"key": "B", "arrived_at": NOW - timedelta(minutes=10), "direction": "upbound"},
        {"key": "C", "arrived_at": NOW - timedelta(minutes=2), "direction": "downbound"},
    ]
    docs = W.arrival_docs("lock_2", [{"key": "L"}], waiting, _predict, set(), NOW)
    assert [d["key"] for d in docs] == ["B", "C"]
    assert docs[0]["tow"] == 30 * 2 + 10      # locking + A ahead of B
    assert docs[1]["tow"] == 30 * 3 + 10      # locking + A + B ahead of C
    logged = {("lock_2", "B", waiting[1]["arrived_at"])}
    assert [d["key"] for d in W.arrival_docs("lock_2", [], waiting, _predict, logged, NOW)] == ["C"]


def test_score_matches_boat_lock_and_arrival_and_picks_the_kind():
    t = NOW - timedelta(hours=3)
    preds = [
        {"lock_id": "lock_2", "key": "0661437", "vessel_name": "VIRGINIA INGRAM", "arrived_at": t,
         "tow": 60, "tow_range": [40, 90], "recreational": 20, "recreational_range": [5, 30]},
        {"lock_id": "lock_2", "key": "REC1", "arrived_at": t, "tow": 60, "tow_range": [40, 90],
         "recreational": 20, "recreational_range": [5, 30]},
        {"lock_id": "lock_3", "key": "0661437", "arrived_at": t, "tow": 60, "tow_range": None,
         "recreational": 20, "recreational_range": None},
    ]
    lockages = [
        {"lock_id": "lock_2", "usace_vessel_no": "0661437", "vessel_name": "VIRGINIA INGRAM",
         "arrival_time": t + timedelta(minutes=4), "wait_time_minutes": 100, "is_recreational": False},
        {"lock_id": "lock_2", "usace_vessel_no": "REC1", "vessel_name": "RECREATIONAL VESSEL",
         "arrival_time": t, "wait_time_minutes": 12, "is_recreational": True},
        {"lock_id": "lock_3", "usace_vessel_no": "0661437",
         "arrival_time": t + timedelta(minutes=30), "wait_time_minutes": 5},   # too far apart: unmatched
    ]
    s = W.score(preds, lockages)
    assert len(s) == 2
    tow, rec = s
    assert (tow["kind"], tow["predicted"], tow["actual"], tow["error"], tow["in_range"]) == ("tow", 60, 100, -40, False)
    assert (rec["kind"], rec["predicted"], rec["in_range"], rec["vessel_name"]) == ("recreational", 20, True, None)


def test_report_shapes():
    s = [{"lock_id": "lock_2", "kind": "tow", "vessel_name": "X", "arrived_at": NOW, "predicted": 60,
          "actual": 50, "error": 10, "in_range": True},
         {"lock_id": "lock_2", "kind": "tow", "vessel_name": "Y", "arrived_at": NOW - timedelta(hours=1),
          "predicted": 20, "actual": 60, "error": -40, "in_range": False}]
    r = W.report(s, {"lock_2": "Lock & Dam #2"})
    assert r["overall"]["n"] == 2 and r["overall"]["mae_minutes"] == 25.0
    assert r["overall"]["within_15_pct"] == 50 and r["overall"]["in_range_pct"] == 50
    assert r["by_kind"]["recreational"] is None
    assert r["by_lock"][0]["lock_name"] == "Lock & Dam #2"
    assert r["recent"][0]["vessel_name"] == "X"
    assert W.summarize([]) is None
