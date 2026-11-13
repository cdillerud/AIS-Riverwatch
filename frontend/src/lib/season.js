// Wording for the season log (GET /api/me/season).

export function fmtHm(minutes) {
  const m = Math.round(Number(minutes) || 0);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60), r = m % 60;
  return r ? `${h} h ${r} min` : `${h} h`;
}

export function seasonLine(b) {
  if (!b) return "";
  const parts = [`${Math.round(b.miles)} river miles`, `${b.hours_underway} h under way`];
  if (b.days_out) parts.push(`${b.days_out} day${b.days_out === 1 ? "" : "s"} out`);
  parts.push(`${b.locks_passed} lock${b.locks_passed === 1 ? "" : "s"}`);
  if (b.locks_passed) parts.push(`${fmtHm(b.minutes_at_locks)} at locks`);
  return parts.join(" · ");
}
