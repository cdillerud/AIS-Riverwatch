// "In the lock": USACE logged the start of this vessel's lockage and not the
// end (the server also checks its position is at that lock).

export function shortLockName(lockId) {
  if (!lockId) return "";
  if (lockId === "melvin_price") return "Mel Price";
  if (lockId === "chain_of_rocks") return "Chain of Rocks";
  return lockId.replace("lock_", "L").toUpperCase();
}

export function minutesSince(iso, nowMs) {
  const t = iso ? Date.parse(iso) : NaN;
  if (!Number.isFinite(t)) return null;
  return Math.max(0, Math.round((nowMs - t) / 60000));
}

function fmtMinutes(m) {
  if (m == null) return "";
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ""}`;
}

// Map vessel (from /api/vessels) -> label parts, or null when not in a lock.
export function inLockInfo(vessel, nowMs = Date.now()) {
  if (!vessel?.in_lock) return null;
  const minutes = minutesSince(vessel.in_lock_since, nowMs);
  const cut = vessel.in_lock_cut > 1 ? vessel.in_lock_cut : null;
  const parts = [`In lock ${shortLockName(vessel.in_lock_id)}`.trim()];
  if (minutes != null) parts.push(fmtMinutes(minutes));
  if (cut) parts.push(`cut ${cut}`);
  return { lockId: vessel.in_lock_id, minutes, cut, label: parts.join(" · ") };
}

// USACE queue entry at a lock (lock board) -> is it in the chamber now?
export function queueEntryInLock(entry) {
  return Boolean(entry?.started_at);
}
