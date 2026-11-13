/* River Watch service worker (hand-written, no build step).
 *
 * - App shell: page navigations are network-first and fall back to the cached
 *   page, so the app still opens with weak or no signal on the river. Hashed
 *   build files under /static/ are cache-first (their names change per build).
 * - Lock board and health (GET /api/locks/board*, /api/health): stale-while-
 *   revalidate with a short network window. The network answer is used when it
 *   arrives within NET_WAIT_MS (live waits stay live); otherwise the last saved
 *   copy is shown and the cache is refreshed in the background. Copies served
 *   from the cache carry an `X-RW-Cached-At` header so the page can say how old
 *   the data is (src/lib/connectivity.js).
 * - Never cached: auth endpoints, anything that isn't GET, other API calls,
 *   WebSockets, other origins.
 * - Alerts: showNotification is called by the page (src/lib/alertNotify.js)
 *   while the app is open, and by the `push` handler below for Web Push sent
 *   by the server while it is closed (src/lib/push.js). Tapping one focuses
 *   or opens the dashboard.
 */
const VERSION = "rw-v1";
const SHELL_CACHE = `${VERSION}-shell`;
const API_CACHE = `${VERSION}-api`;
const SHELL_URLS = ["/", "/manifest.json", "/icon-192.png", "/icon-512.png", "/favicon-32.png"];
const NET_WAIT_MS = 4000;
const API_CACHE_MAX = 40;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((c) => c.addAll(SHELL_URLS))
      .catch(() => { /* offline during install: runtime caching fills in later */ })
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

function isAuthPath(path) {
  return path === "/api/auth" || path.startsWith("/api/auth/");
}

function isCachedApi(path) {
  return path === "/api/health" || path === "/api/locks/board" || path.startsWith("/api/locks/board/");
}

async function trimCache(cache, max) {
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - max; i += 1) await cache.delete(keys[i]);
}

async function saveApi(request, response) {
  if (!response || response.status !== 200) return;
  const headers = new Headers(response.headers);
  headers.set("X-RW-Cached-At", new Date().toISOString());
  const body = await response.clone().blob();
  const cache = await caches.open(API_CACHE);
  await cache.delete(request);          // re-insert so the key order is oldest-first
  await cache.put(request, new Response(body, { status: 200, statusText: response.statusText, headers }));
  await trimCache(cache, API_CACHE_MAX);
}

function apiStaleWhileRevalidate(event) {
  const { request } = event;
  const network = fetch(request).then((res) => {
    event.waitUntil(saveApi(request, res.clone()).catch(() => {}));
    return res;
  });
  const cached = caches.open(API_CACHE).then((c) => c.match(request));
  return new Promise((resolve, reject) => {
    let done = false;
    const fallback = () => cached.then((hit) => {
      if (done) return;
      if (hit) { done = true; resolve(hit); }
    });
    const timer = setTimeout(fallback, NET_WAIT_MS);
    network.then((res) => {
      clearTimeout(timer);
      if (!done) { done = true; resolve(res); }
    }, (err) => {
      clearTimeout(timer);
      cached.then((hit) => {
        if (done) return;
        done = true;
        if (hit) resolve(hit); else reject(err);
      });
    });
  });
}

async function navigationNetworkFirst(request) {
  try {
    const res = await fetch(request);
    if (res && res.status === 200) {
      const cache = await caches.open(SHELL_CACHE);
      await cache.put("/", res.clone());   // one copy of the SPA page serves every route
    }
    return res;
  } catch (err) {
    const hit = await caches.match("/", { cacheName: SHELL_CACHE });
    if (hit) return hit;
    throw err;
  }
}

async function staticCacheFirst(request) {
  const cache = await caches.open(SHELL_CACHE);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res && res.status === 200) cache.put(request, res.clone());
  return res;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;               // POSTs etc. go straight to the network
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;    // fonts, other hosts
  const path = url.pathname;
  if (isAuthPath(path)) return;
  if (path.startsWith("/api/")) {
    if (isCachedApi(path)) event.respondWith(apiStaleWhileRevalidate(event));
    return;                                            // every other API call: untouched
  }
  if (path.startsWith("/ws/")) return;
  if (request.mode === "navigate") {
    event.respondWith(navigationNetworkFirst(request));
    return;
  }
  if (path.startsWith("/static/") || SHELL_URLS.includes(path) || path === "/apple-touch-icon.png" || path === "/icon-maskable-512.png") {
    event.respondWith(staticCacheFirst(request));
  }
});

// Web Push from the server (backend push task, lib/push.js): alerts while
// River Watch is closed. Payload: {title, body, tag, url, silent} - text only.
self.addEventListener("push", (event) => {
  let d = {};
  try {
    d = event.data ? event.data.json() : {};
  } catch (e) {
    d = { body: event.data ? event.data.text() : "" };
  }
  const url = typeof d.url === "string" && d.url.startsWith("/") && !d.url.startsWith("//") ? d.url : "/dashboard";
  const opts = {
    body: d.body || "",
    tag: d.tag || "river-watch",
    renotify: !!d.tag,
    silent: d.silent !== false,
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    data: { url },
  };
  if (!opts.silent) opts.vibrate = [200, 100, 200];
  event.waitUntil(self.registration.showNotification(d.title || "River Watch", opts));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/dashboard";
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) {
      if (new URL(c.url).origin === self.location.origin && "focus" in c) return c.focus();
    }
    return self.clients.openWindow ? self.clients.openWindow(target) : undefined;
  })());
});
