"""
Data freshness: how old each source's data is, so stale numbers are labelled
instead of shown as current.

The USACE worker visits every lock about every 6 minutes (27 locks x 13 s);
a lock's queue older than QUEUE_STALE_MINUTES means fetches for it are
failing or the worker is rate-limited/stuck. On a failed fetch the worker
keeps the previous rows, so the fetch time - not the rows - tells the age.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

QUEUE_STALE_MINUTES = 20
AIS_STALE_MINUTES = 5


def age_minutes(at: Optional[datetime], now: datetime) -> Optional[int]:
    if at is None:
        return None
    if isinstance(at, str):
        at = datetime.fromisoformat(at)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return max(0, int((now - at).total_seconds() // 60))


def queue_freshness(fetched_at: Optional[datetime], now: datetime) -> dict:
    age = age_minutes(fetched_at, now)
    return {"queue_age_minutes": age, "queue_stale": age is None or age > QUEUE_STALE_MINUTES}


def usace_summary(fetched_at_by_lock: Dict[str, datetime], expected: Iterable[str], now: datetime,
                  no_data_locks: Iterable[str] = ()) -> dict:
    """Overall USACE freshness. `no_data_locks` (e.g. 5A, which USACE never
    publishes) don't count against it."""
    skip = set(no_data_locks)
    expected = [l for l in expected if l not in skip]
    ages = {l: age_minutes(fetched_at_by_lock.get(l), now) for l in expected}
    stale = sorted(l for l, a in ages.items() if a is None or a > QUEUE_STALE_MINUTES)
    known = [a for a in ages.values() if a is not None]
    if not expected:
        status = "ok"
    elif len(stale) == len(expected):
        status = "down"
    elif stale:
        status = "degraded"
    else:
        status = "ok"
    return {
        "status": status,
        "locks": len(expected),
        "stale_locks": stale,
        "newest_minutes": min(known) if known else None,
        "oldest_minutes": max(known) if known else None,
    }


def ais_summary(configured: bool, connected: bool, last_data: Optional[datetime], now: datetime) -> dict:
    """The phone/receiver AIS feed is optional: not configured is not a fault."""
    age = age_minutes(last_data, now)
    if not configured:
        status = "not_configured"
    elif not connected or age is None or age > AIS_STALE_MINUTES:
        status = "down"
    else:
        status = "ok"
    return {"status": status, "last_message_minutes_ago": age}


def overall(database_ok: bool, usace: dict) -> str:
    if not database_ok:
        return "down"
    return "ok" if usace["status"] == "ok" else "degraded"

# --- Uptime history -----------------------------------------------------------
# A sample a minute ({t, ok}) while the feed is configured. Gaps (server off)
# count as neither up nor down. An outage = consecutive "down" samples.
SAMPLE_SECONDS = 60
ALERT_AFTER_MINUTES = 15
_GAP = timedelta(seconds=3 * SAMPLE_SECONDS)


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def uptime_percent(samples: List[Tuple[datetime, bool]], now: datetime, hours: float) -> Optional[float]:
    since = now - timedelta(hours=hours)
    win = [ok for t, ok in samples if _utc(t) >= since]
    if not win:
        return None
    return round(100.0 * sum(win) / len(win), 1)


def outages(samples: List[Tuple[datetime, bool]], min_minutes: int = 5) -> List[dict]:
    """Runs of down samples, newest first. A run still going has end=None.
    A gap in the samples (server off) ends a run."""
    runs, start, last = [], None, None
    for t, ok in samples:
        t = _utc(t)
        if start is not None and (ok or (last is not None and t - last > _GAP)):
            runs.append((start, last))
            start = None
        if not ok and start is None:
            start = t
        last = t
    if start is not None:
        runs.append((start, None))
    out = []
    for s, e in runs:
        end = e if e is not None else last
        minutes = int((end - s).total_seconds() // 60) + 1
        if minutes >= min_minutes:
            out.append({"start": s.isoformat(), "end": e.isoformat() if e is not None else None,
                        "minutes": minutes})
    return out[::-1]


def down_since(samples: List[Tuple[datetime, bool]]) -> Optional[datetime]:
    """Start of the outage still under way at the latest sample, else None."""
    since, prev = None, None
    for t, ok in reversed(samples):
        t = _utc(t)
        if ok or (prev is not None and prev - t > _GAP):
            break
        since, prev = t, t
    return since


def uptime_summary(samples: List[Tuple[datetime, bool]], now: datetime) -> dict:
    ds = down_since(samples)
    return {
        "uptime_24h": uptime_percent(samples, now, 24),
        "uptime_7d": uptime_percent(samples, now, 24 * 7),
        "down_since": ds.isoformat() if ds else None,
        "outages_7d": len([o for o in outages(samples)
                           if datetime.fromisoformat(o["start"]) >= now - timedelta(days=7)]),
    }


def alert_due(down_from: Optional[datetime], alerted: bool, now: datetime) -> Optional[str]:
    """'down' once an outage passes ALERT_AFTER_MINUTES, 'up' when an alerted
    outage ends; None otherwise."""
    if down_from is not None and not alerted and now - _utc(down_from) >= timedelta(minutes=ALERT_AFTER_MINUTES):
        return "down"
    if down_from is None and alerted:
        return "up"
    return None