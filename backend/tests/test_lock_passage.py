"""Lock passage state machine (approach -> chamber -> cleared / abandoned)."""
import asyncio
from datetime import datetime, timedelta, timezone

import server

LOCK = "lock_10"
RM = server.LOCKS[LOCK]["river_mile"]


def _run(updates, monkeypatch):
    saved = []

    async def fake_save(lock_id, tracking):
        saved.append((lock_id, dict(tracking)))
    monkeypatch.setattr(server, "save_lockage_record", fake_save)
    server.vessel_lock_tracking.clear()

    async def go():
        for rm, heading in updates:
            await server.track_vessel_lock_passage(
                {"mmsi": "999", "river_mile": rm, "heading": heading, "name": "T"})
    asyncio.run(go())
    return saved


def test_downbound_passage_recorded_even_when_stopped_in_chamber(monkeypatch):
    saved = _run([(RM + 1.5, "southbound"), (RM + 0.1, "stationary"),
                  (RM, "stationary"), (RM - 2.0, "southbound")], monkeypatch)
    assert [s[0] for s in saved] == [LOCK]
    assert saved[0][1]["direction"] == "downbound"
    assert "999" not in server.vessel_lock_tracking  # cleaned up


def test_unknown_heading_does_not_start_tracking(monkeypatch):
    _run([(RM + 1.0, "unknown")], monkeypatch)
    assert "999" not in server.vessel_lock_tracking


def test_stuck_in_chamber_is_abandoned(monkeypatch):
    _run([(RM + 1.0, "southbound"), (RM, "stationary")], monkeypatch)
    entry = server.vessel_lock_tracking["999"][LOCK]
    assert entry["state"] == "in_chamber"
    entry["arrival_time"] = datetime.now(timezone.utc) - timedelta(hours=5)

    async def again():
        await server.track_vessel_lock_passage({"mmsi": "999", "river_mile": RM, "heading": "stationary"})
    asyncio.run(again())
    assert LOCK not in server.vessel_lock_tracking.get("999", {})


def test_passing_without_chamber_fix_is_dropped(monkeypatch):
    saved = _run([(RM + 1.0, "southbound"), (RM - 1.0, "southbound")], monkeypatch)
    assert saved == []
    assert LOCK not in server.vessel_lock_tracking.get("999", {})
