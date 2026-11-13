// Sunrise / sunset on the river, for "arrives after dark" warnings in the
// trip planner and the Auto theme. NOAA-style approximation, good to a few
// minutes - plenty for "will I tie up before dark".

// Mid-river (about Lock 10, Guttenberg IA).
export const MID_RIVER = { lat: 42.8, lon: -91.1 };

// Sunrise and sunset (ms, UTC) for the UTC day of `date`. For Central time
// that UTC day runs 6-7 pm to 6-7 pm, so "t < sunrise || t > sunset" is the
// dark test for any moment.
export function sunTimes(date, lat = MID_RIVER.lat, lon = MID_RIVER.lon) {
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

export function isDark(at, lat = MID_RIVER.lat, lon = MID_RIVER.lon) {
  const t = at instanceof Date ? at : new Date(at);
  const [rise, set] = sunTimes(t, lat, lon);
  return t.getTime() < rise || t.getTime() > set;
}

// Today's sunset (the evening of the Central-time day containing `now`).
export function sunsetOn(now, lat = MID_RIVER.lat, lon = MID_RIVER.lon) {
  const t = now instanceof Date ? now : new Date(now);
  // Central noon is 17-18 h UTC: the UTC day holding it has that evening's sunset.
  const noonish = new Date(t.getTime() - 6 * 3600e3);
  noonish.setUTCHours(18, 0, 0, 0);
  return new Date(sunTimes(noonish, lat, lon)[1]);
}

// Position along the river by river mile, interpolated between locks.
export function positionAtRm(rm, locks) {
  const pts = (locks || [])
    .filter((l) => Number.isFinite(Number(l.lat)) && Number.isFinite(Number(l.lon)) && Number.isFinite(Number(l.river_mile)))
    .map((l) => ({ rm: Number(l.river_mile), lat: Number(l.lat), lon: Number(l.lon) }))
    .sort((a, b) => a.rm - b.rm);
  const r = rm == null || rm === "" ? NaN : Number(rm);
  if (!pts.length || !Number.isFinite(r)) return MID_RIVER;
  if (r <= pts[0].rm) return { lat: pts[0].lat, lon: pts[0].lon };
  const last = pts.at(-1);
  if (r >= last.rm) return { lat: last.lat, lon: last.lon };
  for (let i = 1; i < pts.length; i++) {
    const a = pts.at(i - 1), b = pts.at(i);
    if (r <= b.rm) {
      const f = (r - a.rm) / (b.rm - a.rm);
      return { lat: a.lat + f * (b.lat - a.lat), lon: a.lon + f * (b.lon - a.lon) };
    }
  }
  return MID_RIVER;
}

// Departure options (GET /departure-options) -> which arrive after dark, and
// the latest departure that still arrives before sunset.
export function darkCheck(options, generatedAt, finishRm, locks) {
  if (!Array.isArray(options) || !options.length) return null;
  const base = new Date(generatedAt || Date.now()).getTime();
  const { lat, lon } = positionAtRm(finishRm, locks);
  const rows = options.map((o) => {
    const arrive = new Date(base + Number(o.finish_in_minutes || 0) * 60000);
    return { depart_in_minutes: o.depart_in_minutes, arrive, dark: isDark(arrive, lat, lon) };
  });
  const sunset = sunsetOn(new Date(base), lat, lon);
  const ok = rows.filter((r) => !r.dark && r.arrive <= sunset);
  const latest = ok.length ? ok.reduce((a, b) => (b.depart_in_minutes > a.depart_in_minutes ? b : a)) : null;
  return { rows, sunset, latestBeforeDark: latest ? latest.depart_in_minutes : null, anyDark: rows.some((r) => r.dark) };
}
