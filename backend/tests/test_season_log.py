from datetime import datetime, timedelta, timezone

from services import season_log as S

T0 = datetime(2026, 6, 27, 14, 0, tzinfo=timezone.utc)   # 9 am CDT-ish
LOCKS = [("lock_2", 815.2, "Lock & Dam #2"), ("lock_3", 796.9, "Lock & Dam #3")]


def _track(pairs):
    return [{"t": T0 + timedelta(minutes=m), "rm": rm} for m, rm in pairs]


def test_due_by_distance_or_time():
    assert S.due(None, 800.0, T0)
    assert not S.due((T0, 800.0), 800.1, T0 + timedelta(minutes=5))
    assert S.due((T0, 800.0), 800.3, T0 + timedelta(minutes=1))
    assert S.due((T0, 800.0), 800.0, T0 + timedelta(minutes=31))


def test_summary_counts_miles_hours_and_lock_time():
    # downriver from 830 at 10 mph, 40 min at Lock 2 (815.2), on to 805
    pts = _track([(0, 830.0), (30, 825.0), (60, 820.0), (85, 815.8), (95, 815.5), (110, 815.4),
                  (125, 815.0), (130, 814.8), (160, 810.0), (190, 805.0)])
    s = S.summarize(pts, LOCKS)
    assert s["miles"] == 25.0
    assert s["locks_passed"] == 1
    p = s["passages"][0]
    assert p["lock_id"] == "lock_2" and p["direction"] == "downbound"
    assert p["minutes_at_lock"] == 45          # 815.8 at 85 min -> 814.8 at 130
    assert s["days_out"] == 1
    assert 2.0 <= s["hours_underway"] <= 3.2   # slow minutes at the lock don't count


def test_gaps_and_jumps_are_not_travel():
    pts = _track([(0, 830.0), (120, 800.0), (121, 700.0), (130, 700.5)])   # 2 h gap, then a 100-mile jump
    s = S.summarize(pts, LOCKS)
    assert s["miles"] == 0.5
    # Lock 2 crossed during the 2 h gap (15 mph: plausible); the jump past Lock 3 is not a passage
    assert [p["lock_id"] for p in s["passages"]] == ["lock_2"]
