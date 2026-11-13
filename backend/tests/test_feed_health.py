from datetime import datetime, timedelta, timezone

from services import feed_health as H

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)


def test_queue_freshness_labels_old_queues():
    assert H.queue_freshness(NOW - timedelta(minutes=6), NOW) == {"queue_age_minutes": 6, "queue_stale": False}
    assert H.queue_freshness((NOW - timedelta(minutes=45)).replace(tzinfo=None), NOW)["queue_stale"] is True
    assert H.queue_freshness(None, NOW) == {"queue_age_minutes": None, "queue_stale": True}


def test_usace_summary_status():
    locks = ["lock_1", "lock_2", "lock_5a"]
    fresh = {"lock_1": NOW - timedelta(minutes=3), "lock_2": NOW - timedelta(minutes=7)}
    ok = H.usace_summary(fresh, locks, NOW, no_data_locks=["lock_5a"])
    assert ok["status"] == "ok" and ok["stale_locks"] == [] and ok["oldest_minutes"] == 7
    one_old = {**fresh, "lock_2": NOW - timedelta(hours=2)}
    assert H.usace_summary(one_old, locks, NOW, ["lock_5a"])["stale_locks"] == ["lock_2"]
    assert H.usace_summary(one_old, locks, NOW, ["lock_5a"])["status"] == "degraded"
    assert H.usace_summary({}, locks, NOW, ["lock_5a"])["status"] == "down"


def test_ais_feed_optional():
    assert H.ais_summary(False, False, None, NOW)["status"] == "not_configured"
    assert H.ais_summary(True, True, NOW - timedelta(seconds=30), NOW)["status"] == "ok"
    assert H.ais_summary(True, True, NOW - timedelta(minutes=12), NOW)["status"] == "down"


def test_overall():
    assert H.overall(False, {"status": "ok"}) == "down"
    assert H.overall(True, {"status": "degraded"}) == "degraded"
    assert H.overall(True, {"status": "ok"}) == "ok"


def _samples(pattern, start=NOW - timedelta(minutes=60)):
    """'u' = up, 'd' = down, '.' = no sample (server off), one per minute."""
    return [(start + timedelta(minutes=i), ch == "u") for i, ch in enumerate(pattern) if ch != "."]


def test_uptime_percent_ignores_gaps():
    s = _samples("uuuu....dd")
    assert H.uptime_percent(s, NOW, 24) == 66.7
    assert H.uptime_percent([], NOW, 24) is None


def test_outages_and_down_since():
    s = _samples("uuddddddu" + "u" * 5 + "ddd....dddddd")
    runs = H.outages(s)
    # newest first; the gap splits the last run, and the 3-minute blip is dropped
    assert [r["minutes"] for r in runs] == [6, 6]
    assert runs[0]["end"] is None
    assert H.down_since(s) == s[-6][0]
    assert H.down_since(_samples("dddu")) is None


def test_alert_fires_once_after_15_minutes_then_on_recovery():
    started = NOW - timedelta(minutes=14)
    assert H.alert_due(started, False, NOW) is None
    assert H.alert_due(started, False, NOW + timedelta(minutes=1)) == "down"
    assert H.alert_due(started, True, NOW + timedelta(minutes=30)) is None
    assert H.alert_due(None, True, NOW) == "up"
    assert H.alert_due(None, False, NOW) is None


def test_uptime_summary_shape():
    s = _samples("u" * 50 + "d" * 10)
    out = H.uptime_summary(s, NOW)
    assert out["uptime_24h"] == 83.3 and out["outages_7d"] == 1
    assert out["down_since"] == s[50][0].isoformat()
