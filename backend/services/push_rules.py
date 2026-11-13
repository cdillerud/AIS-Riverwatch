"""
Web Push alert rules, evaluated on the server while River Watch is closed.

Pure functions; they mirror frontend/src/lib/alerts.js (tested side by side in
tests/test_push_rules.py) so a boater gets the same alerts whether the app is
open (on-device toasts) or closed (Web Push from server.py's push task):

  - Tow approaching: a commercial tow within N river miles of the boat and
    closing (heading toward it at >= 1 kn, or the distance has shrunk).
  - Lock ahead busy / clearing: the predicted wait at the next lock ahead
    crosses the user's threshold (5 min hysteresis; the first look is silent).
  - Good time to leave: while stopped, "leave now" becomes the best option of
    /departure-options after it wasn't.

Each subscription keeps its rule state and a "last sent" log in MongoDB, so a
restart neither re-alerts nor forgets a transition. Payloads carry only the
alert text, a tag and the page to open - never the user's email or account.
"""
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

DEDUPE_SECONDS = 30 * 60
LOCK_HYSTERESIS_MIN = 5
CLOSING_STEP_MI = 0.05
FRESH_SECONDS = 10 * 60          # same as STALE_AFTER_MS in utils/vesselDisplay.js
VISIBLE_SECONDS = 2 * 60         # app on screen this recently: its own toasts cover it
DEPART_EVERY_SECONDS = 2 * 60    # same cadence as hooks/useRiverAlerts.js
TOW_MILE_CHOICES = (1, 2, 3, 5)
LOCK_WAIT_CHOICES = (15, 30, 45, 60)

PREF_DEFAULTS = {
    "tow": True,
    "towMiles": 3,
    "lock": True,
    "lockWaitMinutes": 30,
    "depart": True,
    "sound": False,
    # Departure planner choices (lib/departure.js readPrefs): a stopped boat
    # has no heading, so the planner's direction says which way is "ahead".
    "direction": "downbound",
    "mph": 15.0,
}

TOW_SHIP_TYPES = (31, 32, 52)      # towing, towing (large), tug
PLEASURE_SHIP_TYPES = (36, 37)     # sailing, pleasure craft


def normalize_prefs(raw) -> dict:
    p = dict(PREF_DEFAULTS)
    if not isinstance(raw, dict):
        return p
    for k in ("tow", "lock", "depart", "sound"):
        if isinstance(raw.get(k), bool):
            p[k] = raw[k]
    try:
        if int(raw.get("towMiles")) in TOW_MILE_CHOICES:
            p["towMiles"] = int(raw["towMiles"])
    except (TypeError, ValueError):
        pass
    try:
        if int(raw.get("lockWaitMinutes")) in LOCK_WAIT_CHOICES:
            p["lockWaitMinutes"] = int(raw["lockWaitMinutes"])
    except (TypeError, ValueError):
        pass
    if raw.get("direction") in ("upbound", "downbound"):
        p["direction"] = raw["direction"]
    try:
        mph = float(raw.get("mph"))
        if 0 < mph <= 60:
            p["mph"] = mph
    except (TypeError, ValueError):
        pass
    return p


# --- shared -----------------------------------------------------------------

def _num(x) -> Optional[float]:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def parse_time(value) -> Optional[datetime]:
    """datetime or ISO string -> aware UTC datetime (naive values are UTC)."""
    if isinstance(value, datetime):
        t = value
    elif isinstance(value, str) and value:
        try:
            t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def last_seen(v: dict) -> Optional[datetime]:
    v = v or {}
    return parse_time(v.get("last_ais_checkin") or v.get("timestamp") or v.get("last_update"))


def is_fresh(v: dict, now: datetime, max_age: float = FRESH_SECONDS) -> bool:
    """A position recent enough to alert on (unknown time = not fresh)."""
    t = last_seen(v)
    return t is not None and (now - t).total_seconds() <= max_age


def is_stale(v: dict, now: datetime) -> bool:
    """alerts.js isVesselStale: only a known, old time counts as stale."""
    t = last_seen(v)
    return t is not None and (now - t).total_seconds() > FRESH_SECONDS


def has_river_mile(v: dict) -> bool:
    return _num((v or {}).get("river_mile")) is not None


def direction_of(v: dict) -> Optional[str]:
    """lib/timingLock.js directionOf."""
    v = v or {}
    raw = str(v.get("heading") or v.get("heading_direction") or v.get("direction") or "").lower()
    if any(t in raw for t in ("southbound", "downriver", "downbound", "sb")):
        return "downbound"
    if any(t in raw for t in ("northbound", "upriver", "upbound", "nb")):
        return "upbound"
    return None


def is_stopped(v: dict) -> bool:
    kn = _num((v or {}).get("speed"))
    return kn is None or kn < 2


def is_commercial_tow(v: dict) -> bool:
    if not v:
        return False
    barges = (_num(v.get("barge_count")) or 0) > 0
    t = _num(v.get("ship_type"))
    t = int(t) if t is not None else None
    if t in PLEASURE_SHIP_TYPES and not barges:
        return False
    return bool(v.get("is_tow")) or barges or t in TOW_SHIP_TYPES


def user_is_tow(v: dict) -> bool:
    return bool((v or {}).get("is_tow") or (_num((v or {}).get("barge_count")) or 0) > 0)


def fmt_minutes(m) -> str:
    n = _num(m)
    if n is None:
        return "—"
    n = int(round(n))
    if n < 60:
        return f"{n} min"
    h, r = divmod(n, 60)
    return f"{h} h {r} min" if r else f"{h} h"


def lock_short_label(lock_id: str) -> str:
    if not lock_id:
        return ""
    if lock_id == "melvin_price":
        return "Mel Price"
    if lock_id == "chain_of_rocks":
        return "Chain of Rocks"
    return "L" + str(lock_id).replace("lock_", "").upper()


# --- tow approaching --------------------------------------------------------

def tow_alerts(me: dict, boats: Iterable[dict], miles: float = 3, refs: Optional[dict] = None,
               now: Optional[datetime] = None) -> Tuple[List[dict], dict]:
    """alerts.js towAlerts. me: the user's boat; boats: other live boats
    (already without account / simulated / demo boats). refs: {mmsi: distance}
    from the last check. Returns (alerts, new refs)."""
    now = now or datetime.now(timezone.utc)
    refs = refs or {}
    next_refs: Dict[str, float] = {}
    alerts: List[dict] = []
    if not me or not has_river_mile(me) or is_stale(me, now):
        return alerts, next_refs
    my_rm = float(me["river_mile"])
    my_mmsi = str(me.get("mmsi") or "")
    for v in boats or []:
        if not v or str(v.get("mmsi")) == my_mmsi or v.get("is_user_vessel"):
            continue
        if not is_commercial_tow(v) or not has_river_mile(v) or is_stale(v, now):
            continue
        rm = float(v["river_mile"])
        d = abs(rm - my_rm)
        if d > miles + 1:
            continue
        key = str(v.get("mmsi"))
        ref = _num(refs.get(key))
        next_refs[key] = ref if ref is not None and abs(d - ref) < CLOSING_STEP_MI else d
        if d > miles:
            continue
        direction = direction_of(v)
        moving = (_num(v.get("speed")) or 0) >= 1
        heading_to_me = moving and ((direction == "upbound" and rm < my_rm) or (direction == "downbound" and rm > my_rm))
        shrinking = ref is not None and d <= ref - CLOSING_STEP_MI
        if not heading_to_me and not shrinking:
            continue
        where = "upriver" if rm > my_rm else "downriver"
        n_barges = _num(v.get("barge_count")) or 0
        barges = f" with {int(n_barges)} barges" if n_barges > 0 else ""
        name = v.get("name") or key
        alerts.append({
            "key": f"tow:{key}",
            "kind": "tow",
            "title": "Tow approaching",
            "body": f"{name}{barges}, {d:.1f} mi {where} and getting closer.",
        })
    return alerts, next_refs


# --- lock ahead busy / clearing ---------------------------------------------

def lock_wait(row: dict, is_tow: bool = False) -> Optional[float]:
    if not row:
        return None
    src = row.get("wait_at_arrival") or {"tow": row.get("wait_estimate_minutes"),
                                         "recreational": row.get("wait_estimate_recreational_minutes")}
    return _num(src.get("tow") if is_tow else src.get("recreational"))


def lock_alert(row: Optional[dict], prev: Optional[dict] = None, threshold: float = 30,
               is_tow: bool = False) -> Tuple[Optional[dict], Optional[dict]]:
    """alerts.js lockAlert. prev: {"lockId", "level": "busy"|"clear"} or None.
    Alerts only on a level change at the same lock."""
    if not row or row.get("queue_stale"):
        return None, prev
    wait = lock_wait(row, is_tow)
    if wait is None:
        return None, prev
    same_lock = bool(prev) and prev.get("lockId") == row.get("lock_id")
    if wait > threshold:
        level = "busy"
    elif wait <= threshold - LOCK_HYSTERESIS_MIN:
        level = "clear"
    else:
        level = prev.get("level") if same_lock else "clear"
    state = {"lockId": row.get("lock_id"), "level": level}
    if not same_lock or prev.get("level") == level:
        return None, state
    name = row.get("name") or lock_short_label(row.get("lock_id"))
    if level == "busy":
        alert = {"key": f"lock-busy:{row.get('lock_id')}", "kind": "lock", "title": f"{name}: wait going up",
                 "body": f"Expected wait is now about {fmt_minutes(wait)} (over {int(threshold)} min)."}
    else:
        alert = {"key": f"lock-clear:{row.get('lock_id')}", "kind": "lock", "title": f"{name}: wait coming down",
                 "body": f"Expected wait is now about {fmt_minutes(wait)}."}
    return alert, state


# --- best time to leave -----------------------------------------------------

def depart_alert(data: Optional[dict], prev_now_best: Optional[bool] = None) -> Tuple[Optional[dict], Optional[bool]]:
    """alerts.js departAlert: alert when "leave now" becomes best."""
    opts = (data or {}).get("options") or []
    now_idx = next((i for i, o in enumerate(opts) if _num(o.get("depart_in_minutes")) == 0), -1)
    if now_idx < 0 or (data or {}).get("best") is None:
        return None, prev_now_best
    now_best = data["best"] == now_idx
    if not now_best or prev_now_best is not False:
        return None, now_best
    mine = opts[now_idx].get("time_at_locks_minutes")
    others = [_num(o.get("time_at_locks_minutes")) for i, o in enumerate(opts) if i != now_idx]
    others = [m for m in others if m is not None]
    later = min(others) if others else None
    vs = f" vs {fmt_minutes(later)} if you wait" if later is not None and later > (_num(mine) or 0) else ""
    return {
        "key": "depart:now",
        "kind": "depart",
        "title": "Good time to leave",
        "body": f"Leaving now has the least time at locks: about {fmt_minutes(mine)}{vs}.",
    }, now_best


# --- dedupe / presence / payload ----------------------------------------------

def dedupe(alerts: Iterable[dict], last_sent: Optional[dict], now_ts: float,
           window: float = DEDUPE_SECONDS) -> Tuple[List[dict], dict]:
    """Drop alerts whose key was sent within `window` seconds. last_sent:
    {key: epoch seconds}; returns (fresh alerts, pruned + updated log)."""
    log = {k: t for k, t in (last_sent or {}).items()
           if _num(t) is not None and now_ts - float(t) < window}
    fresh = []
    for a in alerts or []:
        if a["key"] in log:
            continue
        log[a["key"]] = now_ts
        fresh.append(a)
    return fresh, log


def app_on_screen(visible_at, now: datetime, window: float = VISIBLE_SECONDS) -> bool:
    """The app reported itself visible recently: its own toasts show the
    alert, so a push would be a duplicate."""
    t = parse_time(visible_at)
    return t is not None and 0 <= (now - t).total_seconds() <= window


def payload(alert: dict, sound: bool = False) -> dict:
    """What goes to the push service (encrypted end to end): text + tag only."""
    return {"title": alert["title"], "body": alert["body"], "tag": alert["key"], "url": "/dashboard",
            "silent": not sound}


def valid_subscription(sub) -> bool:
    """A browser PushSubscription.toJSON(): https endpoint + both keys."""
    if not isinstance(sub, dict):
        return False
    ep = sub.get("endpoint")
    keys = sub.get("keys") or {}
    return (isinstance(ep, str) and ep.startswith("https://") and len(ep) <= 2048
            and isinstance(keys, dict)
            and all(isinstance(keys.get(k), str) and 0 < len(keys[k]) <= 256 for k in ("p256dh", "auth")))
