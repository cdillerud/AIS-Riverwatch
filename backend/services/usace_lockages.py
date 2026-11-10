"""
Completed lockages from the USACE lock queue feed.

https://ndc.ops.usace.army.mil/ords/lockqueue_xml?in_river=MI&in_lock=N lists
each lock's queue AND its completed lockages for roughly the last 30 days. A
completed row has ARRIVAL_DATE, SOL_DATE (start of lockage) and
END_OF_LOCKAGE. A tow too long for the chamber is locked in "cuts": one row
per cut, sharing the vessel and arrival time.

`completed_lockages` turns those rows into one record per lockage in the same
shape the AIS lock-passage tracker writes to db.lockage_history, with
source="usace_lpms" and confidence="high" (lock-operator entered).
"""
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

# Lock queue times are local river time, labelled per row.
_TZ_OFFSETS = {"CST": -6, "CDT": -5, "EST": -5, "EDT": -4, "MST": -7, "MDT": -6}
_DIRECTIONS = {"U": "upbound", "D": "downbound"}


def parse_time(text: Optional[str], tz_label: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        local = datetime.strptime(text.strip(), "%m/%d/%y %H:%M")
    except ValueError:
        return None
    hours = _TZ_OFFSETS.get((tz_label or "CST").strip().upper(), -6)
    return local.replace(tzinfo=timezone(timedelta(hours=hours))).astimezone(timezone.utc)


def _row_value(row, tag: str) -> Optional[str]:
    if isinstance(row, dict):
        value = row.get(tag)
    else:  # xml.etree Element
        el = row.find(tag)
        value = el.text if el is not None else None
    value = value.strip() if isinstance(value, str) else value
    return value or None


def completed_lockages(rows: Iterable, lock_id: str, lock_name: Optional[str] = None) -> List[dict]:
    """Group a lock's completed queue rows (cuts) into lockage records."""
    groups = {}
    for row in rows:
        start = _row_value(row, "SOL_DATE")
        end = _row_value(row, "END_OF_LOCKAGE")
        if not (start and end):
            continue  # still waiting or locking
        tz = _row_value(row, "TIMEZONE")
        mmsi = _row_value(row, "MMSI")
        vessel_no = _row_value(row, "VESSEL_NO")
        name = _row_value(row, "VESSEL_NAME") or "Unknown"
        arrival = parse_time(_row_value(row, "ARRIVAL_DATE"), tz)
        sol = parse_time(start, tz)
        eol = parse_time(end, tz)
        if not (sol and eol):
            continue
        key = (mmsi or vessel_no or name, arrival or sol, _row_value(row, "DIRECTION"))
        g = groups.setdefault(key, {
            "name": name, "mmsi": mmsi, "vessel_no": vessel_no,
            "direction": _DIRECTIONS.get(_row_value(row, "DIRECTION") or "", "unknown"),
            "arrival": arrival, "starts": [], "ends": [], "barges": 0, "cuts": 0,
        })
        g["starts"].append(sol)
        g["ends"].append(eol)
        g["cuts"] += 1
        try:
            g["barges"] += int(_row_value(row, "NUM_BARGES") or 0)
        except ValueError:
            pass

    records = []
    for g in groups.values():
        entry, exit_ = min(g["starts"]), max(g["ends"])
        arrival = g["arrival"] or entry
        if exit_ < entry:
            continue
        wait = max(0.0, (entry - arrival).total_seconds() / 60)
        duration = (exit_ - entry).total_seconds() / 60
        records.append({
            "lock_id": lock_id,
            "lock_name": lock_name,
            "vessel_name": g["name"],
            "mmsi": g["mmsi"],
            "usace_vessel_no": g["vessel_no"],
            "direction": g["direction"],
            "arrival_time": arrival,
            "entry_time": entry,
            "exit_time": exit_,
            "wait_time_minutes": round(wait, 1),
            "lockage_duration_minutes": round(duration, 1),
            "total_time_minutes": round(wait + duration, 1),
            "barge_count": g["barges"],
            "is_tow": g["barges"] > 0,
            "cuts": g["cuts"],
            "is_double_lockage": g["cuts"] > 1,
            "source": "usace_lpms",
            "confidence": "high",
            # When it happened, so the 7-day averages and "recent" sorts use
            # lockage time rather than the time we happened to fetch it.
            "recorded_at": exit_,
        })
    return records


def record_key(record: dict) -> dict:
    """Natural key for idempotent upserts (the feed repeats rows for ~30 days)."""
    return {
        "lock_id": record["lock_id"],
        "source": "usace_lpms",
        "usace_vessel_no": record.get("usace_vessel_no"),
        "vessel_name": record["vessel_name"],
        "entry_time": record["entry_time"],
    }
