"""Published high-water limits for each Upper Mississippi lock, as data.

Every number here was copied from a USACE page (`source_url`) on `checked`.
Re-check with `python backend/scripts/check_lock_limits.py`, which re-scrapes
the district pages and prints any differences (services/lock_limits.py has
the parsers).

Units and gauges - a limit is only ever compared with a reading of the same
quantity at the same place (see services/lock_limits.py):

* St. Paul District (Locks 1-10): flows in cfs and pool elevations in feet
  MSL 1912, from the district's "Flow and elevation thresholds" table. The
  district points to water.usace.army.mil for current values; those are the
  district's own CWMS series at each dam (`cwms_flow`, `cwms_pool`): outflow
  in cfs and headwater (pool) elevation in ft MSL 1912.
* Rock Island District (Locks 11-22): "Closure Stage" in feet on the lock's
  TAILWATER gauge. The current status page does not say which gauge; the
  district's High Water Lock Information page (archived 2013) lists the same
  values as "STOP Navigation at 14.0 TW" etc., and the lock operators' notes in
  the USACE Lock Status Report quote these stages as "tail stage". Current
  readings come from the district's CWMS tailwater-stage series
  (`cwms_tail`), which match the lock's LPMS lower-gage reading and the NWS
  gauge at the lock. Lock 19 publishes only tailwater ELEVATION, not stage, so
  its limit is reference-only.
* St. Louis District (Locks 24-27): its "Operation Limits" page lists pool
  regulation (hinge-point) limits, not closure limits; nothing is compared.
"""

CHECKED = "2026-11-12"

MVP_URL = "https://www.mvp.usace.army.mil/Missions/Navigation/Locks-Dams/"
MVR_URL = "https://www.mvr.usace.army.mil/missions/navigation/lock-status/"
MVR_TW_URL = "http://web.archive.org/web/20130214190838/http://www2.mvr.usace.army.mil/NIC2/highwater.cfm"
MVS_URL = "https://www.mvs.usace.army.mil/Missions/Navigation/Locks-and-Dams/Operation-Limits/"
MPLS_REC_URL = "https://www.mvp.usace.army.mil/Media/News-Releases/"

ST_PAUL = "USACE St. Paul District"
ROCK_ISLAND = "USACE Rock Island District"
ST_LOUIS = "USACE St. Louis District"


def _mvp(cwms: str, outdraft, gates_pulled, closed_cfs, closed_pool, **extra):
    d = {
        "district": ST_PAUL,
        "source_url": MVP_URL,
        "checked": CHECKED,
        "outdraft_cfs": outdraft,          # int, or text when not a flow ("0.2' over dam")
        "gates_pulled_cfs": gates_pulled,  # None where the table says N/A
        "closed_cfs": closed_cfs,
        "closed_pool_ft": closed_pool,     # ft MSL 1912, pool (headwater) at the dam
        "cwms_office": "MVP",
        "cwms_flow": f"{cwms}.Flow-Out.Inst.~15Minutes.0.best",
        "cwms_pool": f"{cwms}.Elev.Inst.~15Minutes.0.best-MSL1912",
    }
    d.update(extra)
    return d


def _mvr(n: int, flood_stage, closure_stage, *, stage_series=True, **extra):
    d = {
        "district": ROCK_ISLAND,
        "source_url": MVR_URL,
        "gauge_source_url": MVR_TW_URL,
        "checked": CHECKED,
        "flood_stage_ft": flood_stage,
        "closure_stage_ft": closure_stage,  # tailwater stage, ft
        "cwms_office": "MVR",
        "cwms_tail": f"MI{n}.Stage-Tail.Inst.30Minutes.0.rev" if stage_series else None,
    }
    d.update(extra)
    return d


LOCK_LIMITS = {
    # LSAF / Upper St. Anthony Falls are not River Watch locks (LSAF: outdraft
    # 20,000, gates pulled 50,000, closed 40,000 cfs / 731.60 ft).
    "lock_1": _mvp(
        "LockDam_01", "0.2' over dam", None, 40_000, 729.40,
        # LSAF and Lock 1 close to recreational boats above 30,000 cfs
        # (St. Paul District news releases; archived MVR high-water table:
        # "STOP Navigation at 30,000 CFS (pleasure craft)").
        rec_closed_cfs=30_000, rec_source_url=MPLS_REC_URL,
    ),
    "lock_2": _mvp("LockDam_02", 31_000, 61_000, 116_000, 692.00),
    # *** outdraft value "has not been re-evaluated since construction was
    # completed to reduce outdraft"
    "lock_3": _mvp("LockDam_03", 21_000, 36_000, 125_000, 683.00),
    "lock_4": _mvp("LockDam_04", 60_000, 89_000, 160_000, 671.50),
    "lock_5": _mvp("LockDam_05", 70_000, 116_000, 188_000, 664.50),
    "lock_5a": _mvp("LockDam_05a", 32_000, 57_000, 183_000, 660.00),
    "lock_6": _mvp("LockDam_06", 44_600, 76_000, 200_000, 651.50),
    "lock_7": _mvp("LockDam_07", 44_000, 82_000, 235_000, 646.50),
    "lock_8": _mvp("LockDam_08", 40_200, 96_000, 225_000, 636.00),
    "lock_9": _mvp("LockDam_09", 55_000, 64_000, 220_000, 631.00),
    "lock_10": _mvp("LockDam_10", 47_000, 73_000, 238_000, 621.00),

    "lock_11": _mvr(11, 16.0, 20.8),
    "lock_12": _mvr(12, 17.0, 18.4),
    "lock_13": _mvr(13, 16.0, 19.0),
    "lock_14": _mvr(14, 11.0, 14.0, aux_closure_stage_ft=10.0),
    "lock_15": _mvr(15, 15.0, 20.0, aux_closure_stage_ft=13.0),
    "lock_16": _mvr(16, 15.0, 17.0),
    "lock_17": _mvr(17, 15.0, 18.1),
    "lock_18": _mvr(18, 10.0, 14.9),
    "lock_19": _mvr(19, 16.0, 21.2, stage_series=False),
    "lock_20": _mvr(20, 14.0, 18.0),
    "lock_21": _mvr(21, 17.0, 21.9),
    "lock_22": _mvr(22, 16.0, 21.4),

    "lock_24": {"district": ST_LOUIS, "source_url": MVS_URL, "checked": CHECKED, "none_published": True},
    "lock_25": {"district": ST_LOUIS, "source_url": MVS_URL, "checked": CHECKED, "none_published": True},
    "melvin_price": {"district": ST_LOUIS, "source_url": MVS_URL, "checked": CHECKED, "none_published": True},
    "chain_of_rocks": {"district": ST_LOUIS, "source_url": MVS_URL, "checked": CHECKED, "none_published": True},
}
