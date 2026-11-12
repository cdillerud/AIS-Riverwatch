"""Departure options for a stopped boat: the trip schedule for each departure time."""
import asyncio

from services import trip_timeline as T

LEGS = [{"lock_id": "lock_2", "distance_mi": 15.0}, {"lock_id": "lock_3", "distance_mi": 18.0}]


def test_later_departure_avoids_a_tow():
    # A tow is at lock_2 between 60 and 120 min from now: 40 min wait then.
    async def wait_fn(lid, minutes_from_now):
        return 40.0 if lid == "lock_2" and 60 <= minutes_from_now < 120 else 1.0

    opts = asyncio.run(T.departure_options(LEGS, 15.0, [0, 30, 120], wait_fn, lambda lid: 20.0, tail_mi=3.0))
    now, half, later = opts
    # Leave now: reach L2 at 60 min -> 40 min wait.
    assert now["locks"][0]["arrive_minutes"] == 60 and now["locks"][0]["wait_minutes"] == 40
    assert half["lock_wait_minutes"] == 41 and later["lock_wait_minutes"] == 2
    # Trip time is the same schedule shifted; finish counts the departure delay and the tail.
    assert later["trip_minutes"] == 60 + 1 + 20 + 72 + 1 + 20 + 12
    assert later["finish_in_minutes"] == 120 + later["trip_minutes"]
    assert now["time_at_locks_minutes"] == 40 + 20 + 1 + 20


def test_no_speed_no_options():
    async def wait_fn(lid, m):
        return 0.0
    assert asyncio.run(T.departure_options(LEGS, 0, [0], wait_fn, lambda lid: 20.0)) == []
