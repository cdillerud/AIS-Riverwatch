"""
Data freshness: how old each source's data is, so stale numbers are labelled
instead of shown as current.

The USACE worker visits every lock about every 6 minutes (27 locks x 13 s);
a lock's queue older than QUEUE_STALE_MINUTES means fetches for it are
failing or the worker is rate-limited/stuck. On a failed fetch the worker
keeps the previous rows, so the fetch time - not the rows - tells the age.
"""
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

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
