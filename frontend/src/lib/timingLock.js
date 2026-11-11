// Which lock is "next" for a boat. Same rule as lock_is_ahead() in
// backend/services/lock_board.py: a boat stopped at a lock (on the approach
// wall or in the chamber) sits about at the lock's river mile, and that lock
// stays its target until it's under way past it. The old strict "RM < mine"
// jumped Lock Timing to the next lock (44 mi away) while still waiting at this one.

export const AT_LOCK_MI = 0.25;
export const PASSING_MI = 0.05;
export const SLOW_KNOTS = 2.0;

export function directionOf(vessel) {
  const raw = (vessel?.heading || vessel?.heading_direction || vessel?.direction || "").toString().toLowerCase();
  if (["southbound", "downriver", "downbound", "sb"].some(t => raw.includes(t))) return "downbound";
  if (["northbound", "upriver", "upbound", "nb"].some(t => raw.includes(t))) return "upbound";
  return null;
}

export function lockIsAhead(lockRm, rm, direction, speedKnots) {
  const slow = Number.isFinite(Number(speedKnots)) && Number(speedKnots) < SLOW_KNOTS;
  const tol = slow ? AT_LOCK_MI : PASSING_MI;
  if (direction === "downbound") return lockRm < rm + tol;
  if (direction === "upbound") return lockRm > rm - tol;
  return false;
}

// The next lock (object from `locks`) for a boat at `rm` going `direction`, or null.
export function nextLockAhead(locks, rm, direction, speedKnots) {
  if (!Number.isFinite(rm) || !direction) return null;
  const ahead = (locks || [])
    .filter(l => Number.isFinite(Number(l.river_mile)))
    .filter(l => lockIsAhead(Number(l.river_mile), rm, direction, speedKnots))
    .sort((a, b) => direction === "downbound"
      ? Number(b.river_mile) - Number(a.river_mile)
      : Number(a.river_mile) - Number(b.river_mile));
  return ahead[0] || null;
}
