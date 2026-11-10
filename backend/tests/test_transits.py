"""Lock-to-lock transit times and predicted arrivals from USACE history."""
from datetime import datetime, timedelta, timezone

from config import LOCKS
from services import transits as T

ORDER = T.lock_order(LOCKS)
T0 = datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)


def _lockage(mmsi, lock_id, direction, arrival, exit_, barges=15):
    return {"mmsi": mmsi, "lock_id": lock_id, "direction": direction, "barge_count": barges,
            "arrival_time": arrival, "entry_time": arrival, "exit_time": exit_, "vessel_name": mmsi}


def _trip(mmsi, start, hours_13_to_14, direction="downbound"):
    a = _lockage(mmsi, "lock_13", direction, start, start + timedelta(hours=1))
    b_arr = a["exit_time"] + timedelta(hours=hours_13_to_14)
    b = _lockage(mmsi, "lock_14", direction, b_arr, b_arr + timedelta(hours=1))
    return [a, b]


def test_order_skips_lock_5a_and_links_neighbours():
    assert "lock_5a" not in ORDER
    assert T.next_lock(ORDER, "lock_5", "downbound") == "lock_6"
    assert T.next_lock(ORDER, "lock_14", "upbound") == "lock_13"
    assert T.previous_lock(ORDER, "lock_14", "downbound") == "lock_13"


def test_transit_times_learned_per_leg_and_size():
    rows = []
    for i, h in enumerate([4.0, 4.5, 5.0, 4.2, 4.8]):
        rows += _trip(f"V{i}", T0 + timedelta(days=i), h)
    rows += [_lockage("X", "lock_13", "downbound", T0, T0 + timedelta(hours=1)),
             _lockage("X", "lock_15", "downbound", T0 + timedelta(hours=9), T0 + timedelta(hours=10))]  # skipped a lock
    stats = T.transit_stats(T.transit_samples(rows, ORDER))
    leg = stats[("lock_13", "lock_14", "downbound")]
    assert leg["n"] == 5 and leg["median_h"] == 4.5
    assert ("lock_13", "lock_14", "downbound", "large") in stats
    assert ("lock_13", "lock_15", "downbound") not in stats      # not consecutive locks


def test_predicted_arrival_window_and_progress():
    rows = []
    for i, h in enumerate([4.0, 4.5, 5.0, 4.2, 4.8]):
        rows += _trip(f"V{i}", T0 + timedelta(days=i), h)
    stats = T.transit_stats(T.transit_samples(rows, ORDER))
    left = T0 + timedelta(days=10)
    recent = [_lockage("NEW", "lock_13", "downbound", left - timedelta(hours=1), left)]
    now = left + timedelta(hours=2)
    arr = T.predicted_arrivals("lock_14", ORDER, stats, recent, present=set(), now=now)
    assert len(arr) == 1 and arr[0]["mmsi"] == "NEW"
    assert arr[0]["eta"] == left + timedelta(hours=4.5) and not arr[0]["overdue"]
    assert 0.4 < arr[0]["progress"] < 0.5
    # Already in Lock 14's queue: not "approaching"
    assert T.predicted_arrivals("lock_14", ORDER, stats, recent, present={"NEW"}, now=now) == []
    # Long overdue (probably tied off): dropped
    assert T.predicted_arrivals("lock_14", ORDER, stats, recent, set(), now=left + timedelta(hours=12)) == []
    # Heading the other way: not approaching Lock 14 from 13
    up = [_lockage("UP", "lock_13", "upbound", left - timedelta(hours=1), left)]
    assert T.predicted_arrivals("lock_14", ORDER, stats, up, set(), now) == []


def test_two_hop_prediction_adds_time_at_the_lock_between():
    rows = []
    for i, h in enumerate([4.0, 4.5, 5.0, 4.2, 4.8]):
        day = T0 + timedelta(days=i)
        a = _lockage(f"V{i}", "lock_12", "downbound", day, day + timedelta(hours=1))
        b_arr = a["exit_time"] + timedelta(hours=3)
        b = _lockage(f"V{i}", "lock_13", "downbound", b_arr, b_arr + timedelta(hours=1))      # 1 h at Lock 13
        c_arr = b["exit_time"] + timedelta(hours=h)
        c = _lockage(f"V{i}", "lock_14", "downbound", c_arr, c_arr + timedelta(hours=1))
        rows += [a, b, c]
    stats = T.transit_stats(T.transit_samples(rows, ORDER))
    stats.update(T.dwell_stats(rows))
    assert stats[("dwell", "lock_13", "downbound")]["median_h"] == 1.0
    left = T0 + timedelta(days=10)
    recent = [_lockage("FAR", "lock_12", "downbound", left - timedelta(hours=1), left)]
    arr = T.predicted_arrivals("lock_14", ORDER, stats, recent, set(), now=left + timedelta(hours=1), max_hops=2)
    assert len(arr) == 1 and arr[0]["hops"] == 2 and arr[0]["via_lock"] == "lock_13"
    assert arr[0]["eta"] == left + timedelta(hours=3 + 1 + 4.5)            # leg + time at L13 + leg
    assert arr[0]["segment_from"] == "lock_12" and arr[0]["segment_to"] == "lock_13"
    later = T.predicted_arrivals("lock_14", ORDER, stats, recent, set(), now=left + timedelta(hours=5), max_hops=2)
    assert later[0]["segment_from"] == "lock_13" and later[0]["segment_to"] == "lock_14"
    one_hop_only = T.predicted_arrivals("lock_14", ORDER, stats, recent, set(), now=left)   # default
    assert one_hop_only == []
