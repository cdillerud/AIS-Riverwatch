from services import marinas as M


def _snap(lat, lon):
    # pretend latitude maps to river miles; far-off points aren't on the river
    return None if lon < -94 else round((lat - 37.0) * 100, 1)


def test_parse_keeps_named_river_marinas_once():
    els = [
        {"type": "way", "id": 1, "center": {"lat": 44.8, "lon": -93.0},
         "tags": {"leisure": "marina", "name": "Twin City Marina", "sanitary_dump_station": "yes", "phone": "651-555-0100"}},
        {"type": "node", "id": 2, "lat": 44.8, "lon": -93.0, "tags": {"leisure": "marina", "name": "Twin City Marina"}},  # duplicate
        {"type": "node", "id": 3, "lat": 44.0, "lon": -93.0, "tags": {"leisure": "marina"}},                              # unnamed
        {"type": "node", "id": 4, "lat": 44.0, "lon": -94.5, "tags": {"leisure": "marina", "name": "Lake Marina"}},      # off river
        {"type": "node", "id": 5, "lat": 43.0, "lon": -91.0, "tags": {"waterway": "fuel", "name": "Fuel Dock"}},
    ]
    out = M.parse(els, _snap)
    assert [m["name"] for m in out] == ["Twin City Marina", "Fuel Dock"]
    tc, fuel = out
    assert tc["river_mile"] == 780.0 and tc["pumpout"] and not tc["fuel"] and tc["kind"] == "marina"
    assert fuel["fuel"] and fuel["kind"] == "fuel" and fuel["osm_id"] == "node/5"


def test_between_is_in_travel_order():
    ms = [{"name": n, "river_mile": rm} for n, rm in (("A", 830), ("B", 815), ("C", 790))]
    assert [m["name"] for m in M.between(ms, 835, 800)] == ["A", "B"]      # downriver
    assert [m["name"] for m in M.between(ms, 780, 820)] == ["C", "B"]      # upriver
