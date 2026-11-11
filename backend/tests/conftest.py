"""
Shared pytest setup.

Unit tests run offline. Tests that call a running backend over HTTP are
"integration" tests: they are skipped unless REACT_APP_BACKEND_URL points at a
running River Watch backend, e.g.

    REACT_APP_BACKEND_URL=http://localhost:8001 pytest backend/tests
"""
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "riverwatch_test")
for p in (str(BACKEND_DIR), str(REPO_ROOT / "ais_push_relay")):
    if p not in sys.path:
        sys.path.insert(0, p)

INTEGRATION_FILES = {
    "test_auth.py",
    "test_new_features.py",
    "test_planning.py",
    "test_trip_plan.py",
    "test_user_vessel_simulation.py",
    "test_water_stations.py",
}


def pytest_collection_modifyitems(config, items):
    if os.environ.get("REACT_APP_BACKEND_URL"):
        return
    skip = pytest.mark.skip(reason="integration test: set REACT_APP_BACKEND_URL to a running backend")
    for item in items:
        if Path(str(item.fspath)).name in INTEGRATION_FILES:
            item.add_marker(skip)


@pytest.fixture
def signed_in(monkeypatch):
    """Requests in this test come from a signed-in (non-admin) user. Every
    /api route except the public list needs one (services/api_access.py)."""
    import server
    user = {"user_id": "u_test", "email": "test@riverwatch-local.com", "vessels": [{"mmsi": "338414076"}]}

    async def fake_current_user(request):
        return user

    monkeypatch.setattr(server, "get_current_user", fake_current_user)
    return user