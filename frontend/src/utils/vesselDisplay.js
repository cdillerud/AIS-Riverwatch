/**
 * Get the display name for a vessel based on user settings
 * @param {Object} vessel - The vessel object
 * @param {boolean} showNames - Whether to show names (true) or MMSIs (false)
 * @returns {string} The display name
 */
export function getVesselDisplayName(vessel, showNames = true) {
  if (!vessel) return 'Unknown';
  
  if (showNames && vessel.name) {
    return vessel.name;
  }
  
  return vessel.mmsi || 'Unknown';
}

/**
 * Get a short display name for a vessel (for compact displays)
 * @param {Object} vessel - The vessel object
 * @param {boolean} showNames - Whether to show names (true) or MMSIs (false)
 * @param {number} maxLength - Maximum length before truncating
 * @returns {string} The display name
 */
export function getVesselShortName(vessel, showNames = true, maxLength = 15) {
  const name = getVesselDisplayName(vessel, showNames);
  if (name.length > maxLength) {
    return name.substring(0, maxLength - 2) + '..';
  }
  return name;
}

/**
 * River mile helpers. `river_mile` is null when a position is off the
 * Mississippi or unknown; such vessels are excluded from river-mile views.
 */
export function hasRiverMile(vessel) {
  const rm = vessel?.river_mile;
  return rm !== null && rm !== undefined && rm !== '' && Number.isFinite(Number(rm));
}

export function formatRiverMile(rm, digits = 1) {
  if (rm === null || rm === undefined || rm === '' || !Number.isFinite(Number(rm))) return '—';
  return Number(rm).toFixed(digits);
}

/**
 * Direction helpers. Backend values: "northbound" (= upbound, toward higher
 * river mile), "southbound" (= downbound), "stationary", "unknown".
 */
export function isUpbound(heading) {
  return heading === 'northbound' || heading === 'upriver' || heading === 'upbound';
}

export function isDownbound(heading) {
  return heading === 'southbound' || heading === 'downriver' || heading === 'downbound';
}

export function directionLabel(heading) {
  if (isUpbound(heading)) return 'Upbound';
  if (isDownbound(heading)) return 'Downbound';
  if (heading === 'stationary') return 'Stationary';
  return 'Unknown';
}

/**
 * Staleness. A position older than STALE_AFTER_MS is not presented as live.
 */
export const STALE_AFTER_MS = 10 * 60 * 1000;

export function getLastSeenMs(vessel) {
  const value = vessel?.last_ais_checkin || vessel?.timestamp || vessel?.last_update;
  if (!value) return null;
  // Backend times are UTC; naive ISO strings (no Z/offset) must not be read as local time.
  const str = typeof value === 'string' && /T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(value) ? `${value}Z` : value;
  const ms = new Date(str).getTime();
  return Number.isNaN(ms) ? null : ms;
}

export function isVesselStale(vessel, nowMs = Date.now()) {
  const seen = getLastSeenMs(vessel);
  return seen !== null && nowMs - seen > STALE_AFTER_MS;
}

export function formatAgo(ms, nowMs = Date.now()) {
  if (ms === null || ms === undefined) return '--';
  const s = Math.max(0, Math.floor((nowMs - ms) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function lastSeenLabel(vessel, nowMs = Date.now()) {
  return `last seen ${formatAgo(getLastSeenMs(vessel), nowMs)}`;
}

/** Short lock label: "L2", "L5A", "Mel Price", "Chain of Rocks". */
export function lockShortLabel(lockId) {
  if (!lockId) return '';
  if (lockId === 'melvin_price') return 'Mel Price';
  if (lockId === 'chain_of_rocks') return 'Chain of Rocks';
  return `L${String(lockId).replace('lock_', '').toUpperCase()}`;
}

/** Knots -> mph string, '--' when speed is missing. */
export function formatSpeedMph(knots, digits = 1) {
  const n = Number(knots);
  if (knots === null || knots === undefined || !Number.isFinite(n)) return '--';
  return (n * 1.15078).toFixed(digits);
}
