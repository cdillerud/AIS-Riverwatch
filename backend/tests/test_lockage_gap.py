from datetime import datetime, timedelta, timezone

import pytest

server = pytest.importorskip("server")
NOW = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)


def test_busy_lock_quiet_for_a_few_hours_is_not_flagged():
    assert server.lockage_gap_note(NOW - timedelta(hours=8), 220, NOW) is None


def test_long_silence_is_flagged_without_claiming_closed():
    note = server.lockage_gap_note((NOW - timedelta(hours=407)).replace(tzinfo=None), 27, NOW)
    assert note.startswith("No lockages reported by USACE in 16 days")
    assert "usually ~6 a week" in note and "may be closed" in note and "CLOSED" not in note


def test_quiet_lock_judged_against_its_own_spacing():
    # 30 lockages in 30 days: a day and a half without one is normal
    assert server.lockage_gap_note(NOW - timedelta(hours=36), 30, NOW) is None
    assert server.lockage_gap_note(NOW - timedelta(days=8), 30, NOW) is not None


def test_no_lockages_at_all():
    assert "30 days" in server.lockage_gap_note(None, 0, NOW)
