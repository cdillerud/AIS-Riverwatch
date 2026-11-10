// Dev server only (yarn start): forward the API and its WebSockets to the backend
// so the app works from a single origin, e.g. through an HTTPS tunnel to a
// phone. Leave REACT_APP_BACKEND_URL unset to use it. Production builds are
// served by nginx, which does the same routing.
const { createProxyMiddleware } = require("http-proxy-middleware");

const target = process.env.BACKEND_PROXY_TARGET || "http://127.0.0.1:8001";

module.exports = function setupProxy(app) {
  // Only /api: the dev server's own live-reload socket lives at /ws, so the
  // AIS feed must use /api/ws/ais here (set REACT_APP_WS_PATH=/api/ws/ais).
  app.use(createProxyMiddleware("/api", { target, ws: true, changeOrigin: false, logLevel: "warn" }));
};
