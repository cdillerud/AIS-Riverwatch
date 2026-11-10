"""Wait-model learning: adopt a refit only when it is better and sane."""
import random
from datetime import datetime, timedelta, timezone

from services import calibration as C

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _samples(n=3000, intercept=27.0, slope=1.25, seed=7):
    """Samples where real tow waits follow intercept + slope * raw queue estimate."""
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        busy = i % 2 == 0
        v0 = rnd.uniform(20, 240) if busy else 0.0
        actual = intercept + slope * v0 + rnd.gauss(0, 15) if busy else max(0.0, rnd.gauss(10, 5))
        out.append({"lock_id": "lock_14", "train": i < n * 2 // 3, "actual": actual, "recreational": False,
                    "queue": 1 if busy else 0, "locking": 0, "v0": v0, "v1": v0, "v2": v0, "lock_median": 30.0,
                    "n_same": 1.0 if busy else 0.0, "n_opp": 0.0, "dbl": 0.0, "lk_rem": 0.0,
                    "own_double": 0.0, "empty": 0.0 if busy else 1.0})
    return out


def _run(monkeypatch, current, samples):
    monkeypatch.setattr(C, "build_samples", lambda rows, split: samples)
    rows = [{"arrival_time": T0}, {"arrival_time": T0 + timedelta(days=30)}]
    return C.recalibrate(rows, current)


BAD = {"tow": {"intercept": 0.0, "slope": 0.4, "empty_lock": 60.0}, "recreational": {"intercept": 5.0, "slope": 0.1}}


def test_refit_adopted_when_clearly_better(monkeypatch):
    report = _run(monkeypatch, BAD, _samples())
    assert report["adopt"] is True, report["reason"]
    assert abs(report["model"]["tow"]["coef"]["v0"] - 1.25) < 0.2
    assert report["new_score"]["all"]["mae"] < report["current_score"]["all"]["mae"]


def test_refit_rejected_when_not_meaningfully_better(monkeypatch):
    samples = _samples()
    first = _run(monkeypatch, BAD, samples)
    again = _run(monkeypatch, first["model"], samples)
    assert again["adopt"] is False and "no improvement" in again["reason"]


def test_not_enough_history(monkeypatch):
    report = _run(monkeypatch, BAD, _samples(n=300))
    assert report["adopt"] is False and "not enough samples" in report["reason"]


def test_out_of_bounds_fit_is_rejected(monkeypatch):
    report = _run(monkeypatch, BAD, _samples(slope=5.0))
    assert report["adopt"] is False and "tow.v0" in report["reason"]
