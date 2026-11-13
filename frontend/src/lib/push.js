// Web Push: alerts that reach the phone while River Watch is closed.
//
// The header bell (components/AlertsPicker.jsx) turns alerts on; when the
// browser supports PushManager and the server has VAPID keys (GET
// /api/push/key), hooks/usePushAlerts.js subscribes this browser and sends the
// subscription plus the alert settings to POST /api/push/subscribe. The server
// runs the same rules as lib/alerts.js every minute (backend
// services/push_rules.py) and pushes; public/sw.js shows the notification.
//
// While the app is on screen it reports so (POST /api/push/presence) and the
// server holds back: the open app shows the alert as a toast instead.
//
// Pure helpers first (tested in push.test.js), then the browser plumbing.
import { API } from "./api";
import { readPrefs } from "./departure";

// --- pure -------------------------------------------------------------------

// VAPID public key (base64url) -> Uint8Array for applicationServerKey.
export function urlBase64ToUint8Array(base64String) {
  const s = String(base64String || "");
  const padded = s + "=".repeat((4 - (s.length % 4)) % 4);
  const b64 = padded.replace(/-/g, "+").replace(/_/g, "/");
  const raw = typeof atob === "function" ? atob(b64) : Buffer.from(b64, "base64").toString("binary");
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

// Does an existing subscription's applicationServerKey match the server's key?
export function sameKey(buffer, base64Key) {
  if (!buffer || !base64Key) return false;
  const a = new Uint8Array(buffer);
  const b = urlBase64ToUint8Array(base64Key);
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) return false;
  return true;
}

// What the server needs to run the rules: the bell's settings plus the
// departure planner's direction / speed (a stopped boat has no heading).
export function pushPrefs(settings, departure = { direction: "downbound", mph: 15 }) {
  const s = settings || {};
  return {
    tow: !!s.tow,
    towMiles: Number(s.towMiles),
    lock: !!s.lock,
    lockWaitMinutes: Number(s.lockWaitMinutes),
    depart: !!s.depart,
    sound: !!s.sound,
    direction: departure?.direction,
    mph: Number(departure?.mph),
  };
}

// status -> { closed: alerts arrive with the app closed?, text }
const OPEN_ONLY = "Alerts arrive only while River Watch is open";
export const PUSH_STATUS_TEXT = {
  active: "Alerts reach you even when River Watch is closed.",
  pending: "Setting up alerts for when River Watch is closed…",
  off: `${OPEN_ONLY}.`,
  "no-boat": `${OPEN_ONLY}: add your boat (Settings > Your Vessel) for alerts with the app closed.`,
  "no-server": `${OPEN_ONLY}: this server isn't set up to send them with the app closed.`,
  unsupported: `${OPEN_ONLY}: this browser can't receive them when it's closed (on iPhone, add River Watch to the Home Screen first).`,
  "no-worker": `${OPEN_ONLY} (the installable app isn't active in this browser).`,
  permission: `${OPEN_ONLY}: allow notifications to get them with the app closed.`,
  error: `${OPEN_ONLY}: couldn't sign this phone up for alerts with the app closed. Try again later.`,
};

export function pushStatusText(status) {
  return PUSH_STATUS_TEXT[status] || PUSH_STATUS_TEXT.off;
}

// --- status store ---------------------------------------------------------------

const STATUS_EVENT = "rw-push-status";
const RESYNC_EVENT = "rw-push-resync";
let status = "off";
let endpoint = null;

export function getPushStatus() {
  return status;
}

export function pushActive() {
  return status === "active";
}

function setStatus(s) {
  status = s;
  try { window.dispatchEvent(new CustomEvent(STATUS_EVENT, { detail: s })); } catch { /* no window */ }
}

export function onPushStatusChange(fn) {
  if (typeof window === "undefined") return () => {};
  const h = (e) => fn(e.detail);
  window.addEventListener(STATUS_EVENT, h);
  return () => window.removeEventListener(STATUS_EVENT, h);
}

// Ask the hook to sync again (e.g. right after notification permission was granted).
export function requestPushResync() {
  try { window.dispatchEvent(new CustomEvent(RESYNC_EVENT)); } catch { /* no window */ }
}

export function onPushResync(fn) {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(RESYNC_EVENT, fn);
  return () => window.removeEventListener(RESYNC_EVENT, fn);
}

// --- browser plumbing ----------------------------------------------------------------

export function pushSupported() {
  return typeof window !== "undefined" && "serviceWorker" in navigator
    && "PushManager" in window && "Notification" in window;
}

let keyPromise = null;
async function serverKey() {
  if (!keyPromise) {
    keyPromise = fetch(`${API}/push/key`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => (d && d.enabled && d.public_key) || null)
      .catch(() => null);
    // Don't remember a failure (offline, signed out) for good.
    keyPromise.then((k) => { if (!k) keyPromise = null; });
  }
  return keyPromise;
}

// The service worker registration (production builds register public/sw.js).
async function registration() {
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    if (reg) return reg;
    return await Promise.race([
      navigator.serviceWorker.ready,
      new Promise((resolve) => setTimeout(() => resolve(null), 4000)),
    ]);
  } catch {
    return null;
  }
}

async function currentSubscription() {
  if (!pushSupported()) return null;
  const reg = await registration();
  if (!reg || !reg.pushManager) return null;
  try { return await reg.pushManager.getSubscription(); } catch { return null; }
}

const jsonHeaders = { "Content-Type": "application/json" };

// Syncs run one at a time, in order.
let chain = Promise.resolve();
function serial(fn) {
  const run = chain.then(fn, fn);
  chain = run.catch(() => {});
  return run;
}

async function doSync(settings, userMmsi) {
  if (!settings || !settings.enabled) { await doUnsubscribe(); setStatus("off"); return; }
  if (!userMmsi) { await doUnsubscribe(); setStatus("no-boat"); return; }
  if (!pushSupported()) { setStatus("unsupported"); return; }
  if (window.Notification.permission !== "granted") { setStatus("permission"); return; }
  if (status !== "active") setStatus("pending");
  const key = await serverKey();
  if (!key) { setStatus("no-server"); return; }
  const reg = await registration();
  if (!reg || !reg.pushManager) { setStatus("no-worker"); return; }
  try {
    let sub = await reg.pushManager.getSubscription();
    if (sub && sub.options && sub.options.applicationServerKey && !sameKey(sub.options.applicationServerKey, key)) {
      await sub.unsubscribe();   // the server's keys changed
      sub = null;
    }
    if (!sub) {
      sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key) });
    }
    const r = await fetch(`${API}/push/subscribe`, {
      method: "POST",
      headers: jsonHeaders,
      credentials: "include",
      body: JSON.stringify({ subscription: sub.toJSON(), mmsi: String(userMmsi), prefs: pushPrefs(settings, readPrefs()) }),
    });
    if (!r.ok) { setStatus(r.status === 403 ? "no-boat" : "error"); return; }
    const data = await r.json();
    endpoint = sub.endpoint;
    setStatus(data.enabled ? "active" : "no-server");
  } catch {
    setStatus("error");
  }
}

async function doUnsubscribe() {
  const sub = await currentSubscription();
  const ep = (sub && sub.endpoint) || endpoint;
  endpoint = null;
  if (ep) {
    try {
      await fetch(`${API}/push/subscribe`, {
        method: "DELETE", headers: jsonHeaders, credentials: "include", body: JSON.stringify({ endpoint: ep }),
      });
    } catch { /* offline: the server drops it once the push service says it's gone */ }
  }
  if (sub) { try { await sub.unsubscribe(); } catch { /* ignore */ } }
}

export function syncPush(settings, userMmsi) {
  return serial(() => doSync(settings, userMmsi));
}

// Alerts off, or signing out (call before the session ends: DELETE needs it).
export function unsubscribePush() {
  return serial(async () => { await doUnsubscribe(); setStatus("off"); });
}

// The app is on screen / was hidden. keepalive: still sent while the page hides.
export function reportPresence(visible) {
  if (!endpoint || status !== "active") return;
  try {
    fetch(`${API}/push/presence`, {
      method: "POST", headers: jsonHeaders, credentials: "include", keepalive: true,
      body: JSON.stringify({ endpoint, visible: !!visible }),
    }).catch(() => {});
  } catch { /* ignore */ }
}
