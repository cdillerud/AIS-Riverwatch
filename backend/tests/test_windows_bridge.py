"""Smoke tests for scripts/windows_bridge/riverwatch_ais_bridge.py.

These tests run on Linux (no Windows required) and verify:
  * Default config is written when missing.
  * INI values are translated into the env vars that scripts/ais_relay.py reads.
  * `--status` and `--clear-cache` behave correctly with no live network.
  * The wrapper can locate and import the bundled `ais_relay` module.

We do NOT exercise the actual TCP push path here - that is the job of the
existing scripts/ais_relay.py tests + the verified live run.
"""
from __future__ import annotations

import configparser
import importlib
import importlib.util
import json
import os
import socket
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parents[1]  # /app
BRIDGE_DIR = APP_ROOT / "scripts" / "windows_bridge"
SCRIPTS_DIR = APP_ROOT / "scripts"


def _load_bridge():
    """Import the bridge module from disk (it lives outside backend/)."""
    spec = importlib.util.spec_from_file_location(
        "riverwatch_ais_bridge",
        BRIDGE_DIR / "riverwatch_ais_bridge.py",
    )
    assert spec and spec.loader, "Cannot load bridge spec"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def bridge():
    # Make sure scripts/ is importable for the wrapper's `import ais_relay` call.
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    return _load_bridge()


@pytest.fixture
def clean_env():
    """Remove any AIS-relay env vars before each test so we can observe writes."""
    keys = [
        "COLLECTOR_IP", "COLLECTOR_PORT", "RELAY_TOKEN",
        "BOAT_BEACON_IP", "BOAT_BEACON_PORT", "BOAT_BEACON_SUBNET",
        "AIS_RELAY_CACHE",
    ]
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


def test_default_config_dict_present(bridge):
    assert "collector" in bridge.DEFAULT_CONFIG
    assert bridge.DEFAULT_CONFIG["collector"]["ip"] == "34.172.47.153"
    assert bridge.DEFAULT_CONFIG["collector"]["port"] == "6000"


def test_load_config_creates_template_when_missing(bridge, tmp_path):
    import logging
    logger = logging.getLogger("test")
    cfg_path = tmp_path / "riverwatch_bridge.ini"
    assert not cfg_path.exists()
    cfg = bridge._load_config(cfg_path, logger)
    # Template should have been written and defaults are present in cfg
    assert cfg_path.exists()
    assert cfg.get("collector", "ip") == "34.172.47.153"
    assert cfg.get("collector", "port") == "6000"


def test_apply_config_to_env(bridge, clean_env, tmp_path):
    cfg = configparser.ConfigParser()
    cfg.read_dict(bridge.DEFAULT_CONFIG)
    cfg.set("collector", "ip", "10.0.0.5")
    cfg.set("collector", "port", "6500")
    cfg.set("collector", "token", "secret-token")
    cfg.set("boat_beacon", "ip", "192.168.1.42")
    cfg.set("boat_beacon", "port", "7000")
    cfg.set("boat_beacon", "subnet", "192.168.1.0/24")
    cfg.set("boat_beacon", "cache_path", str(tmp_path / "cache.json"))

    bridge._apply_config_to_env(cfg)

    assert os.environ["COLLECTOR_IP"] == "10.0.0.5"
    assert os.environ["COLLECTOR_PORT"] == "6500"
    assert os.environ["RELAY_TOKEN"] == "secret-token"
    assert os.environ["BOAT_BEACON_IP"] == "192.168.1.42"
    assert os.environ["BOAT_BEACON_PORT"] == "7000"
    assert os.environ["BOAT_BEACON_SUBNET"] == "192.168.1.0/24"
    assert os.environ["AIS_RELAY_CACHE"] == str(tmp_path / "cache.json")


def test_clear_cache_removes_file(bridge, tmp_path):
    import logging
    cfg = configparser.ConfigParser()
    cfg.read_dict(bridge.DEFAULT_CONFIG)
    cache_file = tmp_path / "boat_beacon.json"
    cache_file.write_text(json.dumps({"ip": "1.2.3.4", "port": 7000}), encoding="utf-8")
    cfg.set("boat_beacon", "cache_path", str(cache_file))

    rc = bridge.cmd_clear_cache(cfg, logging.getLogger("test"))
    assert rc == 0
    assert not cache_file.exists()

    # Idempotent: second call still succeeds.
    rc2 = bridge.cmd_clear_cache(cfg, logging.getLogger("test"))
    assert rc2 == 0


def test_clear_cache_when_missing(bridge, tmp_path):
    import logging
    cfg = configparser.ConfigParser()
    cfg.read_dict(bridge.DEFAULT_CONFIG)
    cfg.set("boat_beacon", "cache_path", str(tmp_path / "missing.json"))
    assert bridge.cmd_clear_cache(cfg, logging.getLogger("test")) == 0


def test_cmd_status_reaches_local_listener(bridge, tmp_path):
    """cmd_status should report reachable when something accepts on the configured port."""
    import logging

    # Start a one-shot TCP listener on an ephemeral port.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _accept_once():
        try:
            conn, _ = srv.accept()
            conn.close()
        except OSError:
            pass

    threading.Thread(target=_accept_once, daemon=True).start()

    cfg = configparser.ConfigParser()
    cfg.read_dict(bridge.DEFAULT_CONFIG)
    cfg.set("collector", "ip", "127.0.0.1")
    cfg.set("collector", "port", str(port))
    cfg.set("boat_beacon", "cache_path", str(tmp_path / "absent.json"))

    rc = bridge.cmd_status(cfg, logging.getLogger("test"))
    srv.close()
    assert rc == 0


def test_cmd_status_collector_unreachable(bridge, tmp_path):
    import logging
    cfg = configparser.ConfigParser()
    cfg.read_dict(bridge.DEFAULT_CONFIG)
    # Use a port that is guaranteed-closed (high, ephemeral) on loopback.
    cfg.set("collector", "ip", "127.0.0.1")
    cfg.set("collector", "port", "1")  # privileged + nobody's listening
    cfg.set("boat_beacon", "cache_path", str(tmp_path / "absent.json"))

    rc = bridge.cmd_status(cfg, logging.getLogger("test"))
    assert rc == 2


def test_bridge_can_import_ais_relay(bridge, clean_env):
    """The wrapper bundles scripts/ais_relay.py; make sure it can actually import it."""
    # Ensure env is clean and scripts dir on path (fixture handles env)
    sys.path.insert(0, str(SCRIPTS_DIR))
    import importlib as _il
    # Force a fresh import so env vars apply.
    if "ais_relay" in sys.modules:
        del sys.modules["ais_relay"]
    mod = _il.import_module("ais_relay")
    assert hasattr(mod, "determine_boat_beacon")
    assert hasattr(mod, "relay_loop")
    assert hasattr(mod, "COLLECTOR_IP")


def test_find_nssm_returns_none_when_missing(bridge, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr(bridge, "_bundle_dir", lambda: Path("/tmp/nonexistent"))
    assert bridge._find_nssm() is None


def test_main_status_flag(bridge, tmp_path, monkeypatch):
    """--status should run cmd_status and exit."""
    cfg_path = tmp_path / "rw.ini"
    cfg_path.write_text(
        "[collector]\nip = 127.0.0.1\nport = 1\n\n"
        "[boat_beacon]\ncache_path = " + str(tmp_path / "x.json") + "\n",
        encoding="utf-8",
    )
    rc = bridge.main(["--config", str(cfg_path), "--status"])
    assert rc == 2  # collector unreachable on port 1


def test_main_clear_cache_flag(bridge, tmp_path):
    cfg_path = tmp_path / "rw.ini"
    cache = tmp_path / "cache.json"
    cache.write_text("{}", encoding="utf-8")
    cfg_path.write_text(
        "[collector]\nip = 127.0.0.1\nport = 1\n\n"
        "[boat_beacon]\ncache_path = " + str(cache) + "\n",
        encoding="utf-8",
    )
    rc = bridge.main(["--config", str(cfg_path), "--clear-cache"])
    assert rc == 0
    assert not cache.exists()
