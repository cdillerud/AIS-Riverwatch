"""Everything under /api needs a session except a short public list."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import server
from services import api_access as A

client = TestClient(server.app)  # startup (DB) hooks not run


@pytest.fixture
def anonymous(monkeypatch):
    async def nobody(request):
        return None

    monkeypatch.setattr(server, "get_current_user", nobody)


def test_public_list():
    for p in ("/api/", "/api/health", "/api/locks", "/api/ais/ingest", "/api/auth/login",
              "/api/auth/config", "/api/install/bootstrap"):
        assert A.is_public(p), p
    for p in ("/api/vessels", "/api/vessels/history/338414076", "/api/locks/board",
              "/api/usace/lock-queue", "/api/planning/meetings", "/api/vessel-cache",
              "/api/healthz", "/api/locksmith"):
        assert not A.is_public(p), p


@pytest.mark.parametrize("path", ["/api/vessels", "/api/vessel-cache", "/api/locks/board",
                                  "/api/vessels/history/338414076", "/api/planning/meetings"])
def test_data_endpoints_need_login(anonymous, path):
    assert client.get(path).status_code == 401


def test_public_endpoints_still_answer(anonymous):
    assert client.get("/api/locks").status_code == 200
    assert client.get("/api/auth/config").status_code == 200


def test_cors_preflight_is_not_blocked(anonymous):
    r = client.options("/api/vessels", headers={"Origin": "http://localhost:3000",
                                                "Access-Control-Request-Method": "GET"})
    assert r.status_code != 401


def test_websockets_refuse_anonymous(anonymous):
    for path in ("/ws/ais", "/api/ws/raw"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(path) as ws:
                ws.receive_json()


def test_rollback_switch(anonymous, monkeypatch):
    monkeypatch.setenv("API_LOGIN_REQUIRED", "false")
    assert client.get("/api/vessel-cache").status_code == 200


def test_relay_scripts_with_ingest_token_are_admin_only(signed_in):
    assert client.get("/api/relay/download").status_code == 403
    assert client.get("/api/relay/phone-localhost/download").status_code == 403
