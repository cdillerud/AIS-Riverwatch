// Live AIS boats (what Boat Beacon shows) placed at the lock they matter to,
// so each lock card lists them next to the USACE queue.
//  - Under way with a known direction: the next lock in that direction,
//    if it is within HEADING_RANGE_MI.
//  - Stopped (or direction unknown): the nearest lock, if within STOPPED_RANGE_MI
//    (tows usually wait 1-3 mi off the lock).
import { isUpbound, isDownbound } from "../utils/vesselDisplay";

export const HEADING_RANGE_MI = 15;
export const STOPPED_RANGE_MI = 3;
const MOVING_KNOTS = 1.5;
const KNOTS_TO_MPH = 1.15078;

export function aisNearLocks(vessels, locks) {
  const sorted = (locks || [])
    .filter(l => Number.isFinite(Number(l.river_mile)))
    .map(l => ({ id: l.id || l.lock_id, rm: Number(l.river_mile) }))
    .sort((a, b) => a.rm - b.rm);
  const out = {};
  if (!sorted.length) return out;
  for (const v of vessels || []) {
    const rm = Number(v.river_mile);
    if (v.river_mile == null || !Number.isFinite(rm)) continue;
    const knots = Number(v.speed) || 0;
    const up = isUpbound(v.heading);
    const down = isDownbound(v.heading);
    let lock = null;
    let moving = false;
    if (knots >= MOVING_KNOTS && (up || down)) {
      // River miles increase upstream.
      lock = up ? sorted.find(l => l.rm > rm) : [...sorted].reverse().find(l => l.rm < rm);
      if (lock && Math.abs(lock.rm - rm) > HEADING_RANGE_MI) lock = null;
      moving = true;
    }
    if (!moving) {
      lock = sorted.reduce((best, l) => (Math.abs(l.rm - rm) < Math.abs(best.rm - rm) ? l : best), sorted[0]);
      if (Math.abs(lock.rm - rm) > STOPPED_RANGE_MI) lock = null;
    }
    if (!lock) continue;
    const dist = Math.abs(lock.rm - rm);
    (out[lock.id] = out[lock.id] || []).push({
      vessel: v,
      distance_mi: Math.round(dist * 10) / 10,
      side: rm >= lock.rm ? "above" : "below",
      moving,
      direction: up ? "upbound" : down ? "downbound" : null,
      eta_minutes: moving ? Math.round((dist / (knots * KNOTS_TO_MPH)) * 60) : null,
    });
  }
  for (const id of Object.keys(out)) out[id].sort((a, b) => a.distance_mi - b.distance_mi);
  return out;
}
