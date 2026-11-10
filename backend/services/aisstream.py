"""
aisstream.io live AIS source.

Opens one outbound WebSocket to aisstream.io, subscribes to a bounding box
around the Upper Mississippi, and hands each message to the same ingest path
the phone/relay TCP feed uses (source="aisstream"), so names, river-channel
filtering, lock tracking and broadcasting behave identically.

Configure with:
  AISSTREAM_API_KEY   API key from aisstream.io (unset = source disabled)
  AISSTREAM_BBOX      optional "lat1,lon1,lat2,lon2" (default: Upper Mississippi)

aisstream delivers JSON that is already decoded; `to_decoded` maps it onto the
pyais field names that `vessel_data_from_decoded` expects.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"

# Minneapolis/St. Paul (~45.0 N) down to St. Louis (~38.6 N), wide enough in
# longitude for the whole channel. Off-channel targets inside the box (Illinois,
# Missouri, St. Croix) are dropped later by the main-channel filter.
DEFAULT_BBOX = (38.4, -93.7, 45.3, -89.8)

MESSAGE_TYPES = [
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
    "ShipStaticData",
    "StaticDataReport",
]

status = {
    "enabled": False,
    "connected": False,
    "messages": 0,
    "ingested": 0,
    "last_message_at": None,
    "last_error": None,
    "bbox": None,
}


def api_key() -> Optional[str]:
    value = (os.environ.get("AISSTREAM_API_KEY") or "").strip()
    return value or None


def bbox() -> tuple:
    raw = (os.environ.get("AISSTREAM_BBOX") or "").strip()
    if raw:
        try:
            parts = tuple(float(x) for x in raw.split(","))
            if len(parts) == 4:
                return parts
        except ValueError:
            pass
        logger.warning("AISSTREAM_BBOX must be 'lat1,lon1,lat2,lon2'; using the default")
    return DEFAULT_BBOX


def subscription(key: str, box: tuple) -> dict:
    lat1, lon1, lat2, lon2 = box
    return {
        "APIKey": key,
        "BoundingBoxes": [[[lat1, lon1], [lat2, lon2]]],
        "FilterMessageTypes": MESSAGE_TYPES,
    }


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _text(value) -> str:
    """AIS pads text fields with '@'; strip it like pyais does for NMEA."""
    return value.replace("@", " ").strip() if isinstance(value, str) else ""


def _dims(target: dict, dim) -> None:
    if isinstance(dim, dict):
        for src, dst in (("A", "to_bow"), ("B", "to_stern"), ("C", "to_port"), ("D", "to_starboard")):
            if _num(dim.get(src)) is not None:
                target[dst] = dim[src]


def to_decoded(msg: dict) -> Optional[dict]:
    """Map one aisstream.io message onto pyais-style decoded fields."""
    if not isinstance(msg, dict):
        return None
    kind = msg.get("MessageType")
    meta = msg.get("MetaData") or {}
    body = (msg.get("Message") or {}).get(kind) or {}
    mmsi = body.get("UserID") or meta.get("MMSI")
    if not kind or not mmsi:
        return None
    out = {"mmsi": int(mmsi)}

    if kind in ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport"):
        out["msg_type"] = {"PositionReport": body.get("MessageID") or 1,
                           "StandardClassBPositionReport": 18,
                           "ExtendedClassBPositionReport": 19}[kind]
        lat = _num(body.get("Latitude"))
        lon = _num(body.get("Longitude"))
        if lat is None or lon is None:
            lat, lon = _num(meta.get("latitude")), _num(meta.get("longitude"))
        out.update({
            "lat": lat,
            "lon": lon,
            "speed": _num(body.get("Sog")),
            "course": _num(body.get("Cog")),
            "heading": _num(body.get("TrueHeading")),
            "status": _num(body.get("NavigationalStatus")),
            "turn": _num(body.get("RateOfTurn")),
        })
        if kind == "ExtendedClassBPositionReport":
            out["shipname"] = _text(body.get("Name"))
            out["ship_type"] = _num(body.get("Type"))
            _dims(out, body.get("Dimension"))
        return out

    if kind == "ShipStaticData":
        out.update({
            "msg_type": 5,
            "shipname": _text(body.get("Name")),
            "callsign": _text(body.get("CallSign")),
            "destination": _text(body.get("Destination")),
            "ship_type": _num(body.get("Type")),
            "draught": _num(body.get("MaximumStaticDraught")),
        })
        if _num(body.get("ImoNumber")):
            out["imo"] = body["ImoNumber"]
        eta = body.get("Eta") or {}
        for src, dst in (("Month", "month"), ("Day", "day"), ("Hour", "hour"), ("Minute", "minute")):
            if _num(eta.get(src)) is not None:
                out[dst] = eta[src]
        _dims(out, body.get("Dimension"))
        return out

    if kind == "StaticDataReport":
        out["msg_type"] = 24
        part_a = body.get("ReportA") or {}
        part_b = body.get("ReportB") or {}
        if part_a.get("Valid", True) and _text(part_a.get("Name")):
            out["shipname"] = _text(part_a["Name"])
        if part_b.get("Valid", True):
            out["ship_type"] = _num(part_b.get("ShipType"))
            out["callsign"] = _text(part_b.get("CallSign"))
            _dims(out, part_b.get("Dimension"))
        return out

    return None


def metadata_name(msg: dict) -> Optional[str]:
    name = ((msg or {}).get("MetaData") or {}).get("ShipName")
    return _text(name) or None


async def handle_message(msg: dict, decode_fn: Callable, ingest_fn: Callable,
                         static_cache: dict, apply_static_fn: Callable) -> bool:
    """Process one aisstream message. Returns True if a vessel report was ingested."""
    decoded = to_decoded(msg)
    if decoded is None:
        return False
    mmsi = str(decoded["mmsi"])
    # aisstream attaches its last known ship name to every message; use it
    # until a static report gives us one.
    name = metadata_name(msg)
    if name and not (static_cache.get(mmsi) or {}).get("name"):
        static_cache.setdefault(mmsi, {})["name"] = name
    vessel_data = decode_fn(decoded)
    if decoded.get("msg_type") in (5, 24) and mmsi in static_cache:
        await apply_static_fn(mmsi, static_cache[mmsi])
    if vessel_data:
        await ingest_fn(vessel_data, source="aisstream")
        return True
    return False


async def run(decode_fn: Callable, ingest_fn: Callable, static_cache: dict, apply_static_fn: Callable,
              connect: Optional[Callable] = None) -> None:
    """Keep a subscription open, reconnecting with backoff. Runs until cancelled."""
    key = api_key()
    if not key:
        logger.info("aisstream.io source disabled (no AISSTREAM_API_KEY)")
        return
    import websockets  # runtime dependency already used by the server

    connect = connect or (lambda: websockets.connect(AISSTREAM_URL, ping_interval=20, max_size=2 ** 20))
    box = bbox()
    status.update({"enabled": True, "bbox": list(box)})
    delay = 5.0
    while True:
        try:
            async with connect() as ws:
                # aisstream closes the socket unless the subscription arrives within 3 s.
                await ws.send(json.dumps(subscription(key, box)))
                status.update({"connected": True, "last_error": None})
                logger.info(f"aisstream.io connected, bbox={box}")
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(msg, dict) and msg.get("error"):
                        # e.g. a bad API key; the server closes right after.
                        status["last_error"] = str(msg.get("error"))[:200]
                        logger.error(f"aisstream.io error: {status['last_error']}")
                        continue
                    status["messages"] += 1
                    status["last_message_at"] = datetime.now(timezone.utc).isoformat()
                    try:
                        if await handle_message(msg, decode_fn, ingest_fn, static_cache, apply_static_fn):
                            status["ingested"] += 1
                    except Exception as e:  # one bad message must not drop the stream
                        logger.debug(f"aisstream.io message skipped: {e}")
                    delay = 5.0
        except asyncio.CancelledError:
            status["connected"] = False
            raise
        except Exception as e:
            status["last_error"] = f"{type(e).__name__}: {e}"[:200]
            logger.warning(f"aisstream.io disconnected: {status['last_error']}")
        status["connected"] = False
        await asyncio.sleep(delay)
        delay = min(delay * 2, 300.0)
