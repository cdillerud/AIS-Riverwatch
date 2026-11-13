"""Lock closures and high-water limits.

Two USACE sources, both machine-readable:

* NDC Corps Locks "Active or Future Stoppages" (LPMS):
  https://ndc.ops.usace.army.mil/ords/lpms/stall_stoppage_json - every current
  and scheduled lock stall/stoppage nationwide (river, lock, chamber, begin,
  end, reason, traffic stopped). Shares the NDC rate limit (5 requests a
  minute) with lockqueue_xml, so server.usace_refresh_task fetches it once a
  pass, in the same paced request stream.
* USACE CWMS Data API (water.usace.army.mil):
  https://cwms-data.usace.army.mil/cwms-data/timeseries - the districts' own
  15/30-minute flow, pool elevation and tailwater stage at each dam.

Limits (services/lock_limits_data.py) are only compared with a reading of the
same quantity, on the same gauge and datum. Anything else is shown as
reference text. Nothing here ever says a lock is OPEN, and a high river is
never reported as a closure: only USACE stoppages set CLOSED/RESTRICTED.
"""
import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from bs4 import BeautifulSoup

from services.lock_limits_data import LOCK_LIMITS, ST_PAUL

logger = logging.getLogger(__name__)

STOPPAGE_URL = "https://ndc.ops.usace.army.mil/ords/lpms/stall_stoppage_json"
CWMS_URL = "https://cwms-data.usace.army.mil/cwms-data/timeseries"

NOTE_PCT = 80                 # planning note at >= 80% of a closure flow / stage
POOL_NOTE_MARGIN_FT = 1.5     # ... or a pool within 1.5 ft of its closure elevation
MAX_READING_AGE = timedelta(hours=8)
TREND_LOOKBACK = timedelta(hours=6)
STOPPAGE_MAX_AGE = timedelta(hours=1)    # older feed => ignore (worker stalled)
UPCOMING_WINDOW = timedelta(hours=48)
MVR_PAGE_MAX_AGE_DAYS = 14

# LPMS Mississippi River lock numbers -> River Watch lock ids. 51/52 are Upper
# and Lower St. Anthony Falls (not River Watch locks); 5A is "55".
_LPMS_MI = {f"{n:02d}": f"lock_{n}" for n in list(range(1, 23)) + [24, 25]}
_LPMS_MI.update({"55": "lock_5a", "26": "melvin_price", "27": "chain_of_rocks"})

_TZ = {"CST": -6, "CDT": -5, "EST": -5, "EDT": -4, "MST": -7, "MDT": -6, "PST": -8, "PDT": -7, "GMT": 0, "UTC": 0}


class RateLimited(Exception):
    pass


# --------------------------------------------------------------------------
# NDC stoppages
# --------------------------------------------------------------------------
def parse_lpms_time(text: Optional[str]) -> Optional[datetime]:
    """'11/09/2026 10:09:00 CST' -> aware UTC datetime; ' CST' (no date) -> None."""
    if not text:
        return None
    parts = text.strip().rsplit(" ", 1)
    if len(parts) != 2 or parts[1] not in _TZ:
        return None
    try:
        local = datetime.strptime(parts[0].strip(), "%m/%d/%Y %H:%M:%S")
    except ValueError:
        return None
    return (local - timedelta(hours=_TZ[parts[1]])).replace(tzinfo=timezone.utc)


def _reason(text: Optional[str]) -> str:
    r = re.sub(r"\(\s+", "(", (text or "").strip()) or "reason not given"
    return r[0].lower() + r[1:] if r[:1].isupper() and not r[:2].isupper() else r


def _central(t: datetime) -> str:
    """Display time in Central time (all River Watch locks are Central)."""
    # US Central: CDT from the 2nd Sunday of March to the 1st Sunday of November
    y = t.year
    start = datetime(y, 3, 8, 8, tzinfo=timezone.utc) + timedelta(days=(6 - date(y, 3, 8).weekday()) % 7)
    end = datetime(y, 11, 1, 7, tzinfo=timezone.utc) + timedelta(days=(6 - date(y, 11, 1).weekday()) % 7)
    dst = start <= t < end
    local = t + timedelta(hours=-5 if dst else -6)
    hour = local.strftime("%I:%M %p").lstrip("0")
    return f"{local.strftime('%b')} {local.day} {hour} {'CDT' if dst else 'CST'}"


def stoppage_effects(rows: List[dict], now: datetime) -> Dict[str, dict]:
    """USACE stoppages on Mississippi River locks -> per-lock effect.

    {lock_id: {"status": "CLOSED"|"RESTRICTED"|None, "closure_info": str,
               "upcoming": str|None}}
    - main chamber (1), traffic stopped, in effect now -> CLOSED
    - other chamber stopped, or a stall without stopped traffic -> RESTRICTED
    - scheduled to start within 48 h -> `upcoming` note only (status untouched)
    """
    out: Dict[str, dict] = {}
    for r in rows or []:
        if not isinstance(r, dict) or (r.get("riverCode") or "").upper() != "MI":
            continue
        lock_id = _LPMS_MI.get(str(r.get("lockNumber") or "").strip().zfill(2))
        if not lock_id:
            continue
        begin, end = parse_lpms_time(r.get("beginStopDate")), parse_lpms_time(r.get("endStopDate"))
        if begin is None or (end is not None and end <= now):
            continue
        main = str(r.get("chamberNumber") or "1").strip() == "1"
        stopped = (r.get("trafficStopped") or "").upper() == "Y"
        reason = _reason(r.get("reasonCode"))
        until = f"until {_central(end)}" if end else "until further notice"
        eff = out.setdefault(lock_id, {"status": None, "closure_info": None, "upcoming": None})
        if begin <= now:
            if main and stopped:
                status, info = "CLOSED", f"Closed by USACE: {reason}, {until}"
            elif stopped:
                status, info = "RESTRICTED", f"Auxiliary chamber closed by USACE: {reason}, {until}"
            else:
                status, info = "RESTRICTED", f"USACE reports delays: {reason}, {until}"
            if eff["status"] != "CLOSED":  # CLOSED wins over RESTRICTED
                if eff["status"] == "RESTRICTED" and status == "RESTRICTED":
                    info = f"{eff['closure_info']}; {info}"
                eff["status"], eff["closure_info"] = status, info
        elif begin - now <= UPCOMING_WINDOW and main and stopped and eff["upcoming"] is None:
            span = f"{_central(begin)} - {_central(end)}" if end else f"from {_central(begin)}"
            eff["upcoming"] = f"USACE scheduled closure {span}: {reason}"
    return {k: v for k, v in out.items() if v["status"] or v["upcoming"]}


async def fetch_stoppages(client) -> List[dict]:
    """One request to the NDC stoppage feed. Raises RateLimited."""
    resp = await client.get(STOPPAGE_URL)
    text = (resp.text or "").strip()
    if resp.status_code == 429 or "rate limit" in text[:200].lower():
        raise RateLimited(text[:120])
    if resp.status_code != 200 or not text.startswith("["):
        raise ValueError(f"HTTP {resp.status_code}: {text[:120]}")
    import json
    rows = json.loads(text, strict=False)
    return rows if isinstance(rows, list) else []


_state: dict = {"stoppages": None, "stoppages_at": None, "readings": {}, "readings_at": None}


def set_stoppages(rows: List[dict], at: Optional[datetime] = None) -> None:
    _state["stoppages"] = rows
    _state["stoppages_at"] = at or datetime.now(timezone.utc)


def current_stoppage_effects(now: Optional[datetime] = None) -> Dict[str, dict]:
    now = now or datetime.now(timezone.utc)
    at = _state.get("stoppages_at")
    if _state.get("stoppages") is None or at is None or now - at > STOPPAGE_MAX_AGE:
        return {}
    return stoppage_effects(_state["stoppages"], now)


# --------------------------------------------------------------------------
# Rock Island lock status page
# --------------------------------------------------------------------------
def _match_row(name: str, match_lock: Callable[[str], Optional[str]]) -> Optional[str]:
    """Lock id for a district table row; "Locks & Dam 14 (Aux)" -> lock_14."""
    lock_id = match_lock(name)
    if lock_id is None and "AUX" in name.upper():
        lock_id = match_lock(re.sub(r"(?i)\blocks\b", "Lock", name))
    return lock_id


def mvr_page_updated(html: str) -> Optional[date]:
    m = re.search(r"Updated:?\s*([A-Z][a-z]+)\.?\s+(\d{1,2}),\s*(\d{4})", BeautifulSoup(html, "html.parser").get_text(" "))
    if not m:
        return None
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", fmt).date()
        except ValueError:
            continue
    return None


def parse_mvr_status(html: str, match_lock: Callable[[str], Optional[str]], now: datetime) -> Dict[str, dict]:
    """Rock Island District status table -> {lock_id: {status, closure_info}}.

    - Auxiliary-chamber rows ("Locks & Dam 14 (Aux)") never set the lock's
      status (the seasonal aux closure used to mark Lock 14 CLOSED); they only
      add text when the main lock has none.
    - A page not updated for MVR_PAGE_MAX_AGE_DAYS is ignored entirely: an
      old OPEN is no evidence, and an old CLOSED may be long over.
    """
    updated = mvr_page_updated(html)
    if updated is not None and (now.date() - updated).days > MVR_PAGE_MAX_AGE_DAYS:
        return {}
    out: Dict[str, dict] = {}
    aux: Dict[str, str] = {}
    for table in BeautifulSoup(html, "html.parser").find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            name = cells[0].get_text(" ", strip=True)
            lock_id = _match_row(name, match_lock)
            if not lock_id:
                continue
            text = cells[2].get_text(" ", strip=True)
            upper = text.upper()
            if "AUX" in name.upper():
                if "CLOSED" in upper:
                    aux[lock_id] = "Auxiliary lock closed (USACE Rock Island District)"
                continue
            if "CLOSED" in upper:
                out[lock_id] = {"status": "CLOSED", "closure_info": text}
            elif "RESTRICT" in upper:
                out[lock_id] = {"status": "RESTRICTED", "closure_info": text}
            elif "OPEN" in upper:
                # "OPEN (Upcoming Closure: ...)" keeps its text
                out[lock_id] = {"status": "OPEN", "closure_info": text if len(text) > 4 else None}
    for lock_id, note in aux.items():
        cur = out.setdefault(lock_id, {"status": None, "closure_info": None})
        if not cur.get("closure_info"):
            cur["closure_info"] = note
    return out


# --------------------------------------------------------------------------
# District limit pages (re-scrape)
# --------------------------------------------------------------------------
def _num(text: str) -> Optional[float]:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", text or "")
    if not m or "'" in text:
        return None
    return float(m.group(0).replace(",", ""))


def parse_mvp_limits(html: str) -> Dict[str, dict]:
    """St. Paul District "Flow and elevation thresholds" table."""
    out = {}
    for table in BeautifulSoup(html, "html.parser").find_all("table"):
        rows = table.find_all("tr")
        if not rows or "outdraft" not in rows[0].get_text(" ").lower():
            continue
        for row in rows[1:]:
            c = [x.get_text(" ", strip=True) for x in row.find_all(["td", "th"])]
            if len(c) < 5:
                continue
            key = c[0].strip().upper()
            lock_id = "lsaf" if key == "LSAF" else f"lock_{key.lower()}"
            out[lock_id] = {
                "outdraft_cfs": int(_num(c[1])) if _num(c[1]) is not None else c[1],
                "gates_pulled_cfs": int(_num(c[2])) if _num(c[2]) is not None else None,
                "closed_cfs": int(_num(c[3])) if _num(c[3]) is not None else None,
                "closed_pool_ft": _num(c[4]),
            }
    return out


def parse_mvr_limits(html: str, match_lock: Callable[[str], Optional[str]]) -> Dict[str, dict]:
    """Rock Island District status table -> flood / closure stages."""
    out: Dict[str, dict] = {}
    for table in BeautifulSoup(html, "html.parser").find_all("table"):
        for row in table.find_all("tr"):
            c = [x.get_text(" ", strip=True) for x in row.find_all(["td", "th"])]
            if len(c) < 5:
                continue
            lock_id = _match_row(c[0], match_lock)
            if not lock_id:
                continue
            if "AUX" in c[0].upper():
                out.setdefault(lock_id, {})["aux_closure_stage_ft"] = _num(c[4])
            else:
                out.setdefault(lock_id, {}).update({"flood_stage_ft": _num(c[3]), "closure_stage_ft": _num(c[4])})
    return out


def diff_limits(scraped: Dict[str, dict], stored: Dict[str, dict] = LOCK_LIMITS) -> List[str]:
    """Human-readable differences between a fresh scrape and the stored data."""
    diffs = []
    for lock_id, vals in sorted(scraped.items()):
        if lock_id not in stored:
            continue
        for key, val in vals.items():
            if stored[lock_id].get(key) != val:
                diffs.append(f"{lock_id}.{key}: stored {stored[lock_id].get(key)!r}, page now {val!r}")
    return diffs


# --------------------------------------------------------------------------
# Current readings (CWMS) and the comparison
# --------------------------------------------------------------------------
def cwms_latest(payload: dict, now: datetime) -> Optional[dict]:
    """Latest value of a CWMS timeseries response, its trend over ~6 h.
    None if there is no value newer than MAX_READING_AGE."""
    vals = [v for v in (payload or {}).get("values") or [] if v and len(v) >= 2 and v[1] is not None]
    if not vals:
        return None
    t_last, v_last = vals[-1][0], float(vals[-1][1])
    at = datetime.fromtimestamp(t_last / 1000, tz=timezone.utc)
    if now - at > MAX_READING_AGE:
        return None
    target = t_last - TREND_LOOKBACK.total_seconds() * 1000
    earlier = [v for v in vals if v[0] <= target]
    delta = v_last - float(earlier[-1][1]) if earlier else None
    return {"value": v_last, "at": at.isoformat(), "units": payload.get("units"), "change_6h": delta}


def _trend(reading: dict, flow: bool) -> Optional[str]:
    d = reading.get("change_6h")
    if d is None:
        return None
    eps = abs(reading["value"]) * 0.02 if flow else 0.2
    return "rising" if d > eps else "falling" if d < -eps else "steady"


def _cfs(v) -> str:
    return f"{int(round(v)):,} cfs"


def assess(lock_id: str, readings: Optional[dict] = None, *, district_restricted: bool = False) -> dict:
    """Compare a lock's current readings with its published closure limits.

    readings: {"flow": cwms_latest(...), "pool": ..., "tail": ...}; missing or
    stale entries make that comparison reference-only.
    Returns {"lock_id", "district", "source_url", "checked", "comparisons":
    [...computed...], "references": [text...], "note": str|None}.
    """
    lim = LOCK_LIMITS.get(lock_id)
    out = {"lock_id": lock_id, "district": None, "source_url": None, "checked": None,
           "comparisons": [], "references": [], "note": None}
    if not lim:
        return out
    readings = readings or {}
    out.update({"district": lim["district"], "source_url": lim["source_url"], "checked": lim["checked"]})
    if lim.get("none_published"):
        out["references"].append(f"{lim['district']} publishes no closure level for this lock (its Operation Limits "
                                 "page lists pool regulation limits only)")
        return out

    district = lim["district"]
    comps, refs = out["comparisons"], out["references"]

    if district == ST_PAUL:
        flow = readings.get("flow")
        rec = lim.get("rec_closed_cfs")
        flow_limits = []
        if rec:
            flow_limits.append(("rec", rec, "closes this lock to recreational boats"))
        if lim.get("closed_cfs"):
            flow_limits.append(("closed", lim["closed_cfs"], "closes this lock" + (" to all traffic" if rec else "")))
        for kind, limit, what in flow_limits:
            if flow:
                pct = round(100 * flow["value"] / limit)
                trend = _trend(flow, True)
                comps.append({
                    "kind": "flow", "limit_kind": kind, "current": round(flow["value"]), "limit": limit,
                    "units": "cfs", "percent": pct, "trend": trend, "observed_at": flow["at"],
                    "gauge": f"USACE CWMS {lim['cwms_flow']} (outflow at the dam)",
                    "text": (f"River at {pct}% of the flow that {what} ({_cfs(limit)})"
                             + (f" - {trend}" if trend else "")),
                })
            else:
                refs.append(f"{what[0].upper()}{what[1:]} at {_cfs(limit)} ({district})")
        pool = readings.get("pool")
        if lim.get("closed_pool_ft") is not None:
            limit = lim["closed_pool_ft"]
            if pool:
                margin = round(limit - pool["value"], 1)
                trend = _trend(pool, False)
                comps.append({
                    "kind": "pool", "limit_kind": "closed", "current": round(pool["value"], 2), "limit": limit,
                    "units": "ft MSL 1912", "margin_ft": margin, "trend": trend, "observed_at": pool["at"],
                    "gauge": f"USACE CWMS {lim['cwms_pool']} (pool at the dam)",
                    "text": (f"Pool at {pool['value']:.1f} ft, {abs(margin):.1f} ft "
                             f"{'below' if margin >= 0 else 'above'} the level that closes this lock ({limit:.1f} ft)"
                             + (f" - {trend}" if trend else "")),
                })
            else:
                refs.append(f"Closes to navigation at pool elevation {limit:.2f} ft MSL 1912 ({district})")
        if isinstance(lim.get("outdraft_cfs"), int):
            refs.append(f"Outdraft warning from {_cfs(lim['outdraft_cfs'])}"
                        + (f", dam gates pulled at {_cfs(lim['gates_pulled_cfs'])}" if lim.get("gates_pulled_cfs") else ""))
    else:  # Rock Island: tailwater stage
        tail = readings.get("tail") if lim.get("cwms_tail") else None
        limit = lim["closure_stage_ft"]
        if tail:
            pct = round(100 * tail["value"] / limit)
            trend = _trend(tail, False)
            comps.append({
                "kind": "tailwater", "limit_kind": "closed", "current": round(tail["value"], 2), "limit": limit,
                "units": "ft", "percent": pct, "margin_ft": round(limit - tail["value"], 1), "trend": trend,
                "observed_at": tail["at"], "gauge": f"USACE CWMS {lim['cwms_tail']} (tailwater gauge at the lock)",
                "text": (f"Tailwater at {tail['value']:.1f} ft, {pct}% of the stage that closes this lock "
                         f"({limit:.1f} ft)" + (f" - {trend}" if trend else "")),
            })
        else:
            refs.append(f"Closes to navigation at {limit:.1f} ft on the tailwater gauge ({district})")
        if lim.get("aux_closure_stage_ft"):
            refs.append(f"Auxiliary lock closes at {lim['aux_closure_stage_ft']:.1f} ft tailwater")
        if lim.get("flood_stage_ft"):
            refs.append(f"Flood stage {lim['flood_stage_ft']:.1f} ft ({district})")

    for c in comps:
        c["near"] = bool((c["kind"] != "pool" and c.get("percent") is not None and c["percent"] >= NOTE_PCT)
                         or (c["kind"] == "pool" and c["margin_ft"] <= POOL_NOTE_MARGIN_FT))
    near = [c for c in comps if c["near"]]
    pick = near or (comps if district_restricted else [])
    if pick:
        top = max(pick, key=lambda c: c.get("percent") or 0 if c["kind"] != "pool" else 100 - 10 * c["margin_ft"])
        out["note"] = f"{top['text']} ({district})"
    return out


async def _fetch_series(client, office: str, name: str, now: datetime) -> Optional[dict]:
    try:
        resp = await client.get(CWMS_URL, params={
            "office": office, "name": name, "unit": "EN",
            "begin": (now - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")},
            headers={"Accept": "application/json;version=2"})
        if resp.status_code != 200:
            logger.debug(f"CWMS {name}: HTTP {resp.status_code}")
            return None
        return cwms_latest(resp.json(), now)
    except Exception as e:
        logger.debug(f"CWMS {name}: {e}")
        return None


async def refresh_readings(client) -> Dict[str, dict]:
    """Fetch every lock's limit-relevant readings from CWMS (a few at a time)."""
    now = datetime.now(timezone.utc)
    sem = asyncio.Semaphore(4)
    readings: Dict[str, dict] = {}

    async def one(lock_id, key, office, name):
        async with sem:
            r = await _fetch_series(client, office, name, now)
        if r:
            readings.setdefault(lock_id, {})[key] = r

    jobs = []
    for lock_id, lim in LOCK_LIMITS.items():
        for key, field in (("flow", "cwms_flow"), ("pool", "cwms_pool"), ("tail", "cwms_tail")):
            if lim.get(field):
                jobs.append(one(lock_id, key, lim["cwms_office"], lim[field]))
    await asyncio.gather(*jobs)
    _state["readings"], _state["readings_at"] = readings, now
    return readings


def current_assessment(lock_id: str, *, district_restricted: bool = False) -> dict:
    at = _state.get("readings_at")
    fresh = at is not None and datetime.now(timezone.utc) - at < MAX_READING_AGE
    return assess(lock_id, _state["readings"].get(lock_id) if fresh else None,
                  district_restricted=district_restricted)


async def refresh_loop(headers: dict, interval_s: int = 900) -> None:
    import httpx
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        while True:
            try:
                r = await refresh_readings(client)
                logger.info(f"Lock limit readings refreshed for {len(r)} locks")
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning(f"Lock limit refresh failed: {e}")
            try:
                await asyncio.sleep(interval_s)
            except asyncio.CancelledError:
                return
