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
