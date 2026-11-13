// Alert rules, evaluated in the browser from data the app already loads.
// Pure functions (tested in alerts.test.js); hooks/useRiverAlerts.js feeds
// them and shows the alerts (lib/alertNotify.js).
//
// - Tow approaching: a commercial tow within N river miles of the user's boat
//   and closing (AIS vessels from the App.js WebSocket / GET /api/vessels).
// - Lock ahead busy / clearing: the predicted wait at the next lock ahead
//   (GET /api/locks/board?scope=ahead) crosses the user's threshold.
// - Best time to leave: while stopped, "leave now" becomes the best option in
//   GET /api/session/{mmsi}/departure-options after it wasn't.
//
// These run while the app is open or backgrounded on the phone. With the app
// closed, the server runs the same rules (backend services/push_rules.py -
// keep the two in step) and sends them by Web Push (lib/push.js).
import { hasRiverMile, isVesselStale, lockShortLabel, getVesselDisplayName } from "../utils/vesselDisplay";
import { directionOf } from "./timingLock";

export const DEDUPE_MS = 30 * 60 * 1000;
export const LOCK_HYSTERESIS_MIN = 5;
export const TOW_MILE_CHOICES = [1, 2, 3, 5];
export const LOCK_WAIT_CHOICES = [15, 30, 45, 60];

// Off until the boater turns them on; no sound unless asked for.
export const ALERT_DEFAULTS = {
  enabled: false,
  sound: false,
  tow: true,
  towMiles: 3,
  lock: true,
  lockWaitMinutes: 30,
  depart: true,
};

const SETTINGS_KEY = "rw-alerts";
const LOG_KEY = "rw-alert-log";
const EVENT = "rw-alerts-change";

export function normalizeSettings(raw) {
  const s = { ...ALERT_DEFAULTS };
  if (!raw || typeof raw !== "object") return s;
  for (const k of ["enabled", "sound", "tow", "lock", "depart"]) {
    if (typeof raw[k] === "boolean") s[k] = raw[k];
  }
  if (TOW_MILE_CHOICES.includes(Number(raw.towMiles))) s.towMiles = Number(raw.towMiles);
  if (LOCK_WAIT_CHOICES.includes(Number(raw.lockWaitMinutes))) s.lockWaitMinutes = Number(raw.lockWaitMinutes);
  return s;
}

export function readAlertSettings() {
  try {
    return normalizeSettings(JSON.parse(localStorage.getItem(SETTINGS_KEY) || "null"));
  } catch {
    return { ...ALERT_DEFAULTS };
  }
}

export function saveAlertSettings(s) {
  const next = normalizeSettings(s);
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(next)); } catch { /* storage unavailable */ }
  try { window.dispatchEvent(new CustomEvent(EVENT, { detail: next })); } catch { /* no window */ }
  return next;
}

export function onAlertSettingsChange(fn) {
  if (typeof window === "undefined") return () => {};
  const h = (e) => fn(e.detail || readAlertSettings());
  window.addEventListener(EVENT, h);
  return () => window.removeEventListener(EVENT, h);
}

// --- dedupe -----------------------------------------------------------------

export function readAlertLog() {
  try {
    const log = JSON.parse(localStorage.getItem(LOG_KEY) || "null");
    return log && typeof log === "object" ? log : {};
  } catch {
    return {};
  }
}

export function saveAlertLog(log) {
  try { localStorage.setItem(LOG_KEY, JSON.stringify(log)); } catch { /* ignore */ }
}

// Drop alerts whose key fired within DEDUPE_MS; returns the ones to show and
// the updated log (old entries pruned).
export function dedupe(alerts, log, now = Date.now()) {
  const next = {};
  for (const [k, t] of Object.entries(log || {})) {
    if (Number.isFinite(t) && now - t < DEDUPE_MS) next[k] = t;
  }
  const fresh = [];
  for (const a of alerts || []) {
    if (next[a.key] != null) continue;
    next[a.key] = now;
    fresh.push(a);
  }
  return { fresh, log: next };
}

// --- shared -----------------------------------------------------------------

export function fmtMinutes(m) {
  if (m == null || !Number.isFinite(Number(m))) return "—";
  const n = Math.round(Number(m));
  if (n < 60) return `${n} min`;
  const h = Math.floor(n / 60);
  const r = n % 60;
  return r ? `${h} h ${r} min` : `${h} h`;
}

const TOW_SHIP_TYPES = [31, 32, 52];        // towing, towing (large), tug
const PLEASURE_SHIP_TYPES = [36, 37];       // sailing, pleasure craft

// A commercial tow: flagged as a tow, pushing barges, or a towing/tug ship
// type. Recreational boats (ship type 36/37 without barges) never count.
export function isCommercialTow(v) {
  if (!v) return false;
  const barges = Number(v.barge_count) > 0;
  const type = Number(v.ship_type);
  if (PLEASURE_SHIP_TYPES.includes(type) && !barges) return false;
  return !!v.is_tow || barges || TOW_SHIP_TYPES.includes(type);
}

export function findUserVessel(vessels, userMmsi) {
  if (!userMmsi) return null;
  return (vessels || []).find((v) => String(v.mmsi) === String(userMmsi)) || null;
}

// Stopped: moving slower than 2 knots (same cut-off as lib/timingLock.js).
export function isStopped(v) {
  const kn = Number(v?.speed);
  return !Number.isFinite(kn) || kn < 2;
}

// --- tow approaching --------------------------------------------------------

const CLOSING_STEP_MI = 0.05;

// refs: { [mmsi]: reference distance } from the previous call (mutated copy
// returned). A tow is "closing" when it is heading toward the boat at >= 1 kn,
// or its distance has shrunk since the reference.
export function towAlerts({ vessels, userMmsi, miles = ALERT_DEFAULTS.towMiles, refs = {}, now = Date.now() }) {
  const me = findUserVessel(vessels, userMmsi);
  const nextRefs = {};
  const alerts = [];
  if (!me || !hasRiverMile(me) || isVesselStale(me, now)) return { alerts, refs: nextRefs };
  const myRm = Number(me.river_mile);
  for (const v of vessels || []) {
    if (!v || String(v.mmsi) === String(userMmsi) || v.is_user_vessel) continue;
    if (!isCommercialTow(v) || !hasRiverMile(v) || isVesselStale(v, now)) continue;
    const rm = Number(v.river_mile);
    const d = Math.abs(rm - myRm);
    if (d > miles + 1) continue;               // far away: forget it
    const key = String(v.mmsi);
    const ref = refs[key];
    // Keep the old reference until the tow has moved enough to tell.
    nextRefs[key] = ref != null && Math.abs(d - ref) < CLOSING_STEP_MI ? ref : d;
    if (d > miles) continue;
    const dir = directionOf(v);
    const moving = Number(v.speed) >= 1;
    const headingToMe = moving && ((dir === "upbound" && rm < myRm) || (dir === "downbound" && rm > myRm));
    const shrinking = ref != null && d <= ref - CLOSING_STEP_MI;
    if (!headingToMe && !shrinking) continue;
    const where = rm > myRm ? "upriver" : "downriver";
    const barges = Number(v.barge_count) > 0 ? ` with ${v.barge_count} barges` : "";
    alerts.push({
      key: `tow:${key}`,
      kind: "tow",
      title: "Tow approaching",
      body: `${getVesselDisplayName(v)}${barges}, ${d.toFixed(1)} mi ${where} and getting closer.`,
    });
  }
  return { alerts, refs: nextRefs };
}

// --- lock ahead busy / clearing ---------------------------------------------

// Predicted wait for this boat at a lock board row: at its arrival time when
// the board has it, else for arriving now. Tows get the tow wait.
export function lockWait(row, userIsTow = false) {
  if (!row) return null;
  const src = row.wait_at_arrival || { tow: row.wait_estimate_minutes, recreational: row.wait_estimate_recreational_minutes };
  const w = userIsTow ? src.tow : src.recreational;
  return w == null || !Number.isFinite(Number(w)) ? null : Number(w);
}

// prev: { lockId, level: "busy" | "clear" } from the last check (or null).
// Alerts only on a change at the same lock; the first look at a lock is silent.
export function lockAlert({ row, prev = null, thresholdMinutes = ALERT_DEFAULTS.lockWaitMinutes, userIsTow = false }) {
  if (!row || row.queue_stale) return { alert: null, state: prev };
  const wait = lockWait(row, userIsTow);
  if (wait == null) return { alert: null, state: prev };
  const sameLock = prev && prev.lockId === row.lock_id;
  let level;
  if (wait > thresholdMinutes) level = "busy";
  else if (wait <= thresholdMinutes - LOCK_HYSTERESIS_MIN) level = "clear";
  else level = sameLock ? prev.level : "clear";
  const state = { lockId: row.lock_id, level };
  if (!sameLock || prev.level === level) return { alert: null, state };
  const name = row.name || lockShortLabel(row.lock_id);
  const alert = level === "busy"
    ? { key: `lock-busy:${row.lock_id}`, kind: "lock", title: `${name}: wait going up`,
        body: `Expected wait is now about ${fmtMinutes(wait)} (over ${thresholdMinutes} min).` }
    : { key: `lock-clear:${row.lock_id}`, kind: "lock", title: `${name}: wait coming down`,
        body: `Expected wait is now about ${fmtMinutes(wait)}.` };
  return { alert, state };
}

// --- best time to leave -----------------------------------------------------

// data: the departure-options response. prevNowBest: was "leave now" best at
// the last check (null = no earlier check). Alerts on the change to best.
export function departAlert({ data, prevNowBest = null }) {
  const opts = data?.options || [];
  const nowIdx = opts.findIndex((o) => Number(o.depart_in_minutes) === 0);
  if (nowIdx < 0 || data?.best == null) return { alert: null, nowBest: prevNowBest };
  const nowBest = data.best === nowIdx;
  if (!nowBest || prevNowBest !== false) return { alert: null, nowBest };
  const mine = opts[nowIdx].time_at_locks_minutes;
  const others = opts.filter((_, i) => i !== nowIdx).map((o) => o.time_at_locks_minutes).filter((m) => Number.isFinite(Number(m)));
  const later = others.length ? Math.min(...others) : null;
  const vs = later != null && later > mine ? ` vs ${fmtMinutes(later)} if you wait` : "";
  return {
    alert: {
      key: "depart:now",
      kind: "depart",
      title: "Good time to leave",
      body: `Leaving now has the least time at locks: about ${fmtMinutes(mine)}${vs}.`,
    },
    nowBest,
  };
}
