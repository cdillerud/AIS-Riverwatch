// "Share my trip": formatting for the public /s/:token page and the share
// button. Pure functions (Jest-tested); relative imports only.
import { fmtRiverTime, fmtRiverDateTime } from "./riverTime";

const MS_MIN = 60000;
export const STALE_MINUTES = 15;
export const REFRESH_MS = 60000;
export const SHARE_HOURS = [4, 12, 24, 72];

function toMs(value) {
  if (!value) return null;
  const t = value instanceof Date ? value.getTime() : Date.parse(value);
  return Number.isNaN(t) ? null : t;
}

// 45 -> "45 min", 80 -> "1 h 20 min", 120 -> "2 h"
export function fmtDuration(minutes) {
  if (minutes === null || minutes === undefined || Number.isNaN(Number(minutes))) return "";
  const m = Math.max(0, Math.round(Number(minutes)));
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r ? `${h} h ${r} min` : `${h} h`;
}

// "just now", "2 min ago", "1 h 5 min ago"
export function fmtAgo(value, nowMs = Date.now()) {
  const t = toMs(value);
  if (t === null) return "";
  const mins = Math.floor((nowMs - t) / MS_MIN);
  if (mins < 1) return "just now";
  return `${fmtDuration(mins)} ago`;
}

export function isStale(value, nowMs = Date.now()) {
  const t = toMs(value);
  return t === null || nowMs - t > STALE_MINUTES * MS_MIN;
}

export function fmtRm(rm) {
  return rm === null || rm === undefined ? "" : `RM ${Number(rm).toFixed(1)}`;
}

// "RM 812.4 · 7.2 mph upriver · updated 2 min ago"
export function statusLine(d, nowMs = Date.now()) {
  if (!d || !d.has_position) return "Position not available yet";
  const parts = [];
  if (d.status === "at_lock" && d.at_lock) parts.push(`At ${d.at_lock}`);
  if (d.river_mile !== null && d.river_mile !== undefined) parts.push(fmtRm(d.river_mile));
  if (d.status === "underway") {
    parts.push(`${Number(d.speed_mph || 0).toFixed(1)} mph${d.direction ? ` ${d.direction}` : ""}`);
  } else if (d.status === "stopped") {
    parts.push("stopped");
  }
  if (d.updated_at) parts.push(`updated ${fmtAgo(d.updated_at, nowMs)}`);
  return parts.join(" · ");
}

// "about 20 min wait (likely 10-35)" / "no wait expected"
export function waitText(next) {
  if (!next || next.wait_minutes === null || next.wait_minutes === undefined) return "";
  const w = Number(next.wait_minutes);
  const range = Array.isArray(next.wait_range_minutes) && next.wait_range_minutes.length === 2
    && next.wait_range_minutes.every((x) => x !== null && x !== undefined)
    ? ` (likely ${Math.round(next.wait_range_minutes[0])}–${Math.round(next.wait_range_minutes[1])} min)`
    : "";
  if (w < 1) return `no wait expected${range}`;
  return `about ${fmtDuration(w)} wait${range}`;
}

// "Lock 3 (RM 796.9) · arrives about 3:57 PM"
export function nextLockLine(next) {
  if (!next || !next.name) return "";
  const at = next.eta_at ? ` · arrives about ${fmtRiverTime(next.eta_at)}` : "";
  return `${next.name}${next.river_mile !== null && next.river_mile !== undefined ? ` (${fmtRm(next.river_mile)})` : ""}${at}`;
}

export function destinationLine(dest) {
  if (!dest || dest.river_mile === null || dest.river_mile === undefined) return "";
  if (!dest.eta_at) return `${fmtRm(dest.river_mile)} · no ETA while stopped or heading away`;
  return `${fmtRm(dest.river_mile)} · about ${fmtRiverTime(dest.eta_at)} (${fmtDuration(dest.eta_minutes)})`;
}

export function untilLine(expiresAt) {
  const t = toMs(expiresAt);
  return t === null ? "" : `Link works until ${fmtRiverDateTime(expiresAt)}`;
}

export function shareUrl(origin, token) {
  return `${String(origin || "").replace(/\/+$/, "")}/s/${encodeURIComponent(token)}`;
}

export function shareText(boatName) {
  return `Follow ${boatName || "my boat"} on the river (River Watch)`;
}

// Vertical river strip: upriver (higher river miles) at the top. Returns the
// marks with a 0-100 "top" percentage, or [] when there is nothing to place.
export function stripMarks(d) {
  if (!d || d.river_mile === null || d.river_mile === undefined) return [];
  const marks = [{ kind: "boat", label: d.boat_name || "Boat", rm: Number(d.river_mile) }];
  if (d.next_lock && d.next_lock.river_mile !== null && d.next_lock.river_mile !== undefined) {
    marks.push({ kind: "lock", label: d.next_lock.name, rm: Number(d.next_lock.river_mile) });
  }
  if (d.destination && d.destination.river_mile !== null && d.destination.river_mile !== undefined) {
    marks.push({ kind: "destination", label: "Destination", rm: Number(d.destination.river_mile) });
  }
  const rms = marks.map((m) => m.rm);
  let hi = Math.max(...rms);
  let lo = Math.min(...rms);
  if (hi - lo < 4) { hi += 2; lo -= 2; }
  const pad = (hi - lo) * 0.1;
  hi += pad; lo -= pad;
  return marks.map((m) => ({ ...m, top: Math.round(((hi - m.rm) / (hi - lo)) * 1000) / 10 }));
}
