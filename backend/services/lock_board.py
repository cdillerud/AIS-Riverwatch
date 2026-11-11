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
    """Fallback rule only, for a lock with no learned barge table yet."""
    return bool(barges) and barges > MAX_SINGLE_CUT_BARGES and lock_id not in LONG_CHAMBERS


# --------------------------------------------------------------------------
# Learned lockage table: for each lock, how long a tow of N barges takes to
# lock through and how often it needs more than one lockage (a double, or the
# towboat locked separately), from that lock's USACE history, shrunk toward
# the river-wide figure for N barges where the lock has few examples.
# Backtest 2026-11-11 (3,158 tow lockages fit, next 1,580 scored): lockage
# duration MAE 21.9 -> 16.7 min; the >9-barge rule called 14% of tows
# single/double wrongly (4-barge tows often lock with the boat separate,
# ~90 min, where the rule said ~30).
# --------------------------------------------------------------------------
BARGE_TABLE_SHRINK = 5   # pseudo-count pulling a lock's cell toward the river-wide value
MAX_BARGE_BUCKET = 16


def barge_bucket(barges) -> int:
    try:
        return max(0, min(int(barges or 0), MAX_BARGE_BUCKET))
    except (TypeError, ValueError):
        return 0


def _median(xs: List[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def river_barge_stats(records: Iterable[dict]) -> dict:
    """River-wide {bucket: {"minutes", "double_share", "n"}} over tow lockages."""
    groups: dict = {}
    for r in records:
        d = r.get("lockage_duration_minutes")
        if not r.get("is_tow") or d is None or d <= 0 or r.get("in_progress"):
            continue
        groups.setdefault(barge_bucket(r.get("barge_count")), []).append(r)
    return {b: {"minutes": _median([x["lockage_duration_minutes"] for x in g]),
                "double_share": sum(1 for x in g if (x.get("cuts") or 1) >= 2) / len(g), "n": len(g)}
            for b, g in groups.items()}


def lock_barge_table(records: Iterable[dict], river: dict, k: float = BARGE_TABLE_SHRINK) -> dict:
    """{bucket: {"minutes", "double_share", "n"}} for one lock: its own median
    and double share per barge count, shrunk toward `river` (river_barge_stats)."""
    own = river_barge_stats(records)
    table = {}
    for b in set(own) | set(river):
        o, g = own.get(b), river.get(b)
        if not g:
            table[b] = dict(o)
            continue
        n = o["n"] if o else 0
        om = o["minutes"] if o else g["minutes"]
        od = o["double_share"] if o else g["double_share"]
        table[b] = {"minutes": round((om * n + g["minutes"] * k) / (n + k), 1),
                    "double_share": round((od * n + g["double_share"] * k) / (n + k), 3), "n": n}
    return table


def _barge_cell(typical: dict, barges) -> Optional[dict]:
    table = typical.get("by_barges") or {}
    b = barge_bucket(barges)
    return table.get(b) or table.get(str(b))   # JSON round trips turn keys into strings


def double_chance(lock_id: str, barges, typical: dict) -> float:
    """Chance a tow of this size needs more than one lockage here."""
    cell = _barge_cell(typical, barges) if barges else None
    if cell and cell.get("double_share") is not None:
        return float(cell["double_share"])
    return 1.0 if needs_double(lock_id, barges) else 0.0


def expected_lockage_minutes(lock_id: str, barges: Optional[int], typical: dict) -> float:
    """Expected lockage duration for one vessel at this lock, from its history."""
    single = typical.get("avg_single_lockage_minutes") or DEFAULT_SINGLE
    if not barges:
        return float(typical.get("avg_recreational_lockage_minutes") or min(single, DEFAULT_LIGHT))
    cell = _barge_cell(typical, barges)
    if cell and cell.get("minutes"):
        return float(cell["minutes"])
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
    # Tow model v2 (services/calibration.fit_tow_features): L1 fit on queue
    # features + per-lock effects, 4,067 lockages Oct 11-31 2026, scored on the
    # next 10 days: tow MAE 43.0 min (v1 46.7), 70% within 30 min, 84% within
    # 60. Opposite-direction tows waiting cost ~19 min each vs ~10 for
    # same-direction (locks alternate). The nightly job refits and replaces
    # this only when the refit is more accurate on recent data.
    "tow": {
        "kind": "l1_features",
        "coef": {
            "intercept": 30.82,
            "v0": 0.989,
            "n_same": 10.302,
            "n_opp": 19.382,
            "dbl": 4.954,
            "lk_rem": -0.13,
            "own_double": 6.289,
            "empty": -17.985
        },
        "lock_effects": {
            "chain_of_rocks": 0.0,
            "lock_1": -6.0,
            "lock_10": 7.69,
            "lock_11": 4.86,
            "lock_12": -13.04,
            "lock_13": -6.22,
            "lock_14": -0.99,
            "lock_15": 7.37,
            "lock_16": -9.67,
            "lock_17": -12.77,
            "lock_18": -8.9,
            "lock_19": 10.2,
            "lock_2": -3.52,
            "lock_20": -6.0,
            "lock_21": 2.64,
            "lock_22": 6.38,
            "lock_24": -10.47,
            "lock_25": 19.47,
            "lock_3": -7.13,
            "lock_4": -12.53,
            "lock_5": -10.43,
            "lock_6": -12.76,
            "lock_7": -5.66,
            "lock_8": 8.18,
            "lock_9": -3.12,
            "melvin_price": -3.03
        }
    },
    # L1 (median) fit, 2026-11-11 (services/calibration.fit_recreational): most
    # pleasure boats lock with no wait; least squares (5.7 + 0.09q) put ~6 min on all.
    "recreational": {"intercept": 0.7, "slope": 0.09},
    "fitted_on": "2026-10-11..2026-10-31, 4067 USACE lockages (recreational refit 2026-11-11)",
    "test_mae_minutes": {"tow": 43.0, "recreational": 6.2},
}


# Tow wait model v2 features (services/calibration.py fits them nightly):
# raw queue minutes, waiting tows going the same / opposite way (locks
# alternate directions, so opposite-direction tows cost more), double
# lockages ahead, minutes left on the lockage in progress, whether the
# arriving tow itself needs two cuts, and an empty-lock flag; plus a
# per-lock effect.
TOW_FEATURES = ["v0", "n_same", "n_opp", "dbl", "lk_rem", "own_double", "empty"]


def tow_wait(f: dict, model: Optional[dict] = None) -> float:
    """Tow wait from queue features under the given (default: current) model."""
    m = (model or CALIBRATION)["tow"]
    if m.get("kind") == "l1_features":
        z = m["coef"]["intercept"] + sum(m["coef"].get(k, 0.0) * float(f.get(k) or 0.0) for k in TOW_FEATURES)
        z += m.get("lock_effects", {}).get(f.get("lock_id"), 0.0)
        return max(0.0, z)
    if f.get("empty"):
        return float(m["empty_lock"])
    return max(0.0, m["intercept"] + m["slope"] * float(f.get("v0") or 0.0))


def queue_features(lock_id: str, locking: List[dict], waiting: List[dict], typical: dict,
                   direction: Optional[str], raw_minutes: float, locking_remaining: float,
                   own_double: Optional[float] = None) -> dict:
    """Features for tow_wait(). Without a direction the waiting tows are split
    evenly between same and opposite; without the arriving tow's size, the
    lock's share of double lockages is used."""
    # Predicted vessels (with a probability) count fractionally
    weight = [float(w.get("probability", 1.0)) for w in waiting]
    total = sum(weight)
    if direction in ("upbound", "downbound"):
        n_same = sum(wt for w, wt in zip(waiting, weight) if w.get("direction") == direction)
        n_opp = total - n_same
    else:
        n_same = n_opp = total / 2.0
    if own_double is None:
        own_double = float(typical.get("double_share") or 0.0)
    return {
        "lock_id": lock_id,
        "v0": float(raw_minutes),
        "n_same": n_same,
        "n_opp": n_opp,
        "dbl": float(sum(wt * double_chance(lock_id, w.get("barges"), typical) for w, wt in zip(waiting, weight))),
        "lk_rem": float(locking_remaining),
        "own_double": float(own_double),
        "empty": 1.0 if not locking and not waiting else 0.0,
    }


def predict_waits(lock_id: str, locking: List[dict], waiting: List[dict], typical: dict,
                  direction: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """Calibrated wait for a tow and for a recreational boat arriving now.

    `direction` (upbound/downbound) narrows the recreational estimate to the
    queue going the same way; without it the whole queue is used."""
    now = now or datetime.now(timezone.utc)
    queue_minutes = estimate_wait(lock_id, locking, waiting, typical, now)
    feats = queue_features(lock_id, locking, waiting, typical, direction, queue_minutes,
                           estimate_wait(lock_id, locking, [], typical, now))
    tow = tow_wait(feats)
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
        # Predicted vessels count by the chance they really continue to this lock
        p = float(v.get("probability", 1.0))
        free_at = max(free_at, at) + timedelta(minutes=p * expected_lockage_minutes(lock_id, v.get("barges"), typical))
        ahead.append(v)
    raw = max(0.0, (free_at - arrive_at).total_seconds() / 60)
    return {"queue_minutes": round(raw), "ahead": ahead}


SIMULATE_BEYOND = timedelta(minutes=90)


def predict_waits_at(lock_id: str, locking: List[dict], waiting: List[dict], approaching: List[dict],
                     typical: dict, arrive_at: datetime, now: Optional[datetime] = None,
                     direction: Optional[str] = None) -> dict:
    """Calibrated tow / recreational wait for a boat arriving at `arrive_at`."""
    now = now or datetime.now(timezone.utc)
    sim = queue_minutes_at(lock_id, locking, waiting, approaching, typical, arrive_at, now)
    q = sim["queue_minutes"]
    # Boats seen on AIS heading in ahead of you are observed, not guessed.
    ais_ahead = any(v.get("source") == "ais" for v in sim["ahead"] if v not in waiting)
    if (arrive_at - now) <= SIMULATE_BEYOND and not ais_ahead:
        # Close in, the queue as it stands predicts better than simulating it
        # forward with USACE-based guesses (backtest 1 h ahead: MAE 57.6 vs
        # 65.2 min). Arrivals confirmed on AIS are simulated instead: the
        # backtest's error came from guessed boats that never showed up.
        # (Not backtested: AIS history is too short so far.)
        tow = predict_waits(lock_id, locking, waiting, typical, direction, now)["tow"]
    else:
        # Further out, simulate: the lockage in progress finishes, waiting and
        # predicted vessels lock through first (2 h: 66.6 vs 67.6; 4 h: 70.2 vs 76.1).
        feats = queue_features(lock_id, [] if not sim["ahead"] and q <= 0 else locking, sim["ahead"],
                               typical, direction, q, 0.0)
        tow = tow_wait(feats)
    rec = CALIBRATION["recreational"]["intercept"] + CALIBRATION["recreational"]["slope"] * q
    return {"tow": round(max(0.0, tow)), "recreational": round(max(0.0, rec)),
            "queue_minutes": q, "ahead_count": len(sim["ahead"]),
            "ahead": [{"vessel_name": v.get("vessel_name"), "mmsi": v.get("mmsi"), "barges": v.get("barges"),
                       "direction": v.get("direction"), "predicted": "eta" in v,
                       # "queue" (USACE: at the lock), "ais" (seen heading in) or "usace_prediction"
                       "source": v.get("source") or ("usace_prediction" if "eta" in v else "queue"),
                       "eta": v["eta"].isoformat() if isinstance(v.get("eta"), datetime) else v.get("eta"),
                       "distance_mi": v.get("distance_mi"),
                       "probability": v.get("probability", 1.0)} for v in sim["ahead"]]}


# A boat stopped at a lock (waiting on the approach wall or in the chamber)
# sits about at the lock's river mile; the lock is still the one ahead of it
# until it is under way past it. Same rule in frontend/src/lib/timingLock.js.
AT_LOCK_MI = 0.25       # chamber + approach, when slow
PASSING_MI = 0.05       # GPS jitter, when under way
SLOW_KNOTS = 2.0


def lock_is_ahead(lock_rm: float, rm: float, direction: Optional[str], speed_knots: Optional[float] = None) -> bool:
    """Is the lock at `lock_rm` still ahead of a boat at `rm` going `direction`
    (upbound/downbound, or northbound/southbound)?"""
    slow = speed_knots is not None and float(speed_knots) < SLOW_KNOTS
    tol = AT_LOCK_MI if slow else PASSING_MI
    if direction in ("downbound", "southbound"):
        return lock_rm < rm + tol
    if direction in ("upbound", "northbound"):
        return lock_rm > rm - tol
    return False


def locks_in_view(locks: List[dict], from_rm: Optional[float], direction: Optional[str],
                  scope: str = "all", speed_knots: Optional[float] = None) -> List[dict]:
    """Order locks for the board.

    scope="ahead" with a position and direction: only locks in front of the
    boat (including the one it's stopped at), nearest first. Otherwise every
    lock, north to south (or south to north for an upbound boat)."""
    if scope == "ahead" and from_rm is not None and direction in ("upbound", "downbound"):
        ahead = [lk for lk in locks if lock_is_ahead(lk["river_mile"], from_rm, direction, speed_knots)]
        return sorted(ahead, key=lambda lk: lk["river_mile"], reverse=(direction == "downbound"))
    return sorted(locks, key=lambda lk: lk["river_mile"], reverse=(direction != "upbound"))
