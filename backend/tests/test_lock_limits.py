"""Lock closures (NDC stoppages, Rock Island page) and high-water limits."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services import lock_limits as ll
from services.lock_limits_data import LOCK_LIMITS

FIX = Path(__file__).parent / "fixtures" / "lock_limits"
NOW = datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)


server = pytest.importorskip("server")
_match = server.match_lock_name


def _stop(lock, begin, end=" CST", chamber="1", stopped="Y", reason="Maintaining lock or lock equipment", river="MI"):
    return {"eroc": "B3", "riverCode": river, "lockNumber": lock, "chamberNumber": chamber,
            "beginStopDate": begin, "endStopDate": end, "isScheduled": "Yes", "reasonCode": reason,
            "trafficStopped": stopped}


# --- NDC stoppage feed ------------------------------------------------------
def test_real_feed_without_mississippi_rows_changes_nothing():
    rows = json.loads((FIX / "ndc_stall_stoppage.json").read_text())
    assert rows and all(r["riverCode"] != "MI" or r["lockNumber"] in ("51", "52") for r in rows)
    assert ll.stoppage_effects(rows, NOW) == {}


def test_parse_lpms_time():
    assert ll.parse_lpms_time("11/09/2026 10:09:00 CST") == datetime(2026, 11, 9, 16, 9, tzinfo=timezone.utc)
    assert ll.parse_lpms_time("06/10/2026 10:00:00 CDT") == datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
    assert ll.parse_lpms_time(" CST") is None
    assert ll.parse_lpms_time(None) is None


def test_active_main_chamber_stoppage_closes_lock():
    rows = [_stop("08", "11/12/2026 07:00:00 CST", "11/14/2026 17:00:00 CST", reason="Repairing lock or lock hardware")]
    eff = ll.stoppage_effects(rows, NOW)
    assert eff["lock_8"]["status"] == "CLOSED"
    assert eff["lock_8"]["closure_info"] == "Closed by USACE: repairing lock or lock hardware, until Nov 14 5:00 PM CST"


def test_open_ended_stoppage_and_lpms_lock_codes():
    rows = [_stop("55", "11/01/2026 00:00:00 CST"), _stop("26", "11/12/2026 08:00:00 CST"),
            _stop("27", "11/12/2026 08:00:00 CST"), _stop("51", "11/01/2026 00:00:00 CST")]
    eff = ll.stoppage_effects(rows, NOW)
    assert set(eff) == {"lock_5a", "melvin_price", "chain_of_rocks"}   # 51 = Upper St. Anthony Falls
    assert eff["lock_5a"]["closure_info"].endswith("until further notice")


def test_auxiliary_chamber_or_stall_is_restricted_not_closed():
    eff = ll.stoppage_effects([_stop("26", "11/12/2026 08:00:00 CST", chamber="2")], NOW)
    assert eff["melvin_price"]["status"] == "RESTRICTED"
    assert eff["melvin_price"]["closure_info"].startswith("Auxiliary chamber closed by USACE")
    eff = ll.stoppage_effects([_stop("15", "11/12/2026 08:00:00 CST", stopped="N", reason="Debris")], NOW)
    assert eff["lock_15"]["status"] == "RESTRICTED"


def test_closed_wins_over_restricted():
    rows = [_stop("27", "11/12/2026 08:00:00 CST", chamber="2"), _stop("27", "11/12/2026 09:00:00 CST")]
    assert ll.stoppage_effects(rows, NOW)["chain_of_rocks"]["status"] == "CLOSED"


def test_finished_and_other_river_stoppages_are_ignored():
    rows = [_stop("08", "11/10/2026 07:00:00 CST", "11/12/2026 07:00:00 CST"),
            _stop("08", "11/12/2026 07:00:00 CST", river="OH")]
    assert ll.stoppage_effects(rows, NOW) == {}


def test_scheduled_closure_is_a_note_only():
    rows = [_stop("13", "11/13/2026 07:00:00 CST", "11/13/2026 19:00:00 CST")]
    eff = ll.stoppage_effects(rows, NOW)
    assert eff["lock_13"]["status"] is None
    assert eff["lock_13"]["upcoming"] == ("USACE scheduled closure Nov 13 7:00 AM CST - Nov 13 7:00 PM CST: "
                                          "maintaining lock or lock equipment")
    # more than 48 h ahead: nothing yet
    assert ll.stoppage_effects([_stop("13", "11/20/2026 07:00:00 CST")], NOW) == {}


def test_stale_stoppage_feed_is_ignored():
    ll.set_stoppages([_stop("08", "11/12/2026 07:00:00 CST")], at=NOW - timedelta(hours=2))
    assert ll.current_stoppage_effects(NOW) == {}
    ll.set_stoppages([_stop("08", "11/12/2026 07:00:00 CST")], at=NOW - timedelta(minutes=10))
    assert ll.current_stoppage_effects(NOW)["lock_8"]["status"] == "CLOSED"
    ll.set_stoppages(None, at=None)


# --- Rock Island status page ------------------------------------------------
def test_mvr_page_older_than_two_weeks_is_ignored():
    html = (FIX / "mvr_lock_status.html").read_text(encoding="utf-8")
    assert ll.mvr_page_updated(html).isoformat() == "2026-09-30"
    assert ll.parse_mvr_status(html, _match, NOW) == {}


def test_mvr_aux_row_does_not_close_main_lock():
    html = (FIX / "mvr_lock_status.html").read_text(encoding="utf-8")
    fresh = datetime(2026, 10, 2, tzinfo=timezone.utc)
    st = ll.parse_mvr_status(html, _match, fresh)
    assert st["lock_14"] == {"status": "OPEN", "closure_info": "Auxiliary lock closed (USACE Rock Island District)"}
    assert st["lock_11"]["status"] == "OPEN" and st["lock_22"]["status"] == "OPEN"
    assert "lock_24" not in st


# --- Published limits (re-scrape) -------------------------------------------
def test_mvp_table_matches_stored_limits():
    scraped = ll.parse_mvp_limits((FIX / "mvp_locks_dams.html").read_text(encoding="utf-8"))
    assert scraped["lock_2"] == {"outdraft_cfs": 31000, "gates_pulled_cfs": 61000, "closed_cfs": 116000,
                                 "closed_pool_ft": 692.0}
    assert scraped["lock_1"]["outdraft_cfs"] == "0.2' over dam" and scraped["lock_1"]["gates_pulled_cfs"] is None
    assert scraped["lock_3"]["outdraft_cfs"] == 21000          # "21,000***"
    assert "lock_5a" in scraped and "lsaf" in scraped
    assert ll.diff_limits(scraped) == []


def test_mvr_table_matches_stored_limits():
    scraped = ll.parse_mvr_limits((FIX / "mvr_lock_status.html").read_text(encoding="utf-8"), _match)
    assert scraped["lock_14"] == {"flood_stage_ft": 11.0, "closure_stage_ft": 14.0, "aux_closure_stage_ft": 10.0}
    assert ll.diff_limits(scraped) == []


def test_diff_reports_a_changed_limit():
    assert ll.diff_limits({"lock_2": {"closed_cfs": 120000}}) == ["lock_2.closed_cfs: stored 116000, page now 120000"]


def test_every_lock_has_limits_with_a_source():
    from config import LOCKS
    assert set(LOCK_LIMITS) == set(LOCKS)
    for lim in LOCK_LIMITS.values():
        assert lim["source_url"].startswith("http") and lim["checked"]


# --- Readings and the comparison ---------------------------------------------
def test_cwms_latest_and_trend():
    payload = json.loads((FIX / "cwms_ld02_flow.json").read_text())
    r = ll.cwms_latest(payload, NOW)
    assert round(r["value"]) == 23081 and r["at"].startswith("2026-11-13T02:15")
    assert r["change_6h"] < 0
    assert ll.cwms_latest(payload, NOW + timedelta(hours=12)) is None   # stale
    assert ll.cwms_latest({"values": []}, NOW) is None


def _r(value, change=0.0):
    return {"value": value, "at": NOW.isoformat(), "units": "x", "change_6h": change}


def test_st_paul_flow_and_pool_comparison():
    a = ll.assess("lock_2", {"flow": _r(83_520, 5000), "pool": _r(686.5)})
    flow, pool = a["comparisons"]
    assert flow["text"] == "River at 72% of the flow that closes this lock (116,000 cfs) - rising"
    assert "LockDam_02.Flow-Out" in flow["gauge"]
    assert pool["text"] == "Pool at 686.5 ft, 5.5 ft below the level that closes this lock (692.0 ft) - steady"
    assert a["note"] is None
    assert any("Outdraft warning from 31,000 cfs" in r for r in a["references"])


def test_note_only_at_80_percent_or_when_restricted():
    a = ll.assess("lock_2", {"flow": _r(95_000, -3000)})
    assert a["note"] == ("River at 82% of the flow that closes this lock (116,000 cfs) - falling "
                         "(USACE St. Paul District)")
    assert ll.assess("lock_2", {"flow": _r(50_000)})["note"] is None
    assert ll.assess("lock_2", {"flow": _r(50_000)}, district_restricted=True)["note"].startswith("River at 43%")


def test_pool_near_closure_elevation_gets_a_note():
    a = ll.assess("lock_4", {"pool": _r(670.3, 0.6)})
    assert a["note"].startswith("Pool at 670.3 ft, 1.2 ft below the level that closes this lock (671.5 ft) - rising")


def test_lock_1_uses_recreational_limit():
    a = ll.assess("lock_1", {"flow": _r(27_000, 1500)})
    assert a["comparisons"][0]["text"] == ("River at 90% of the flow that closes this lock to recreational boats "
                                           "(30,000 cfs) - rising")
    assert a["note"].startswith("River at 90% of the flow that closes this lock to recreational boats")


def test_missing_reading_falls_back_to_reference_text():
    a = ll.assess("lock_2", {})
    assert a["comparisons"] == [] and a["note"] is None
    assert "Closes this lock at 116,000 cfs (USACE St. Paul District)" in a["references"]
    assert "Closes to navigation at pool elevation 692.00 ft MSL 1912 (USACE St. Paul District)" in a["references"]


def test_rock_island_tailwater_comparison():
    a = ll.assess("lock_14", {"tail": _r(11.4, 0.5)})
    c = a["comparisons"][0]
    assert c["text"] == "Tailwater at 11.4 ft, 81% of the stage that closes this lock (14.0 ft) - rising"
    assert a["note"].endswith("(USACE Rock Island District)")
    assert "Auxiliary lock closes at 10.0 ft tailwater" in a["references"]


def test_lock_19_is_reference_only():
    # Lock 19 has no tailwater STAGE series - never compare an elevation with a stage
    a = ll.assess("lock_19", {"tail": _r(485.9)})
    assert a["comparisons"] == []
    assert a["references"][0] == "Closes to navigation at 21.2 ft on the tailwater gauge (USACE Rock Island District)"


def test_st_louis_publishes_no_closure_level():
    a = ll.assess("melvin_price", {"flow": _r(400_000)})
    assert a["comparisons"] == [] and a["note"] is None
    assert "publishes no closure level" in a["references"][0]


def test_unknown_lock():
    assert ll.assess("lock_99")["comparisons"] == []
