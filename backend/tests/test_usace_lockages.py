"""Completed lockages from the USACE lock queue feed become lockage history."""
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from services.usace_lockages import completed_lockages, parse_time, record_key

# Real rows from lockqueue_xml?in_river=MI&in_lock=15 on 2026-11-10.
LOCK15 = """<?xml version="1.0"?><ROWSET>
 <ROW><VESSEL_NAME>WISCONSIN</VESSEL_NAME><VESSEL_NO>0568371</VESSEL_NO><DIRECTION>D</DIRECTION>
  <NUM_BARGES>15</NUM_BARGES><ARRIVAL_DATE>11/10/26 10:49</ARRIVAL_DATE><TIMEZONE>CST</TIMEZONE><MMSI>367505680</MMSI></ROW>
 <ROW><VESSEL_NAME>MISS MARLEY</VESSEL_NAME><VESSEL_NO>1284517</VESSEL_NO><DIRECTION>U</DIRECTION>
  <NUM_BARGES>4</NUM_BARGES><SOL_DATE>11/10/26 07:16</SOL_DATE><ARRIVAL_DATE>11/10/26 07:15</ARRIVAL_DATE>
  <END_OF_LOCKAGE>11/10/26 08:15</END_OF_LOCKAGE><TIMEZONE>CST</TIMEZONE><MMSI>368054570</MMSI></ROW>
 <ROW><VESSEL_NAME>MISS MARLEY</VESSEL_NAME><VESSEL_NO>1284517</VESSEL_NO><DIRECTION>U</DIRECTION>
  <NUM_BARGES>0</NUM_BARGES><SOL_DATE>11/10/26 08:26</SOL_DATE><ARRIVAL_DATE>11/10/26 07:15</ARRIVAL_DATE>
  <END_OF_LOCKAGE>11/10/26 08:50</END_OF_LOCKAGE><TIMEZONE>CST</TIMEZONE><MMSI>368054570</MMSI></ROW>
 <ROW><VESSEL_NAME>CRIMSON GLORY</VESSEL_NAME><VESSEL_NO>0515916</VESSEL_NO><DIRECTION>D</DIRECTION>
  <NUM_BARGES>6</NUM_BARGES><SOL_DATE>11/10/26 03:07</SOL_DATE><ARRIVAL_DATE>11/10/26 01:14</ARRIVAL_DATE>
  <END_OF_LOCKAGE>11/10/26 04:11</END_OF_LOCKAGE><TIMEZONE>CST</TIMEZONE><MMSI>366984330</MMSI></ROW>
 <ROW><VESSEL_NAME>CRIMSON GLORY</VESSEL_NAME><VESSEL_NO>0515916</VESSEL_NO><DIRECTION>D</DIRECTION>
  <NUM_BARGES>9</NUM_BARGES><SOL_DATE>11/10/26 01:55</SOL_DATE><ARRIVAL_DATE>11/10/26 01:14</ARRIVAL_DATE>
  <END_OF_LOCKAGE>11/10/26 02:58</END_OF_LOCKAGE><TIMEZONE>CST</TIMEZONE><MMSI>366984330</MMSI></ROW>
</ROWSET>"""


def _records():
    rows = ET.fromstring(LOCK15).findall(".//ROW")
    return {r["vessel_name"]: r for r in completed_lockages(rows, "lock_15", "Lock & Dam #15")}


def test_waiting_vessels_are_not_history():
    assert "WISCONSIN" not in _records()


def test_cuts_are_combined_into_one_lockage():
    crimson = _records()["CRIMSON GLORY"]
    assert crimson["cuts"] == 2 and crimson["is_double_lockage"]
    assert crimson["barge_count"] == 15                      # 9 + 6
    assert crimson["direction"] == "downbound"
    assert crimson["wait_time_minutes"] == 41.0              # 01:14 -> 01:55
    assert crimson["lockage_duration_minutes"] == 136.0      # 01:55 -> 04:11
    assert crimson["mmsi"] == "366984330"
    assert crimson["source"] == "usace_lpms" and crimson["confidence"] == "high"


def test_times_are_converted_to_utc():
    marley = _records()["MISS MARLEY"]
    assert marley["entry_time"] == datetime(2026, 11, 10, 13, 16, tzinfo=timezone.utc)   # 07:16 CST
    assert marley["recorded_at"] == marley["exit_time"]
    assert marley["lockage_duration_minutes"] == 94.0        # 07:16 -> 08:50, both cuts
    assert parse_time("07/04/26 12:00", "CDT") == datetime(2026, 7, 4, 17, 0, tzinfo=timezone.utc)
    assert parse_time("garbage", "CST") is None


def test_record_key_is_stable_for_repeated_rows():
    first = _records()["CRIMSON GLORY"]
    again = _records()["CRIMSON GLORY"]
    assert record_key(first) == record_key(again)


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status


class _Client:
    def __init__(self, text):
        self._text = text

    async def get(self, url):
        return _Resp(self._text)


def test_rate_limit_reply_is_not_an_empty_lock(monkeypatch):
    import asyncio
    import pytest
    import server

    async def no_store(rows, lock_no):
        return 0
    monkeypatch.setattr(server, "_store_usace_lockages", no_store)
    limited = _Client('{"error": "Rate limit exceeded. Maximum 5 requests per minute allowed."}\n')
    with pytest.raises(server.UsaceRateLimited):
        asyncio.run(server.fetch_usace_lock(limited, "15"))

    active = asyncio.run(server.fetch_usace_lock(_Client(LOCK15), "15"))
    assert active == 1                                     # WISCONSIN waiting; the rest completed
    assert server.usace_lock_queue_cache["data"]["367505680"]["num_barges"] == 15
    server.usace_lock_rows.pop("15", None)
    server._rebuild_usace_indexes()
