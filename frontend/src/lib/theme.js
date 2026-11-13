// Colour themes. The choice is per device (a phone in the sun and a tablet in
// the cabin want different ones), kept in localStorage. "auto" follows the
// sun on the Upper Mississippi: Sunlight from sunrise to sunset, Dark after.
export const THEMES = [
  { id: "dark", label: "Dark", hint: "The default" },
  { id: "sun", label: "Sunlight", hint: "High contrast for bright sun" },
  { id: "night", label: "Night (red)", hint: "Red on black; keeps night vision" },
  { id: "auto", label: "Auto", hint: "Sunlight by day, Dark at night" },
];
const IDS = new Set(THEMES.map((t) => t.id));
const KEY = "rw-theme";
const EVENT = "rw-theme-change";
const META = { dark: "#020617", sun: "#ffffff", night: "#000000" };

// Mid-river (about Lock 10, Guttenberg IA).
const LAT = 42.8, LON = -91.1;

// Sunrise and sunset (ms, UTC) for the UTC day of `date`; NOAA-style
// approximation, good to a few minutes.
export function sunTimes(date, lat = LAT, lon = LON) {
  const rad = Math.PI / 180;
  const y = date.getUTCFullYear(), m = date.getUTCMonth(), d = date.getUTCDate();
  const base = Date.UTC(y, m, d);
  const day = Math.round((base - Date.UTC(y, 0, 0)) / 864e5);
  const decl = 23.44 * rad * Math.sin((2 * Math.PI * (284 + day)) / 365);
  const cosH = (Math.sin(-0.833 * rad) - Math.sin(lat * rad) * Math.sin(decl)) / (Math.cos(lat * rad) * Math.cos(decl));
  const H = Math.acos(Math.max(-1, Math.min(1, cosH))) / rad;
  const B = (2 * Math.PI * (day - 81)) / 364;
  const eot = 9.87 * Math.sin(2 * B) - 7.53 * Math.cos(B) - 1.5 * Math.sin(B);
  const noon = 720 - 4 * lon - eot;
  return [base + (noon - 4 * H) * 6e4, base + (noon + 4 * H) * 6e4];
}

export function isDaylight(now = new Date()) {
  const [rise, set] = sunTimes(now);
  const t = now.getTime();
  return t >= rise && t <= set;
}

export function resolveTheme(choice, now = new Date()) {
  if (choice === "auto") return isDaylight(now) ? "sun" : "dark";
  return IDS.has(choice) ? choice : "dark";
}

export function storedTheme() {
  try {
    const v = window.localStorage.getItem(KEY);
    return IDS.has(v) ? v : "dark";
  } catch (e) {
    return "dark";
  }
}

export function applyTheme(choice, now = new Date()) {
  if (typeof document === "undefined") return;
  const t = resolveTheme(choice, now);
  const el = document.documentElement;
  if (t === "dark") delete el.dataset.theme;
  else el.dataset.theme = t;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", META[t]);
}

export function setTheme(choice) {
  if (!IDS.has(choice)) return;
  try {
    window.localStorage.setItem(KEY, choice);
  } catch (e) {
    /* private mode: still applies for this visit */
  }
  current = choice;
  applyTheme(choice);
  window.dispatchEvent(new CustomEvent(EVENT, { detail: choice }));
}

let current = "dark";

// Call once at startup: applies the saved theme and keeps "auto" in step
// with sunrise and sunset.
export function initTheme() {
  current = storedTheme();
  applyTheme(current);
  setInterval(() => {
    if (current === "auto") applyTheme(current);
  }, 5 * 60 * 1000);
}

export function onThemeChange(fn) {
  const h = (e) => fn(e.detail);
  window.addEventListener(EVENT, h);
  return () => window.removeEventListener(EVENT, h);
}
