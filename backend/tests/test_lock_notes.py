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
