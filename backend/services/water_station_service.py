# River Watch Backend - Water Station Service (v2)
#
# Fetches real-time values for a lock's authoritative station and any
# nearby reference stations, then applies *only* that station's thresholds
# to derive a flood-category status. If a station has no thresholds we
# return status="not_defined" and a human-readable status_explanation.
#
# Fetch sources:
#   - USGS  -> waterservices.usgs.gov  (JSON)
#   - NWS   -> NWPS API at api.water.noaa.gov (JSON, replaces legacy AHPS XML)
#   - USACE -> rivergages.mvr.usace.army.mil station HTML (fallback for NWS)
#
# Every record carries:
#   value, units, observed_at, status, status_explanation,
#   thresholds, threshold_source, datum, distance_from_lock_miles,
#   source_status, fetch_method, fallback_used, fetch_error
#
# Importantly: reference stations are NEVER allowed to drive the lock's
# flood status; their thresholds are intentionally None.

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Optional

import httpx

from config import LOCKS
from lock_stations import LOCK_STATIONS

logger = logging.getLogger(__name__)

# In-process cache (60 s)
_STATION_CACHE: Dict[str, dict] = {}
_STATION_CACHE_AT: Dict[str, datetime] = {}
_CACHE_TTL = 60  # seconds

_HTTP_TIMEOUT = 12.0
_DEFAULT_UA = "RiverWatch/1.0 (+https://github.com/cdillerud/AIS-Riverwatch)"


# ---------------------------------------------------------------------------
# Source-specific fetchers
# ---------------------------------------------------------------------------

async def _fetch_usgs(station: dict) -> dict:
    """Real-time values from the USGS Water Services JSON endpoint."""
    site_id = station["station_id"]
    url = station["data_url"]
    result = {
        "value": None,
        "observed_at": None,
        "raw": {},
        "fetch_error": None,
        "source_status": "ok",
        "fetch_method": "usgs_waterservices",
        "fallback_used": False,
    }
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers={"User-Agent": _DEFAULT_UA}) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                result["fetch_error"] = f"USGS {site_id} returned HTTP {resp.status_code}"
                result["source_status"] = "error"
                return result
            data = resp.json()
            for series in data.get("value", {}).get("timeSeries", []):
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
            if result["value"] is None:
                result["source_status"] = "no_data"
                result["fetch_error"] = f"USGS {site_id} returned no gage_height series"
    except Exception as e:
        logger.warning(f"[water] USGS fetch failed for {site_id}: {e}")
        result["fetch_error"] = str(e)
        result["source_status"] = "unreachable"
    return result


async def _fetch_nwps(client: httpx.AsyncClient, lid: str) -> dict:
    """
    Fetch latest observed stage from the NWPS API (api.water.noaa.gov).

    Endpoint: /nwps/v1/gauges/{lid}
    Response includes:
      status.observed.primary       -> current stage (ft)
      status.observed.primaryUnit
      status.observed.validTime
      status.observed.floodCategory -> 'no_flooding' | 'action' | 'minor' | 'moderate' | 'major'
      status.observed.secondary     -> flow (kcfs typically)
    """
    url = f"https://api.water.noaa.gov/nwps/v1/gauges/{lid}"
    out = {
        "value": None,
        "observed_at": None,
        "raw": {},
        "flood_category_api": None,
        "fetch_error": None,
        "source_status": "ok",
        "fetch_method": "nwps_api",
        "data_url": url,
    }
    try:
        resp = await client.get(url, headers={"User-Agent": _DEFAULT_UA, "Accept": "application/json"})
        if resp.status_code != 200:
            out["fetch_error"] = f"NWPS {lid} returned HTTP {resp.status_code}"
            out["source_status"] = "error"
            return out
        data = resp.json()
        status = (data.get("status") or {}).get("observed") or {}
        primary = status.get("primary")
        primary_unit = status.get("primaryUnit", "ft")
        valid_time = status.get("validTime")
        flood_cat = status.get("floodCategory")
        secondary = status.get("secondary")
        secondary_unit = status.get("secondaryUnit")
        if primary is None:
            out["fetch_error"] = f"NWPS {lid} returned no observed.primary"
            out["source_status"] = "no_data"
            return out
        try:
            out["value"] = round(float(primary), 2)
        except (TypeError, ValueError):
            out["fetch_error"] = f"NWPS {lid} primary not numeric: {primary!r}"
            out["source_status"] = "no_data"
            return out
        out["observed_at"] = valid_time
        out["flood_category_api"] = flood_cat
        out["raw"]["river_stage_ft"] = out["value"] if primary_unit == "ft" else None
        out["raw"]["nwps_primary"] = out["value"]
        out["raw"]["nwps_primary_unit"] = primary_unit
        if secondary is not None:
            try:
                sec = float(secondary)
                out["raw"]["nwps_secondary"] = sec
                out["raw"]["nwps_secondary_unit"] = secondary_unit
                if secondary_unit == "kcfs":
                    out["raw"]["discharge_cfs"] = round(sec * 1000.0, 0)
                elif secondary_unit == "cfs":
                    out["raw"]["discharge_cfs"] = round(sec, 0)
            except (TypeError, ValueError):
                pass
    except Exception as e:
        logger.warning(f"[water] NWPS fetch failed for {lid}: {e}")
        out["fetch_error"] = str(e)
        out["source_status"] = "unreachable"
    return out


_USACE_LATEST_RE = re.compile(
    r"Latest&nbsp;Stage</font></td>\s*<td[^>]*>\s*<font[^>]*>([-\d\.M]+)\s*Ft\.",
    re.IGNORECASE,
)
_USACE_TIMESTAMP_RE = re.compile(
    r"Latest Data<br>([0-9/]+\s+[0-9:]+\s+\w+)",
    re.IGNORECASE,
)
_USACE_WATER_TEMP_RE = re.compile(
    r"Latest Water Temp</font></td>\s*<td[^>]*>\s*<font[^>]*>([-\d\.M]+)\s*&deg;F",
    re.IGNORECASE,
)


async def _fetch_usace_rivergages(client: httpx.AsyncClient, sid: str) -> dict:
    """
    Fallback fetch by scraping the USACE Rivergages station page.

    Endpoint: https://rivergages.mvr.usace.army.mil/WaterControl/stationinfo2.cfm?sid=SID&fid=&dt=S

    Note: USACE 'Latest Stage' is the local-gage-zero reading and may
    differ from the NWPS tailwater value (e.g. HSTM5 NWPS = 6.49 ft
    tailwater, USACE = 86.81 ft local stage above 1912 gage zero).
    We surface the reading verbatim and tag fetch_method='usace_rivergages'
    so the consumer can see this is a fallback rather than the primary
    observed stage.
    """
    url = f"https://rivergages.mvr.usace.army.mil/WaterControl/stationinfo2.cfm?sid={sid}&fid=&dt=S"
    out = {
        "value": None,
        "observed_at": None,
        "raw": {},
        "fetch_error": None,
        "source_status": "ok",
        "fetch_method": "usace_rivergages",
        "data_url": url,
    }
    try:
        resp = await client.get(url, headers={"User-Agent": _DEFAULT_UA})
        if resp.status_code != 200:
            out["fetch_error"] = f"USACE {sid} returned HTTP {resp.status_code}"
            out["source_status"] = "error"
            return out
        body = resp.text
        m = _USACE_LATEST_RE.search(body)
        if not m:
            out["fetch_error"] = "Latest Stage row not found on USACE page"
            out["source_status"] = "no_data"
            return out
        raw = m.group(1).strip()
        if raw.upper() == "M":  # USACE uses "M" for missing
            out["fetch_error"] = "USACE reports missing data (M)"
            out["source_status"] = "no_data"
            return out
        try:
            out["value"] = round(float(raw), 2)
            out["raw"]["usace_stage_ft"] = out["value"]
        except ValueError:
            out["fetch_error"] = f"could not parse USACE stage '{raw}'"
            out["source_status"] = "no_data"
            return out
        ts = _USACE_TIMESTAMP_RE.search(body)
        if ts:
            out["observed_at"] = ts.group(1).strip()
        tw = _USACE_WATER_TEMP_RE.search(body)
        if tw and tw.group(1).strip().upper() != "M":
            try:
                temp_f = float(tw.group(1))
                out["raw"]["water_temp_f"] = round(temp_f, 1)
                out["raw"]["water_temp_c"] = round((temp_f - 32) * 5 / 9, 1)
            except ValueError:
                pass
    except Exception as e:
        logger.warning(f"[water] USACE fetch failed for {sid}: {e}")
        out["fetch_error"] = str(e)
        out["source_status"] = "unreachable"
    return out


async def _fetch_nws_with_fallback(station: dict) -> dict:
    """
    Try NWPS API first; if it fails or returns no data, fall back to USACE
    Rivergages. Result always carries fetch_method + fallback_used so the
    UI can label the reading appropriately.
    """
    lid = station["station_id"]
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        primary = await _fetch_nwps(client, lid)
        if primary["value"] is not None:
            primary["fallback_used"] = False
            return primary
        # Try USACE as fallback
        fallback = await _fetch_usace_rivergages(client, lid)
        fallback["fallback_used"] = True
        fallback["primary_fetch_error"] = primary.get("fetch_error")
        fallback["primary_source_status"] = primary.get("source_status")
        return fallback


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
        fetched = await _fetch_nws_with_fallback(station)
    else:
        fetched = {
            "value": None,
            "observed_at": None,
            "raw": {},
            "fetch_error": f"unsupported source {station['source']}",
            "source_status": "unsupported",
            "fetch_method": None,
            "fallback_used": False,
        }

    _STATION_CACHE[cache_key] = fetched
    _STATION_CACHE_AT[cache_key] = now
    return fetched


# ---------------------------------------------------------------------------
# Status categorization (uses ONLY this station's own thresholds)
# ---------------------------------------------------------------------------

def _categorize(value: Optional[float], thresholds: Optional[Dict[str, float]]) -> Dict:
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
    # Prefer the fetcher-reported data_url (NWPS / USACE) over the static one
    # in the station definition so the UI/debug view shows the URL that
    # actually produced the reading.
    data_url = fetched.get("data_url") or station.get("data_url")
    return {
        "role": role,                                       # "official" | "reference"
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
        "source_status": fetched.get("source_status"),
        "fetch_method": fetched.get("fetch_method"),
        "fallback_used": fetched.get("fallback_used", False),
        "primary_fetch_error": fetched.get("primary_fetch_error"),
        "data_url": data_url,
        "source_url": station.get("source_url"),
        "note": station.get("note"),
    }


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------

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
        "schema_version": 2,
        "notes": [
            "official.value should be compared only with official.thresholds.",
            "references[*].thresholds (if any) are not applied to the lock's status.",
            "When official.thresholds is null, status will be 'not_defined' and the UI shows 'Flood category not defined for this gauge.'",
            "fetch_method='nwps_api' is the primary NWS source; fetch_method='usace_rivergages' indicates a fallback to the USACE rivergages station page.",
            "Reference station readings/discharge are kept in references[*], NOT merged into legacy 'conditions' without labelling.",
        ],
    }
    return base
