"""End-to-end tests for the push-ingest mode of the relay.

Boots the relay on ephemeral ports, then exercises:
  * Raw-TCP push on the legacy ingest port (mimics scripts/ais_relay.py)
  * HTTP /ingest/nmea endpoint
  * Token auth when AIS_RELAY_TOKEN is set
  * /health 'mode' transitions: idle -> push
  * Fan-out of pushed lines to a downstream TCP client on TCP_PORT
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import json
import contextlib

import pytest


RELAY_MAIN = "/app/ais_push_relay/main.py"


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(port: int, timeout: float = 6.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.5) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode())
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.2)
    raise TimeoutError(f"relay :{port} never became healthy")


@pytest.fixture()
def relay():
    ws_port = _free_port()
    tcp_port = _free_port()
    ingest_port = _free_port()
    state_path = f"/tmp/relay_state_{ws_port}.json"
    try:
        os.unlink(state_path)
    except FileNotFoundError:
        pass
    env = {
        **os.environ,
        "WS_PORT": str(ws_port),
        "TCP_PORT": str(tcp_port),
        "INGEST_PORT": str(ingest_port),
        "STATE_PATH": state_path,
        "AIS_RELAY_TOKEN": "",
    }
    proc = subprocess.Popen(
        [sys.executable, RELAY_MAIN],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(ws_port)
        yield {"ws": ws_port, "tcp": tcp_port, "ingest": ingest_port, "state_path": state_path}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            os.unlink(state_path)
        except FileNotFoundError:
            pass


def _get_health(ws_port: int) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{ws_port}/health", timeout=2.0) as resp:
        return json.loads(resp.read().decode())


def test_health_has_push_ingest_block_and_idle_mode(relay):
    d = _get_health(relay["ws"])
    assert d["status"] == "ok"
    assert d["mode"] == "idle"
    pi = d["push_ingest"]
    assert pi["lines_received"] == 0
    assert pi["current_clients"] == 0
    assert pi["last_line_at"] is None
    assert pi["last_client"] is None
    assert pi["token_required"] is False
    assert str(relay["ingest"]) in pi["ingest_tcp"]
    assert d["upstream"]["connected"] is False
    assert d["fanout_clients"] == 0


def test_tcp_push_increments_lines_and_flips_mode_to_push(relay):
    """Mimics scripts/ais_relay.py - newline-delimited NMEA on the ingest port."""
    s = socket.create_connection(("127.0.0.1", relay["ingest"]), timeout=3)
    try:
        for _ in range(7):
            s.sendall(b"!AIVDM,1,1,,A,15RTgt0PAso;90TKcjM8h6g208CQ,0*4A\n")
            time.sleep(0.02)
    finally:
        s.close()
    # Give the relay a beat to record
    time.sleep(0.5)
    d = _get_health(relay["ws"])
    assert d["mode"] == "push"
    assert d["push_ingest"]["lines_received"] >= 7
    assert d["push_ingest"]["last_line_at"] is not None
    assert d["push_ingest"]["last_client"] is not None


def test_http_ingest_endpoint(relay):
    body = json.dumps({"lines": ["!AIVDM,httpA", "$GPRMC,httpB"]}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{relay['ws']}/ingest/nmea",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        result = json.loads(resp.read())
    assert result["status"] == "ok"
    assert result["lines_accepted"] == 2
    d = _get_health(relay["ws"])
    assert d["push_ingest"]["lines_received"] >= 2


def test_http_ingest_rejects_empty(relay):
    req = urllib.request.Request(
        f"http://127.0.0.1:{relay['ws']}/ingest/nmea",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=2.0)
    assert exc.value.code == 400


def test_pushed_lines_are_fanned_out_to_tcp_clients(relay):
    """Connect a fan-out reader, push lines, verify reader sees them in order."""
    fanout = socket.create_connection(("127.0.0.1", relay["tcp"]), timeout=3)
    fanout.settimeout(4.0)
    pusher = socket.create_connection(("127.0.0.1", relay["ingest"]), timeout=3)
    try:
        for i in range(3):
            pusher.sendall(f"!AIVDM,FAN{i}\n".encode())
            time.sleep(0.1)
        buf = b""
        while buf.count(b"\n") < 3:
            chunk = fanout.recv(256)
            if not chunk:
                break
            buf += chunk
    finally:
        pusher.close()
        fanout.close()
    lines = [ln for ln in buf.decode().splitlines() if ln.strip()]
    assert len(lines) >= 3
    assert lines[0] == "!AIVDM,FAN0"
    assert lines[1] == "!AIVDM,FAN1"
    assert lines[2] == "!AIVDM,FAN2"


@pytest.fixture()
def relay_with_token():
    ws_port = _free_port()
    tcp_port = _free_port()
    ingest_port = _free_port()
    state_path = f"/tmp/relay_state_{ws_port}.json"
    env = {
        **os.environ,
        "WS_PORT": str(ws_port),
        "TCP_PORT": str(tcp_port),
        "INGEST_PORT": str(ingest_port),
        "STATE_PATH": state_path,
        "AIS_RELAY_TOKEN": "sekret-token-42",
    }
    proc = subprocess.Popen(
        [sys.executable, RELAY_MAIN],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(ws_port)
        yield {"ws": ws_port, "ingest": ingest_port, "token": "sekret-token-42"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            os.unlink(state_path)
        except FileNotFoundError:
            pass


def test_http_ingest_requires_token_when_configured(relay_with_token):
    body = json.dumps({"lines": ["!AIVDM,test"]}).encode()
    # No header -> 401
    req = urllib.request.Request(
        f"http://127.0.0.1:{relay_with_token['ws']}/ingest/nmea",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=2.0)
    assert exc.value.code == 401
    # Wrong header -> 401
    req = urllib.request.Request(
        f"http://127.0.0.1:{relay_with_token['ws']}/ingest/nmea",
        data=body,
        headers={"Content-Type": "application/json", "X-Relay-Token": "wrong"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=2.0)
    assert exc.value.code == 401
    # Right header -> 200
    req = urllib.request.Request(
        f"http://127.0.0.1:{relay_with_token['ws']}/ingest/nmea",
        data=body,
        headers={"Content-Type": "application/json", "X-Relay-Token": relay_with_token["token"]},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        assert resp.status == 200


def test_health_token_required_flag(relay_with_token):
    d = _get_health(relay_with_token["ws"])
    assert d["push_ingest"]["token_required"] is True
