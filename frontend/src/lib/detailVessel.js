// Turn a boat listed at a lock (USACE queue row, AIS row, "ahead of you" row)
// into what VesselDetailModal shows. A boat with a live AIS position opens
// its live record; one known only from USACE gets a record built from the
// USACE row (name, barges, direction, lock), and the modal adds its lockage
// history by MMSI.

const norm = (x) => String(x || "").toUpperCase().replace(/[^A-Z0-9]/g, "");

function direction(d) {
  if (d === "U" || d === "upbound") return "upbound";
  if (d === "D" || d === "downbound") return "downbound";
  return d || null;
}

export function toDetailVessel(entry, liveVessels = [], lockName = null) {
  if (!entry) return null;
  // Already a live vessel (has a position)
  if (entry.river_mile != null || entry.lat != null) return entry;
  const mmsi = entry.mmsi ? String(entry.mmsi) : null;
  const name = entry.vessel_name || entry.name || null;
  const live = liveVessels.find(v => (mmsi && String(v.mmsi) === mmsi) || (name && norm(v.name) === norm(name)));
  if (live) return live;
  const barges = entry.barges ?? entry.num_barges ?? null;
  const status = entry.status || (entry.started_at || entry.sol_date ? "locking" : entry.source === "queue" || entry.arrived_at || entry.arrival_date || entry.position ? "waiting" : null);
  return {
    mmsi,
    name,
    direction: direction(entry.direction),
    barge_count: barges,
    is_tow: Number(barges) > 0,
    river_mile: null,
    usace_source: "USACE lock queue",
    usace_status: status,
    usace_lock: lockName || entry.lock_name || null,
    no_ais_position: true,
  };
}
