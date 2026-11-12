// Fingerprint of what the map draws for a vessel list. The 30 s poll keeps
// the previous array (no re-render) only when nothing visible changed. It
// used to compare just the length and first/last MMSI, so while the live
// socket was down positions, barge counts and "in the lock" froze.
const r = (x, d) => (x == null || !Number.isFinite(Number(x)) ? "" : Number(x).toFixed(d));

export function vesselSignature(v) {
  return [
    v.mmsi, r(v.lat, 4), r(v.lon, 4), r(v.speed, 1), r(v.river_mile, 2), v.heading || "",
    v.last_ais_checkin || v.timestamp || v.last_update || "", v.name || "",
    v.barge_count ?? "", v.usace_status || "", v.in_lock ? `L${v.in_lock_id}:${v.in_lock_cut}` : "",
  ].join("|");
}

export function vesselListSignature(list) {
  return (list || []).map(vesselSignature).join(";");
}

export function sameVesselList(a, b) {
  return (a?.length || 0) === (b?.length || 0) && vesselListSignature(a) === vesselListSignature(b);
}
