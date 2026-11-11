"""Own boat with no live data sits at its home berth, stopped."""
from datetime import datetime, timedelta, timezone

from services import home_berth as H

NOW = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)
HOME = {"lat": 44.855313, "lon": -93.011967, "river_mile": 830.3}   # REBOOT, just above AT EASE
OLD_FIX = {"lat": 44.75, "lon": -92.86, "river_mile": 808.0, "speed": 5.2, "heading_direction": "southbound",
           "last_position_update": (NOW - timedelta(days=2)).isoformat()}


def test_recent_real_fix_wins():
    fix = {**OLD_FIX, "last_position_update": (NOW - timedelta(minutes=20)).isoformat()}
    pos, src = H.position_to_show({"last_position": fix, "home_berth": HOME}, NOW)
    assert src == "last" and pos["river_mile"] == 808.0 and pos["speed"] == 5.2


def test_old_fix_means_back_at_the_slip():
    # The bug: REBOOT frozen at RM 808 "doing 6 mph" from a days-old update.
    pos, src = H.position_to_show({"last_position": OLD_FIX, "home_berth": HOME}, NOW)
    assert src == "home" and pos["river_mile"] == 830.3 and pos["speed"] == 0.0
    assert pos["heading_direction"] == "stationary"


def test_parked_position_never_counts_as_fresh():
    parked = {"lat": HOME["lat"], "lon": HOME["lon"], "river_mile": 830.3, "speed": 0.0}  # no timestamp
    pos, src = H.position_to_show({"last_position": parked, "home_berth": HOME}, NOW)
    assert src == "home"


def test_no_berth_old_fix_is_shown_stopped():
    pos, src = H.position_to_show({"last_position": OLD_FIX}, NOW)
    assert src == "last" and pos["river_mile"] == 808.0 and pos["speed"] == 0.0


def test_nothing_known():
    assert H.position_to_show({}, NOW) == (None, "none")
    pos, src = H.position_to_show({"home_berth": HOME}, NOW)
    assert src == "home"
