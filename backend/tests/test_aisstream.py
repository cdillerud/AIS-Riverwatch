"""aisstream.io messages flow through the same ingest path as the phone feed."""
import asyncio
import json
from contextlib import asynccontextmanager

import server
from services import aisstream

POS = {
    "MessageType": "PositionReport",
    "MetaData": {"MMSI": 367523360, "ShipName": "MARY J            ", "latitude": 44.70, "longitude": -92.86},
    "Message": {"PositionReport": {"UserID": 367523360, "MessageID": 1, "Latitude": 44.70, "Longitude": -92.86,
                                   "Sog": 4.3, "Cog": 315.0, "TrueHeading": 314, "NavigationalStatus": 0,
                                   "RateOfTurn": 0}},
}
STATIC = {
    "MessageType": "ShipStaticData",
    "MetaData": {"MMSI": 367523360, "ShipName": "MARY J"},
    "Message": {"ShipStaticData": {"UserID": 367523360, "Name": "MARY J@@@@", "CallSign": "WDC1234",
                                   "Type": 52, "Destination": "ST PAUL",
                                   "Dimension": {"A": 20, "B": 10, "C": 5, "D": 5},
                                   "MaximumStaticDraught": 2.7,
                                   "Eta": {"Month": 11, "Day": 12, "Hour": 8, "Minute": 30}}},
}


def test_position_and_static_translation():
    d = aisstream.to_decoded(POS)
    assert d["msg_type"] == 1 and d["mmsi"] == 367523360
    assert (d["lat"], d["lon"], d["speed"], d["course"], d["heading"]) == (44.70, -92.86, 4.3, 315.0, 314)
    s = aisstream.to_decoded(STATIC)
    assert s["msg_type"] == 5 and s["ship_type"] == 52 and s["to_bow"] + s["to_stern"] == 30
    assert s["month"] == 11 and s["callsign"] == "WDC1234"
    assert aisstream.metadata_name(POS) == "MARY J"
    assert aisstream.to_decoded({"MessageType": "PositionReport"}) is None
    assert aisstream.to_decoded({"MessageType": "Interrogation", "MetaData": {"MMSI": 1}, "Message": {}}) is None


class FakeWS:
    def __init__(self, messages):
        self.sent = []
        self._messages = [json.dumps(m) for m in messages]

    async def send(self, data):
        self.sent.append(json.loads(data))

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._messages:
            raise asyncio.CancelledError  # end the run loop
        return self._messages.pop(0)


def test_stream_subscribes_and_ingests_with_source(monkeypatch):
    monkeypatch.setenv("AISSTREAM_API_KEY", "test-key")
    monkeypatch.delenv("AISSTREAM_BBOX", raising=False)
    ws = FakeWS([STATIC, POS, {"error": "nope"}])

    @asynccontextmanager
    async def connect():
        yield ws

    ingested = []

    async def ingest(vd, source):
        ingested.append((vd["mmsi"], vd.get("name"), source))

    async def apply_static(mmsi, data):
        return None

    monkeypatch.setattr(server, "persist_vessel_sighting", lambda v: asyncio.sleep(0))
    monkeypatch.setattr(server, "get_usace_vessel_info", lambda m: None)
    cache = server.vessel_static_cache
    cache.pop("367523360", None)
    try:
        asyncio.run(aisstream.run(server.vessel_data_from_decoded, ingest, cache, apply_static, connect=connect))
    except asyncio.CancelledError:
        pass

    sub = ws.sent[0]
    assert sub["APIKey"] == "test-key" and sub["BoundingBoxes"] == [[[38.4, -93.7], [45.3, -89.8]]]
    assert ("367523360", "MARY J", "aisstream") in ingested
    assert aisstream.status["last_error"] == "nope"
    cache.pop("367523360", None)


def test_disabled_without_key(monkeypatch):
    monkeypatch.delenv("AISSTREAM_API_KEY", raising=False)
    assert asyncio.run(aisstream.run(None, None, {}, None)) is None
