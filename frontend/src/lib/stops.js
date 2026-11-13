// Marinas ahead with an arrival estimate: cruising time from the last point
// you pass (your position, or leaving a lock) - so lock waits and lockages
// on the way are counted - and whether you'd get there after dark.
import { isDark, positionAtRm } from "./sun";

// anchors: [{rm, departMinutes}] - where you are now (minutes 0) and when you
// leave each lock ahead, in travel order.
export function stopsAhead(marinas, { fromRm, direction, mph, anchors = [], now = new Date(), locks = [], limit = 6, maxMiles = 80 }) {
  const rm0 = Number(fromRm);
  const speed = Number(mph);
  if (!Array.isArray(marinas) || !Number.isFinite(rm0) || !(speed > 0)) return [];
  const up = direction === "upbound";
  const ahead = (rm) => (up ? rm > rm0 + 0.2 : rm < rm0 - 0.2);
  const pts = [{ rm: rm0, departMinutes: 0 }, ...anchors.filter((a) => Number.isFinite(Number(a.rm)))]
    .sort((a, b) => (up ? a.rm - b.rm : b.rm - a.rm));
  const out = [];
  for (const m of marinas) {
    const rm = Number(m.river_mile);
    if (!ahead(rm) || Math.abs(rm - rm0) > maxMiles) continue;
    // last point at or before the marina in travel order
    let from = pts[0];
    for (const p of pts) {
      if (up ? p.rm <= rm : p.rm >= rm) from = p;
    }
    const eta = from.departMinutes + (Math.abs(rm - from.rm) / speed) * 60;
    const arriveAt = new Date(now.getTime() + eta * 60000);
    const pos = positionAtRm(rm, locks);
    out.push({ ...m, miles: Math.abs(rm - rm0), etaMinutes: eta, arriveAt, dark: isDark(arriveAt, pos.lat, pos.lon) });
  }
  out.sort((a, b) => a.miles - b.miles);
  return out.slice(0, limit);
}

// Lock departure times from a departure option (GET /departure-options):
// arrive + expected wait + your own share of the lockage time.
export function anchorsFromOption(option, locks) {
  if (!option || !Array.isArray(option.locks) || !option.locks.length) return [];
  const waits = option.locks.reduce((s, l) => s + Number(l.wait_minutes || 0), 0);
  const ownLockage = Math.max(0, (Number(option.time_at_locks_minutes || 0) - waits) / option.locks.length);
  const rmOf = (id) => {
    const l = (locks || []).find((x) => x.id === id || x.lock_id === id);
    return l ? Number(l.river_mile) : NaN;
  };
  return option.locks.map((l) => ({
    rm: rmOf(l.lock_id),
    departMinutes: Number(option.depart_in_minutes || 0) + Number(l.arrive_minutes || 0) + Number(l.wait_minutes || 0) + ownLockage,
  }));
}

// Lock departure times from trip-plan legs (under way).
export function anchorsFromLegs(legs) {
  return (legs || [])
    .filter((l) => l.lock_rm != null && (l.depart_eta_minutes != null || l.user_eta_minutes != null))
    .map((l) => ({ rm: Number(l.lock_rm), departMinutes: Number(l.depart_eta_minutes ?? l.user_eta_minutes) }));
}
