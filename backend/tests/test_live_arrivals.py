from datetime import datetime, timedelta, timezone

from services.live_arrivals import merge_live_arrivals

NOW = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)
LOCKS = {"lock_2": 815.2, "lock_3": 796.9, "lock_4": 752.8}


def live(mmsi, rm, speed=0.0, heading=None, ship_type=31, age_min=1, name=None):
    return {"mmsi": mmsi, "name": name or f"V{mmsi}", "river_mile": rm, "speed": speed, "heading": heading,
            "ship_type": ship_type, "timestamp": NOW - timedelta(minutes=age_min)}


def pred(mmsi, eta_h=2.0, p=0.64):
    return {"vessel_name": f"P{mmsi}", "mmsi": mmsi, "direction": "upbound", "barges": 4,
            "eta": NOW + timedelta(hours=eta_h), "probability": p}


def test_unseen_prediction_is_kept():
    out = merge_live_arrivals("lock_3", LOCKS, [pred("1")], [], NOW)
    assert len(out) == 1 and out[0]["source"] == "usace_prediction" and out[0]["probability"] == 0.64


def test_prediction_seen_heading_here_gets_ais_eta_and_full_weight():
    out = merge_live_arrivals("lock_3", LOCKS, [pred("1")], [live("1", 786.9, speed=5, heading="northbound")], NOW)
    assert len(out) == 1 and out[0]["source"] == "ais" and out[0]["probability"] == 1.0
    assert out[0]["barges"] == 4   # kept from USACE
    expected = NOW + timedelta(hours=10 / (5 * 1.15078))
    assert abs((out[0]["eta"] - expected).total_seconds()) < 1


def test_prediction_seen_tied_off_is_dropped():
    out = merge_live_arrivals("lock_3", LOCKS, [pred("1")], [live("1", 770.0, speed=0)], NOW)
    assert out == []


def test_prediction_seen_stopped_near_lock_arrives_now():
    out = merge_live_arrivals("lock_3", LOCKS, [pred("1")], [live("1", 795.0, speed=0)], NOW)
    assert len(out) == 1 and out[0]["eta"] == NOW and out[0]["source"] == "ais"


def test_ais_only_tow_heading_here_is_added():
    out = merge_live_arrivals("lock_2", LOCKS, [], [live("9", 823.0, speed=4, heading="southbound")], NOW,
                              barges_by_mmsi={"9": 15})
    assert len(out) == 1 and out[0]["mmsi"] == "9" and out[0]["barges"] == 15 and out[0]["direction"] == "downbound"


def test_ignored_boats():
    boats = [
        live("own", 823.0, speed=4, heading="southbound"),              # the user's boat
        live("rec", 823.0, speed=4, heading="southbound", ship_type=37),  # pleasure craft
        live("old", 823.0, speed=4, heading="southbound", age_min=30),   # stale position
        live("away", 823.0, speed=4, heading="northbound"),             # heading away
        live("past", 790.0, speed=4, heading="northbound"),             # lock 3 is in between
        live("stop", 816.0, speed=0),                                    # stopped, not predicted: may be moored
        live("q", 820.0, speed=4, heading="southbound"),                # USACE already has it at the lock
    ]
    out = merge_live_arrivals("lock_2", LOCKS, [], boats, NOW, own_mmsi="own", at_lock=["q"])
    assert out == []


def test_sorted_by_eta():
    boats = [live("far", 835.0, speed=5, heading="southbound"), live("near", 818.0, speed=5, heading="southbound")]
    out = merge_live_arrivals("lock_2", LOCKS, [pred("x", eta_h=0.1)], boats, NOW)
    assert [a["mmsi"] for a in out] == ["x", "near", "far"]


def test_ais_arrival_ahead_counts_even_close_in():
    from services import lock_board
    typical = {"avg_single_lockage_minutes": 30, "avg_double_lockage_minutes": 90, "sample_count": 50,
               "is_baseline": False}
    arrive = NOW + timedelta(minutes=60)
    empty = lock_board.predict_waits_at("lock_2", [], [], [], typical, arrive, NOW, direction="downbound")
    tow_in = [{"vessel_name": "T", "mmsi": "9", "barges": 15, "direction": "upbound", "probability": 1.0,
               "source": "ais", "eta": NOW + timedelta(minutes=50)}]
    busy = lock_board.predict_waits_at("lock_2", [], [], tow_in, typical, arrive, NOW, direction="downbound")
    assert busy["recreational"] > empty["recreational"]
    assert busy["tow"] > empty["tow"]
    assert busy["ahead"][0]["source"] == "ais" and busy["ahead"][0]["eta"].startswith("2026-11-10T20:50")


def test_boat_at_lock_matched_by_name_when_usace_mmsi_differs():
    # USACE lists MARGIT B under an old MMSI; AIS broadcasts another
    boats = [live("366975420", 820.0, speed=4, heading="southbound", name="MARGIT B")]
    out = merge_live_arrivals("lock_2", LOCKS, [], boats, NOW, at_lock=["368371860", "MARGIT B"])
    assert out == []
