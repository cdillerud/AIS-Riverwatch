// Helpers for the first-run wizard (components/FirstRunWizard.jsx).

export const MMSI_RE = /^\d{9}$/;

// One list of named places on the river: marinas (OpenStreetMap) and locks.
export function riverPlaces(marinas, locks) {
  const out = [];
  for (const m of marinas || []) {
    if (m && m.name && Number.isFinite(Number(m.river_mile))) {
      out.push({ key: `m:${m.osm_id || m.name}`, name: m.name, kind: "marina", river_mile: Number(m.river_mile), lat: m.lat, lon: m.lon });
    }
  }
  for (const l of locks || []) {
    if (l && l.name && Number.isFinite(Number(l.river_mile))) {
      out.push({ key: `l:${l.id}`, name: l.name, kind: "lock", river_mile: Number(l.river_mile), lat: l.lat, lon: l.lon });
    }
  }
  out.sort((a, b) => b.river_mile - a.river_mile);   // upriver first, as on the river
  return out;
}

export function placesAhead(places, fromRm, direction, maxMiles = 400) {
  const rm = Number(fromRm);
  if (!Number.isFinite(rm)) return [];
  return (places || [])
    .filter((p) => (direction === "upbound" ? p.river_mile > rm + 0.5 : p.river_mile < rm - 0.5))
    .filter((p) => Math.abs(p.river_mile - rm) <= maxMiles)
    .sort((a, b) => Math.abs(a.river_mile - rm) - Math.abs(b.river_mile - rm));
}

// The trip TripPlanPanel / DeparturePlanner read from localStorage("activeTrip").
export function tripFor(fromRm, dest, direction) {
  if (!dest) return null;
  return {
    trip_id: null,
    name: `To ${dest.name}`,
    start_rm: Number(fromRm),
    end_rm: dest.river_mile,
    heading: direction === "upbound" ? "northbound" : "southbound",
    departure_time: null,
    notes: "",
  };
}

export function validBoat(name, hasAis, mmsi) {
  if (!String(name || "").trim()) return "Give your boat a name";
  if (hasAis && !MMSI_RE.test(String(mmsi || ""))) return "An MMSI is 9 digits";
  if (hasAis && String(mmsi).startsWith("000")) return "That isn't a valid MMSI";
  return null;
}
