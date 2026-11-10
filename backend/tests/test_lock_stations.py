"""Each lock's water conditions come from the gauge at that lock."""
import asyncio

from config import LOCKS, LOCK_GAUGES
from lock_stations import LOCK_STATIONS
from services import water_station_service as ws


def test_official_station_is_the_gauge_at_the_lock():
    for lock_id in LOCKS:
        official = LOCK_STATIONS[lock_id]["official_station"]
        assert official["source"] == "NWS", lock_id
        assert official["station_id"] == LOCK_GAUGES[lock_id]["nwsli"], lock_id
        assert official["river_mile"] == LOCKS[lock_id]["river_mile"], lock_id
    # The distant gauge Lock 20 used before is kept only as a reference, without thresholds
    refs = LOCK_STATIONS["lock_20"]["reference_stations"]
    assert refs[0]["station_id"] == "05587450" and refs[0]["thresholds"] is None


def test_nws_flood_stages_come_from_the_same_gauge(monkeypatch):
    async def fake_fetch(station):
        return {"value": 16.2, "units": "ft", "observed_at": "2026-11-10T20:30:00Z", "raw": {},
                "fetch_method": "nwps_api", "source_status": "ok",
                "thresholds_api": {"action": 13.0, "flood": 15.0, "moderate": 20.0, "major": float("inf")}}

    monkeypatch.setattr(ws, "_fetch_one", fake_fetch)
    data = asyncio.run(ws.get_water_conditions("lock_20"))
    official = data["official"]
    assert official["station_id"] == "CANM7" and official["status"] == "flood"
    assert official["thresholds"]["major"] is None            # missing category, not infinity
    assert official["threshold_source"] == "NWS NWPS flood categories for CANM7"
