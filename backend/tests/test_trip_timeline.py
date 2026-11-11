import asyncio

from services.trip_timeline import schedule


def run(coro):
    return asyncio.run(coro)


def test_time_at_each_lock_pushes_later_locks_back():
    calls = []

    async def wait_fn(lock_id, arrive):
        calls.append((lock_id, round(arrive)))
        return {"a": 10, "b": 30}[lock_id]

    legs = [{"lock_id": "a", "distance_mi": 12}, {"lock_id": "b", "distance_mi": 24}]
    out = run(schedule(legs, 12.0, wait_fn, lambda lid: 20))
    # a: 60 min travel, +10 wait +20 lock -> leave at 90
    assert out[0] == {"lock_id": "a", "arrive_minutes": 60, "wait_minutes": 10, "lockage_minutes": 20,
                      "depart_minutes": 90, "time_at_earlier_locks_minutes": 0}
    # b: 120 min more travel from a -> arrive 210 (not 180), the wait asked for that time
    assert out[1]["arrive_minutes"] == 210 and out[1]["depart_minutes"] == 260
    assert out[1]["time_at_earlier_locks_minutes"] == 30
    assert calls == [("a", 60), ("b", 210)]


def test_unknown_wait_counts_as_zero_and_stopped_boat_has_no_schedule():
    async def no_wait(lock_id, arrive):
        return None

    out = run(schedule([{"lock_id": "a", "distance_mi": 6}], 12.0, no_wait, lambda lid: 15))
    assert out[0]["wait_minutes"] == 0 and out[0]["depart_minutes"] == 45
    assert run(schedule([{"lock_id": "a", "distance_mi": 6}], 0, no_wait, lambda lid: 15)) == []
