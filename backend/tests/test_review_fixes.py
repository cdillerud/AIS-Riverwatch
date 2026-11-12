"""Fixes from the 2026-11-12 backend review."""
import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
server = importlib.import_module("server")
from services import live_arrivals as LA  # noqa: E402


def test_eta_with_no_river_mile_is_none_not_a_crash():
    assert server.calculate_eta_to_lock(None, 6, "southbound", 796.9) is None
    assert server.calculate_required_speed(None, "southbound", 796.9, 30) is None
    assert server.calculate_eta_to_lock(800.0, 6, "southbound", 796.9) is not None


class _WS:
    def __init__(self):
        self.sent = []

    async def send_json(self, m):
        self.sent.append(m)


def test_feed_boat_is_yours_only_for_an_admin(monkeypatch):
    mgr = server.ais_manager
    monkeypatch.setattr(mgr, "_config", {"user_mmsi": "338414076"})
    viewer, admin = _WS(), _WS()
    monkeypatch.setattr(mgr, "_subscribers", {viewer: {"mmsi": "", "admin": False},
                                              admin: {"mmsi": "", "admin": True}})
    asyncio.run(mgr._broadcast_vessel_update({"mmsi": "338414076", "name": "REBOOT"}))
    assert viewer.sent[0]["vessel"]["is_user_vessel"] is False
    assert admin.sent[0]["vessel"]["is_user_vessel"] is True


def test_account_boats_are_not_traffic(monkeypatch):
    now = datetime.now(timezone.utc)
    boats = {
        "111": {"mmsi": "111", "river_mile": 800.0, "speed": 6, "is_user_vessel": True, "timestamp": now},
        "222": {"mmsi": "222", "river_mile": 800.0, "speed": 6, "vessel_type": "recreational", "timestamp": now},
        "333": {"mmsi": "333", "river_mile": 800.0, "speed": 6, "ship_type": 31, "timestamp": now},
    }
    monkeypatch.setattr(server, "active_vessels", boats)
    assert [b["mmsi"] for b in server._live_positions(now)] == ["333"]


def test_live_boat_without_a_time_is_not_live():
    now = datetime.now(timezone.utc)
    # A tow 5 mi above Lock 3 (RM 796.9), heading down toward it.
    base = {"mmsi": "333", "name": "TOW", "river_mile": 802.0, "speed": 6.0, "heading": "southbound", "ship_type": 31}
    rms = {"lock_2": 815.2, "lock_3": 796.9, "lock_4": 752.8}
    with_ts = LA.merge_live_arrivals("lock_3", rms, [], [{**base, "timestamp": now}], now)
    no_ts = LA.merge_live_arrivals("lock_3", rms, [], [{**base, "timestamp": None}], now)
    assert [a.get("mmsi") for a in with_ts] == ["333"]
    assert no_ts == []


class _Req:
    pass


def test_planning_views_only_for_your_own_boat(monkeypatch):
    monkeypatch.setattr(server._api_access, "login_required", lambda: True)

    async def me(_):
        return {"user_id": "u1", "role": "user", "vessels": [{"mmsi": "111"}]}
    monkeypatch.setattr(server, "get_current_user", me)
    asyncio.run(server._check_session_owner(_Req(), "111"))
    with pytest.raises(server.HTTPException) as e:
        asyncio.run(server._check_session_owner(_Req(), "222"))
    assert e.value.status_code == 403
    monkeypatch.setattr(server._api_access, "login_required", lambda: False)
    asyncio.run(server._check_session_owner(_Req(), "222"))   # no-login install
