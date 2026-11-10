// Single source for backend URLs.
//
// REACT_APP_BACKEND_URL is optional. When it is unset or empty the app talks to
// its own origin (nginx proxies /api and /ws), so the same build works on the
// cloud VM, a Pi on the LAN, or any hostname.
const RAW_BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").trim().replace(/\/+$/, "");

export const BACKEND_URL =
  RAW_BACKEND_URL || (typeof window !== "undefined" ? window.location.origin : "");

export const API = `${BACKEND_URL}/api`;

// ws:// or wss:// base derived from the backend URL (https -> wss).
export const WS_BASE_URL = BACKEND_URL.replace(/^https:/i, "wss:").replace(/^http:/i, "ws:");

// AIS feed WebSocket path. The backend serves both /ws/ais and /api/ws/ais;
// pick whichever the reverse proxy forwards with Upgrade headers.
export const AIS_WS_PATH = process.env.REACT_APP_WS_PATH || "/ws/ais";
