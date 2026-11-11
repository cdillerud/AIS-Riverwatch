"""Learned per-lock "likely" ranges around the tow wait estimate."""
from services import calibration as C, lock_board as LB

RANGES = {"kind": "ratio", "p": [0.2, 0.8], "global": [0.5, 2.0], "locks": {"lock_25": [0.25, 4.0]}}


def test_range_widens_with_the_estimate_and_by_lock():
    assert LB.tow_range("lock_10", 50, RANGES) == [20, 110]       # (60*0.5-10, 60*2-10), river-wide band
    assert LB.tow_range("lock_25", 50, RANGES) == [5, 230]        # its own, wider band
    assert LB.tow_range("lock_10", 0, RANGES) == [0, 10]          # empty lock still gets a range
    assert LB.tow_range("lock_10", 50, {}) is None                # nothing learned yet
    # The range always contains the estimate itself.
    lo, hi = LB.tow_range("lock_10", 50, {"kind": "ratio", "global": [1.2, 1.5]})
    assert lo <= 50 <= hi


def test_fit_ranges_from_held_out_samples():
    model = {"tow": {"kind": "l1_features", "coef": {"intercept": 30.0}, "lock_effects": {}}}
    # Estimate is 30 for every sample; actual waits spread 0..190 at lock_a.
    samples = [{"lock_id": "lock_a", "recreational": False, "actual": float(a)} for a in range(0, 200, 10)]
    samples += [{"lock_id": "lock_b", "recreational": False, "actual": 30.0}] * 5     # too few for its own band
    samples += [{"lock_id": "lock_a", "recreational": True, "actual": 0.0}] * 50     # pleasure boats ignored
    r = C.fit_ranges(model, samples)
    assert r["kind"] == "ratio" and set(r["locks"]) == {"lock_a"}
    lo, hi = LB.tow_range("lock_a", 30, r)
    inside = sum(1 for s in samples if s["lock_id"] == "lock_a" and not s["recreational"] and lo <= s["actual"] <= hi)
    assert 10 <= inside <= 15                                    # about the middle 60% of 20
    assert LB.tow_range("lock_b", 30, r) is not None             # falls back to the river-wide band
    assert C.fit_ranges(model, samples[:3]) == {}
