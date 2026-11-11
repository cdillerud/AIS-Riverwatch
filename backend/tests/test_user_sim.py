"""Simulated own boat: moves, stops at locks, carries on."""
import asyncio
from datetime import datetime, timedelta, timezone

from services import user_sim as S

T0 = datetime(2026, 11, 11, 17, 0, tzinfo=timezone.utc)
LOCKS = [796.9, 815.2]  # L3, L2


def sim(**kw):
    s = {"enabled": True, "river_mile": 816.0, "speed_knots": 10.0, "heading": "southbound"}
    s.update(kw)
    return s


def test_moves_downbound_and_upbound():
    s = S.step(sim(river_mile=830.0), LOCKS, 360, T0)          # 10 kn = 11.5 mph, 6 min
    assert abs(s["river_mile"] - (830.0 - 1.15078)) < 1e-6
    s = S.step(sim(river_mile=800.0, heading="northbound"), LOCKS, 360, T0)
    assert abs(s["river_mile"] - 801.15078) < 1e-6


def test_stops_at_the_lock_then_carries_on():
    s = S.step(sim(river_mile=815.5, lock_dwell_minutes=20), LOCKS, 360, T0)
    assert s["river_mile"] == 815.2 and s["holding"]               # parked at L2
    s = S.step(s, LOCKS, 10, T0 + timedelta(minutes=19))
    assert s["river_mile"] == 815.2 and s["holding"]               # still locking
    s = S.step(s, LOCKS, 360, T0 + timedelta(minutes=21))
    assert not s["holding"] and s["river_mile"] < 815.2            # through, downbound
    assert abs(s["river_mile"] - (815.2 - 1.15078)) < 1e-6         # no second stop at L2


def test_upbound_stops_at_the_first_lock_reached():
    s = S.step(sim(river_mile=790.0, heading="northbound", speed_knots=2000), LOCKS, 3600, T0)
    assert s["river_mile"] == 796.9                                # L3 before L2


def test_dwell_zero_glides_through_and_stopped_boat_stays():
    s = S.step(sim(river_mile=815.5, lock_dwell_minutes=0), LOCKS, 360, T0)
    assert s["river_mile"] < 815.2 and not s.get("holding")
    s = S.step(sim(speed_knots=0), LOCKS, 360, T0)
    assert s["river_mile"] == 816.0
    s = S.step(sim(enabled=False), LOCKS, 360, T0)
    assert s["river_mile"] == 816.0


def test_held_boat_reports_zero_speed(monkeypatch):
    import server
    s = sim(river_mile=815.2, holding=True)
    monkeypatch.delitem(server.active_vessels, "338414076", raising=False)
    asyncio.run(server._update_simulated_user_vessel("338414076", s))
    assert server.active_vessels["338414076"]["speed"] == 0.0
    server.active_vessels.pop("338414076", None)
