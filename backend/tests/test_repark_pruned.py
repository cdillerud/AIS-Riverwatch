"""A parked boat sends no updates; when the stale sweep drops it, it goes back
to its home berth instead of vanishing until the next page load."""
import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
server = importlib.import_module("server")

HOME = {"lat": 44.855313, "lon": -93.011967, "river_mile": 830.3}
NOW = datetime.now(timezone.utc)


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


class _Users:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection=None):
        wanted = set(query["vessels.mmsi"]["$in"])
        return _Cursor(d for d in self.docs if any(v["mmsi"] in wanted for v in d["vessels"]))


class _DB:
    def __init__(self, docs):
        self.users = _Users(docs)


def _run(monkeypatch, vessels, removed, sim=None):
    parked_calls = []

    async def fake_park(mmsi):
        parked_calls.append(mmsi)
        return True

    monkeypatch.setattr(server, "db", _DB([{"vessels": vessels}]))
    monkeypatch.setattr(server, "_park_at_home", fake_park)
    monkeypatch.setattr(server, "user_vessel_simulation", sim or {})
    server.active_vessels.clear()
    return asyncio.run(server._repark_pruned(removed)), parked_calls


def test_parked_boat_goes_back_to_its_berth(monkeypatch):
    parked, calls = _run(monkeypatch, [{"mmsi": "338414076", "home_berth": HOME,
                                        "last_position": {**HOME, "speed": 0.0}}], ["338414076"])
    assert parked == ["338414076"] and calls == ["338414076"]


def test_recent_real_fix_stays_pruned(monkeypatch):
    fix = {"lat": 44.7, "lon": -92.9, "speed": 6.0,
           "last_position_update": (NOW - timedelta(minutes=20)).isoformat()}
    parked, calls = _run(monkeypatch, [{"mmsi": "338414076", "home_berth": HOME,
                                        "last_position": fix}], ["338414076"])
    assert parked == [] and calls == []


def test_no_berth_or_simulated_or_not_pruned_is_left_alone(monkeypatch):
    vessels = [{"mmsi": "111", "last_position": {"lat": 44.0, "lon": -92.0}},   # no berth
               {"mmsi": "222", "home_berth": HOME},                              # simulated
               {"mmsi": "333", "home_berth": HOME}]                              # not pruned
    parked, calls = _run(monkeypatch, vessels, ["111", "222"],
                         sim={"222": {"enabled": True}})
    assert parked == [] and calls == []
