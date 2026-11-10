"""Persisted state for the River Watch AIS relay.

Stores the currently selected Boat Beacon upstream feed plus scanner
artefacts so a relay restart picks up the operator's last selection
without re-scanning.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_STATE_PATH = os.environ.get("STATE_PATH", "/data/state.json")
_DEFAULT_STATE: Dict[str, Any] = {
    "schema_version": 1,
    "selected_feed": None,            # {ip, port, selected_at, source, last_successful_sample}
    "last_scan": None,                # {started_at, finished_at, subnet, candidates_count}
    "scan_results": [],               # list of candidate dicts
    "scan_status": {                  # latest scan status (status only - results list is canonical)
        "state": "idle",              # idle | running | completed | error
        "started_at": None,
        "finished_at": None,
        "progress": 0.0,
        "scanned": 0,
        "total": 0,
        "subnet": None,
        "error": None,
    },
    "upstream": {                     # observed state of the Boat Beacon TCP client
        "connected": False,
        "last_connect_at": None,
        "last_error": None,
        "lines_received": 0,
        "last_line_at": None,
        "selected_ip": None,
        "selected_port": None,
    },
}

_lock = threading.RLock()
_state: Dict[str, Any] = {}


def _ensure_loaded() -> Dict[str, Any]:
    global _state
    if _state:
        return _state
    if os.path.exists(_STATE_PATH):
        try:
            with open(_STATE_PATH, "r") as f:
                _state = json.load(f)
        except Exception:
            _state = json.loads(json.dumps(_DEFAULT_STATE))
    else:
        _state = json.loads(json.dumps(_DEFAULT_STATE))
        _atomic_write(_state)
    # Patch missing keys (forward-compat with older state files)
    for k, v in _DEFAULT_STATE.items():
        _state.setdefault(k, json.loads(json.dumps(v)))
    return _state


def _atomic_write(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH) or ".", exist_ok=True)
    tmp = _STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=False, default=str)
    os.replace(tmp, _STATE_PATH)


def snapshot() -> Dict[str, Any]:
    with _lock:
        _ensure_loaded()
        return json.loads(json.dumps(_state))


def update(**fields: Any) -> Dict[str, Any]:
    with _lock:
        s = _ensure_loaded()
        for k, v in fields.items():
            s[k] = v
        _atomic_write(s)
        return json.loads(json.dumps(s))


def update_scan_status(**fields: Any) -> Dict[str, Any]:
    with _lock:
        s = _ensure_loaded()
        s["scan_status"].update(fields)
        _atomic_write(s)
        return json.loads(json.dumps(s["scan_status"]))


def update_upstream(**fields: Any) -> None:
    with _lock:
        s = _ensure_loaded()
        s["upstream"].update(fields)
        _atomic_write(s)


def set_scan_results(results: List[Dict[str, Any]], subnet: Optional[str]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        s = _ensure_loaded()
        s["scan_results"] = results
        s["last_scan"] = {
            "started_at": s["scan_status"].get("started_at"),
            "finished_at": now,
            "subnet": subnet,
            "candidates_count": len(results),
        }
        _atomic_write(s)


def get_selected_feed() -> Optional[Dict[str, Any]]:
    with _lock:
        s = _ensure_loaded()
        return s.get("selected_feed")


def set_selected_feed(ip: str, port: int, last_successful_sample: Optional[str]) -> Dict[str, Any]:
    feed = {
        "selected_ip": ip,
        "selected_port": int(port),
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "source": "boat_beacon_scanner",
        "last_successful_sample": last_successful_sample,
    }
    with _lock:
        s = _ensure_loaded()
        s["selected_feed"] = feed
        s["upstream"]["selected_ip"] = ip
        s["upstream"]["selected_port"] = int(port)
        _atomic_write(s)
        return feed


def clear_selected_feed() -> None:
    with _lock:
        s = _ensure_loaded()
        s["selected_feed"] = None
        s["upstream"]["selected_ip"] = None
        s["upstream"]["selected_port"] = None
        _atomic_write(s)
