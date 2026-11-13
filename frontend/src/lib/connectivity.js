// Is the page offline, and how old is the data it's showing?
//
// Watches every /api fetch: a live answer means online; a network failure
// means offline; an answer the service worker (public/sw.js) served from its
// cache carries `X-RW-Cached-At`, so we know the time of that saved copy.
// navigator.onLine and the online/offline events are folded in too.

const listeners = new Set();
let state = { offline: false, weak: false, dataAt: null };
let lastLiveAt = null;

function set(next) {
  if (next.offline === state.offline && next.weak === state.weak && next.dataAt === state.dataAt) return;
  state = next;
  listeners.forEach((fn) => { try { fn(state); } catch { /* ignore */ } });
}

export function getConnectivity() {
  return state;
}

export function onConnectivityChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function navigatorOffline() {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

// A response arrived. `cachedAt` is the X-RW-Cached-At header (or null).
export function noteApiResponse(cachedAt, now = Date.now()) {
  if (cachedAt) {
    const at = Date.parse(cachedAt);
    const dataAt = Number.isFinite(at) ? Math.max(at, lastLiveAt || 0) : lastLiveAt;
    // From the cache while the phone says it's online: weak signal, not none.
    set({ offline: true, weak: !navigatorOffline(), dataAt });
    return;
  }
  lastLiveAt = now;
  set({ offline: false, weak: false, dataAt: now });
}

export function noteApiFailure() {
  set({ offline: true, weak: false, dataAt: lastLiveAt });
}

export function noteBrowserOnline(online) {
  if (online) set({ ...state, offline: false, weak: false });
  else set({ offline: true, weak: false, dataAt: lastLiveAt });
}

// "Offline - showing data from 2:41 PM" (null when online).
export function offlineText(s, fmt = (ms) => new Date(ms).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })) {
  if (!s || !s.offline) return null;
  const lead = s.weak ? "Weak signal" : "Offline";
  return s.dataAt ? `${lead} — showing data from ${fmt(s.dataAt)}` : `${lead} — no saved data yet`;
}

function isApi(url) {
  if (!url) return false;
  try {
    const u = new URL(url, typeof window !== "undefined" ? window.location.href : "http://localhost/");
    return u.pathname.startsWith("/api/");
  } catch {
    return false;
  }
}

export function installConnectivityWatch() {
  if (typeof window === "undefined" || !window.fetch || window.fetch.__riverwatchConn) return;
  const inner = window.fetch;
  const wrapped = (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input?.url;
    const p = inner(input, init);
    if (!isApi(url)) return p;
    return p.then(
      (res) => {
        try { noteApiResponse(res.headers && res.headers.get("X-RW-Cached-At")); } catch { /* ignore */ }
        return res;
      },
      (err) => {
        if (!(err && err.name === "AbortError")) noteApiFailure();
        throw err;
      },
    );
  };
  Object.assign(wrapped, inner);
  wrapped.__riverwatchConn = true;
  window.fetch = wrapped;
  window.addEventListener("online", () => noteBrowserOnline(true));
  window.addEventListener("offline", () => noteBrowserOnline(false));
  if (navigatorOffline()) noteBrowserOnline(false);
}
