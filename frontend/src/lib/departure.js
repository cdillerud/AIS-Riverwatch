// Helpers for the departure planner (components/DeparturePlanner.jsx).

const KEY = "departurePrefs";
const DEFAULTS = { direction: "downbound", mph: 15 };

export function readPrefs() {
  try {
    const p = JSON.parse(localStorage.getItem(KEY) || "null");
    if (p && ["downbound", "upbound"].includes(p.direction) && Number(p.mph) > 0) return { direction: p.direction, mph: Number(p.mph) };
  } catch { /* storage unavailable */ }
  return { ...DEFAULTS };
}

export function savePrefs(p) {
  try { localStorage.setItem(KEY, JSON.stringify(p)); } catch { /* ignore */ }
}

// Clock time `minutes` after `fromIso` (the server's generated_at), e.g. "2:45 PM".
export function clockIn(minutes, fromIso) {
  const base = fromIso ? new Date(fromIso) : new Date();
  const t = new Date(base.getTime() + Number(minutes || 0) * 60000);
  return t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function departureLabel(minutes, fromIso) {
  if (!minutes) return "Now";
  const rel = minutes < 60 ? `+${minutes}m` : `+${minutes / 60}h`;
  return `${rel} (${clockIn(minutes, fromIso)})`;
}
