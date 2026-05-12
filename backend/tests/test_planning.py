# River Watch - Tests for Traffic Planning endpoints
#
# Run with:  cd /app/backend && python -m pytest tests/test_planning.py -q

import os
import pytest
import requests

API_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not API_BASE:
    # fall back to frontend env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    API_BASE = line.split("=", 1)[1].strip()
                    break
    except Exception:
        API_BASE = "http://localhost:8001"
API = API_BASE.rstrip("/") + "/api"


def test_planning_locks_returns_27_locks():
    r = requests.get(f"{API}/planning/locks", timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    locks = d["locks"]
    assert len(locks) == 27
    # Sorted upstream → downstream
    rms = [l["river_mile"] for l in locks]
    assert rms == sorted(rms, reverse=True)
    assert locks[0]["lock_id"] == "lock_1"


def test_trip_plan_downstream_order():
    r = requests.post(
        f"{API}/planning/trip",
        json={"origin_rm": 820, "destination_rm": 600, "base_speed_knots": 8},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["direction"] == "downstream"
    assert d["total_distance_miles"] == 220.0
    assert d["lock_count"] >= 9
    # First leg should be the upstream-most lock crossed (highest RM < 820)
    lock_legs = [leg for leg in d["legs"] if leg["type"] == "lock"]
    rms = [leg["lock_rm"] for leg in lock_legs]
    assert rms == sorted(rms, reverse=True), f"Expected descending RM order, got {rms}"
    # Final leg is destination
    assert d["legs"][-1]["type"] == "destination"
    assert d["legs"][-1]["to_rm"] == 600.0


def test_trip_plan_upstream_order():
    r = requests.post(
        f"{API}/planning/trip",
        json={"origin_rm": 600, "destination_rm": 820, "base_speed_knots": 6},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["direction"] == "upstream"
    lock_legs = [leg for leg in d["legs"] if leg["type"] == "lock"]
    rms = [leg["lock_rm"] for leg in lock_legs]
    assert rms == sorted(rms), f"Expected ascending RM order, got {rms}"


def test_trip_plan_rejects_equal_endpoints():
    r = requests.post(
        f"{API}/planning/trip",
        json={"origin_rm": 700, "destination_rm": 700, "base_speed_knots": 8},
        timeout=10,
    )
    assert r.status_code == 400


def test_trip_plan_default_speed_when_no_speed_provided():
    r = requests.post(
        f"{API}/planning/trip",
        json={"origin_rm": 820, "destination_rm": 815},
        timeout=10,
    )
    assert r.status_code == 200
    d = r.json()
    assert d["speed_source"] in ("default", "ais")  # ais if MMSI happens to be auto-detected
    assert d["base_speed_knots"] > 0


def test_lock_queue_returns_structure():
    r = requests.get(f"{API}/planning/lock-queue/lock_2?lookahead_hours=12", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["lock_id"] == "lock_2"
    assert d["lock_rm"] == 815.2
    assert "queue" in d and isinstance(d["queue"], list)
    # If demo vessels are active, queue ordered ascending by ETA
    etas = [v["eta_minutes"] for v in d["queue"]]
    assert etas == sorted(etas)
    # Slots are 1-indexed and sequential
    for idx, v in enumerate(d["queue"], start=1):
        assert v["slot"] == idx


def test_lock_queue_unknown_lock_returns_404():
    r = requests.get(f"{API}/planning/lock-queue/lock_999", timeout=10)
    assert r.status_code == 404


def test_meetings_predictor_returns_list():
    r = requests.get(f"{API}/planning/meetings?lookahead_hours=6", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "encounters" in d
    assert isinstance(d["encounters"], list)
    # Ordered ascending by time
    times = [e["time_minutes"] for e in d["encounters"]]
    assert times == sorted(times)
    # Demo vessels: DELTA QUEEN downbound from RM830, RIVER RUNNER upbound from RM800.
    # We expect at least one head-on encounter when demo vessels are active.
    types = {e["type"] for e in d["encounters"]}
    # Don't assert presence of head_on (demo could be disabled), but assert valid types
    for t in types:
        assert t in ("head_on", "overtake")


def test_bottlenecks_forecast_returns_all_locks():
    r = requests.get(f"{API}/planning/bottlenecks?hours=6", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["hours"] == 6.0
    forecast = d["forecast"]
    assert len(forecast) == 27
    # Sorted by utilization desc
    utils = [b["utilization"] for b in forecast]
    assert utils == sorted(utils, reverse=True)
    for b in forecast:
        assert b["severity"] in ("low", "moderate", "high")
        assert b["arrivals_in_window"] == b["arrivals_upstream"] + b["arrivals_downstream"]


def test_bottlenecks_window_validation():
    r = requests.get(f"{API}/planning/bottlenecks?hours=0", timeout=10)
    assert r.status_code == 422
    r = requests.get(f"{API}/planning/bottlenecks?hours=99", timeout=10)
    assert r.status_code == 422
