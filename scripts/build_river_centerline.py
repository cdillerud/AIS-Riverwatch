#!/usr/bin/env python3
"""
Build backend/data/umr_centerline.json from the USACE National Waterway Network.

Source: USDOT/BTS NTAD "Waterway Network" (USACE National Waterway Network),
public domain. Each link carries AMILE/BMILE (official river miles at its two
ends), so interpolating along the link geometry gives a mile-calibrated
sailing line - far better than any lat/lon formula.

Waterways used:
  6080  Mississippi River, Minneapolis MN -> mouth of Missouri R (RM 910 -> 195.5)
  6079  Mississippi River, mouth of Missouri R -> Ohio R          (RM 195.5 -> 0)

Output (compact JSON):
  {
    "source": ..., "generated_at": ...,
    "points": [[lat, lon, rm], ...]          # ordered by descending RM
    "locks":  [{"name", "rm_upper", "rm_lower", "lat", "lon"}, ...]
    "tributaries": {"ST. CROIX RIVER": [[[lat, lon], ...], ...], ...}
  }

Tributary lines (St. Croix, Minnesota, Black, Illinois, Missouri, Kaskaskia,
Ohio, ...) are used to decide which channel a position belongs to: a vessel
nearer a tributary line than the Mississippi line is not Mississippi traffic.

Usage:
  python scripts/build_river_centerline.py            # downloads from ArcGIS
  python scripts/build_river_centerline.py links.json tribs.json  # saved query results
"""
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

QUERY_URL = (
    "https://services7.arcgis.com/n1YM8pTrFmm7L4hs/ArcGIS/rest/services/"
    "Waterway_Networks/FeatureServer/1/query"
)
OUT = Path(__file__).resolve().parent.parent / "backend" / "data" / "umr_centerline.json"
MIN_SPACING_M = 80.0  # thin vertices closer than this


def _query(params: dict) -> dict:
    params = {"outSR": "4326", "f": "json", **params}
    url = QUERY_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120) as resp:
        return json.load(resp)


def fetch_links() -> dict:
    return _query({
        "where": "RIVERNAME='MISSISSIPPI RIVER' AND WATERWAY IN ('6080','6079')",
        "outFields": "LINKNUM,LINKNAME,AMILE,BMILE,WATERWAY",
    })


def fetch_tributaries() -> dict:
    return _query({
        "where": "RIVERNAME<>'MISSISSIPPI RIVER'",
        "geometry": "-93.6,36.9,-89.0,45.3",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "RIVERNAME,LINKNAME,AMILE,BMILE,WATERWAY",
    })


def build_tributaries(data: dict) -> dict:
    tribs = {}
    for f in data.get("features", []):
        name = f["attributes"]["RIVERNAME"]
        for path in f["geometry"]["paths"]:
            pts, last = [], None
            for lon, lat in path:
                if last is None or hav_m(last, (lon, lat)) >= MIN_SPACING_M * 2:
                    pts.append([round(lat, 5), round(lon, 5)])
                    last = (lon, lat)
            if (lon, lat) != last:
                pts.append([round(lat, 5), round(lon, 5)])
            if len(pts) >= 2:
                tribs.setdefault(name, []).append(pts)
    return tribs


def hav_m(a, b) -> float:
    """Haversine distance in metres between (lon, lat) pairs."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def chain_paths(paths):
    """Join a link's (possibly multipart) paths into one ordered vertex list."""
    paths = [list(p) for p in paths if len(p) >= 2]
    line = paths.pop(0)
    while paths:
        best = None
        for i, p in enumerate(paths):
            for rev in (False, True):
                q = p[::-1] if rev else p
                for at_end in (True, False):
                    d = hav_m(line[-1], q[0]) if at_end else hav_m(q[-1], line[0])
                    if best is None or d < best[0]:
                        best = (d, i, q, at_end)
        _, i, q, at_end = best
        paths.pop(i)
        line = line + q[1:] if at_end else q[:-1] + line
    return line


def build(data: dict, trib_data: dict) -> dict:
    links = []
    for f in data["features"]:
        a = f["attributes"]
        if a["AMILE"] is None or a["BMILE"] is None:
            continue
        hi, lo = max(a["AMILE"], a["BMILE"]), min(a["AMILE"], a["BMILE"])
        links.append({"name": a["LINKNAME"], "hi": hi, "lo": lo, "line": chain_paths(f["geometry"]["paths"])})
    links.sort(key=lambda l: (-l["hi"], -l["lo"]))

    # Orient every link upstream(hi) -> downstream(lo) using its neighbours.
    for i, l in enumerate(links):
        line = l["line"]
        if i + 1 < len(links):
            nxt = links[i + 1]["line"]
            d_end = min(hav_m(line[-1], nxt[0]), hav_m(line[-1], nxt[-1]))
            d_start = min(hav_m(line[0], nxt[0]), hav_m(line[0], nxt[-1]))
            if d_start < d_end:
                l["line"] = line[::-1]
        else:
            prv = links[i - 1]["line"]
            if hav_m(line[-1], prv[-1]) < hav_m(line[0], prv[-1]):
                l["line"] = line[::-1]

    points, locks = [], []
    for l in links:
        line = l["line"]
        seg = [hav_m(line[k], line[k + 1]) for k in range(len(line) - 1)]
        total = sum(seg) or 1.0
        cum = 0.0
        for k, (lon, lat) in enumerate(line):
            rm = l["hi"] - (l["hi"] - l["lo"]) * (cum / total)
            if not points or rm < points[-1][2] - 1e-9:
                if not points or hav_m((points[-1][1], points[-1][0]), (lon, lat)) >= MIN_SPACING_M or k == len(line) - 1:
                    points.append([round(lat, 6), round(lon, 6), round(rm, 3)])
            if k < len(seg):
                cum += seg[k]
        nm = l["name"].upper()
        if ("LOCK" in nm or "L/D" in nm) and (l["hi"] - l["lo"]) <= 0.5:
            mid = line[len(line) // 2]
            locks.append({"name": l["name"], "rm_upper": l["hi"], "rm_lower": l["lo"],
                          "lat": round(mid[1], 5), "lon": round(mid[0], 5)})

    return {
        "source": "USACE National Waterway Network via USDOT/BTS NTAD Waterway_Networks layer 1 "
                  "(waterways 6080, 6079); public domain",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "points": points,
        "locks": locks,
        "tributaries": build_tributaries(trib_data),
    }


def main():
    if len(sys.argv) > 2:
        data, tribs = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
    else:
        data, tribs = fetch_links(), fetch_tributaries()
    out = build(data, tribs)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    pts = out["points"]
    print(f"wrote {OUT} : {len(pts)} points, RM {pts[0][2]} -> {pts[-1][2]}, {len(out['locks'])} lock links, "
          f"{len(out['tributaries'])} tributaries")


if __name__ == "__main__":
    main()
