"""
Lock board: the "lock-first" view.

Built entirely from USACE data (the lock queue feed and the lockage history it
fills), so it works with no AIS feed at all. For each lock: status, who is
locking and waiting, an estimated wait for a boat arriving now, and typical
lockage times (single vs double cut).

Wait estimate: time left on the lockage in progress plus the expected lockage
time of every vessel already waiting. Lock staff alternate directions and lock
recreational boats with tows when they can, so this is an estimate, labelled
as such in the UI.
"""
from datetime import datetime, timezone
from typing import Iterable, List, Optional

# Chambers long enough (1,200 ft) for a 15-barge tow in one cut.
LONG_CHAMBERS = {"lock_19", "melvin_price", "chain_of_rocks"}
# Larger tows don't fit a 600 ft chamber with the towboat and lock in two cuts.
MAX_SINGLE_CUT_BARGES = 9

# Fallbacks when a lock has no recorded history yet (minutes).
DEFAULT_SINGLE = 30.0
DEFAULT_DOUBLE = 110.0
DEFAULT_LIGHT = 20.0   # towboat with no barges / recreational


def needs_double(lock_id: str, barges: Optional[int]) -> bool:
    return bool(barges) and barges > MAX_SINGLE_CUT_BARGES and lock_id not in LONG_CHAMBERS


def expected_lockage_minutes(lock_id: str, barges: Optional[int], typical: dict) -> float:
    """Expected lockage duration for one vessel at this lock, from its history."""
    single = typical.get("avg_single_lockage_minutes") or DEFAULT_SINGLE
    if not barges:
        return float(typical.get("avg_recreational_lockage_minutes") or min(single, DEFAULT_LIGHT))
    if needs_double(lock_id, barges):
        return float(typical.get("avg_double_lockage_minutes") or max(DEFAULT_DOUBLE, 2 * single))
    return float(single)


def estimate_wait(lock_id: str, locking: Iterable[dict], waiting: Iterable[dict], typical: dict,
                  now: Optional[datetime] = None) -> float:
    """Minutes until a boat arriving now could start its lockage."""
    now = now or datetime.now(timezone.utc)
    total = 0.0
    for v in locking:
        expected = expected_lockage_minutes(lock_id, v.get("barges"), typical)
        started = v.get("started_at")
        elapsed = (now - started).total_seconds() / 60 if started else 0.0
        total += max(0.0, expected - elapsed)
    for v in waiting:
        total += expected_lockage_minutes(lock_id, v.get("barges"), typical)
    return round(total, 0)


def locks_in_view(locks: List[dict], from_rm: Optional[float], direction: Optional[str],
                  scope: str = "all") -> List[dict]:
    """Order locks for the board.

    scope="ahead" with a position and direction: only locks in front of the
    boat, nearest first. Otherwise every lock, north to south (or south to
    north for an upbound boat)."""
    if scope == "ahead" and from_rm is not None and direction in ("upbound", "downbound"):
        if direction == "downbound":
            ahead = [lk for lk in locks if lk["river_mile"] < from_rm]
            return sorted(ahead, key=lambda lk: -lk["river_mile"])
        ahead = [lk for lk in locks if lk["river_mile"] > from_rm]
        return sorted(ahead, key=lambda lk: lk["river_mile"])
    return sorted(locks, key=lambda lk: lk["river_mile"], reverse=(direction != "upbound"))
