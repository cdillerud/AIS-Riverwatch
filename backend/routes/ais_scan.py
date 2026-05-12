"""Backend proxy for the AIS push relay scanner.

These routes forward HTTP calls to the relay container's internal HTTP
API. The frontend talks only to the backend (no relay implementation
details leak out).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ais-scan", tags=["AIS Scanner"])

# Resolve the relay base URL once at import time. Override via env in
# docker-compose if running the relay on a non-default hostname.
RELAY_BASE_URL = os.environ.get("AIS_RELAY_URL", "http://ais-relay:8088").rstrip("/")
RELAY_TIMEOUT = float(os.environ.get("AIS_RELAY_TIMEOUT", "8.0"))


class ScanStartRequest(BaseModel):
    subnet: Optional[str] = Field(None, description="Optional CIDR override (e.g. 192.168.1.0/24)")
    ports: Optional[list] = Field(None, description="Optional explicit port list")


class ScanSelectRequest(BaseModel):
    ip: str
    port: int


async def _relay_get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=RELAY_TIMEOUT) as client:
        try:
            r = await client.get(f"{RELAY_BASE_URL}{path}")
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Relay unreachable at {RELAY_BASE_URL}{path}: {e}",
            )
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise HTTPException(status_code=r.status_code, detail=detail)
    return r.json()


async def _relay_post(path: str, json: dict) -> dict:
    async with httpx.AsyncClient(timeout=RELAY_TIMEOUT) as client:
        try:
            r = await client.post(f"{RELAY_BASE_URL}{path}", json=json)
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Relay unreachable at {RELAY_BASE_URL}{path}: {e}",
            )
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise HTTPException(status_code=r.status_code, detail=detail)
    return r.json()


@router.post("/start")
async def start_scan(body: ScanStartRequest):
    """Trigger a scan on the relay. Optional subnet override."""
    return await _relay_post("/scan/boat-beacon", body.model_dump(exclude_none=True))


@router.get("/status")
async def scan_status():
    """Current scan + selected-feed + upstream connection state from the relay."""
    return await _relay_get("/scan/status")


@router.get("/results")
async def scan_results():
    """List of candidate AIS feeds discovered by the most recent scan."""
    return await _relay_get("/scan/results")


@router.post("/select")
async def scan_select(body: ScanSelectRequest):
    """Persist the chosen Boat Beacon feed and have the relay open the upstream."""
    return await _relay_post("/scan/select", body.model_dump())


@router.post("/clear")
async def scan_clear():
    """Forget the persisted feed and stop the upstream client."""
    return await _relay_post("/scan/clear", {})
