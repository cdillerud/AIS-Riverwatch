"""Lock-first board: wait estimates, ordering, and the API built on USACE data."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from services import lock_board

TYPICAL = {"avg_single_lockage_minutes": 24.0, "avg_double_lockage_minutes": 122.0,
           "avg_recreational_lockage_minutes": 15.0}
NOW = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)


def test_double_cut_rules():
    assert lock_board.needs_double("lock_14", 15)
    assert not lock_board.needs_double("lock_14", 6)
    assert not lock_board.needs_double("lock_19", 15)          # 1,200 ft chamber
    assert not lock_board.needs_double("lock_14", 0)


def test_wait_estimate_counts_remaining_lockage_and_queue():
    locking = [{"barges": 15, "started_at": NOW - timedelta(minutes=100)}]   # 22 min left of 122
    waiting = [{"barges": 6}, {"barges": 0}]                                   # 24 + 15
    assert lock_board.estimate_wait("lock_14", locking, waiting, TYPICAL, NOW) == 61
    assert lock_board.estimate_wait("lock_14", [], [], TYPICAL, NOW) == 0
    overdue = [{"barges": 15, "started_at": NOW - timedelta(minutes=300)}]
    assert lock_board.estimate_wait("lock_14", overdue, [], TYPICAL, NOW) == 0


def test_locks_ahead_of_the_boat():
    locks = [{"lock_id": "a", "river_mile": 800}, {"lock_id": "b", "river_mile": 600},
             {"lock_id": "c", "river_mile": 400}]
    down = lock_board.locks_in_view(locks, 700, "downbound", "ahead")
    assert [lk["lock_id"] for lk in down] == ["b", "c"]
    up = lock_board.locks_in_view(locks, 500, "upbound", "ahead")
    assert [lk["lock_id"] for lk in up] == ["b", "a"]
    every = lock_board.locks_in_view(locks, None, None, "all")
    assert [lk["lock_id"] for lk in every] == ["a", "b", "c"]


def test_board_endpoint_from_usace_queue(monkeypatch):
    import server

    async def status():
        return {"lock_14": server.LockStatus(lock_id="lock_14", status="OPEN", status_source="district_page")}

    async def averages(lock_id=None):
        return {"lock_14": {**TYPICAL, "sample_count": 66, "is_baseline": False}}

    class Agg:
        async def to_list(self, n):
            return []

    class Coll:
        def aggregate(self, p):
            return Agg()

    class FakeDB:
        lockage_history = Coll()

    monkeypatch.setattr(server, "fetch_usace_lock_status", status)
    monkeypatch.setattr(server, "get_lockage_averages", averages)
    monkeypatch.setattr(server, "db", FakeDB())
    monkeypatch.setitem(server.usace_lock_rows, "14", [
        {"vessel_name": "WISCONSIN", "mmsi": "367505680", "direction": "D", "num_barges": 15,
         "status": "waiting", "arrival_date": "11/10/26 10:49", "timezone": "CST"},
    ])
    client = TestClient(server.app)
    r = client.get("/api/locks/board", params={"from_rm": 520, "direction": "downbound", "scope": "ahead", "limit": 3})
    assert r.status_code == 200
    locks = r.json()["locks"]
    assert locks[0]["lock_id"] == "lock_14" and locks[0]["status"] == "OPEN"
    assert locks[0]["waiting"][0]["vessel_name"] == "WISCONSIN" and locks[0]["waiting"][0]["needs_double"]
    assert locks[0]["queue_minutes"] == 122                       # raw: one double lockage ahead
    waiting = [{"barges": 15, "direction": "downbound"}]
    feats = lock_board.queue_features("lock_14", [], waiting, {**TYPICAL, "sample_count": 66, "is_baseline": False},
                                      "downbound", 122, 0)
    assert locks[0]["wait_estimate_minutes"] == round(lock_board.tow_wait(feats))    # calibrated tow wait
    rec = lock_board.CALIBRATION["recreational"]
    assert locks[0]["wait_estimate_recreational_minutes"] == round(rec["intercept"] + rec["slope"] * 122)
    assert len(locks) == 3 and all(lk["river_mile"] < 520 for lk in locks)
    assert client.get("/api/locks/board", params={"direction": "sideways"}).status_code == 400


def test_traffic_summary_counts_only_the_watched_lock(monkeypatch):
    import server

    now = datetime.now(timezone.utc)

    def boat(mmsi, rm, heading):
        return server.VesselPosition(mmsi=mmsi, name=mmsi, lat=0.0, lon=0.0, speed=5.0, course=0.0,
                                     river_mile=rm, heading=heading, timestamp=now)

    class Cursor:
        def sort(self, *a):
            return self

        def limit(self, n):
            return self

        async def to_list(self, length):
            return []

    class Coll:
        def find(self, *a, **k):
            return Cursor()

    class FakeDB:
        lockage_history = Coll()

    monkeypatch.setattr(server, "db", FakeDB())
    monkeypatch.setattr(server, "active_vessels", {
        "1": boat("1", 500.0, "southbound"),    # 7 mi above Lock 14 (RM 493): counted
        "2": boat("2", 840.0, "southbound"),    # Twin Cities: not counted
        "3": boat("3", 490.0, "northbound"),    # near, and also in the USACE queue
    })
    monkeypatch.setitem(server.usace_lock_rows, "14", [
        {"vessel_name": "THREE", "mmsi": "3", "direction": "U", "status": "waiting"},
        {"vessel_name": "QUEUE ONLY", "mmsi": "9", "direction": "D", "status": "waiting"},
    ])
    data = TestClient(server.app).get("/api/traffic-summary/lock_14").json()
    assert data["total_vessels"] == 3                # 1, 3 (once), 9
    assert data["southbound"] == 2 and data["northbound"] == 1
    assert data["feed_vessels"] == 3 and data["at_lock_usace"] == 2


def test_calibrated_waits():
    empty = lock_board.predict_waits("lock_14", [], [], TYPICAL, None, NOW)
    assert empty["queue_minutes"] == 0 and 0 <= empty["tow"] <= 30 and empty["recreational"] <= 10
    waiting = [{"barges": 15, "direction": "downbound"}, {"barges": 15, "direction": "downbound"}]
    same = lock_board.predict_waits("lock_14", [], waiting, TYPICAL, "downbound", NOW)
    opposite = lock_board.predict_waits("lock_14", [], waiting, TYPICAL, "upbound", NOW)
    unknown = lock_board.predict_waits("lock_14", [], waiting, TYPICAL, None, NOW)
    assert same["tow"] > empty["tow"]
    assert opposite["tow"] > same["tow"]                 # locks alternate: the other direction costs more
    assert same["tow"] <= unknown["tow"] <= opposite["tow"]
    assert same["recreational"] > opposite["recreational"]  # pleasure craft: only the same-direction queue


def test_v1_models_still_predict():
    v1 = {"tow": {"intercept": 26.5, "slope": 1.264, "empty_lock": 10.0}}
    assert lock_board.tow_wait({"v0": 100.0, "empty": 0.0}, v1) == 26.5 + 126.4
    assert lock_board.tow_wait({"v0": 0.0, "empty": 1.0}, v1) == 10.0


def test_wait_at_arrival_counts_tows_that_get_there_first():
    from datetime import timedelta
    typical = {"avg_single_lockage_minutes": 30.0, "avg_double_lockage_minutes": 120.0,
               "avg_recreational_lockage_minutes": 15.0}
    approaching = [
        {"vessel_name": "SOON", "barges": 15, "eta": NOW + timedelta(minutes=30)},   # double, ahead of us
        {"vessel_name": "LATE", "barges": 15, "eta": NOW + timedelta(minutes=300)},  # after us: ignored
    ]
    arrive = NOW + timedelta(minutes=60)
    sim = lock_board.queue_minutes_at("lock_14", [], [], approaching, typical, arrive, NOW)
    assert [v["vessel_name"] for v in sim["ahead"]] == ["SOON"]
    assert sim["queue_minutes"] == 90            # SOON locks 0:30-2:30; we arrive at 1:00
    empty = lock_board.queue_minutes_at("lock_14", [], [], [], typical, arrive, NOW)
    assert empty == {"queue_minutes": 0, "ahead": []}
    # Within 90 min the queue as it stands is used (backtest: better close in)
    near = lock_board.predict_waits_at("lock_14", [], [], approaching, typical, arrive, NOW)
    assert near["ahead_count"] == 1 and near["ahead"][0]["predicted"] is True
    assert near["tow"] == lock_board.predict_waits("lock_14", [], [], typical, None, NOW)["tow"]
    # Further out the lock is simulated forward with the vessels expected ahead
    far_arrive = NOW + timedelta(minutes=120)
    far = lock_board.predict_waits_at("lock_14", [], [], approaching, typical, far_arrive, NOW)
    q = lock_board.queue_minutes_at("lock_14", [], [], approaching, typical, far_arrive, NOW)["queue_minutes"]
    feats = lock_board.queue_features("lock_14", [], [approaching[0]], typical, None, q, 0.0)
    assert far["tow"] == round(lock_board.tow_wait(feats)) and q == 30
    later = lock_board.predict_waits_at("lock_14", [], [], approaching, typical, NOW + timedelta(minutes=600), NOW)
    assert later["ahead_count"] == 2
