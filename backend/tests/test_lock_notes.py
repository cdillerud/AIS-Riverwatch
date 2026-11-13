"""Planning warnings per lock (closed / restricted / no recent lockages)."""
import asyncio
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
server = importlib.import_module("server")


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, docs):
        self.docs = docs

    def find(self, *a, **k):
        return _Cursor(self.docs)


class _DB:
    def __init__(self, docs):
        self.lock_status = _Coll(docs)


def test_only_warnings_become_notes(monkeypatch):
    docs = [
        {"lock_id": "lock_1", "status": "UNKNOWN", "status_source": "lockage_gap", "closure_info": "No lockages in 19 days"},
        {"lock_id": "lock_5", "status": "OPEN", "status_source": "recent_lockage", "closure_info": "Lockage completed 5 min ago"},
        {"lock_id": "lock_14", "status": "CLOSED", "status_source": "district_page", "closure_info": "CLOSED **"},
        {"lock_id": "lock_15", "status": "OPEN", "closure_info": None},
    ]
    monkeypatch.setattr(server, "db", _DB(docs))
    monkeypatch.setattr(server, "_lock_notes_cache", (None, {}))
    notes = asyncio.run(server._lock_notes())
    assert notes == {"lock_1": "No lockages in 19 days", "lock_14": "CLOSED **"}


def test_limit_and_scheduled_closure_notes_are_added(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from services import lock_limits as ll

    now = datetime.now(timezone.utc)
    reading = {"value": 100_000.0, "at": now.isoformat(), "units": "cfs", "change_6h": 0.0}
    monkeypatch.setitem(ll._state, "readings", {"lock_2": {"flow": reading}, "lock_3": {"flow": dict(reading, value=40_000.0)}})
    monkeypatch.setitem(ll._state, "readings_at", now)
    begin = (now + timedelta(hours=10) - timedelta(hours=6)).strftime("%m/%d/%Y %H:%M:%S") + " CST"
    monkeypatch.setitem(ll._state, "stoppages", [{"riverCode": "MI", "lockNumber": "14", "chamberNumber": "1",
                                                   "beginStopDate": begin, "endStopDate": " CST",
                                                   "reasonCode": "Maintaining lock or lock equipment",
                                                   "trafficStopped": "Y"}])
    monkeypatch.setitem(ll._state, "stoppages_at", now)
    docs = [{"lock_id": "lock_14", "status": "OPEN", "closure_info": None},
            {"lock_id": "lock_3", "status": "OPEN", "closure_info": None}]
    monkeypatch.setattr(server, "db", _DB(docs))
    monkeypatch.setattr(server, "_lock_notes_cache", (None, {}))
    notes = asyncio.run(server._lock_notes())
    assert notes["lock_2"] == ("River at 86% of the flow that closes this lock (116,000 cfs) - steady "
                               "(USACE St. Paul District)")
    assert notes["lock_14"].startswith("USACE scheduled closure ")
    assert "lock_3" not in notes   # 32% of 125,000 cfs: no note
