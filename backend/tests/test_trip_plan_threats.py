"""Trip plan: a tow that will already be through the lock is not a threat."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

import server


def _boat(mmsi, rm, knots, heading, barges=None, is_tow=True):
    v = server.VesselPosition(mmsi=mmsi, name=mmsi, lat=0.0, lon=0.0, speed=knots, course=180.0,
                              river_mile=rm, heading=heading, timestamp=datetime.now(timezone.utc))
    v.is_tow = is_tow
    v.barge_count = barges
    return v


def _plan(monkeypatch, vessels, lock_id="lock_3"):
    async def averages(lock_id=None):
        return {"lock_3": {"avg_single_lockage_minutes": 27.0, "avg_double_lockage_minutes": 124.0,
                           "avg_tow_lockage_minutes": 60.0, "avg_recreational_lockage_minutes": 15.0}}
    monkeypatch.setattr(server, "get_lockage_averages", averages)
    monkeypatch.setattr(server, "active_vessels", vessels)
    r = TestClient(server.app).get("/api/session/338414076/trip-plan", params={"max_locks": 3})
    assert r.status_code == 200, r.text
    return next(leg for leg in r.json()["legs"] if leg["lock_id"] == lock_id)


def test_tow_through_the_lock_before_user_arrives_is_not_a_threat(monkeypatch, signed_in):
    # User RM 830 downbound ~12 mph -> Lock 3 (RM 796.9) in ~2h46m.
    # MARY J 0.5 mi above Lock 3, 3.1 mph: there in ~10 min, through in ~1 h.
    leg = _plan(monkeypatch, {
        "338414076": _boat("338414076", 830.0, 10.43, "southbound", is_tow=False),
        "MARYJ": _boat("MARYJ", 797.4, 2.7, "southbound", barges=15),
    })
    assert leg["lock_id"] == "lock_3"
    assert leg["threatening_vessel"] is None and leg["status"] == "clear"


def test_tow_still_locking_when_user_arrives_is_a_threat_with_delay(monkeypatch, signed_in):
    # User 5 mi above Lock 3 at ~12 mph (~25 min); a 15-barge double reaches it in ~10 min
    # and needs ~2 h: the user will be held up.
    leg = _plan(monkeypatch, {
        "338414076": _boat("338414076", 801.9, 10.43, "southbound", is_tow=False),
        "BIGTOW": _boat("BIGTOW", 797.4, 2.7, "southbound", barges=15),
    })
    assert leg["threatening_vessel"]["mmsi"] == "BIGTOW"
    assert leg["status"] in ("cant_beat", "speed_up")
    assert leg["expected_delay_minutes"] > 60
