"""
Marinas and fuel docks along the Upper Mississippi, from OpenStreetMap
(Overpass API), pinned to a river mile so the trip planner can list stops
ahead. Data (c) OpenStreetMap contributors, ODbL - the app shows that credit.

Coverage is what OSM has: ~50 named marinas on the river in Nov 2026, some
missing. Refreshed weekly; unnamed features are dropped (a boater can't call
or look up "-").
"""
from __future__ import annotations

from typing import Callable, Iterable, List, Optional

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Upper Mississippi corridor (Cairo IL to Minneapolis), generous on longitude.
BBOX = (37.0, -95.0, 46.0, -89.0)
QUERY = (
    "[out:json][timeout:90];("
    'nwr["leisure"="marina"]({b});'
    'nwr["waterway"="fuel"]({b});'
    'nwr["amenity"="fuel"]["boat"="yes"]({b});'
    ");out center tags;"
).format(b=",".join(str(x) for x in BBOX))
MAX_OFFSET_MI = 1.5      # marinas sit in sloughs and harbors off the channel
REFRESH_DAYS = 7
OSM_CREDIT = "Marina data (c) OpenStreetMap contributors"


def _has_fuel(tags: dict) -> bool:
    if tags.get("waterway") == "fuel" or tags.get("amenity") == "fuel":
        return True
    if any(k.startswith("fuel:") and tags.get(k) == "yes" for k in tags):
        return True
    cat = tags.get("seamark:small_craft_facility:category", "")
    return "fuel" in cat


def _yes(tags: dict, *keys) -> bool:
    return any(tags.get(k) in ("yes", "customers") for k in keys)


def parse(elements: Iterable[dict], river_mile: Callable[[float, float], Optional[float]]) -> List[dict]:
    """Overpass elements -> marina docs on the river, one per named place."""
    out, seen = [], set()
    for e in elements:
        tags = e.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        rm = river_mile(lat, lon)
        if rm is None:
            continue
        key = (name.lower(), round(rm, 0))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "osm_id": f"{e.get('type', 'node')}/{e.get('id')}",
            "name": name,
            "lat": round(float(lat), 5),
            "lon": round(float(lon), 5),
            "river_mile": round(float(rm), 1),
            "kind": "fuel" if tags.get("leisure") != "marina" else "marina",
            "fuel": _has_fuel(tags),
            "pumpout": _yes(tags, "sanitary_dump_station", "pump_out"),
            "power": _yes(tags, "power_supply"),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            "vhf": tags.get("vhf") or tags.get("seamark:radio_station:channel"),
        })
    out.sort(key=lambda m: -m["river_mile"])
    return out


def between(marinas: Iterable[dict], from_rm: float, to_rm: float) -> List[dict]:
    """Marinas between two river miles, in travel order (from -> to)."""
    lo, hi = sorted((float(from_rm), float(to_rm)))
    rows = [m for m in marinas if lo <= m["river_mile"] <= hi]
    rows.sort(key=lambda m: m["river_mile"], reverse=from_rm > to_rm)
    return rows
