// Days the Traffic Report can cover: today (so far) back `count` days, as
// Central-time calendar days (the river's local day, which the server uses).
export function centralDateParts(at) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Chicago", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(at);
  const get = (t) => Number(parts.find((p) => p.type === t).value);
  return { y: get("year"), m: get("month"), d: get("day") };
}

export function reportDates(now, count) {
  const { y, m, d } = centralDateParts(now);
  const out = [];
  for (let i = 0; i <= count; i += 1) {
    // Noon UTC keeps the calendar arithmetic clear of DST edges.
    const dt = new Date(Date.UTC(y, m - 1, d - i, 12));
    const value = dt.toISOString().slice(0, 10);
    const pretty = dt.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
    out.push({ value, label: i === 0 ? `Today so far (${pretty})` : i === 1 ? `Yesterday (${pretty})` : pretty });
  }
  return out;
}
