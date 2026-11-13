"""Web Push alerts: rules (services/push_rules.py), subscribe/unsubscribe and
the background tick (server.py). pywebpush is mocked; nothing leaves the box."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import server
from services import push_rules as R

NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)


def _boat(mmsi, rm, **kw):
    return {"mmsi": mmsi, "river_mile": rm, "speed": 6.0, "timestamp": NOW.isoformat(), **kw}


# --- tow approaching ---------------------------------------------------------

def test_tow_heading_toward_the_boat_alerts():
    me = _boat("111", 800.0, speed=0)
    tow = _boat("367", 802.0, heading="southbound", ship_type=31, name="MISS ANN", barge_count=12)
    alerts, refs = R.tow_alerts(me, [tow], miles=3, now=NOW)
    assert [a["key"] for a in alerts] == ["tow:367"]
    assert alerts[0]["body"] == "MISS ANN with 12 barges, 2.0 mi upriver and getting closer."
    assert refs == {"367": 2.0}


def test_tow_moving_away_or_too_far_is_quiet_until_it_closes():
    me = _boat("111", 800.0, speed=0)
    away = _boat("367", 802.0, heading="northbound", ship_type=31)
    alerts, refs = R.tow_alerts(me, [away], miles=3, now=NOW)
    assert alerts == [] and refs == {"367": 2.0}
    # Drifting closer (no usable heading) counts as closing once it has moved enough
    drift = _boat("367", 801.5, speed=0.5, ship_type=31)
    alerts, refs = R.tow_alerts(me, [drift], miles=3, refs=refs, now=NOW)
    assert [a["key"] for a in alerts] == ["tow:367"]
    # Too far: no alert; beyond miles + 1 the reference is forgotten
    far = _boat("367", 803.5, heading="southbound", ship_type=31)
    assert R.tow_alerts(me, [far], miles=3, now=NOW) == ([], {"367": 3.5})
    assert R.tow_alerts(me, [_boat("367", 805.0, ship_type=31)], miles=3, now=NOW) == ([], {})


def test_only_commercial_tows_count():
    me = _boat("111", 800.0, speed=0)
    boats = [
        _boat("1", 801.0, heading="southbound", ship_type=37),              # pleasure craft
        _boat("2", 801.0, heading="southbound", ship_type=70),              # cargo, no barges
        _boat("3", 801.0, heading="southbound", is_user_vessel=True, is_tow=True),
        _boat("111", 801.0, heading="southbound", ship_type=31),            # itself
        _boat("4", 801.0, heading="southbound", ship_type=37, barge_count=3),  # pushing barges
        _boat("5", 801.0, heading="southbound", is_tow=True,
              timestamp=(NOW - timedelta(minutes=30)).isoformat()),         # stale
    ]
    alerts, _ = R.tow_alerts(me, boats, miles=3, now=NOW)
    assert [a["key"] for a in alerts] == ["tow:4"]


def test_no_alerts_for_a_stale_own_position():
    me = _boat("111", 800.0, timestamp=(NOW - timedelta(minutes=20)).isoformat())
    tow = _boat("367", 801.0, heading="southbound", ship_type=31)
    assert R.tow_alerts(me, [tow], now=NOW) == ([], {})


# --- lock ahead busy / clearing ----------------------------------------------

def _row(wait, lock="lock_3", **kw):
    return {"lock_id": lock, "name": "Lock 3", "wait_estimate_minutes": 90,
            "wait_estimate_recreational_minutes": wait, "queue_stale": False, **kw}


def test_lock_threshold_with_hysteresis():
    a, st = R.lock_alert(_row(50), None, 30)
    assert a is None and st == {"lockId": "lock_3", "level": "busy"}    # first look is silent
    a, st = R.lock_alert(_row(28), st, 30)                               # inside the 5 min band
    assert a is None and st["level"] == "busy"
    a, st = R.lock_alert(_row(25), st, 30)
    assert a["key"] == "lock-clear:lock_3" and a["title"] == "Lock 3: wait coming down"
    assert a["body"] == "Expected wait is now about 25 min."
    a, st = R.lock_alert(_row(30), st, 30)                               # at threshold: not over
    assert a is None and st["level"] == "clear"
    a, st = R.lock_alert(_row(75), st, 30)
    assert a["key"] == "lock-busy:lock_3" and a["body"] == "Expected wait is now about 1 h 15 min (over 30 min)."


def test_lock_change_of_lock_or_stale_queue_is_silent():
    st = {"lockId": "lock_2", "level": "clear"}
    a, st2 = R.lock_alert(_row(90), st, 30)
    assert a is None and st2 == {"lockId": "lock_3", "level": "busy"}
    assert R.lock_alert(_row(5, queue_stale=True), st2, 30) == (None, st2)
    # A tow gets the tow wait
    a, _ = R.lock_alert(_row(5), {"lockId": "lock_3", "level": "clear"}, 30, is_tow=True)
    assert a["key"] == "lock-busy:lock_3"


# --- leave now ----------------------------------------------------------------

def _opts(best):
    return {"best": best, "options": [
        {"depart_in_minutes": 0, "time_at_locks_minutes": 40},
        {"depart_in_minutes": 30, "time_at_locks_minutes": 70},
    ]}


def test_depart_alert_only_on_change_to_best():
    assert R.depart_alert(_opts(0), None) == (None, True)           # first look
    assert R.depart_alert(_opts(1), None) == (None, False)
    a, nb = R.depart_alert(_opts(0), False)
    assert nb is True and a["key"] == "depart:now"
    assert a["body"] == "Leaving now has the least time at locks: about 40 min vs 1 h 10 min if you wait."
    assert R.depart_alert(_opts(0), True) == (None, True)
    assert R.depart_alert({"options": [], "best": None}, False) == (None, False)


# --- dedupe / prefs / payload ---------------------------------------------------

def test_dedupe_30_minutes():
    alerts = [{"key": "tow:1"}, {"key": "tow:1"}, {"key": "lock-busy:lock_3"}]
    fresh, log = R.dedupe(alerts, {"lock-busy:lock_3": 1000.0, "old": -5000.0}, 1000.0 + 600)
    assert [a["key"] for a in fresh] == ["tow:1"]
    assert log == {"lock-busy:lock_3": 1000.0, "tow:1": 1600.0}
    fresh, _ = R.dedupe([{"key": "lock-busy:lock_3"}], log, 1000.0 + R.DEDUPE_SECONDS)
    assert [a["key"] for a in fresh] == ["lock-busy:lock_3"]


def test_prefs_are_normalized():
    p = R.normalize_prefs({"tow": False, "towMiles": 4, "lockWaitMinutes": "45", "direction": "upbound",
                           "mph": 99, "email": "x@example.com"})
    assert p["tow"] is False and p["towMiles"] == 3 and p["lockWaitMinutes"] == 45
    assert p["direction"] == "upbound" and p["mph"] == 15.0 and "email" not in p
    assert R.normalize_prefs(None) == R.PREF_DEFAULTS


def test_payload_is_text_only():
    p = R.payload({"key": "tow:1", "kind": "tow", "title": "Tow approaching", "body": "x"})
    assert p == {"title": "Tow approaching", "body": "x", "tag": "tow:1", "url": "/dashboard", "silent": True}
    assert R.payload({"key": "k", "title": "t", "body": "b"}, sound=True)["silent"] is False


def test_presence_window():
    assert R.app_on_screen((NOW - timedelta(seconds=90)).isoformat(), NOW)
    assert not R.app_on_screen(NOW - timedelta(minutes=3), NOW)
    assert not R.app_on_screen(None, NOW)


def test_subscription_shape():
    ok = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "k", "auth": "a"}}
    assert R.valid_subscription(ok)
    assert not R.valid_subscription({**ok, "endpoint": "http://evil.local/x"})
    assert not R.valid_subscription({**ok, "keys": {"p256dh": "k"}})
    assert not R.valid_subscription("nope")


# --- endpoints + tick with a fake db -----------------------------------------------

def _match(doc, q):
    for k, want in q.items():
        have = doc.get(k)
        if isinstance(want, dict) and "$ne" in want:
            if have == want["$ne"]:
                return False
        elif isinstance(want, dict) and "$in" in want:
            if have not in want["$in"]:
                return False
        elif have != want:
            return False
    return True


class _Res:
    def __init__(self, n):
        self.matched_count = self.deleted_count = n


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, n=None):
        return [dict(d) for d in self.docs]


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, q, proj=None):
        return next((dict(d) for d in self.docs if _match(d, q)), None)

    def find(self, q, proj=None):
        return _Cursor([d for d in self.docs if _match(d, q)])

    async def count_documents(self, q):
        return sum(1 for d in self.docs if _match(d, q))

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if _match(d, q):
                d.update(upd.get("$set", {}))
                return _Res(1)
        if upsert:
            self.docs.append({**upd.get("$setOnInsert", {}), **upd.get("$set", {})})
        return _Res(0)

    async def delete_one(self, q):
        for i, d in enumerate(self.docs):
            if _match(d, q):
                del self.docs[i]
                return _Res(1)
        return _Res(0)


class _DB:
    def __init__(self, users):
        self.push_subscriptions = _Coll()
        self.users = _Coll(users)


OWNER = {"user_id": "u_owner", "email": "owner@example.com", "role": "user",
         "vessels": [{"mmsi": "338414076", "boat_name": "REBOOT"}]}
SUB = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "BPk", "auth": "au"}}


@pytest.fixture
def env(monkeypatch):
    fake = _DB([OWNER])
    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BPUBLIC")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "private")
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:ops@example.com")
    monkeypatch.setattr(server, "_webpush", lambda **kw: None)
    who = {"user": OWNER}

    async def current(request):
        return who["user"]
    monkeypatch.setattr(server, "get_current_user", current)
    return fake, who


def test_key_endpoint_says_off_without_keys(env, monkeypatch):
    c = TestClient(server.app)
    assert c.get("/api/push/key").json() == {"enabled": True, "public_key": "BPUBLIC"}
    monkeypatch.delenv("VAPID_PRIVATE_KEY")
    assert c.get("/api/push/key").json() == {"enabled": False, "public_key": None}
    r = c.post("/api/push/subscribe", json={"subscription": SUB, "mmsi": "338414076"})
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert env[0].push_subscriptions.docs == []


def test_subscribe_only_for_your_own_boat(env):
    fake, who = env
    c = TestClient(server.app)
    assert c.post("/api/push/subscribe", json={"subscription": SUB, "mmsi": "367000001"}).status_code == 403
    # Admins can see any boat, but alerts follow only boats on their own account.
    who["user"] = {"user_id": "u_admin", "is_admin": True, "vessels": []}
    assert c.post("/api/push/subscribe", json={"subscription": SUB, "mmsi": "338414076"}).status_code == 403
    who["user"] = None
    assert c.post("/api/push/subscribe", json={"subscription": SUB, "mmsi": "338414076"}).status_code == 401
    who["user"] = OWNER
    bad = {**SUB, "endpoint": "http://10.0.0.1/x"}
    assert c.post("/api/push/subscribe", json={"subscription": bad, "mmsi": "338414076"}).status_code == 400
    assert fake.push_subscriptions.docs == []


def test_subscribe_update_unsubscribe(env):
    fake, who = env
    c = TestClient(server.app)
    r = c.post("/api/push/subscribe", json={"subscription": SUB, "mmsi": "338414076",
                                            "prefs": {"towMiles": 5, "lock": False}})
    assert r.status_code == 200 and r.json() == {"ok": True, "enabled": True}
    [doc] = fake.push_subscriptions.docs
    assert doc["user_id"] == "u_owner" and doc["prefs"]["towMiles"] == 5 and doc["prefs"]["lock"] is False
    assert "email" not in doc
    doc["last_sent"] = {"tow:1": 1.0}
    doc["state"] = {"lock": {"lockId": "lock_3", "level": "busy"}}
    # Same browser, new threshold: one doc, state restarts, dedupe log kept
    c.post("/api/push/subscribe", json={"subscription": SUB, "mmsi": "338414076", "prefs": {"towMiles": 2}})
    [doc] = fake.push_subscriptions.docs
    assert doc["prefs"]["towMiles"] == 2 and doc["state"] == {} and doc["last_sent"] == {"tow:1": 1.0}
    # Presence + someone else can't remove it
    assert c.post("/api/push/presence", json={"endpoint": SUB["endpoint"], "visible": False}).status_code == 200
    assert doc["visible_at"] is None
    who["user"] = {"user_id": "u_other", "vessels": []}
    assert c.request("DELETE", "/api/push/subscribe", json={"endpoint": SUB["endpoint"]}).json()["removed"] == 0
    who["user"] = OWNER
    assert c.request("DELETE", "/api/push/subscribe", json={"endpoint": SUB["endpoint"]}).json()["removed"] == 1
    assert fake.push_subscriptions.docs == []


class _Sent:
    def __init__(self, status=None):
        self.calls = []
        self.status = status

    def __call__(self, **kw):
        self.calls.append(kw)
        if self.status:
            class Resp:
                status_code = self.status
            raise server._WebPushException("push failed", response=Resp())


def _tick_env(monkeypatch, fake, sender, now):
    monkeypatch.setattr(server, "_webpush", sender)
    me = {"mmsi": "338414076", "name": "REBOOT", "river_mile": 800.0, "speed": 0.0,
          "timestamp": now.isoformat(), "is_user_vessel": True}
    tow = {"mmsi": "367", "name": "MISS ANN", "river_mile": 802.0, "speed": 6.0, "heading": "southbound",
           "ship_type": 31, "timestamp": now.isoformat()}
    monkeypatch.setattr(server, "active_vessels", {"338414076": me, "367": tow})
    monkeypatch.setattr(server, "prepare_vessel_for_output", lambda v, m=None: dict(v))
    fake.push_subscriptions.docs.append({
        **SUB, "user_id": "u_owner", "mmsi": "338414076",
        "prefs": {"tow": True, "towMiles": 3, "lock": False, "depart": False},
        "state": {}, "last_sent": {}, "visible_at": None})


def test_tick_pushes_once_then_dedupes(env, monkeypatch):
    fake, _ = env
    sender = _Sent()
    now = datetime.now(timezone.utc)
    _tick_env(monkeypatch, fake, sender, now)
    stats = asyncio.run(server.push_alerts_tick(now))
    assert stats["sent"] == 1 and len(sender.calls) == 1
    call = sender.calls[0]
    body = json.loads(call["data"])
    assert body["tag"] == "tow:367" and body["title"] == "Tow approaching"
    assert "owner@example.com" not in call["data"] and "u_owner" not in call["data"]
    assert call["vapid_claims"] == {"sub": "mailto:ops@example.com"}
    doc = fake.push_subscriptions.docs[0]
    assert "tow:367" in doc["last_sent"] and doc["state"]["tow_refs"] == {"367": 2.0}
    # Next minute (or after a restart: state is in the db): no repeat
    asyncio.run(server.push_alerts_tick(now + timedelta(minutes=1)))
    assert len(sender.calls) == 1


def test_tick_skips_while_the_app_is_on_screen(env, monkeypatch):
    fake, _ = env
    sender = _Sent()
    now = datetime.now(timezone.utc)
    _tick_env(monkeypatch, fake, sender, now)
    fake.push_subscriptions.docs[0]["visible_at"] = now - timedelta(seconds=30)
    asyncio.run(server.push_alerts_tick(now))
    assert sender.calls == []
    assert "tow:367" in fake.push_subscriptions.docs[0]["last_sent"]   # the toast counted


def test_tick_drops_gone_subscriptions_and_boats_off_the_account(env, monkeypatch):
    fake, _ = env
    now = datetime.now(timezone.utc)
    _tick_env(monkeypatch, fake, _Sent(status=410), now)
    assert asyncio.run(server.push_alerts_tick(now))["removed"] == 1
    assert fake.push_subscriptions.docs == []
    # Transient failure: kept, retried next tick
    sender = _Sent(status=500)
    _tick_env(monkeypatch, fake, sender, now)
    asyncio.run(server.push_alerts_tick(now))
    assert len(fake.push_subscriptions.docs) == 1 and fake.push_subscriptions.docs[0]["last_sent"] == {}
    # The boat was removed from the account
    fake.users.docs[0] = {**OWNER, "vessels": []}
    asyncio.run(server.push_alerts_tick(now))
    assert fake.push_subscriptions.docs == []


def test_tick_ignores_stale_boats(env, monkeypatch):
    fake, _ = env
    sender = _Sent()
    now = datetime.now(timezone.utc)
    _tick_env(monkeypatch, fake, sender, now - timedelta(minutes=20))
    assert asyncio.run(server.push_alerts_tick(now))["checked"] == 0
    assert sender.calls == []


def test_tick_lock_rule_uses_the_lock_board(env, monkeypatch):
    fake, _ = env
    sender = _Sent()
    now = datetime.now(timezone.utc)
    _tick_env(monkeypatch, fake, sender, now)
    doc = fake.push_subscriptions.docs[0]
    doc["prefs"] = {"tow": False, "lock": True, "lockWaitMinutes": 30, "depart": False, "direction": "downbound"}
    doc["state"] = {"lock": {"lockId": "lock_3", "level": "clear"}}
    asked = []

    async def board(direction=None, **kw):
        asked.append(direction)
        return {"locks": [
            {"lock_id": "lock_2", "name": "Lock 2", "river_mile": 815.2, "wait_estimate_minutes": 0,
             "wait_estimate_recreational_minutes": 0},
            {"lock_id": "lock_3", "name": "Lock 3", "river_mile": 796.9, "wait_estimate_minutes": 120,
             "wait_estimate_recreational_minutes": 50, "queue_stale": False},
        ]}
    monkeypatch.setattr(server, "get_lock_board", board)
    asyncio.run(server.push_alerts_tick(now))
    assert asked == ["downbound"]   # stopped boat: the planner's direction
    assert [json.loads(c["data"])["tag"] for c in sender.calls] == ["lock-busy:lock_3"]


def test_tick_depart_rule_while_stopped_every_two_minutes(env, monkeypatch):
    fake, _ = env
    sender = _Sent()
    now = datetime.now(timezone.utc)
    _tick_env(monkeypatch, fake, sender, now)
    doc = fake.push_subscriptions.docs[0]
    doc["prefs"] = {"tow": False, "lock": False, "depart": True, "direction": "upbound", "mph": 20}
    answers = [_opts(1), _opts(0)]
    asked = []

    async def options(mmsi, direction, request=None, cruise_mph=15.0, **kw):
        assert request is None and mmsi == "338414076"
        asked.append((direction, cruise_mph))
        return answers.pop(0)
    monkeypatch.setattr(server, "get_departure_options", options)
    asyncio.run(server.push_alerts_tick(now))                          # leaving later is best
    asyncio.run(server.push_alerts_tick(now + timedelta(minutes=1)))   # not re-checked yet
    asyncio.run(server.push_alerts_tick(now + timedelta(minutes=2)))   # leaving now became best
    assert asked == [("upbound", 20.0), ("upbound", 20.0)]
    assert [json.loads(c["data"])["tag"] for c in sender.calls] == ["depart:now"]
