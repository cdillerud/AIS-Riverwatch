"""Backend efficiency changes (2026-11-12 review)."""
import asyncio
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
server = importlib.import_module("server")

REC = {"lock_id": "lock_2", "vessel_name": "STARFIRE", "usace_vessel_no": "123", "entry_time": 1, "exit_time": 2}


class _Coll:
    def __init__(self):
        self.batches = []

    async def bulk_write(self, ops, ordered=False):
        self.batches.append(len(ops))


class _DB:
    def __init__(self):
        self.lockage_history = _Coll()


def test_usace_rows_are_written_only_when_new_or_changed(monkeypatch):
    db = _DB()
    feed = [REC]
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "_usace_stored", {})
    monkeypatch.setattr(server, "usace_lock_id", lambda n: "lock_2")
    monkeypatch.setattr(server._usace_lockages, "completed_lockages", lambda rows, lid, name: [dict(r) for r in feed])
    assert asyncio.run(server._store_usace_lockages([], "02")) == 1
    assert asyncio.run(server._store_usace_lockages([], "02")) == 0      # same row again: no write
    feed[:] = [{**REC, "exit_time": 3}]                                   # second cut finished
    assert asyncio.run(server._store_usace_lockages([], "02")) == 1
    assert db.lockage_history.batches == [1, 1]


def test_usace_name_forms_are_indexed(monkeypatch):
    info = {"vessel_name": "MV CAPT-JOHN", "status": "waiting", "lock_id": "lock_2"}
    monkeypatch.setattr(server, "usace_lock_rows", {"02": [info]})
    monkeypatch.setattr(server, "usace_lock_queue_cache", {})
    server._rebuild_usace_indexes()
    assert server.get_usace_vessel_info(mmsi="", vessel_name="CAPT JOHN") is info
    assert server.get_usace_vessel_info(mmsi="", vessel_name="MV CAPT JOHN") is info
    assert server.get_usace_vessel_info(mmsi="", vessel_name="SOMEONE ELSE") is None
