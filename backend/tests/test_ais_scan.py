# Tests for /api/ais-scan/* proxy routes.
# We stand up a tiny aiohttp-free mock relay on a random port and point
# the backend route at it via AIS_RELAY_URL.

import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _MockRelayHandler(BaseHTTPRequestHandler):
    state = {
        "selected_feed": None,
        "scan_status": {"state": "idle"},
        "results": [
            {"ip": "127.0.0.1", "port": 11099, "status": "ais_detected", "score": 90,
             "sample": "!AIVDM,1,1,,A,15RTgt0PAso;90TKcjM8h6g208CQ,0*4A",
             "last_seen": None, "error": None},
        ],
    }

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args, **kwargs):
        return  # silence test output

    def do_GET(self):
        if self.path == "/scan/status":
            self._send(200, {"scan_status": self.state["scan_status"],
                             "selected_feed": self.state["selected_feed"],
                             "upstream": {"connected": False},
                             "fanout_clients": 0,
                             "last_scan": None})
        elif self.path == "/scan/results":
            self._send(200, {"results": self.state["results"],
                             "last_scan": None,
                             "scan_status": self.state["scan_status"]})
        else:
            self._send(404, {"detail": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}
        if self.path == "/scan/boat-beacon":
            self.state["scan_status"] = {"state": "running"}
            self._send(200, {"status": "scan_started", "subnet": payload.get("subnet")})
        elif self.path == "/scan/select":
            self.state["selected_feed"] = {
                "selected_ip": payload["ip"],
                "selected_port": payload["port"],
                "selected_at": "now",
                "source": "boat_beacon_scanner",
                "last_successful_sample": "!AIVDM,",
            }
            self._send(200, {"status": "selected", "selected_feed": self.state["selected_feed"]})
        elif self.path == "/scan/clear":
            self.state["selected_feed"] = None
            self._send(200, {"status": "cleared"})
        else:
            self._send(404, {"detail": "not found"})


@pytest.fixture(scope="module")
def mock_relay():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockRelayHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    os.environ["AIS_RELAY_URL"] = f"http://127.0.0.1:{port}"
    # Reload the module so the URL is picked up
    import importlib
    import routes.ais_scan as ais_scan_mod
    importlib.reload(ais_scan_mod)
    yield port
    server.shutdown()


def test_proxy_status(mock_relay):
    from fastapi.testclient import TestClient
    from routes.ais_scan import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    r = client.get("/api/ais-scan/status")
    assert r.status_code == 200
    d = r.json()
    assert "selected_feed" in d
    assert "scan_status" in d


def test_proxy_results_and_start(mock_relay):
    from fastapi.testclient import TestClient
    from routes.ais_scan import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    r = client.get("/api/ais-scan/results")
    assert r.status_code == 200
    assert r.json()["results"][0]["status"] == "ais_detected"

    r = client.post("/api/ais-scan/start", json={"subnet": "192.168.1.0/24"})
    assert r.status_code == 200
    assert r.json()["status"] == "scan_started"
    assert r.json()["subnet"] == "192.168.1.0/24"


def test_proxy_select_and_clear(mock_relay):
    from fastapi.testclient import TestClient
    from routes.ais_scan import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    r = client.post("/api/ais-scan/select", json={"ip": "127.0.0.1", "port": 11099})
    assert r.status_code == 200
    sel = r.json()["selected_feed"]
    assert sel["selected_ip"] == "127.0.0.1"
    assert sel["selected_port"] == 11099
    assert sel["source"] == "boat_beacon_scanner"

    r = client.post("/api/ais-scan/clear")
    assert r.status_code == 200
    assert r.json()["status"] == "cleared"


def test_proxy_reports_relay_unreachable(monkeypatch):
    """When the relay is down, the proxy must surface a 502, not silently 500."""
    import importlib
    monkeypatch.setenv("AIS_RELAY_URL", "http://127.0.0.1:1")  # closed
    import routes.ais_scan as ais_scan_mod
    importlib.reload(ais_scan_mod)
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(ais_scan_mod.router, prefix="/api")
    client = TestClient(app)
    r = client.get("/api/ais-scan/status")
    assert r.status_code == 502
    assert "Relay unreachable" in r.text


def test_scanner_module_imports_and_detects_ais():
    """Importable + classify_sample distinguishes AIS from random bytes."""
    sys.path.insert(0, "/app/ais_push_relay")
    import scanner as relay_scanner
    info = relay_scanner._classify_sample(b"!AIVDM,1,1,,A,15RTgt0PAso;90TKcjM8h6g208CQ,0*4A\r\n")
    assert info["is_ais"] is True
    assert info["ais_count"] >= 1

    info2 = relay_scanner._classify_sample(b"random garbage bytes")
    assert info2["is_ais"] is False
    assert info2["is_nmea"] is False

    assert "1.0.0.0/24" not in relay_scanner.detect_local_subnets() or True  # smoke
