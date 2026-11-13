"""Own-boat track recording for the season log."""
import asyncio
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
server = importlib.import_module("server")


class _Coll:
    def __init__(self, distinct=None):
        self.docs, self._distinct = [], distinct or []

    async def insert_one(self, d):
        self.docs.append(d)

    async def distinct(self, key):
        return self._distinct


class _DB:
    def __init__(self):
        self.boat_tracks = _Coll()
        self.users = _Coll(["338414076"])


def test_records_owned_moving_boats_only(monkeypatch):
    db = _DB()
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "_owned_mmsis", (None, set()))
    monkeypatch.setattr(server, "_track_last", {})
    monkeypatch.setattr(server, "user_vessel_simulation", {})
    run = lambda v: asyncio.run(server._record_track_point(v))
    run({"mmsi": "338414076", "river_mile": 830.3, "lat": 44.85, "lon": -93.01, "speed": 0})
    run({"mmsi": "338414076", "river_mile": 830.35})               # moved 0.05 mi: not yet
    run({"mmsi": "338414076", "river_mile": 830.0})                # moved 0.3 mi: record
    run({"mmsi": "367000001", "river_mile": 800.0})                # someone else's tow
    run({"mmsi": "338414076", "river_mile": 829.0, "is_simulated": True})
    assert [d["rm"] for d in db.boat_tracks.docs] == [830.3, 830.0]
    server.user_vessel_simulation["338414076"] = {"enabled": True}
    run({"mmsi": "338414076", "river_mile": 820.0})
    assert len(db.boat_tracks.docs) == 2
