"""Live AIS outranks typed-in, phone-GPS, simulated and restored positions."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import server
from services import live_ais as L

NOW = datetime(2026, 11, 11, 16, 0, tzinfo=timezone.utc)
TOW = "366967590"
OWNER = {"user_id": "u_claimer", "vessels": [{"mmsi": TOW}]}
POS = {"lat": 44.75, "lon": -92.85, "speed": 0, "course": 0, "source": "manual"}


@pytest.fixture(autouse=True)
def _clean():
    L.reset()
    yield
    L.reset()


def test_window():
    assert L.refusal(TOW, NOW) is None                       # never heard
    L.record_position(TOW, NOW - timedelta(seconds=20))
    assert L.on_live_ais(TOW, NOW)
    assert "just now" in L.refusal(TOW, NOW)
    assert "9 min ago" in L.refusal(TOW, NOW + timedelta(minutes=9))
    assert L.refusal(TOW, NOW + timedelta(minutes=11)) is None  # out of range: owner's GPS again
    assert L.refusal("367000000", NOW) is None                # other boats unaffected


def test_claimed_towboat_cannot_be_moved_while_on_ais(monkeypatch):
    L.record_position(TOW)
    with pytest.raises(HTTPException) as e:
        asyncio.run(server.update_session_position(TOW, dict(POS), OWNER))
    assert e.value.status_code == 409 and "live AIS" in e.value.detail

    admin = {"user_id": "u_admin", "is_admin": True}
    with pytest.raises(HTTPException) as e:
        asyncio.run(server.update_session_position(TOW, dict(POS), admin))
    assert e.value.status_code == 409


def test_simulation_does_not_overwrite_a_live_ais_boat(monkeypatch):
    sentinel = object()
    monkeypatch.setitem(server.active_vessels, TOW, sentinel)
    L.record_position(TOW)
    asyncio.run(server._update_simulated_user_vessel(
        TOW, {"enabled": True, "river_mile": 820.0, "speed_knots": 8.0, "heading": "southbound"}))
    assert server.active_vessels[TOW] is sentinel


def test_ais_report_marks_the_boat_live(monkeypatch):
    async def noop(*a, **k):
        return None

    mgr = server.AISConnectionManager()
    monkeypatch.setattr(mgr, "_broadcast_vessel_update", noop)
    monkeypatch.setattr(server, "track_vessel_lock_passage", noop)
    monkeypatch.setattr(server, "track_ais_inferred_lockage", noop)
    monkeypatch.setattr(server, "is_on_upper_mississippi", lambda lat, lon: True)
    monkeypatch.setattr(server, "is_mmsi_blocked", lambda m: False)
    monkeypatch.delitem(server.active_vessels, TOW, raising=False)

    asyncio.run(mgr.ingest_vessel_data({"mmsi": TOW, "lat": 44.75, "lon": -92.85, "speed": 5.0,
                                        "course": 120.0, "name": "DANIEL P MECKLENBORG"}))
    assert L.on_live_ais(TOW)
    server.active_vessels.pop(TOW, None)
