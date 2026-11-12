"""Learned lockage minutes / double chance by barge count (lock_board)."""
from services import lock_board as LB


def _tow(barges, minutes, cuts=1, lock="lock_7"):
    return {"lock_id": lock, "is_tow": True, "barge_count": barges, "lockage_duration_minutes": minutes, "cuts": cuts}


def test_river_stats_and_shrinkage():
    river_rows = [_tow(4, 30.0, lock="lock_x")] * 20 + [_tow(15, 120.0, 2, lock="lock_x")] * 20
    river = LB.river_barge_stats(river_rows + [{"is_tow": False, "lockage_duration_minutes": 10}])
    assert river[4] == {"minutes": 30.0, "double_share": 0.0, "n": 20}
    assert river[15]["double_share"] == 1.0
    # This lock locks 4-barge tows with the boat separate (2 cuts, ~90 min).
    own = [_tow(4, 90.0, 2)] * 15
    table = LB.lock_barge_table(own, river, k=5)
    assert table[4]["n"] == 15
    assert table[4]["minutes"] == 75.0              # (90*15 + 30*5) / 20
    assert table[4]["double_share"] == 0.75         # (1*15 + 0*5) / 20
    assert table[15]["n"] == 0 and table[15]["minutes"] == 120.0   # no own data: river-wide


def test_expected_minutes_and_double_chance_use_the_table():
    typical = {"avg_single_lockage_minutes": 30.0, "avg_double_lockage_minutes": 110.0,
               "by_barges": {"4": {"minutes": 88.0, "double_share": 0.8, "n": 30}}}   # JSON string keys
    assert LB.expected_lockage_minutes("lock_7", 4, typical) == 88.0
    assert LB.double_chance("lock_7", 4, typical) == 0.8
    # Sizes the table hasn't seen fall back to the rule.
    assert LB.expected_lockage_minutes("lock_7", 15, typical) == 110.0
    assert LB.double_chance("lock_7", 15, typical) == 1.0
    assert LB.double_chance("lock_7", 6, {}) == 0.0
    assert LB.double_chance("lock_19", 15, {}) == 0.0                 # 1,200 ft chamber
    # Pleasure boats / light boats are not tows: table not used.
    assert LB.expected_lockage_minutes("lock_7", 0, typical) == 20.0


def test_queue_features_count_doubles_fractionally():
    typical = {"by_barges": {4: {"minutes": 88.0, "double_share": 0.5, "n": 30},
                             15: {"minutes": 120.0, "double_share": 1.0, "n": 30}}}
    waiting = [{"barges": 4, "direction": "upbound"}, {"barges": 15, "direction": "downbound"}]
    f = LB.queue_features("lock_7", [], waiting, typical, "upbound", 208.0, 0.0)
    assert f["dbl"] == 1.5 and f["n_same"] == 1 and f["n_opp"] == 1
    assert LB.estimate_wait("lock_7", [], waiting, typical) == 208.0
