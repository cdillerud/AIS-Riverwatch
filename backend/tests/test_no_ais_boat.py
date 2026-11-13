"""Boats without AIS / DSC get an app ID instead of an MMSI."""
import asyncio
import importlib
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
server = importlib.import_module("server")


class _Users:
    def __init__(self):
        self.pushed = []

    async def find_one(self, *a, **k):
        return None

    async def update_one(self, q, u):
        if "$push" in u:
            self.pushed.append(u["$push"]["vessels"])


class _Settings:
    async def find_one(self, *a, **k):
        return None


class _DB:
    def __init__(self):
        self.users = _Users()
        self.user_settings = _Settings()


def _run(monkeypatch, body):
    db = _DB()
    monkeypatch.setattr(server, "db", db)

    async def me(request):
        return {"user_id": "u1", "vessels": []}

    monkeypatch.setattr(server, "get_current_user", me)
    out = asyncio.run(server.add_user_vessel(None, server.VesselAdd(**body)))
    return out, db


def test_no_mmsi_gets_an_app_id(monkeypatch):
    out, db = _run(monkeypatch, {"boat_name": "Sea Biscuit", "is_primary": True})
    m = out["vessel"]["mmsi"]
    assert len(m) == 9 and m.isdigit() and m.startswith("000")
    assert out["vessel"]["no_ais"] is True
    assert db.users.pushed[0]["mmsi"] == m


def test_real_mmsi_kept_and_app_prefix_refused(monkeypatch):
    out, _ = _run(monkeypatch, {"mmsi": " 338414076 ", "boat_name": "REBOOT"})
    assert out["vessel"]["mmsi"] == "338414076" and out["vessel"]["no_ais"] is False
    with pytest.raises(HTTPException):
        _run(monkeypatch, {"mmsi": "000123456", "boat_name": "X"})
    with pytest.raises(HTTPException):
        _run(monkeypatch, {"boat_name": "  "})
