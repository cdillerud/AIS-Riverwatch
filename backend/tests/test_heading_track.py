"""Direction from the vessel's own track beats a single compass reading at bends."""
from datetime import datetime, timedelta, timezone

import server

T0 = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)


def test_track_overrides_course_at_a_bend():
    server._rm_track.pop("T1", None)
    lat, lon = server.river_mile_to_coords(823.0)
    # One southerly reading where the channel runs ENE: course alone says upbound
    assert server.determine_heading(10, 177, lat, lon) == "northbound"
    # ...but the boat has been losing river miles: it is going downstream
    server.heading_with_track("T1", 824.0, 10, 180, *server.river_mile_to_coords(824.0), now=T0)
    assert server.heading_with_track("T1", 823.0, 10, 177, lat, lon, now=T0 + timedelta(minutes=5)) == "southbound"


def test_falls_back_to_course_without_enough_movement():
    server._rm_track.pop("T2", None)
    lat, lon = server.river_mile_to_coords(830.0)
    assert server.heading_with_track("T2", 830.0, 10, 177, lat, lon, now=T0) == "southbound"
    # old points age out of the window
    server.heading_with_track("T3", 830.0, 10, 0, lat, lon, now=T0)
    assert server.heading_with_track("T3", 828.0, 10, 177, lat, lon, now=T0 + timedelta(minutes=30)) == "southbound"
    assert server._rm_track["T3"][0][1] == 828.0


def test_stopped_vessel_is_stationary_and_resets_track():
    server.heading_with_track("T4", 830.0, 10, 177, *server.river_mile_to_coords(830.0), now=T0)
    assert server.heading_with_track("T4", 829.0, 0.1, 177, *server.river_mile_to_coords(829.0), now=T0) == "stationary"
    assert "T4" not in server._rm_track
