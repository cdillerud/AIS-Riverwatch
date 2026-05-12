# River Watch Backend - Water Station Service
#
# Fetches real-time values for a lock's authoritative station and any
# nearby reference stations, then applies *only* that station's thresholds
# to derive a flood-category status. If a station has no thresholds we
# return status="unknown" and a human-readable status_explanation.

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from config import LOCKS
from lock_stations import LOCK_STATIONS

logger = logging.getLogger(__name__)

# Simple in-process cache for station fetches (60 s)
_STATION_CACHE: Dict[str, dict] = {}
_STATION_CACHE_AT: Dict[str, datetime] = {}
_CACHE_TTL = 60  # seconds


async def _fetch_usgs(station: dict) -> dict:
    """Fetch real-time values from a USGS Water Services JSON endpoint."""
    site_id = station["station_id"]
    url = station["data_url"]
    result = {"value": None, "observed_at": None, "raw": {}, "fetch_error": None}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                result["fetch_error"] = f"USGS {site_id} returned HTTP {resp.status_code}"
                return result
            data = resp.json()
            ts = data.get("value", {}).get("timeSeries", [])
            for series in ts:
                pc = series.get("variable", {}).get("variableCode", [{}])[0].get("value")
                vals = series.get("values", [{}])[0].get("value", [])
                if not vals:
                    continue
                latest = vals[-1]
                try:
                    val = float(latest.get("value"))
                except (TypeError, ValueError):
                    continue
                when = latest.get("dateTime")
                if pc == "00065":  # gage height
                    result["value"] = round(val, 2)
                    result["observed_at"] = when
                    result["raw"]["gage_height_ft"] = round(val, 2)
                elif pc == "00060":  # discharge
                    result["raw"]["discharge_cfs"] = round(val, 0)
                elif pc == "00010":  # water temp (C)
                    result["raw"]["water_temp_c"] = round(val, 1)
                    result["raw"]["water_temp_f"] = round(val * 9 / 5 + 32, 1)
    except Exception as e:
        logger.warning(f"[water] USGS fetch failed for {site_id}: {e}")
        result["fetch_error"] = str(e)
    return result


async def _fetch_nws(station: dict) -> dict:
    """Fetch latest observed river stage from NWS AHPS hydrograph XML."""
    nws_id = station["station_id"]
    url = station["data_url"]
    result = {"value": None, "observed_at": None, "raw": {}, "fetch_error": None}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                result["fetch_error"] = f"NWS {nws_id} returned HTTP {resp.status_code}"
                return result
            text = resp.text
            # Most-recent observed point inside <observed>...</observed>
            obs_block = re.search(r"<observed>(.*?)</observed>", text, re.DOTALL)
            if not obs_block:
                result["fetch_error"] = "no <observed> block in NWS XML"
                return result
            datums = re.findall(
                r"<datum>.*?<valid[^>]*>([^<]+)</valid>.*?<primary[^>]*>([^<]+)</primary>.*?</datum>",
                obs_block.group(1),
                re.DOTALL,
            )
            if not datums:
                result["fetch_error"] = "no observed <datum> rows in NWS XML"
                return result
            valid_time, value = datums[-1]
            try:
                result["value"] = round(float(value), 2)
                result["observed_at"] = valid_time.strip()
                result["raw"]["river_stage_ft"] = result["value"]
            except ValueError:
                result["fetch_error"] = f"could not parse NWS value '{value}'"
    except Exception as e:
        logger.warning(f"[water] NWS fetch failed for {nws_id}: {e}")
        result["fetch_error"] = str(e)
    return result


async def _fetch_one(station: dict) -> dict:
    """Fetch + cache for a single station definition."""
    sid = station["station_id"]
    cache_key = f"{station['source']}:{sid}"
    now = datetime.now(timezone.utc)
    if cache_key in _STATION_CACHE_AT and (now - _STATION_CACHE_AT[cache_key]).total_seconds() < _CACHE_TTL:
        return _STATION_CACHE[cache_key]

    if station["source"] == "USGS":
        fetched = await _fetch_usgs(station)
    elif station["source"] == "NWS":
        fetched = await _fetch_nws(station)
    else:
        fetched = {"value": None, "observed_at": None, "raw": {}, "fetch_error": f"unsupported source {station['source']}"}

    _STATION_CACHE[cache_key] = fetched
    _STATION_CACHE_AT[cache_key] = now
    return fetched


def _categorize(value: Optional[float], thresholds: Optional[Dict[str, float]]) -> Dict:
    """Apply ONLY this station's thresholds to derive flood-category status."""
    if value is None:
        return {
            "status": "unknown",
            "status_explanation": "No current reading available from this station.",
        }
    if not thresholds:
        return {
            "status": "not_defined",
            "status_explanation": "Flood category not defined for this gauge.",
        }
    if value >= thresholds["major"]:
        sev = "major"
    elif value >= thresholds["moderate"]:
        sev = "moderate"
    elif value >= thresholds["flood"]:
        sev = "flood"
    elif value >= thresholds["action"]:
        sev = "action"
    else:
        sev = "normal"
    pretty = {
        "major": "Major flood",
        "moderate": "Moderate flood",
        "flood": "Flood stage",
        "action": "Action stage",
        "normal": "Below action stage",
    }
    return {
        "status": sev,
        "status_explanation": f"{pretty[sev]} - reading {value} ft compared against this station's thresholds.",
    }


def _build_record(station: dict, fetched: dict, lock_rm: float, role: str) -> Dict:
    """Compose the full structured record requested by the audit spec."""
    cat = _categorize(fetched.get("value"), station.get("thresholds"))
    return {
        "role": role,                                  # "official" | "reference"
        "station_id": station["station_id"],
        "station_name": station["station_name"],
        "source": station["source"],
        "river_mile": station.get("river_mile"),
        "distance_from_lock_miles": (
            round(abs(lock_rm - station["river_mile"]), 1) if station.get("river_mile") is not None else None
        ),
        "measurement_type": station.get("measurement_type"),
        "value": fetched.get("value"),
        "units": station.get("units", "ft"),
        "datum": station.get("datum"),
        "observed_at": fetched.get("observed_at"),
        "thresholds": station.get("thresholds"),
        "threshold_source": station.get("threshold_source"),
        "status": cat["status"],
        "status_explanation": cat["status_explanation"],
        "raw": fetched.get("raw", {}),
        "fetch_error": fetched.get("fetch_error"),
        "data_url": station.get("data_url"),
        "source_url": station.get("source_url"),
        "note": station.get("note"),
    }


async def get_water_conditions(lock_id: str) -> Dict:
    """Return the structured water-condition payload for a lock."""
    if lock_id not in LOCKS:
        return {"error": "Invalid lock ID"}
    if lock_id not in LOCK_STATIONS:
        return {"error": f"No station mapping configured for {lock_id}"}

    lock = LOCKS[lock_id]
    cfg = LOCK_STATIONS[lock_id]
    official = cfg["official_station"]
    references = cfg.get("reference_stations", [])
    lock_rm = lock["river_mile"]

    # Fetch in parallel
    coros = [_fetch_one(official)] + [_fetch_one(s) for s in references]
    fetched_list = await asyncio.gather(*coros)

    off = _build_record(official, fetched_list[0], lock_rm, role="official")
    refs = [
        _build_record(s, f, lock_rm, role="reference")
        for s, f in zip(references, fetched_list[1:])
    ]

    return {
        "lock_id": lock_id,
        "lock_name": lock["name"],
        "lock_river_mile": lock_rm,
        "official": off,
        "references": refs,
        "selection_reason": cfg.get("selection_reason"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_debug(lock_id: str) -> Dict:
    """Debug view: same payload plus raw selection reasoning and source URLs."""
    base = await get_water_conditions(lock_id)
    if "error" in base:
        return base
    base["debug"] = {
        "schema_version": 1,
        "notes": [
            "official.value should be compared only with official.thresholds.",
            "references[*].thresholds (if any) are not applied to the lock's status.",
            "When official.thresholds is null, status will be 'not_defined' and the UI shows 'Flood category not defined for this gauge.'",
        ],
    }
    return base
