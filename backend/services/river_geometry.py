"""
River geometry: linear referencing against the official Mississippi sailing line.

Replaces the old latitude-only river-mile formula, which was off by up to ~19
river miles (e.g. at Locks 4, 7, 8 and 16), and the compass-based
"northbound/southbound" rule, which is wrong wherever the river runs east-west
(it flows WEST through the Quad Cities).

Data: backend/data/umr_centerline.json, built by scripts/build_river_centerline.py
from the USACE National Waterway Network (official river miles on every link).

Public API
----------
project(lat, lon)           -> Projection | None   (snap to sailing line)
river_mile(lat, lon)        -> float | None
upstream_bearing(lat, lon)  -> float | None        (compass bearing toward higher RM)
travel_direction(course, lat, lon) -> "upbound" | "downbound" | None
coords_for_mile(rm)         -> (lat, lon) | None
channel(lat, lon)           -> "MISSISSIPPI RIVER" | tributary name | None

A position that is nearer a navigable tributary's channel line (St. Croix,
Minnesota, Black, Illinois, Missouri, ...) than the Mississippi's is NOT
Mississippi traffic, so project() returns None for it.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "umr_centerline.json"

EARTH_RADIUS_MI = 3958.8
# Positions further than this from the sailing line are treated as "not on the
# Mississippi" (tributaries, lakes, roads). Wide pools / backwaters (Lake Pepin,
# Pool 13) put legitimate traffic up to ~2-3 miles off the line.
DEFAULT_MAX_OFFSET_MI = 3.0
_CELL_DEG = 0.1  # spatial index cell size


@dataclass(frozen=True)
class Projection:
    river_mile: float
    offset_mi: float          # distance from the sailing line
    upstream_bearing: float   # degrees true, pointing toward increasing river mile
    lat: float                # snapped point on the line
    lon: float


class _Lines:
    """Spatial index over a set of polylines (tributaries)."""

    def __init__(self, named_lines: Dict[str, list]):
        self.segs: List[Tuple[str, float, float, float, float]] = []
        self.index: Dict[Tuple[int, int], List[int]] = {}
        for name, lines in named_lines.items():
            for line in lines:
                for (la1, lo1), (la2, lo2) in zip(line, line[1:]):
                    k = len(self.segs)
                    self.segs.append((name, la1, lo1, la2, lo2))
                    for cy in range(_cell(min(la1, la2)), _cell(max(la1, la2)) + 1):
                        for cx in range(_cell(min(lo1, lo2)), _cell(max(lo1, lo2)) + 1):
                            self.index.setdefault((cy, cx), []).append(k)

    def nearest(self, lat: float, lon: float, ring: int) -> Tuple[Optional[str], float]:
        cy, cx = _cell(lat), _cell(lon)
        seen = set()
        for dy in range(-ring, ring + 1):
            for dx in range(-ring, ring + 1):
                seen.update(self.index.get((cy + dy, cx + dx), ()))
        kx, ky = math.cos(math.radians(lat)) * 69.172, 69.0
        best_name, best = None, float("inf")
        for k in seen:
            name, la1, lo1, la2, lo2 = self.segs[k]
            d = _seg_dist((lo1 - lon) * kx, (la1 - lat) * ky, (lo2 - lon) * kx, (la2 - lat) * ky)[0]
            if d < best:
                best_name, best = name, d
        return best_name, best


def _seg_dist(ax, ay, bx, by) -> Tuple[float, float]:
    """Distance from origin to segment AB (local miles) and the param t."""
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
    px, py = ax + t * dx, ay + t * dy
    return math.sqrt(px * px + py * py), t


class _Centerline:
    def __init__(self, points: List[List[float]]):
        # points ordered by descending river mile: [lat, lon, rm]
        self.lat = [p[0] for p in points]
        self.lon = [p[1] for p in points]
        self.rm = [p[2] for p in points]
        self.n = len(points)
        self.index: Dict[Tuple[int, int], List[int]] = {}
        for i in range(self.n - 1):
            lo_lat, hi_lat = sorted((self.lat[i], self.lat[i + 1]))
            lo_lon, hi_lon = sorted((self.lon[i], self.lon[i + 1]))
            for cy in range(_cell(lo_lat), _cell(hi_lat) + 1):
                for cx in range(_cell(lo_lon), _cell(hi_lon) + 1):
                    self.index.setdefault((cy, cx), []).append(i)

    def candidates(self, lat: float, lon: float, ring: int) -> List[int]:
        cy, cx = _cell(lat), _cell(lon)
        seen = set()
        for dy in range(-ring, ring + 1):
            for dx in range(-ring, ring + 1):
                seen.update(self.index.get((cy + dy, cx + dx), ()))
        return list(seen)


def _cell(v: float) -> int:
    return int(math.floor(v / _CELL_DEG))


@lru_cache(maxsize=1)
def _load() -> Tuple[_Centerline, list, _Lines]:
    data = json.loads(DATA_FILE.read_text())
    return _Centerline(data["points"]), data.get("locks", []), _Lines(data.get("tributaries", {}))


def official_lock_links() -> list:
    """Lock links from the waterway network: name, rm_upper, rm_lower, lat, lon."""
    return _load()[1]  # noqa


def _bearing(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def project(lat: Optional[float], lon: Optional[float],
            max_offset_mi: float = DEFAULT_MAX_OFFSET_MI) -> Optional[Projection]:
    """
    Snap a position to the sailing line. None if invalid, too far off-river,
    or nearer a tributary channel than the Mississippi.
    """
    hit = _project_main(lat, lon, max_offset_mi)
    if hit is None:
        return None
    proj, (qlat, qlon, ring) = hit
    trib, trib_d = _load()[2].nearest(qlat, qlon, ring)
    if trib is not None and trib_d < proj.offset_mi:
        return None
    return proj


def channel(lat: Optional[float], lon: Optional[float],
            max_offset_mi: float = DEFAULT_MAX_OFFSET_MI) -> Optional[str]:
    """Which navigable channel a position is on, or None if on neither."""
    hit = _project_main(lat, lon, max_offset_mi)
    if hit is None:
        if lat is None or lon is None:
            return None
        trib, d = _load()[2].nearest(float(lat), float(lon), 1)
        return trib if trib is not None and d <= max_offset_mi else None
    proj, (qlat, qlon, ring) = hit
    trib, trib_d = _load()[2].nearest(qlat, qlon, ring)
    if trib is not None and trib_d < proj.offset_mi:
        return trib
    return "MISSISSIPPI RIVER"


def _project_main(lat, lon, max_offset_mi):
    if lat is None or lon is None:
        return None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None

    cl = _load()[0]
    ring = max(1, int(math.ceil(max_offset_mi / 69.0 / _CELL_DEG / math.cos(math.radians(lat)))))
    cands = cl.candidates(lat, lon, ring)
    if not cands:
        return None

    # Local equirectangular frame (miles) centred on the query point.
    kx = math.cos(math.radians(lat)) * 69.172
    ky = 69.0
    best = None
    for i in cands:
        ax, ay = (cl.lon[i] - lon) * kx, (cl.lat[i] - lat) * ky
        bx, by = (cl.lon[i + 1] - lon) * kx, (cl.lat[i + 1] - lat) * ky
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
        px, py = ax + t * dx, ay + t * dy
        d2 = px * px + py * py
        if best is None or d2 < best[0]:
            best = (d2, i, t)

    d2, i, t = best
    offset = math.sqrt(d2)
    if offset > max_offset_mi:
        return None
    rm = cl.rm[i] + (cl.rm[i + 1] - cl.rm[i]) * t
    s_lat = cl.lat[i] + (cl.lat[i + 1] - cl.lat[i]) * t
    s_lon = cl.lon[i] + (cl.lon[i + 1] - cl.lon[i]) * t
    # Points are ordered downstream, so upstream is from i+1 back toward i.
    # Smooth over a few vertices so one kinked segment doesn't flip direction.
    j0, j1 = max(0, i - 2), min(cl.n - 1, i + 3)
    up = _bearing(cl.lat[j1], cl.lon[j1], cl.lat[j0], cl.lon[j0])
    return Projection(round(rm, 2), round(offset, 3), round(up, 1), s_lat, s_lon), (lat, lon, ring)


def river_mile(lat: Optional[float], lon: Optional[float],
               max_offset_mi: float = DEFAULT_MAX_OFFSET_MI) -> Optional[float]:
    p = project(lat, lon, max_offset_mi)
    return None if p is None else round(p.river_mile, 1)


def upstream_bearing(lat: Optional[float], lon: Optional[float]) -> Optional[float]:
    p = project(lat, lon)
    return None if p is None else p.upstream_bearing


def angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings, 0..180."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def travel_direction(course: Optional[float], lat: Optional[float], lon: Optional[float]) -> Optional[str]:
    """
    'upbound' (toward higher river mile) or 'downbound', using the LOCAL river
    bearing at the vessel's position. None if position is off-river or course
    is unavailable (AIS COG 360 = not available).
    """
    if course is None:
        return None
    try:
        course = float(course)
    except (TypeError, ValueError):
        return None
    if course < 0 or course >= 360:
        return None
    up = upstream_bearing(lat, lon)
    if up is None:
        return None
    return "upbound" if angle_diff(course, up) < 90.0 else "downbound"


def coords_for_mile(rm: float) -> Optional[Tuple[float, float]]:
    """Point on the sailing line at a given river mile (None outside coverage)."""
    cl = _load()[0]
    if rm is None or rm > cl.rm[0] or rm < cl.rm[-1]:
        return None
    lo, hi = 0, cl.n - 1  # rm descending
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if cl.rm[mid] >= rm:
            lo = mid
        else:
            hi = mid
    span = cl.rm[lo] - cl.rm[hi]
    t = 0.0 if span == 0 else (cl.rm[lo] - rm) / span
    return (round(cl.lat[lo] + (cl.lat[hi] - cl.lat[lo]) * t, 6),
            round(cl.lon[lo] + (cl.lon[hi] - cl.lon[lo]) * t, 6))


def channel_bearing_at_mile(rm: float, span_mi: float = 0.5) -> Optional[float]:
    """Upstream bearing of the channel at a river mile, measured across
    +/- span_mi so one short sailing-line segment can't skew it. This is the
    course a boat steers to go upbound there; downbound is the reverse. Not
    simply north/south: at RM 823 (Grey Cloud Island) the river runs
    east-northeast, so 177 deg there is nearly straight across the channel."""
    lo, hi = coverage()
    a = coords_for_mile(min(rm + span_mi, hi))
    b = coords_for_mile(max(rm - span_mi, lo))
    if a is None or b is None or a == b:
        return None
    return round(_bearing(b[0], b[1], a[0], a[1]), 1)


def coverage() -> Tuple[float, float]:
    cl = _load()[0]
    return cl.rm[-1], cl.rm[0]


# ---------------------------------------------------------------------------
# Shared helpers used by server.py / navigation_service / vessel_service so
# there is exactly ONE implementation of river mile + direction.
# ---------------------------------------------------------------------------
def _compass_fallback(course: float) -> str:
    return "up" if (270 <= course <= 360 or 0 <= course < 90) else "down"


def heading_label(speed, course, lat=None, lon=None,
                  up: str = "northbound", down: str = "southbound",
                  min_speed_knots: float = 0.5) -> str:
    """
    Direction of travel relative to the river.

    Returns `up` (toward higher river mile), `down`, "stationary" or "unknown".
    Uses the local river bearing when a position is given (correct in reaches
    that run east-west); falls back to a north/south compass rule only when no
    position is available.
    """
    try:
        speed = float(speed) if speed is not None else None
    except (TypeError, ValueError):
        speed = None
    if speed is None or speed < min_speed_knots:
        return "stationary"
    try:
        course = float(course) if course is not None else None
    except (TypeError, ValueError):
        course = None
    if course is None or course < 0 or course >= 360:
        return "unknown"
    if lat is not None and lon is not None:
        d = travel_direction(course, lat, lon)
        if d is None:
            return "unknown"  # off the Mississippi: don't guess
        return up if d == "upbound" else down
    return up if _compass_fallback(course) == "up" else down
