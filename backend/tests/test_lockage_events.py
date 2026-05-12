# River Watch - Tests for the AIS-inferred lockage dwell tracker
#
# Run with:  cd /app/backend && python -m pytest tests/test_lockage_events.py -q

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
import pytest

# Allow `import server` when run from /app/backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    server.ais_dwell_sessions.clear()
    yield
    server.ais_dwell_sessions.clear()


def _vessel(mmsi, name, rm, speed=0.0, heading="northbound"):
    return {
        "mmsi": mmsi,
        "name": name,
        "river_mile": rm,
        "speed": speed,
        "heading": heading,
        "is_tow": True,
        "barge_count": 6,
    }


def test_dwell_opens_session_when_vessel_idles_in_lock_zone():
    asyncio.run(server.track_ais_inferred_lockage(
        _vessel("TEST1", "M/V DWELL", rm=815.2, speed=0.1, heading="northbound")
    ))
    keys = [k for k in server.ais_dwell_sessions if k[0] == "TEST1"]
    assert keys, f"expected dwell session for TEST1, got {list(server.ais_dwell_sessions)}"
    session = server.ais_dwell_sessions[keys[0]]
    assert session["vessel_name"] == "M/V DWELL"
    assert session["direction_at_entry"] == "upbound"


def test_dwell_ignored_when_speed_above_threshold():
    asyncio.run(server.track_ais_inferred_lockage(
        _vessel("TEST2", "M/V FAST", rm=815.2, speed=2.0)
    ))
    keys = [k for k in server.ais_dwell_sessions if k[0] == "TEST2"]
    assert not keys, "fast-moving vessel should not open a dwell session"


def test_dwell_writes_record_when_exited_after_min_duration(monkeypatch):
    inserted = []

    class _FakeColl:
        async def insert_one(self, doc):
            inserted.append(doc)

    monkeypatch.setattr(server.db, "lockage_history", _FakeColl())

    # Open session
    asyncio.run(server.track_ais_inferred_lockage(
        _vessel("TEST3", "M/V LOCK", rm=815.21, speed=0.1)
    ))
    keys = [k for k in server.ais_dwell_sessions if k[0] == "TEST3"]
    assert keys, "session should be open"
    sess = server.ais_dwell_sessions[keys[0]]

    # Backdate start_time so duration crosses the 60s threshold
    sess["start_time"] = datetime.now(timezone.utc) - timedelta(seconds=90)

    # Vessel leaves the dwell zone
    asyncio.run(server.track_ais_inferred_lockage(
        _vessel("TEST3", "M/V LOCK", rm=816.0, speed=1.5)
    ))

    assert len(inserted) == 1, f"expected one record, got {inserted}"
    rec = inserted[0]
    assert rec["lock_id"] == "lock_2"
    assert rec["mmsi"] == "TEST3"
    assert rec["source"] == "ais_inferred"
    assert rec["confidence"] == "medium"
    assert rec["lockage_duration_minutes"] >= 1.0
    # Session should be cleaned up
    assert not [k for k in server.ais_dwell_sessions if k[0] == "TEST3"]


def test_dwell_skips_record_when_below_min_duration(monkeypatch):
    inserted = []

    class _FakeColl:
        async def insert_one(self, doc):
            inserted.append(doc)

    monkeypatch.setattr(server.db, "lockage_history", _FakeColl())

    asyncio.run(server.track_ais_inferred_lockage(
        _vessel("TEST4", "M/V BRIEF", rm=815.2, speed=0.1)
    ))
    # Immediately leave - very short dwell
    asyncio.run(server.track_ais_inferred_lockage(
        _vessel("TEST4", "M/V BRIEF", rm=816.5, speed=2.0)
    ))
    assert not inserted, "brief dwell should not generate a record"
