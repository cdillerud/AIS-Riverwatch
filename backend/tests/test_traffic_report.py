"""Daily Traffic Report: day boundaries, counts, renderings, endpoints, email."""
import asyncio
import email
import email.policy
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from services import traffic_report as T

LOCKS = {
    "lock_2": {"name": "Lock & Dam #2 (Hastings)", "river_mile": 815.2},
    "lock_3": {"name": "Lock & Dam #3 (Red Wing)", "river_mile": 796.9},
    "lock_5a": {"name": "Lock & Dam #5A (Fountain City)", "river_mile": 728.5},
}
DAY = date(2026, 11, 10)  # CST: the day is 06:00 UTC Nov 10 -> 06:00 UTC Nov 11
NOW = datetime(2026, 11, 11, 15, tzinfo=timezone.utc)


def _row(lock, kind="tow", wait=30.0, barges=15, direction="downbound", name="BOAT",
         arrival=datetime(2026, 11, 10, 18, 0)):
    return {"lock_id": lock, "vessel_name": name, "direction": direction, "barge_count": barges,
            "is_tow": kind == "tow", "is_recreational": kind == "rec", "wait_time_minutes": wait,
            "lockage_duration_minutes": 40.0, "arrival_time": arrival, "exit_time": arrival + timedelta(hours=1)}


def _report(rows=None, prior=None, statuses=None, now=NOW):
    rows = rows if rows is not None else [
        _row("lock_2", wait=10), _row("lock_2", wait=200, name="SLOW TOW", arrival=datetime(2026, 11, 10, 3, 0)),
        _row("lock_3", kind="rec", wait=0, barges=0), _row("lock_3", kind="other", wait=5, barges=0)]
    prior = prior if prior is not None else [{"lock_id": "lock_2"}] * 14 + [{"lock_id": "lock_3"}] * 7
    return T.build_report(DAY, rows, prior, LOCKS, statuses, now=now)


def test_central_day_bounds_follow_dst():
    assert T.day_bounds_utc(date(2026, 11, 10)) == (datetime(2026, 11, 10, 6, tzinfo=timezone.utc),
                                                    datetime(2026, 11, 11, 6, tzinfo=timezone.utc))
    assert T.day_bounds_utc(date(2026, 7, 4))[0] == datetime(2026, 7, 4, 5, tzinfo=timezone.utc)
    start, end = T.day_bounds_utc(date(2026, 11, 1))  # fall back: a 25-hour day
    assert end - start == timedelta(hours=25)
    start, end = T.day_bounds_utc(date(2026, 3, 8))   # spring forward: 23 hours
    assert end - start == timedelta(hours=23)
    assert T.central_today(datetime(2026, 11, 11, 3, tzinfo=timezone.utc)) == date(2026, 11, 10)


def test_counts_waits_and_usual():
    r = _report()
    t = r["totals"]
    assert (t["lockages"], t["tows"], t["recreational"], t["other"], t["barges"]) == (4, 2, 1, 1, 30)
    assert t["usual_lockages"] == 3.0 and t["vs_usual_pct"] == 33
    l2 = next(lr for lr in r["locks"] if lr["lock_id"] == "lock_2")
    assert l2["median_tow_wait_min"] == 105 and l2["max_wait_min"] == 200 and l2["usual_lockages"] == 2.0
    assert [lr["lock_id"] for lr in r["locks"]] == ["lock_2", "lock_3", "lock_5a"]  # upstream first
    assert r["no_data_locks"] == ["Lock & Dam #5A (Fountain City)"]
    assert r["longest_waits"][0]["vessel"] == "SLOW TOW"
    assert r["longest_waits"][0]["arrived"] == "Nov 9, 9:00 PM"  # 03:00 UTC = previous evening, CST
    assert r["complete"]
    assert any(h.startswith("Busier than usual") for h in r["highlights"])
    assert any("Longest wait: SLOW TOW" in h for h in r["highlights"])
    assert any("pleasure-boat lockage, no wait" in h for h in r["highlights"])


def test_in_progress_day_and_empty_day():
    r = _report(now=datetime(2026, 11, 10, 20, tzinfo=timezone.utc))
    assert not r["complete"] and r["highlights"][0].startswith("Day still in progress")
    assert not any("than usual" in h for h in r["highlights"])
    empty = _report(rows=[])
    assert empty["totals"]["lockages"] == 0
    assert "No completed lockages" in " ".join(empty["highlights"])
    T.render_html(empty)  # renders without data


def test_closures_and_html_escaping():
    rows = [_row("lock_2", name="<script>x</script>")]
    r = _report(rows=rows, statuses={"lock_3": {"status": "CLOSED", "closure_info": "Maintenance & repair"}})
    assert r["closures"] == [{"lock_id": "lock_3", "name": "Lock & Dam #3 (Red Wing)", "status": "CLOSED",
                              "info": "Maintenance & repair"}]
    html = T.render_html(r, app_url="https://riverwatch.example")
    assert "<script>x" not in html and "&lt;script&gt;x" in html
    assert "Maintenance &amp; repair" in html and "Closures and restrictions" in html
    assert "https://riverwatch.example" in html


def test_csv_and_eml():
    r = _report()
    lines = T.render_csv(r).strip().splitlines()
    assert lines[0].startswith("date,lock_id,name")
    assert len(lines) == 3  # 5A has no data and is left out
    msg = email.message_from_bytes(T.render_eml(r), policy=email.policy.default)
    assert msg["X-Unsent"] == "1" and msg["Subject"] == r["title"]
    parts = {p.get_content_type(): p for p in msg.walk()}
    assert {"text/plain", "text/html", "text/csv"} <= set(parts)
    assert sorted(p.get_filename() for p in msg.walk() if p.get_content_type() == "text/csv") == [
        "riverwatch-tows-2026-11-10.csv", "riverwatch-traffic-2026-11-10.csv"]
    sent = T.build_email(r, to="a@example.com", sender="RiverWatch <r@example.com>")
    assert sent["To"] == "a@example.com" and "X-Unsent" not in sent


def test_lockage_types_and_long_single_threshold():
    hist = [{"lock_id": "lock_2", "is_tow": True, "cuts": 1, "lockage_duration_minutes": float(m)}
            for m in range(20, 50)]                                    # 30 singles, 20..49 min
    hist += [{"lock_id": "lock_3", "is_tow": True, "cuts": 1, "lockage_duration_minutes": 30.0}] * 5
    th = T.long_single_thresholds(hist)
    assert th == {"lock_2": 47.0}                                      # lock_3: too few to judge
    tow = {"is_tow": True, "cuts": 1, "lockage_duration_minutes": 70.0}
    assert T.lockage_type(tow, th["lock_2"]) == "Long single"
    assert T.lockage_type({**tow, "lockage_duration_minutes": 35.0}, 47.0) == "Single"
    assert T.lockage_type(tow, None) == "Single"                        # no threshold: never flagged
    assert T.lockage_type({**tow, "cuts": 2}) == "Double"
    split = [{"barges": 9}, {"barges": 6}]
    boat = [{"barges": 4}, {"barges": 0}]
    assert T.lockage_type({**tow, "cuts": 2, "cut_times": split}) == "Double"
    assert T.lockage_type({**tow, "cuts": 2, "cut_times": boat}) == "Boat separate"
    assert T.lockage_type({**tow, "cuts": 3}) == "Triple"
    assert T.lockage_type({"is_tow": False, "is_recreational": False}) == "Light boat"


def test_vessel_detail_per_lock():
    s1, e1 = datetime(2026, 11, 10, 18, 30), datetime(2026, 11, 10, 19, 20)
    s2, e2 = datetime(2026, 11, 10, 19, 25), datetime(2026, 11, 10, 20, 30)
    double = {**_row("lock_2", name="BIG TOW", wait=45), "cuts": 2, "entry_time": s1,
              "lockage_duration_minutes": 120.0, "cut_times": [{"start": s1, "end": e1}, {"start": s2, "end": e2}]}
    early = {**_row("lock_2", name="EARLY", barges=6, arrival=datetime(2026, 11, 10, 12, 0)), "cuts": 1,
             "entry_time": datetime(2026, 11, 10, 12, 10), "lockage_duration_minutes": 80.0}
    light = {**_row("lock_2", kind="other", name="LIGHT BOAT", barges=0), "cuts": 1,
             "entry_time": datetime(2026, 11, 10, 21, 0)}
    rec = _row("lock_2", kind="rec", name="RECREATIONAL VESSEL", barges=0)
    s3, e3, s4, e4 = (datetime(2026, 11, 10, 22, 0), datetime(2026, 11, 10, 22, 50),
                      datetime(2026, 11, 10, 22, 55), datetime(2026, 11, 10, 23, 20))
    boat_sep = {**_row("lock_2", name="SMALL TOW", barges=4), "cuts": 2, "entry_time": s3,
                "cut_times": [{"start": s3, "end": e3, "barges": 4}, {"start": s4, "end": e4, "barges": 0}]}
    double["cut_times"] = [{**c, "barges": b} for c, b in zip(double["cut_times"], (9, 6))]
    r = T.build_report(DAY, [double, early, light, rec, boat_sep], [], LOCKS, now=NOW,
                       long_single_min={"lock_2": 50.0})
    l2 = r["locks"][0]
    assert [v["vessel"] for v in l2["vessels"]] == ["EARLY", "BIG TOW", "LIGHT BOAT", "SMALL TOW"]  # no pleasure
    assert [v["type"] for v in l2["vessels"]] == ["Long single", "Double", "Light boat", "Boat separate"]
    big = l2["vessels"][1]
    assert big["cut_minutes"] == [50, 65] and big["cut_barges"] == [9, 6]
    assert big["barges"] == 15 and big["wait_min"] == 45
    assert big["started"] == "12:30 PM" and big["arrived"] == "12:00 PM"
    assert (l2["singles"], l2["long_singles"], l2["doubles"], l2["boat_separate"], l2["light_boats"]) == (1, 1, 1, 1, 1)
    assert r["totals"]["doubles"] == 1 and r["totals"]["boat_separate"] == 1
    html = T.render_html(r)
    assert "Tows by lock" in html and "Double (9+6 barges, 50 + 65 min)" in html
    assert "Boat separate (50 + 25 min)" in html and "Long single" in html
    csv_lines = T.render_tows_csv(r).strip().splitlines()
    assert csv_lines[0].startswith("date,lock_id,lock_name") and len(csv_lines) == 5
    assert "Double" in csv_lines[2] and "9+6" in csv_lines[2] and "50 + 65" in csv_lines[2]


def test_endpoint_formats(monkeypatch, signed_in):
    import server

    async def fake_build(day):
        return _report()

    monkeypatch.setattr(server, "build_traffic_report", fake_build)
    monkeypatch.setattr(server._traffic_report, "central_today", lambda now=None: date(2026, 11, 11))
    c = TestClient(server.app)
    assert c.get("/api/reports/traffic").json()["date"] == "2026-11-10"
    h = c.get("/api/reports/traffic", params={"date": "2026-11-10", "format": "html", "download": "true"})
    assert h.status_code == 200 and h.headers["content-type"].startswith("text/html")
    assert 'filename="riverwatch-traffic-2026-11-10.html"' in h.headers["content-disposition"]
    assert c.get("/api/reports/traffic", params={"format": "csv"}).headers["content-type"].startswith("text/csv")
    e = c.get("/api/reports/traffic", params={"format": "eml"})
    assert e.headers["content-type"] == "message/rfc822" and "attachment" in e.headers["content-disposition"]
    tows = c.get("/api/reports/traffic", params={"format": "tows", "download": "true"})
    assert tows.headers["content-type"].startswith("text/csv")
    assert 'filename="riverwatch-tows-2026-11-10.csv"' in tows.headers["content-disposition"]
    assert c.get("/api/reports/traffic", params={"format": "pdf"}).status_code == 400
    assert c.get("/api/reports/traffic", params={"date": "2026-11-12"}).status_code == 400  # future
    assert c.get("/api/reports/traffic", params={"date": "2026-09-01"}).status_code == 400  # too old
    assert c.get("/api/reports/traffic", params={"date": "11/10/2026"}).status_code == 400


def test_report_needs_login():
    import server
    assert TestClient(server.app).get("/api/reports/traffic").status_code == 401


def test_email_off_without_smtp(monkeypatch, signed_in):
    import server
    monkeypatch.delenv("REPORT_SMTP_HOST", raising=False)
    c = TestClient(server.app)
    assert c.post("/api/reports/traffic/email-me").status_code == 503
    assert asyncio.run(server.send_daily_reports(NOW)) == 0


class _Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query, projection=None):
        docs = self.docs

        class _C:
            async def to_list(self, n):
                return [d for d in docs if d.get("report_subscription", {}).get("daily_email")]
        return _C()

    async def find_one(self, key):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in key.items())), None)

    async def insert_one(self, doc):
        self.docs.append(doc)


def test_daily_send_once_per_subscriber(monkeypatch):
    import server
    monkeypatch.setenv("REPORT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("REPORT_EMAIL_FROM", "RiverWatch <r@example.com>")
    monkeypatch.setenv("REPORT_SEND_HOUR", "6")

    class _DB:
        users = _Coll([{"user_id": "u1", "email": "one@example.com", "report_subscription": {"daily_email": True}},
                       {"user_id": "u2", "email": "two@example.com", "report_subscription": {"daily_email": False}},
                       {"user_id": "u3", "report_subscription": {"daily_email": True}}])  # no email
        report_sends = _Coll()

    sent_to = []

    async def fake_build(day):
        assert day == date(2026, 11, 10)
        return _report()

    monkeypatch.setattr(server, "db", _DB())
    monkeypatch.setattr(server, "build_traffic_report", fake_build)
    monkeypatch.setattr(server._report_mailer, "send", lambda msg, timeout=30.0: sent_to.append(msg["To"]))

    early = datetime(2026, 11, 11, 11, tzinfo=timezone.utc)  # 5 AM CST: too early
    assert asyncio.run(server.send_daily_reports(early)) == 0
    at7 = datetime(2026, 11, 11, 13, tzinfo=timezone.utc)    # 7 AM CST
    assert asyncio.run(server.send_daily_reports(at7)) == 1
    assert sent_to == ["one@example.com"]
    assert asyncio.run(server.send_daily_reports(at7 + timedelta(minutes=10))) == 0  # not twice
