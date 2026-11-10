"""The shared AIS feed is owned by the server; viewers only subscribe."""
import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient

import server

client = TestClient(server.app)  # no context manager: startup (DB) hooks not run


def test_dashboard_websocket_cannot_repoint_the_feed(monkeypatch):
    calls = []

    async def fake_configure(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(server.ais_manager, "configure", fake_configure)
    monkeypatch.setattr(server.ais_manager, "_config", {"ip_address": "192.168.1.104", "port": 5353})

    with client.websocket_connect("/ws/ais") as ws:
        # A stale browser config (the old Docker default) asks for another target.
        ws.send_json({"action": "connect", "ip_address": "ais-relay", "port": 5353,
                      "user_mmsi": "338414876", "boat_name": "REBOOT"})
        status = ws.receive_json()
        assert status["type"] in ("connected", "disconnected")
        assert ws.receive_json()["type"] == "vessels"

    assert calls == []
    assert server.ais_manager._config["ip_address"] == "192.168.1.104"
    assert server.vessel_static_cache["338414876"]["name"] == "REBOOT"


def test_late_static_data_names_a_vessel_already_on_the_map(monkeypatch):
    mmsi = "367729030"
    now = datetime.now(timezone.utc)
    vessel = server.VesselPosition(mmsi=mmsi, name="", lat=44.75, lon=-92.85, speed=0.0, course=0.0,
                                   river_mile=840.0, heading="stationary", timestamp=now)
    monkeypatch.setitem(server.active_vessels, mmsi, vessel)
    sent = []

    async def fake_broadcast(v):
        sent.append(v)

    monkeypatch.setattr(server.ais_manager, "_broadcast_vessel_update", fake_broadcast)

    asyncio.run(server.ais_manager._apply_static_to_active(mmsi, {"name": "ANSON NORTHRUP", "ship_type": 52}))
    assert server.active_vessels[mmsi].name == "ANSON NORTHRUP"
    assert len(sent) == 1 and sent[0]["name"] == "ANSON NORTHRUP"

    # Same data again: nothing changed, nothing re-broadcast.
    asyncio.run(server.ais_manager._apply_static_to_active(mmsi, {"name": "ANSON NORTHRUP", "ship_type": 52}))
    assert len(sent) == 1


AIVDO_OWN = "!AIVDO,1,1,,,13u?etPv2;0n:dDPwUM1U1Cb069D,0*67"


def test_own_ship_aivdo_is_adopted_and_never_channel_filtered(monkeypatch):
    from pyais import decode
    own_mmsi = str(decode(AIVDO_OWN).asdict()["mmsi"])
    mgr = server.AISConnectionManager()
    mgr._config = {"ip_address": "x", "port": 1, "user_mmsi": "", "boat_name": ""}
    sent = []

    async def fake_broadcast(v):
        sent.append(v)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(mgr, "_broadcast_vessel_update", fake_broadcast)
    monkeypatch.setattr(server, "broadcast_raw_line", noop)
    monkeypatch.setattr(server, "is_on_upper_mississippi", lambda lat, lon: False)  # e.g. in a marina
    monkeypatch.delitem(server.active_vessels, own_mmsi, raising=False)
    monkeypatch.setattr(server, "is_mmsi_blocked", lambda m: False)

    asyncio.run(mgr._process_line(AIVDO_OWN))

    assert mgr._config["user_mmsi"] == own_mmsi
    assert own_mmsi in server.active_vessels
    assert sent and sent[-1]["mmsi"] == own_mmsi
    server.active_vessels.pop(own_mmsi, None)
