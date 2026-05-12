# River Watch - Tests for the lock water-condition mapping and debug endpoint
#
# Run with:  cd /app/backend && python -m pytest tests/test_water_stations.py -q

import os
import pytest
import requests

API_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not API_BASE:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    API_BASE = line.split("=", 1)[1].strip()
                    break
    except Exception:
        API_BASE = "http://localhost:8001"
API = API_BASE.rstrip("/") + "/api"


# --- Lock 2 audit ---------------------------------------------------------

def test_lock2_official_is_hstm5_with_hastings_thresholds():
    r = requests.get(f"{API}/water-conditions/lock_2", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    off = d["official"]
    assert off["station_id"] == "HSTM5"
    assert off["source"] == "NWS"
    assert off["thresholds"] == {"action": 13.0, "flood": 15.0, "moderate": 17.0, "major": 18.0}
    assert "Hastings" in off["threshold_source"]
    assert "600.00" in off["datum"]
    assert off["measurement_type"] == "river_stage"
    assert d["lock_river_mile"] == 815.2


def test_lock2_prescott_is_reference_only():
    r = requests.get(f"{API}/water-conditions/lock_2", timeout=15)
    d = r.json()
    refs = d["references"]
    assert len(refs) >= 1
    prescott = next((s for s in refs if s["station_id"] == "05344500"), None)
    assert prescott is not None, refs
    assert prescott["role"] == "reference"
    # Reference station has NO thresholds - we must not cross-apply them
    assert prescott["thresholds"] is None
    assert prescott["threshold_source"] is None
    assert prescott["status"] == "not_defined"
    assert "Flood category not defined" in prescott["status_explanation"]
    assert "650.00" in prescott["datum"]
    assert prescott["note"] and "do NOT compare" in prescott["note"]


def test_lock2_debug_endpoint_explains_selection():
    r = requests.get(f"{API}/locks/lock_2/water-condition-debug", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["official"]["station_id"] == "HSTM5"
    assert len(d["references"]) >= 1
    assert "HSTM5" in d["selection_reason"]
    assert "debug" in d
    assert any("only with official.thresholds" in n for n in d["debug"]["notes"])


# --- Generic shape audit --------------------------------------------------

REQUIRED_FIELDS = {
    "station_id", "station_name", "source", "river_mile",
    "distance_from_lock_miles", "measurement_type", "value", "units",
    "datum", "observed_at", "thresholds", "threshold_source",
    "status", "status_explanation",
}


@pytest.mark.parametrize("lock_id", ["lock_1", "lock_2", "lock_5", "lock_13", "lock_19", "melvin_price"])
def test_water_condition_has_required_fields(lock_id):
    r = requests.get(f"{API}/water-conditions/{lock_id}", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    off = d["official"]
    missing = REQUIRED_FIELDS - set(off.keys())
    assert not missing, f"{lock_id} missing fields: {missing}"
    assert d["lock_id"] == lock_id
    assert d["lock_river_mile"] is not None


def test_unknown_lock_returns_404():
    r = requests.get(f"{API}/water-conditions/lock_999", timeout=10)
    assert r.status_code == 404
    r = requests.get(f"{API}/locks/lock_999/water-condition-debug", timeout=10)
    assert r.status_code == 404


def test_lock5_thresholds_are_not_defined():
    """L&D 5/5A/6/7 share the Winona feed and we intentionally don't apply Winona thresholds."""
    r = requests.get(f"{API}/water-conditions/lock_5", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["official"]["thresholds"] is None
    assert d["official"]["status"] in ("not_defined", "unknown")
    if d["official"]["status"] == "not_defined":
        assert "Flood category not defined" in d["official"]["status_explanation"]


def test_lock1_thresholds_are_defined_and_cited():
    r = requests.get(f"{API}/water-conditions/lock_1", timeout=15)
    d = r.json()
    off = d["official"]
    assert off["thresholds"] is not None
    assert off["threshold_source"] is not None
    assert "St. Paul" in off["threshold_source"]
