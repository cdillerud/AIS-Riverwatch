"""Share my trip: public, expiring links to one boat (services/trip_share.py)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import server
from services import api_access as A
from services import lock_board as LB
from services import trip_share as TS

NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
LOCKS = [("Lock 2", 815.2), ("Lock 3", 796.9)]


# --- pure logic --------------------------------------------------------------

def test_hours_are_clamped_and_tokens_are_random():
    assert TS.clamp_hours(None) == 24
    assert TS.clamp_hours(0) == 1 and TS.clamp_hours(500) == 72 and TS.clamp_hours("6") == 6
    assert TS.clamp_hours("soon") == 24
    a, b = TS.new_token(), TS.new_token()
    assert a != b and len(a) >= 20 and all(c.isalnum() or c in "-_" for c in a)


def test_new_share_expiry_and_destination():
    d = TS.new_share(" 338414076 ", "u1", 6, "812.44", " REBOOT ", now=NOW)
    assert d["mmsi"] == "338414076" and d["boat_name"] == "REBOOT" and d["destination_rm"] == 812.4
    assert d["expires_at"] == NOW + timedelta(hours=6) and d["revoked"] is False
    assert TS.new_share("1", "u1", None, "x", None, now=NOW)["destination_rm"] is None


def test_active_means_not_revoked_and_not_expired():
    doc = {"expires_at": NOW + timedelta(hours=1), "revoked": False}
    assert TS.is_active(doc, NOW)
    assert not TS.is_active({**doc, "revoked": True}, NOW)
    assert not TS.is_active({**doc, "expires_at": NOW - timedelta(seconds=1)}, NOW)
    assert not TS.is_active(None, NOW) and not TS.is_active({"revoked": False}, NOW)
    # Mongo returns naive UTC datetimes
    assert TS.is_active({"expires_at": (NOW + timedelta(minutes=5)).replace(tzinfo=None)}, NOW)


def test_owner_view_has_no_user_id():
    v = TS.owner_view({**TS.new_share("1", "u1", 2, None, "B", now=NOW), "_id": "x"})
    assert "user_id" not in v and "_id" not in v and v["expires_at"].startswith("2026-11-12T17:00")


def test_thresholds_match_lock_board():
    assert TS.AT_LOCK_MI == LB.AT_LOCK_MI and TS.SLOW_KNOTS == LB.SLOW_KNOTS


def test_status_and_direction():
    assert TS.lock_at(796.8, LOCKS) == "Lock 3" and TS.lock_at(790.0, LOCKS) is None
    assert TS.boat_status(0.2, "Lock 3") == "at_lock"
    assert TS.boat_status(6.0, "Lock 3") == "underway"   # passing through
    assert TS.boat_status(0.2, None) == "stopped"
    assert TS.direction_word("northbound") == "upriver" and TS.direction_word("downbound") == "downriver"
    assert TS.direction_word("stationary") is None


def test_destination_eta_counts_time_at_locks():
    legs = [{"lock_rm": 796.9, "user_eta_minutes": 30, "depart_eta_minutes": 75},
            {"lock_rm": 815.2, "user_eta_minutes": 200, "depart_eta_minutes": 250}]  # past destination
    # 10 mph upriver from RM 790 to RM 806.9: leave Lock 3 at 75 min, then 10 mi = 60 min
    assert TS.destination_eta_minutes(790.0, 10.0, "northbound", 806.9, legs) == 135.0
    assert TS.destination_eta_minutes(790.0, 10.0, "northbound", 795.0, []) == 30.0
    assert TS.destination_eta_minutes(790.0, 10.0, "southbound", 806.9, legs) is None   # wrong way
    assert TS.destination_eta_minutes(790.0, 0, "northbound", 806.9, legs) is None      # stopped


def _vessel(**kw):
    v = {"mmsi": "338414076", "name": "REBOOT", "lat": 44.7612345, "lon": -92.8712345, "speed": 6.26,
         "course": 12.4, "heading": "northbound", "river_mile": 790.04, "timestamp": "2026-11-12T14:58:00+00:00",
         "barge_count": None, "callsign": "WDX1234", "destination": "HASTINGS"}
    v.update(kw)
    return v


PLAN = {"heading": "northbound", "legs": [{
    "lock_id": "lock_3", "lock_name": "Lock 3", "lock_rm": 796.9, "user_eta_minutes": 57.4,
    "expected_wait_minutes": 20, "expected_wait_range_minutes": [10, 35], "depart_eta_minutes": 92,
    "threatening_vessel": {"mmsi": "999", "name": "SECRET TOW"}, "status": "speed_up"}]}

ALLOWED = {"boat_name", "has_position", "river_mile", "lat", "lon", "speed_mph", "heading", "direction",
           "updated_at", "status", "at_lock", "next_lock", "destination", "expires_at", "generated_at"}


def test_public_payload_is_allow_listed():
    out = TS.public_payload("REBOOT", _vessel(), PLAN, LOCKS, destination_rm=806.9, now=NOW)
    assert set(out) == ALLOWED
    assert out["river_mile"] == 790.0 and out["speed_mph"] == 7.2 and out["direction"] == "upriver"
    assert out["status"] == "underway" and out["heading"] == 12
    assert out["next_lock"]["name"] == "Lock 3" and out["next_lock"]["wait_minutes"] == 20
    assert out["next_lock"]["wait_range_minutes"] == [10, 35]
    assert out["next_lock"]["eta_at"].startswith("2026-11-12T15:57")
    assert out["destination"]["river_mile"] == 806.9 and out["destination"]["eta_minutes"] is not None
    text = json.dumps(out)
    for secret in ("338414076", "SECRET TOW", "999", "WDX1234", "HASTINGS", "mmsi", "user_id", "email"):
        assert secret not in text, secret


def test_public_payload_without_position_or_plan():
    out = TS.public_payload("REBOOT", None, None, LOCKS, destination_rm=None, now=NOW)
    assert out["status"] == "unknown" and out["has_position"] is False
    assert out["lat"] is None and out["next_lock"] is None and out["destination"] is None
    stopped = TS.public_payload(None, _vessel(speed=0.1, river_mile=796.85), None, LOCKS, now=NOW)
    assert stopped["boat_name"] == "REBOOT" and stopped["status"] == "at_lock" and stopped["at_lock"] == "Lock 3"
    assert stopped["direction"] is None


def test_rate_limiter_window():
    rl = TS.RateLimiter(limit=3, window_s=60)
    assert all(rl.allow("t", now=t) for t in (0, 1, 2))
    assert not rl.allow("t", now=3)
    assert rl.allow("other", now=3)
    assert rl.allow("t", now=61)


# --- endpoints ---------------------------------------------------------------

def _match(doc, q):
    for k, want in q.items():
        if k == "vessels.mmsi":
            if not any(v.get("mmsi") == want for v in doc.get("vessels") or []):
                return False
            continue
        have = doc.get(k)
        if isinstance(want, dict) and "$gt" in want:
            if have is None or not have > want["$gt"]:
                return False
        elif have != want:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration


class _Res:
    def __init__(self, n):
        self.matched_count = n


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, q, proj=None):
        return next((dict(d) for d in self.docs if _match(d, q)), None)

    def find(self, q, proj=None):
        return _Cursor([d for d in self.docs if _match(d, q)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def count_documents(self, q):
        return sum(1 for d in self.docs if _match(d, q))

    async def update_one(self, q, upd):
        for d in self.docs:
            if _match(d, q):
                d.update(upd.get("$set", {}))
                return _Res(1)
        return _Res(0)


class _DB:
    def __init__(self, users):
        self.trip_shares = _Coll()
        self.users = _Coll(users)


OWNER = {"user_id": "u_owner", "email": "owner@example.com", "role": "user",
         "vessels": [{"mmsi": "338414076", "boat_name": "REBOOT"}]}


@pytest.fixture
def env(monkeypatch):
    fake = _DB([OWNER])
    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setattr(server, "_share_rate", TS.RateLimiter(limit=30, window_s=60))
    monkeypatch.setattr(server, "_share_cache", {})
    monkeypatch.setattr(server, "active_vessels", {"338414076": _vessel()})

    async def plan(mmsi, request=None, destination_rm=None, **kw):
        assert request is None
        return PLAN
    monkeypatch.setattr(server, "get_session_trip_plan", plan)
    who = {"user": OWNER}

    async def current(request):
        return who["user"]
    monkeypatch.setattr(server, "get_current_user", current)
    return fake, who


def test_share_path_is_public():
    assert A.is_public("/api/public/share/abc")
    assert not A.is_public("/api/share") and not A.is_public("/api/publicity")


def test_create_view_list_revoke(env):
    fake, who = env
    c = TestClient(server.app)
    r = c.post("/api/share", json={"mmsi": "338414076", "hours": 6, "destination_rm": 806.9})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert r.json()["boat_name"] == "REBOOT" and "user_id" not in r.json()
    assert fake.trip_shares.docs[0]["user_id"] == "u_owner"

    assert [s["token"] for s in c.get("/api/share").json()["shares"]] == [token]

    who["user"] = None   # a family member, not signed in
    r = c.get(f"/api/public/share/{token}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == ALLOWED and body["boat_name"] == "REBOOT"
    for secret in ("338414076", "owner@example.com", "u_owner", "SECRET TOW"):
        assert secret not in r.text
    assert c.get("/api/share").status_code == 401

    who["user"] = OWNER
    assert c.delete(f"/api/share/{token}").status_code == 200
    who["user"] = None
    assert c.get(f"/api/public/share/{token}").status_code == 404


def test_only_your_own_boat(env):
    fake, who = env
    c = TestClient(server.app)
    assert c.post("/api/share", json={"mmsi": "367000001"}).status_code == 403
    # An admin may simulate any boat, but not publish someone else's position.
    who["user"] = {"user_id": "u_admin", "role": "admin", "vessels": []}
    assert c.post("/api/share", json={"mmsi": "338414076"}).status_code == 403
    assert c.post("/api/share", json={"mmsi": "338414076", "hours": 100}).status_code == 422
    assert fake.trip_shares.docs == []


def test_unknown_expired_and_others_tokens(env):
    fake, who = env
    c = TestClient(server.app)
    assert c.get("/api/public/share/nope").status_code == 404
    old = TS.new_share("338414076", "u_owner", 1, None, "REBOOT", now=datetime.now(timezone.utc) - timedelta(hours=2))
    fake.trip_shares.docs.append(old)
    assert c.get(f"/api/public/share/{old['token']}").status_code == 404
    # Someone else can't revoke your link
    live = TS.new_share("338414076", "u_owner", 1, None, "REBOOT")
    fake.trip_shares.docs.append(live)
    who["user"] = {"user_id": "u_other", "vessels": []}
    assert c.delete(f"/api/share/{live['token']}").status_code == 404
    # Boat removed from the account: link stops working
    fake.users.docs[0] = {**OWNER, "vessels": []}
    who["user"] = None
    assert c.get(f"/api/public/share/{live['token']}").status_code == 404


def test_public_view_is_rate_limited(env, monkeypatch):
    fake, _ = env
    monkeypatch.setattr(server, "_share_rate", TS.RateLimiter(limit=2, window_s=60))
    live = TS.new_share("338414076", "u_owner", 1, None, "REBOOT")
    fake.trip_shares.docs.append(live)
    c = TestClient(server.app)
    codes = [c.get(f"/api/public/share/{live['token']}").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
