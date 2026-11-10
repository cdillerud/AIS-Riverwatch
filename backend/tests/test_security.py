"""Auth on state-changing endpoints, SSRF guard on feed targets, ingest token."""
import pytest
from fastapi.testclient import TestClient

import server

client = TestClient(server.app)  # no context manager: startup (DB) hooks not run


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/debug/inject-nmea", {}),
    ("get", "/api/debug/state", None),
    ("get", "/api/sessions", None),
    ("post", "/api/blocked-mmsi", {"mmsi": "1"}),
    ("delete", "/api/blocked-mmsi/1", None),
    ("post", "/api/settings", {"x": 1}),
    ("post", "/api/usace/refresh", None),
    ("post", "/api/lockage/record", None),
    ("post", "/api/demo-vessels/resume-all", None),
    ("post", "/api/connection/test", {"ip_address": "169.254.169.254", "port": 80, "user_mmsi": ""}),
    ("post", "/api/connection/start", {"ip_address": "10.0.0.1", "port": 5353, "user_mmsi": ""}),
    ("post", "/api/connection/stop", None),
    ("post", "/api/vessel-cache/123", {"name": "x"}),
    ("get", "/api/relay/download", None),
])
def test_state_changing_endpoints_require_login(method, path, body):
    kwargs = {"json": body} if body is not None else {}
    r = getattr(client, method)(path, **kwargs)
    assert r.status_code == 401, (path, r.status_code, r.text[:200])


@pytest.mark.parametrize("host", ["127.0.0.1", "169.254.169.254", "0.0.0.0", "224.0.0.1", "::1", "localhost"])
def test_feed_target_blocks_internal_addresses(host):
    assert server.validate_feed_target(host, 5353) is not None


def test_feed_target_rules(monkeypatch):
    assert server.validate_feed_target("ais-relay", 5353) is None          # allowlisted docker service
    assert server.validate_feed_target("192.168.0.25", 5353) is None        # boat LAN (self-hosted default)
    assert server.validate_feed_target("192.168.0.25", 0) is not None
    assert server.validate_feed_target("192.168.0.25", "x") is not None
    assert server.validate_feed_target("", 5353) is not None
    monkeypatch.setenv("AIS_ALLOW_PRIVATE_TARGETS", "false")              # hosted SaaS mode
    assert server.validate_feed_target("192.168.0.25", 5353) is not None


def test_ingest_requires_token_when_configured(monkeypatch):
    monkeypatch.setenv("AIS_INGEST_TOKEN", "s3cret")
    assert client.post("/api/ais/ingest", json={"lines": []}).status_code == 401
    r = client.post("/api/ais/ingest", json={"lines": []}, headers={"X-Ingest-Token": "wrong"})
    assert r.status_code == 401
    r = client.post("/api/ais/ingest", json={"lines": []}, headers={"X-Ingest-Token": "s3cret"})
    assert r.status_code == 200


def test_ingest_rejects_oversized_batches(monkeypatch):
    monkeypatch.delenv("AIS_INGEST_TOKEN", raising=False)
    r = client.post("/api/ais/ingest", json={"lines": ["x"] * 2001})
    assert r.status_code == 413


def test_position_updates_require_owning_the_boat(monkeypatch):
    async def stranger(request):
        return {"user_id": "u1", "email": "x@example.com", "vessels": [{"mmsi": "111111111"}]}
    monkeypatch.setattr(server, "get_current_user", stranger)
    r = client.post("/api/session/338414076/position", json={"lat": 44.7, "lon": -92.8})
    assert r.status_code == 403
    r = client.post("/api/user-position", json={"mmsi": "338414076", "lat": 44.7, "lon": -92.8})
    assert r.status_code == 403
