"""River mile / direction / channel tests against the USACE sailing line."""
import json

import pytest

from services import river_geometry as g
from config import is_on_upper_mississippi


def test_every_lock_projects_to_its_official_river_mile():
    for lock in g.official_lock_links():
        rm = g.river_mile(lock["lat"], lock["lon"])
        assert rm is not None, lock["name"]
        assert lock["rm_lower"] - 0.25 <= rm <= lock["rm_upper"] + 0.25, (lock["name"], rm)


@pytest.mark.parametrize("lat,lon,official", [
    # Places the old latitude formula got wrong by 12-19 river miles.
    (44.32422, -91.92108, 752.8),  # Lock 4, Alma (old formula: 772.0)
    (43.86438, -91.30794, 702.0),  # Lock 7, Dresbach (old: 720.1)
    (41.42684, -91.0123, 457.2),   # Lock 16, Muscatine (old: 474.9)
])
def test_former_worst_cases_now_accurate(lat, lon, official):
    assert g.river_mile(lat, lon) == pytest.approx(official, abs=0.3)


def test_quad_cities_westward_travel_is_downbound():
    # The river flows WEST through the Quad Cities; compass logic called this "northbound".
    assert g.travel_direction(270, 41.52, -90.53) == "downbound"
    assert g.heading_label(8, 270, 41.52, -90.53) == "southbound"
    assert g.heading_label(8, 90, 41.52, -90.53) == "northbound"


def test_heading_edge_cases():
    assert g.heading_label(0.2, 180, 44.5, -92.2) == "stationary"
    assert g.heading_label(None, 180) == "stationary"
    assert g.heading_label(6, 360) == "unknown"     # AIS COG 360 = not available
    assert g.heading_label(6, None) == "unknown"
    assert g.heading_label(6, 0) == "northbound"     # no position: compass fallback
    assert g.heading_label(6, 180, 45.056, -92.80) == "unknown"  # St. Croix: not Mississippi


def test_tributaries_are_not_mississippi_traffic():
    data = json.loads(g.DATA_FILE.read_text())
    for name, lines in data["tributaries"].items():
        for line in lines:
            for lat, lon in line[1:-1]:
                hit = g._project_main(lat, lon, 3.0)
                if hit and hit[0].offset_mi > 0.3:
                    assert g.channel(lat, lon) == name, (name, lat, lon)


def test_main_channel_is_never_filtered():
    data = json.loads(g.DATA_FILE.read_text())
    bad = [p for p in data["points"] if 185 <= p[2] <= 850 and not is_on_upper_mississippi(p[0], p[1])]
    assert bad == []


@pytest.mark.parametrize("lat,lon", [
    (44.7495, -92.8220),  # Mississippi RM 812.5 between Lock 2 and Prescott (old St. Croix box dropped it)
    (38.8870, -90.1800),  # Alton, above Mel Price (old Illinois rule dropped it)
])
def test_regressions_from_old_box_filters(lat, lon):
    assert is_on_upper_mississippi(lat, lon)


def test_off_river_positions_rejected():
    assert g.river_mile(44.95, -93.40) is None   # Minneapolis suburbs
    assert g.river_mile(0, 0) is None
    assert g.river_mile(None, -91) is None
    assert g.river_mile(91, 181) is None


def test_mile_to_coords_round_trip():
    for rm in (200.0, 455.5, 615.0, 700.0, 800.0, 845.0):
        lat, lon = g.coords_for_mile(rm)
        assert g.river_mile(lat, lon) == pytest.approx(rm, abs=0.15)
    assert g.coords_for_mile(5000) is None
