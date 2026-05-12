# River Watch Backend - Lock Water Station Catalog
#
# Defines, for every Upper Mississippi lock:
#   - official_station: the authoritative gauge tied to that specific lock,
#     including flood-category thresholds and datum.
#   - reference_stations: nearby USGS gauges that can be displayed as
#     supporting data. Their thresholds (if any) must NOT be applied to
#     the lock's status. They live on different gage zeros and the
#     comparison would be wrong.
#
# Threshold sources are cited explicitly via `threshold_source` so the
# debug endpoint can return provenance.
#
# Stations:
#   - source = "USGS": real-time JSON via waterservices.usgs.gov
#   - source = "NWS":  hydrograph_to_xml.php via water.weather.gov
#   - source = "USACE": real-time series via NDC/RM/USACE feeds (not yet wired)
#
# If `thresholds` is None we render "Flood category not defined for this gauge"
# in the UI rather than forcing a status.

from typing import Dict, List, Optional, TypedDict


class StationDef(TypedDict, total=False):
    station_id: str
    station_name: str
    source: str            # "USGS" | "NWS" | "USACE"
    river_mile: Optional[float]
    measurement_type: str  # "gage_height" | "river_stage" | "pool_elevation"
    units: str             # "ft" | "ft NAVD88" | etc.
    datum: Optional[str]
    data_url: Optional[str]
    source_url: Optional[str]
    thresholds: Optional[Dict[str, float]]
    threshold_source: Optional[str]
    note: Optional[str]


def _usgs(site_id: str, name: str, river_mile: float, *, thresholds=None, threshold_source=None, datum="USGS gage zero (NGVD29 unless otherwise stated)") -> StationDef:
    return {
        "station_id": site_id,
        "station_name": name,
        "source": "USGS",
        "river_mile": river_mile,
        "measurement_type": "gage_height",
        "units": "ft",
        "datum": datum,
        "data_url": f"https://waterservices.usgs.gov/nwis/iv/?format=json&sites={site_id}&parameterCd=00065,00060,00010&siteStatus=active",
        "source_url": f"https://waterdata.usgs.gov/monitoring-location/{site_id}/",
        "thresholds": thresholds,
        "threshold_source": threshold_source,
    }


def _nws(nws_id: str, name: str, river_mile: float, *, datum: str, thresholds, threshold_source: str) -> StationDef:
    return {
        "station_id": nws_id,
        "station_name": name,
        "source": "NWS",
        "river_mile": river_mile,
        "measurement_type": "river_stage",
        "units": "ft",
        "datum": datum,
        "data_url": f"https://water.weather.gov/ahps2/hydrograph_to_xml.php?gage={nws_id}&output=xml",
        "source_url": f"https://water.weather.gov/ahps2/hydrograph.php?gage={nws_id}",
        "thresholds": thresholds,
        "threshold_source": threshold_source,
    }


# Standard NWS thresholds for the major Upper Mississippi NWS forecast points.
# Source: NOAA AHPS pages for each gauge.
NWS_THRESHOLDS = {
    "STPM5": {"action": 10.0, "flood": 14.0, "moderate": 17.0, "major": 20.0,
              "source": "NWS/NOAA AHPS - St. Paul (STPM5)"},
    "HSTM5": {"action": 13.0, "flood": 15.0, "moderate": 17.0, "major": 18.0,
              "source": "NWS/NOAA AHPS - Hastings (HSTM5)"},
    "PREW3": {"action": 12.0, "flood": 16.0, "moderate": 18.0, "major": 21.0,
              "source": "NWS/NOAA AHPS - Prescott (PREW3)"},
    "WINM5": {"action": 9.0, "flood": 13.0, "moderate": 15.0, "major": 18.0,
              "source": "NWS/NOAA AHPS - Winona (WINM5)"},
    "MCGI4": {"action": 14.0, "flood": 18.0, "moderate": 21.0, "major": 24.0,
              "source": "NWS/NOAA AHPS - McGregor (MCGI4)"},
    "CLNI4": {"action": 16.0, "flood": 20.0, "moderate": 22.0, "major": 25.0,
              "source": "NWS/NOAA AHPS - Clinton (CLNI4)"},
    "KEOI4": {"action": 12.0, "flood": 16.0, "moderate": 18.0, "major": 21.0,
              "source": "NWS/NOAA AHPS - Keokuk (KEOI4)"},
    "GRFI2": {"action": 21.0, "flood": 25.0, "moderate": 28.0, "major": 31.0,
              "source": "NWS/NOAA AHPS - Grafton (GRFI2)"},
    "EADM7": {"action": 28.0, "flood": 30.0, "moderate": 35.0, "major": 40.0,
              "source": "NWS/NOAA AHPS - St. Louis Eads Bridge (EADM7)"},
}


def _by_nws_thresh(key: str):
    t = NWS_THRESHOLDS[key]
    return {"action": t["action"], "flood": t["flood"], "moderate": t["moderate"], "major": t["major"]}, t["source"]


def _t_st_paul(): return _by_nws_thresh("STPM5")
def _t_hastings(): return _by_nws_thresh("HSTM5")
def _t_prescott(): return _by_nws_thresh("PREW3")
def _t_winona(): return _by_nws_thresh("WINM5")
def _t_mcgregor(): return _by_nws_thresh("MCGI4")
def _t_clinton(): return _by_nws_thresh("CLNI4")
def _t_keokuk(): return _by_nws_thresh("KEOI4")
def _t_grafton(): return _by_nws_thresh("GRFI2")
def _t_eads(): return _by_nws_thresh("EADM7")


# Per-lock station configuration.
# When in doubt for a given lock we keep the closest USGS gauge as the
# "official" data feed but mark thresholds as None so the UI displays a
# "Flood category not defined for this gauge" notice instead of forcing
# a status with mismatched thresholds.
LOCK_STATIONS: Dict[str, Dict] = {

    # --- Pool 1 -----------------------------------------------------------
    "lock_1": {
        "official_station": _usgs(
            "05331000",
            "Mississippi River at St. Paul, MN",
            839.3,
            thresholds=_t_st_paul()[0],
            threshold_source=_t_st_paul()[1],
            datum="USGS gage zero 687.85 ft NGVD29 (St. Paul)",
        ),
        "reference_stations": [],
        "selection_reason": "Closest active USGS real-time gauge; NWS thresholds for St. Paul (STPM5) align with USGS 05331000.",
    },

    # --- Pool 2  -- the case the user verified ----------------------------
    "lock_2": {
        "official_station": _nws(
            "HSTM5",
            "Mississippi River below L&D 2 at Hastings, MN",
            815.2,
            datum="USACE Gage Zero 600.00 ft 1912 MSL (NGVD29)",
            thresholds=_t_hastings()[0],
            threshold_source=_t_hastings()[1],
        ),
        "reference_stations": [
            {
                **_usgs(
                    "05344500",
                    "Mississippi River at Prescott, WI",
                    811.0,
                    thresholds=None,
                    threshold_source=None,
                    datum="USGS gage zero 650.00 ft NGVD29 (Prescott)",
                ),
                "note": "Nearby downstream gauge, ~4 mi below L&D 2. Different datum (650 ft vs. 600 ft) - do NOT compare its stage values to Hastings thresholds.",
            }
        ],
        "selection_reason": "L&D 2 has its own NWS forecast point (HSTM5) with USACE-defined gage zero. Prescott is retained as a reference only.",
    },

    # --- Pool 3 (Red Wing) ------------------------------------------------
    "lock_3": {
        "official_station": _usgs(
            "05344500",
            "Mississippi River at Prescott, WI",
            811.0,
            thresholds=_t_prescott()[0],
            threshold_source=_t_prescott()[1],
            datum="USGS gage zero 650.00 ft NGVD29 (Prescott)",
        ),
        "reference_stations": [],
        "selection_reason": "Closest USGS real-time gauge upstream of L&D 3; thresholds match NWS Prescott (PREW3).",
    },

    # --- Locks 4-7 (Winona) ----------------------------------------------
    "lock_4": {
        "official_station": _usgs(
            "05378500",
            "Mississippi River at Winona, MN",
            725.7,
            thresholds=_t_winona()[0],
            threshold_source=_t_winona()[1],
            datum="USGS gage zero NGVD29 (Winona)",
        ),
        "reference_stations": [],
        "selection_reason": "Nearest USGS real-time gauge. NWS Winona thresholds applied because the gauges share the WINM5 forecast point.",
    },
    "lock_5": {
        "official_station": _usgs(
            "05378500",
            "Mississippi River at Winona, MN",
            725.7,
            thresholds=None,
            threshold_source=None,
            datum="USGS gage zero NGVD29 (Winona)",
        ),
        "reference_stations": [],
        "selection_reason": "Winona is the closest USGS real-time gauge but is ~12 mi below L&D 5 and on a different pool; thresholds intentionally left undefined for this lock.",
    },
    "lock_5a": {
        "official_station": _usgs(
            "05378500",
            "Mississippi River at Winona, MN",
            725.7,
            thresholds=None,
            threshold_source=None,
            datum="USGS gage zero NGVD29 (Winona)",
        ),
        "reference_stations": [],
        "selection_reason": "Same caveat as L&D 5 - Winona is nearby but distinct pool.",
    },
    "lock_6": {
        "official_station": _usgs(
            "05378500",
            "Mississippi River at Winona, MN",
            725.7,
            thresholds=None,
            threshold_source=None,
            datum="USGS gage zero NGVD29 (Winona)",
        ),
        "reference_stations": [],
        "selection_reason": "Same caveat as L&D 5/5A.",
    },
    "lock_7": {
        "official_station": _usgs(
            "05378500",
            "Mississippi River at Winona, MN",
            725.7,
            thresholds=None,
            threshold_source=None,
            datum="USGS gage zero NGVD29 (Winona)",
        ),
        "reference_stations": [],
        "selection_reason": "Same caveat as L&D 5/5A; Winona is the nearest USGS feed.",
    },

    # --- Locks 8-10 (McGregor) -------------------------------------------
    "lock_8": {
        "official_station": _usgs(
            "05389500",
            "Mississippi River at McGregor, IA",
            633.4,
            thresholds=_t_mcgregor()[0],
            threshold_source=_t_mcgregor()[1],
            datum="USGS gage zero NGVD29 (McGregor)",
        ),
        "reference_stations": [],
        "selection_reason": "Nearest USGS real-time gauge; thresholds match NWS McGregor (MCGI4).",
    },
    "lock_9": {
        "official_station": _usgs(
            "05389500",
            "Mississippi River at McGregor, IA",
            633.4,
            thresholds=None,
            threshold_source=None,
            datum="USGS gage zero NGVD29 (McGregor)",
        ),
        "reference_stations": [],
        "selection_reason": "McGregor is the closest USGS feed but is below L&D 9; thresholds left undefined.",
    },
    "lock_10": {
        "official_station": _usgs(
            "05389500",
            "Mississippi River at McGregor, IA",
            633.4,
            thresholds=None,
            threshold_source=None,
            datum="USGS gage zero NGVD29 (McGregor)",
        ),
        "reference_stations": [],
        "selection_reason": "McGregor below L&D 10; thresholds left undefined to avoid mismatched categorization.",
    },

    # --- Locks 11-16 (Clinton) -------------------------------------------
    "lock_11": {
        "official_station": _usgs(
            "05420500",
            "Mississippi River at Clinton, IA",
            511.8,
            thresholds=_t_clinton()[0],
            threshold_source=_t_clinton()[1],
            datum="USGS gage zero NGVD29 (Clinton)",
        ),
        "reference_stations": [],
        "selection_reason": "Clinton is the central NWS-defined gauge; thresholds match CLNI4.",
    },
    "lock_12": {"official_station": _usgs("05420500", "Mississippi River at Clinton, IA", 511.8, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Clinton is the closest USGS real-time gauge; thresholds intentionally undefined."},
    "lock_13": {"official_station": _usgs("05420500", "Mississippi River at Clinton, IA", 511.8, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Clinton is the closest USGS real-time gauge; thresholds intentionally undefined."},
    "lock_14": {"official_station": _usgs("05420500", "Mississippi River at Clinton, IA", 511.8, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Clinton is the closest USGS real-time gauge; thresholds intentionally undefined."},
    "lock_15": {"official_station": _usgs("05420500", "Mississippi River at Clinton, IA", 511.8, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Clinton is the closest USGS real-time gauge; thresholds intentionally undefined."},
    "lock_16": {"official_station": _usgs("05420500", "Mississippi River at Clinton, IA", 511.8, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Clinton is the closest USGS real-time gauge; thresholds intentionally undefined."},

    # --- Locks 17-19 (Keokuk) --------------------------------------------
    "lock_17": {"official_station": _usgs("05474500", "Mississippi River at Keokuk, IA", 364.2, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Keokuk is the closest USGS real-time gauge; thresholds intentionally undefined."},
    "lock_18": {"official_station": _usgs("05474500", "Mississippi River at Keokuk, IA", 364.2, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Keokuk is the closest USGS real-time gauge; thresholds intentionally undefined."},
    "lock_19": {
        "official_station": _usgs(
            "05474500",
            "Mississippi River at Keokuk, IA",
            364.2,
            thresholds=_t_keokuk()[0],
            threshold_source=_t_keokuk()[1],
            datum="USGS gage zero NGVD29 (Keokuk)",
        ),
        "reference_stations": [],
        "selection_reason": "Keokuk gauge is at L&D 19; thresholds match NWS Keokuk (KEOI4).",
    },

    # --- Locks 20-25 + Melvin Price (Grafton) ----------------------------
    "lock_20": {"official_station": _usgs("05587450", "Mississippi River at Grafton, IL", 218.0, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Grafton is the closest NWS-defined real-time gauge; thresholds intentionally undefined for this lock."},
    "lock_21": {"official_station": _usgs("05587450", "Mississippi River at Grafton, IL", 218.0, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Grafton is the closest NWS-defined real-time gauge; thresholds intentionally undefined for this lock."},
    "lock_22": {"official_station": _usgs("05587450", "Mississippi River at Grafton, IL", 218.0, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Grafton is the closest NWS-defined real-time gauge; thresholds intentionally undefined for this lock."},
    "lock_24": {"official_station": _usgs("05587450", "Mississippi River at Grafton, IL", 218.0, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Grafton is the closest NWS-defined real-time gauge; thresholds intentionally undefined for this lock."},
    "lock_25": {"official_station": _usgs("05587450", "Mississippi River at Grafton, IL", 218.0, thresholds=None, threshold_source=None), "reference_stations": [], "selection_reason": "Grafton is the closest NWS-defined real-time gauge; thresholds intentionally undefined for this lock."},
    "melvin_price": {
        "official_station": _usgs(
            "05587450",
            "Mississippi River at Grafton, IL",
            218.0,
            thresholds=_t_grafton()[0],
            threshold_source=_t_grafton()[1],
            datum="USGS gage zero NGVD29 (Grafton)",
        ),
        "reference_stations": [],
        "selection_reason": "Grafton is the closest NWS-defined real-time gauge to Melvin Price; thresholds match GRFI2.",
    },

    # --- Chain of Rocks (St. Louis) --------------------------------------
    "chain_of_rocks": {
        "official_station": _usgs(
            "07010000",
            "Mississippi River at St. Louis, MO",
            180.0,
            thresholds=_t_eads()[0],
            threshold_source=_t_eads()[1],
            datum="USGS gage zero 379.94 ft NGVD29 (Eads Bridge)",
        ),
        "reference_stations": [],
        "selection_reason": "St. Louis (USGS 07010000) is the closest NWS-defined real-time gauge; thresholds match EADM7.",
    },
}
