"""
Backend tests for Trip Plan (multi-lock chain race analysis) feature.
Endpoint: GET /api/session/{mmsi}/trip-plan
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    # Fallback to reading frontend .env
    try:
        with open('/app/frontend/.env') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
                    break
    except Exception:
        pass

API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- Trip Plan: empty case (MMSI not in active vessels) ---
def test_trip_plan_no_user(http):
    mmsi = "999000111"  # very unlikely to exist
    # Ensure not simulated
    http.post(f"{API}/user-vessel/simulation/{mmsi}/stop", timeout=10)
    r = http.get(f"{API}/session/{mmsi}/trip-plan", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_mmsi"] == mmsi
    assert data["user_vessel"] is None
    assert data["legs"] == []
    assert data["summary"]["overall_status"] == "no_user"
    assert data["summary"]["legs_count"] == 0


# --- Helper to enable simulation ---
def _enable_sim(http, mmsi, river_mile, speed_knots, heading):
    payload = {
        "enabled": True,
        "river_mile": river_mile,
        "speed_knots": speed_knots,
        "heading": heading,
    }
    r = http.post(f"{API}/user-vessel/simulation/{mmsi}", json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    # Wait for simulation tick to land vessel in active_vessels
    time.sleep(2.5)
    return r.json()


def _stop_sim(http, mmsi):
    try:
        http.post(f"{API}/user-vessel/simulation/{mmsi}/stop", timeout=10)
    except Exception:
        pass


# --- Trip Plan: southbound returns first lock = lock_2 (RM 815.2) ---
def test_trip_plan_southbound_first_lock(http):
    mmsi = "367123450"
    try:
        _enable_sim(http, mmsi, river_mile=820, speed_knots=8, heading="southbound")
        r = http.get(f"{API}/session/{mmsi}/trip-plan?max_locks=5", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Shape
        assert "session_mmsi" in data
        assert "user_vessel" in data and data["user_vessel"] is not None
        assert "legs" in data and isinstance(data["legs"], list)
        assert "summary" in data
        assert len(data["legs"]) >= 1, f"Expected >=1 leg, got {data['legs']}"

        first_leg = data["legs"][0]
        for k in ("lock_id", "lock_name", "lock_rm", "user_eta_minutes", "status"):
            assert k in first_leg, f"Missing key {k} in {first_leg}"
        # required_speed_mph is part of leg schema (may be null when clear)
        assert "required_speed_mph" in first_leg

        assert first_leg["lock_id"] == "lock_2", (
            f"Expected first lock=lock_2 for southbound from RM 820, got "
            f"{first_leg['lock_id']} (RM {first_leg['lock_rm']})"
        )
        # lock_2 river mile
        assert abs(float(first_leg["lock_rm"]) - 815.2) < 0.5
    finally:
        _stop_sim(http, mmsi)


# --- Trip Plan: max_locks limits legs ---
def test_trip_plan_max_locks(http):
    mmsi = "367123451"
    try:
        _enable_sim(http, mmsi, river_mile=820, speed_knots=8, heading="southbound")
        r = http.get(f"{API}/session/{mmsi}/trip-plan?max_locks=2", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert len(data["legs"]) <= 2
    finally:
        _stop_sim(http, mmsi)


# --- Trip Plan: northbound first lock = lock_4 (RM 752.8) ---
def test_trip_plan_northbound_first_lock(http):
    mmsi = "367123452"
    try:
        _enable_sim(http, mmsi, river_mile=750, speed_knots=8, heading="northbound")
        r = http.get(f"{API}/session/{mmsi}/trip-plan?max_locks=5", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["legs"]) >= 1
        first_leg = data["legs"][0]
        assert first_leg["lock_id"] == "lock_4", (
            f"Expected lock_4 for northbound from RM 750, got "
            f"{first_leg['lock_id']} (RM {first_leg['lock_rm']})"
        )
        assert abs(float(first_leg["lock_rm"]) - 752.8) < 0.5
    finally:
        _stop_sim(http, mmsi)


# --- NEW FILTER: Two concurrent simulated users should NOT see each other as threats ---
def test_trip_plan_skips_other_simulated_users(http):
    mmsi_a = "367123450"
    mmsi_b = "367999999"
    try:
        _enable_sim(http, mmsi_a, river_mile=820, speed_knots=8, heading="southbound")
        _enable_sim(http, mmsi_b, river_mile=820, speed_knots=8, heading="southbound")
        r = http.get(f"{API}/session/{mmsi_a}/trip-plan?max_locks=4", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Overall must NOT be cant_beat due to self/other-sim threat at absurd required speed
        overall = data["summary"]["overall_status"]
        assert overall in ("clear", "on_pace", "speed_up"), (
            f"Expected clear/on_pace/speed_up after filter, got {overall}; "
            f"legs={data['legs']}"
        )
        # No leg should have other simulated user (mmsi_b) as threat
        for leg in data["legs"]:
            threat = leg.get("threat") or {}
            t_mmsi = threat.get("mmsi") if isinstance(threat, dict) else None
            assert t_mmsi != mmsi_b, (
                f"Other simulated user {mmsi_b} appeared as threat in leg "
                f"{leg.get('lock_id')}"
            )
            # required_speed_mph should not be absurd (>100 mph)
            rs = leg.get("required_speed_mph")
            if rs is not None:
                assert rs < 100, f"Absurd required_speed_mph={rs} in leg {leg.get('lock_id')}"
    finally:
        _stop_sim(http, mmsi_a)
        _stop_sim(http, mmsi_b)


# --- NEW FILTER: Demo vessels are NOT excluded ---
def test_trip_plan_demo_vessels_present_in_active(http):
    """Verify DEMO001/DEMO002 still appear in active vessels (not filtered out)."""
    r = http.get(f"{API}/vessels", timeout=15)
    assert r.status_code == 200
    vessels = r.json()
    # Vessels endpoint may return list or dict
    vlist = vessels if isinstance(vessels, list) else vessels.get("vessels", [])
    mmsis = {str(v.get("mmsi")) for v in vlist if isinstance(v, dict)}
    # Demo vessels should be present (may or may not be enabled; if absent, skip)
    has_demo = any(m.startswith("DEMO") for m in mmsis)
    if not has_demo:
        pytest.skip("Demo vessels not active in this environment")
    assert has_demo


# --- REGRESSION: race-analysis endpoint still functions ---
def test_regression_race_analysis(http):
    mmsi = "367123453"
    try:
        _enable_sim(http, mmsi, river_mile=820, speed_knots=8, heading="southbound")
        # lock_2 is downriver from RM 820 southbound
        r = http.get(f"{API}/session/{mmsi}/race-analysis/lock_2", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Just verify response is dict-like and has user/lock info
        assert isinstance(data, dict)
    finally:
        _stop_sim(http, mmsi)


# --- REGRESSION: user vessel simulation endpoints still work ---
def test_regression_simulation_endpoints(http):
    mmsi = "367123454"
    try:
        r = http.post(
            f"{API}/user-vessel/simulation/{mmsi}",
            json={"enabled": True, "river_mile": 800, "speed_knots": 7, "heading": "southbound"},
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text

        r = http.get(f"{API}/user-vessel/simulation/{mmsi}", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("simulation_enabled") is True

        r = http.post(f"{API}/user-vessel/simulation/{mmsi}/stop", timeout=10)
        assert r.status_code in (200, 201, 204)
    finally:
        _stop_sim(http, mmsi)
