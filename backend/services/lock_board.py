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
from datetime import datetime, timedelta, timezone
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
        if v.get("cuts_completed"):
            # Mid double lockage (a cut is already through): at least one more cut.
            expected = max(expected, float(typical.get("avg_double_lockage_minutes") or DEFAULT_DOUBLE))
        started = v.get("started_at")
        elapsed = (now - started).total_seconds() / 60 if started else 0.0
        total += max(0.0, expected - elapsed)
    for v in waiting:
        total += expected_lockage_minutes(lock_id, v.get("barges"), typical)
    return round(total, 0)


# Calibration fitted by scripts/backtest_waits.py on USACE lockage history
# (4,055 lockages Oct 11-31 2026, 26 locks) and scored on the following 10 days
# (1,825 lockages): tows MAE 48 min / 82% within 60 min; recreational MAE
# 8 min / 96% within 30 min; overall bias -5 min. The raw queue sum
# (estimate_wait) underestimated tows by ~37 min and overestimated pleasure
# craft by ~28 min: lock staff slot recreational boats in around tows.
# Re-run the backtest as history grows and update these numbers.
CALIBRATION = {
    "tow": {"intercept": 26.5, "slope": 1.264, "empty_lock": 10.0},
    "recreational": {"intercept": 5.8, "slope": 0.088},
    "fitted_on": "2026-10-11..2026-10-31, 4055 USACE lockages",
    "test_mae_minutes": {"tow": 48.3, "recreational": 8.0},
}


def predict_waits(lock_id: str, locking: List[dict], waiting: List[dict], typical: dict,
                  direction: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """Calibrated wait for a tow and for a recreational boat arriving now.

    `direction` (upbound/downbound) narrows the recreational estimate to the
    queue going the same way; without it the whole queue is used."""
    now = now or datetime.now(timezone.utc)
    queue_minutes = estimate_wait(lock_id, locking, waiting, typical, now)
    if not locking and not waiting:
        tow = CALIBRATION["tow"]["empty_lock"]
    else:
        tow = CALIBRATION["tow"]["intercept"] + CALIBRATION["tow"]["slope"] * queue_minutes
    same_dir = [w for w in waiting if not direction or w.get("direction") == direction]
    rec_queue = estimate_wait(lock_id, locking, same_dir, typical, now)
    rec = CALIBRATION["recreational"]["intercept"] + CALIBRATION["recreational"]["slope"] * rec_queue
    return {
        "tow": round(max(0.0, tow)),
        "recreational": round(max(0.0, rec)),
        "queue_minutes": queue_minutes,
    }


def queue_minutes_at(lock_id: str, locking: List[dict], waiting: List[dict], approaching: List[dict],
                     typical: dict, arrive_at: datetime, now: Optional[datetime] = None) -> dict:
    """Simulate the lock forward to `arrive_at` (first come, first served).

    The lockage in progress finishes, the waiting vessels lock through in
    order, and vessels predicted to arrive (approaching, each with an `eta`)
    join the line when they get there. Returns the raw queue minutes a boat
    arriving at `arrive_at` would face, comparable with estimate_wait() so the
    same CALIBRATION applies, plus who is expected ahead."""
    now = now or datetime.now(timezone.utc)
    free_at = now
    for v in locking:
        expected = expected_lockage_minutes(lock_id, v.get("barges"), typical)
        started = v.get("started_at") or now
        free_at = max(free_at, started + timedelta(minutes=expected))
    ahead = []
    queue = [(now, w) for w in waiting] + [
        (a["eta"], a) for a in approaching if a.get("eta") and a["eta"] <= arrive_at
    ]
    queue.sort(key=lambda q: q[0])
    for at, v in queue:
        free_at = max(free_at, at) + timedelta(minutes=expected_lockage_minutes(lock_id, v.get("barges"), typical))
        ahead.append(v)
    raw = max(0.0, (free_at - arrive_at).total_seconds() / 60)
    return {"queue_minutes": round(raw), "ahead": ahead}


def predict_waits_at(lock_id: str, locking: List[dict], waiting: List[dict], approaching: List[dict],
                     typical: dict, arrive_at: datetime, now: Optional[datetime] = None) -> dict:
    """Calibrated tow / recreational wait for a boat arriving at `arrive_at`."""
    sim = queue_minutes_at(lock_id, locking, waiting, approaching, typical, arrive_at, now)
    q = sim["queue_minutes"]
    if q <= 0 and not sim["ahead"]:
        tow = CALIBRATION["tow"]["empty_lock"]
    else:
        tow = CALIBRATION["tow"]["intercept"] + CALIBRATION["tow"]["slope"] * q
    rec = CALIBRATION["recreational"]["intercept"] + CALIBRATION["recreational"]["slope"] * q
    return {"tow": round(max(0.0, tow)), "recreational": round(max(0.0, rec)),
            "queue_minutes": q, "ahead_count": len(sim["ahead"]),
            "ahead": [{"vessel_name": v.get("vessel_name"), "barges": v.get("barges"),
                       "direction": v.get("direction"), "predicted": "eta" in v} for v in sim["ahead"]]}


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
