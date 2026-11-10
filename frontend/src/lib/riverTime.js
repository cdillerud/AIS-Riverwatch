// Lock and river times are shown in Central time, where every Upper
// Mississippi lock (and its lockmaster) keeps time - not the device's zone,
// which could be anything. "CT" is appended only when the device is in a
// different zone, so most users see plain times.
export const RIVER_TZ = "America/Chicago";

let deviceIsCentral = true;
try {
  const now = new Date();
  const fmt = (tz) => now.toLocaleString("en-US", { timeZone: tz, hour: "numeric", minute: "numeric", day: "numeric" });
  deviceIsCentral = fmt(RIVER_TZ) === fmt(Intl.DateTimeFormat().resolvedOptions().timeZone);
} catch (e) {
  deviceIsCentral = true;
}

const suffix = () => (deviceIsCentral ? "" : " CT");

function toDate(value) {
  if (!value) return null;
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtRiverTime(value) {
  const d = toDate(value);
  return d ? d.toLocaleTimeString(undefined, { timeZone: RIVER_TZ, hour: "numeric", minute: "2-digit" }) + suffix() : "";
}

export function fmtRiverDateTime(value) {
  const d = toDate(value);
  return d
    ? d.toLocaleString(undefined, { timeZone: RIVER_TZ, month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + suffix()
    : "";
}
