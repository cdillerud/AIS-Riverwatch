"""A vessel is drawn 'in the lock' only when USACE shows its lockage under way
and its own position is at that lock."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
server = importlib.import_module("server")

LOCKING = {"status": "locking", "lock_id": "lock_14", "sol_date": "11/11/26 15:35",
           "timezone": "CST", "cuts_completed": 0}
L2 = server.LOCKS["lock_2"]


def test_locking_at_the_lock():
    f = server._in_lock_fields(LOCKING, {"river_mile": 493.1})     # L14 is RM 493.0
    assert f["in_lock"] and f["in_lock_id"] == "lock_14" and f["in_lock_cut"] == 1
    assert f["in_lock_since"] == "2026-11-11T21:35:00+00:00"  # 15:35 CST


def test_second_cut_of_a_double():
    assert server._in_lock_fields({**LOCKING, "cuts_completed": 1}, {"river_mile": 493.0})["in_lock_cut"] == 2


def test_not_in_lock():
    assert not server._in_lock_fields({**LOCKING, "status": "waiting"}, {"river_mile": 493.0})["in_lock"]
    assert not server._in_lock_fields(None, {"river_mile": 493.0})["in_lock"]
    # Stale queue row: the boat's own position is miles from that lock.
    assert not server._in_lock_fields(LOCKING, {"river_mile": 488.0})["in_lock"]
    # No position to check against: trust USACE.
    assert server._in_lock_fields(LOCKING, {"river_mile": None})["in_lock"]


def test_position_check_without_river_mile():
    """river_mile is often unset; fall back to the AIS position."""
    row = {**LOCKING, "lock_id": "lock_2"}
    near = {"river_mile": None, "lat": L2["lat"] + 0.001, "lon": L2["lon"]}
    far = {"river_mile": None, "lat": L2["lat"] + 0.025, "lon": L2["lon"]}   # ~1.7 mi
    assert server._in_lock_fields(row, near)["in_lock"]
    assert not server._in_lock_fields(row, far)["in_lock"]


def test_pleasure_boat_in_a_recreational_lockage(monkeypatch):
    rec = {"status": "locking", "lock_id": "lock_2", "vessel_name": "RECREATIONAL VESSEL",
           "sol_date": "11/11/26 15:35", "timezone": "CST", "cuts_completed": 0}
    monkeypatch.setattr(server, "usace_lock_rows", {"02": [rec]})
    boat = {"lat": L2["lat"] + 0.002, "lon": L2["lon"], "speed": 0.3}
    f = server._recreational_in_lock_fields(boat)
    assert f["in_lock"] and f["in_lock_id"] == "lock_2"
    # Moving past, too far away, or the lockage is a tow's: not in the lock.
    assert not server._recreational_in_lock_fields({**boat, "speed": 6.0})["in_lock"]
    assert not server._recreational_in_lock_fields({**boat, "lat": L2["lat"] + 0.02})["in_lock"]
    monkeypatch.setattr(server, "usace_lock_rows", {"02": [{**rec, "vessel_name": "STARFIRE"}]})
    assert not server._recreational_in_lock_fields(boat)["in_lock"]
