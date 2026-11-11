"""
Arrival and departure times for each lock on a trip, counting the time spent
at the locks before it.

Before 2026-11-10 the trip plan's ETA for every lock was distance / speed from
the boat's current position: no time for waiting or locking through. Five
locks downstream that made the final ETA hours early.

Here each lock's arrival is when the boat leaves the previous lock, plus travel.
At each lock: the expected wait when the boat gets there (`wait_fn`, the same
model as Lock Timing) plus its own lockage (`lockage_fn`).
"""
from typing import Awaitable, Callable, List, Optional


async def schedule(legs: List[dict], speed_mph: float,
                   wait_fn: Callable[[str, float], Awaitable[Optional[float]]],
                   lockage_fn: Callable[[str], float]) -> List[dict]:
    """`legs`: [{lock_id, distance_mi}] in travel order, distance from the
    previous point (the boat, then each lock). Returns per lock
    {arrive_minutes, wait_minutes, lockage_minutes, depart_minutes,
    time_at_earlier_locks_minutes}, all from now."""
    if not speed_mph or speed_mph <= 0:
        return []
    out = []
    t = 0.0
    at_locks = 0.0
    for leg in legs:
        t += float(leg["distance_mi"]) / speed_mph * 60
        arrive = t
        wait = await wait_fn(leg["lock_id"], arrive)
        wait = max(0.0, float(wait)) if wait is not None else 0.0
        lockage = max(0.0, float(lockage_fn(leg["lock_id"]) or 0))
        out.append({
            "lock_id": leg["lock_id"],
            "arrive_minutes": round(arrive),
            "wait_minutes": round(wait),
            "lockage_minutes": round(lockage),
            "depart_minutes": round(arrive + wait + lockage),
            "time_at_earlier_locks_minutes": round(at_locks),
        })
        t = arrive + wait + lockage
        at_locks += wait + lockage
    return out
