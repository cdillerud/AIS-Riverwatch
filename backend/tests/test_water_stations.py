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
    # NWPS API live - we expect a numeric value back and fetch_method=nwps_api
    assert off["fetch_method"] in ("nwps_api", "usace_rivergages"), off
    assert off["data_url"].startswith("https://api.water.noaa.gov/nwps/v1/gauges/HSTM5"), off["data_url"]
    # Live API should give us a fresh reading
    if off["value"] is not None:
        assert 0 < off["value"] < 50, f"unexpected HSTM5 stage {off['value']}"
        assert off["source_status"] == "ok"


def test_lock2_official_current_summary():
    """Legacy /api/water-conditions response now exposes an official_current block."""
    r = requests.get(f"{API}/water-conditions/lock_2", timeout=15)
    assert r.status_code == 200
    d = r.json()
    oc = d["official_current"]
    assert oc["station_id"] == "HSTM5"
    assert "available" in oc
    assert "fetch_method" in oc
    assert "fallback_used" in oc
    assert "source_status" in oc
    if oc["available"]:
        assert oc["value"] is not None
        assert oc["unavailable_reason"] is None
    else:
        assert oc["unavailable_reason"] is not None


def test_lock2_reference_conditions_block_is_separate():
    r = requests.get(f"{API}/water-conditions/lock_2", timeout=15)
    d = r.json()
    rc = d["reference_conditions"]
    assert isinstance(rc, list) and len(rc) >= 1
    prescott = next((s for s in rc if s["station_id"] == "05344500"), None)
    assert prescott is not None
    # Reference reading must NOT have leaked into the official conditions block
    conditions = d["conditions"]
    assert conditions["from_reference"] is False
    # Discharge in conditions, if present, must originate from official NWPS,
    # NOT from the Prescott reference.
    if conditions["discharge_cfs"] is not None:
        # NWPS HSTM5 secondary is in kcfs (typically 15-25). Prescott is in
        # raw cfs (typically 20k-50k). The presence of either is fine as long
        # as it came from the official station - assert it matches official.raw.
        assert d["official"]["raw"].get("discharge_cfs") == conditions["discharge_cfs"]


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
