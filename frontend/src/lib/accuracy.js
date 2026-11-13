// Plain-language lines for the public accuracy page (GET /api/accuracy).

export const MIN_SCORED = 20;   // fewer live lockages than this: "collecting", not a number

export function waitHeadline(summary, kindLabel) {
  if (!summary || summary.n < MIN_SCORED) return null;
  return {
    label: kindLabel,
    typical: `${Math.round(summary.median_abs_error_minutes)} min`,
    within30: `${summary.within_30_pct}%`,
    inRange: summary.in_range_pct == null ? null : `${summary.in_range_pct}%`,
    n: summary.n,
  };
}

export function collectingNote(waits) {
  const scored = (waits && waits.overall && waits.overall.n) || 0;
  if (scored >= MIN_SCORED) return null;
  const logged = (waits && waits.logged) || 0;
  return `The live record is new: ${logged} arrival${logged === 1 ? "" : "s"} logged and ${scored} scored so far. ` +
    `Results appear here once ${MIN_SCORED} lockages are scored.`;
}

export function signedMinutes(m) {
  if (m == null) return "";
  const r = Math.round(m);
  if (r === 0) return "on time";
  return r > 0 ? `${r} min high` : `${-r} min low`;
}

// Held-out test score from the nightly recalibration.
export function modelTestLine(test) {
  const sc = test && test.score;
  if (!sc || !sc.all) return null;
  const tow = sc.tow, rec = sc.recreational;
  const parts = [];
  if (tow) parts.push(`${Math.round(tow.median_abs_error)} min for tows (${Math.round(tow.within_30 * 100)}% within 30 min)`);
  if (rec) parts.push(`${Math.round(rec.median_abs_error)} min for pleasure boats`);
  const detail = parts.length ? parts.join(" and ") : `${Math.round(sc.all.median_abs_error)} min`;
  return `On ${sc.all.n.toLocaleString()} recent lockages held back from training, the wait model's typical miss was ${detail}.`;
}