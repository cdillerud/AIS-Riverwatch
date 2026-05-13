"""Regression tests for the vessel-display hygiene cleanup.

Covers:
  1. /api/vessels never marks vessels as is_user_vessel=True
  2. Demo vessels are auto-suppressed once a live AIS update has been seen
     (when DEMO_VESSELS_MODE == 'auto')
  3. Stale vessels are removed by _prune_stale_vessels
  4. Filtered MMSIs (FILTERED_MMSI) are blocked before being added
"""
from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

server = importlib.import_module("server")


def _reset_live_state():
    server.live_ais_state["last_seen"] = None
    server.live_ais_state["lines_received"] = 0
    server.live_ais_state["last_mmsi"] = None


def _clear_active():
    server.active_vessels.clear()


def test_filtered_mmsi_blocked():
    assert server.is_mmsi_blocked("2339005") is True
    assert server.is_mmsi_blocked("367505810") is False


def test_record_live_event_and_suppression():
    _reset_live_state()
    _clear_active()
    server.DEMO_VESSELS_MODE = "auto"

    assert server._should_suppress_demo_vessels() is False
    server._record_live_ais_event("367505810")
    assert server._should_suppress_demo_vessels() is True

    # Demo MMSIs must NOT trigger live AIS state changes
    _reset_live_state()
    server._record_live_ais_event("DEMO001")
    assert server.live_ais_state["last_seen"] is None
    assert server._should_suppress_demo_vessels() is False


def test_demo_mode_on_off():
    _reset_live_state()
    server.DEMO_VESSELS_MODE = "on"
    assert server._should_suppress_demo_vessels() is False
    server.DEMO_VESSELS_MODE = "off"
    assert server._should_suppress_demo_vessels() is True
    server.DEMO_VESSELS_MODE = "auto"


def test_is_demo_vessel_helper():
    assert server._is_demo_vessel({"is_demo": True}, "DEMO001") is True
    assert server._is_demo_vessel({}, "DEMO002") is True
    assert server._is_demo_vessel({"is_demo": False}, "367505810") is False


def test_prune_stale_vessels_removes_old_entries():
    _clear_active()

    class _Stub:
        def __init__(self, mmsi, ts):
            self.mmsi = mmsi
            self.timestamp = ts

    now = datetime.now(timezone.utc)
    server.active_vessels["366967104"] = _Stub("366967104", now - timedelta(hours=1))
    server.active_vessels["367505810"] = _Stub("367505810", now - timedelta(seconds=10))

    removed = server._prune_stale_vessels(max_age_seconds=600)
    assert "366967104" in removed
    assert "367505810" not in removed
    assert "367505810" in server.active_vessels
    assert "366967104" not in server.active_vessels


def test_prune_stale_skips_demo_and_protected():
    _clear_active()

    class _Stub:
        def __init__(self, mmsi, ts):
            self.mmsi = mmsi
            self.timestamp = ts

    old = datetime.now(timezone.utc) - timedelta(hours=2)
    # demo vessel - must be retained
    server.active_vessels["DEMO001"] = _Stub("DEMO001", old)
    # protected user MMSI - must be retained
    server.active_vessels["368273170"] = _Stub("368273170", old)
    # arbitrary stale vessel - must be removed
    server.active_vessels["366967104"] = _Stub("366967104", old)

    removed = server._prune_stale_vessels(
        max_age_seconds=600, protect_mmsis={"368273170"}
    )

    assert "DEMO001" in server.active_vessels
    assert "368273170" in server.active_vessels
    assert "366967104" in removed
    assert "366967104" not in server.active_vessels


def test_prepare_vessel_for_output_no_session():
    """A vessel produced via prepare_vessel_for_output(..., None) must NOT be is_user."""
    class _V:
        def model_dump(self):
            return {"mmsi": "367505810", "name": "TEST", "lat": 44.0, "lon": -92.0,
                    "speed": 5.0, "course": 180.0, "river_mile": 800.0}

    out = server.prepare_vessel_for_output(_V(), None)
    assert out["is_user_vessel"] is False

    out2 = server.prepare_vessel_for_output(_V(), "367505810")
    assert out2["is_user_vessel"] is True
