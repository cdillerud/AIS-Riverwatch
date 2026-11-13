import {
  fmtDuration, fmtAgo, isStale, statusLine, waitText, nextLockLine, destinationLine,
  shareUrl, stripMarks,
} from "./tripShare";

const NOW = Date.parse("2026-11-12T15:00:00Z");
const base = {
  boat_name: "REBOOT", has_position: true, river_mile: 812.44, speed_mph: 7.2, direction: "upriver",
  status: "underway", at_lock: null, updated_at: "2026-11-12T14:58:00Z",
};

test("durations and ages", () => {
  expect(fmtDuration(45)).toBe("45 min");
  expect(fmtDuration(80)).toBe("1 h 20 min");
  expect(fmtDuration(120)).toBe("2 h");
  expect(fmtDuration(null)).toBe("");
  expect(fmtAgo("2026-11-12T14:59:40Z", NOW)).toBe("just now");
  expect(fmtAgo("2026-11-12T14:58:00Z", NOW)).toBe("2 min ago");
  expect(fmtAgo("2026-11-12T13:55:00Z", NOW)).toBe("1 h 5 min ago");
  expect(isStale("2026-11-12T14:50:00Z", NOW)).toBe(false);
  expect(isStale("2026-11-12T14:30:00Z", NOW)).toBe(true);
  expect(isStale(null, NOW)).toBe(true);
});

test("status line", () => {
  expect(statusLine(base, NOW)).toBe("RM 812.4 · 7.2 mph upriver · updated 2 min ago");
  expect(statusLine({ ...base, status: "stopped", direction: null }, NOW)).toBe("RM 812.4 · stopped · updated 2 min ago");
  expect(statusLine({ ...base, status: "at_lock", at_lock: "Lock 3", river_mile: 796.9 }, NOW))
    .toBe("At Lock 3 · RM 796.9 · updated 2 min ago");
  expect(statusLine({ has_position: false }, NOW)).toBe("Position not available yet");
});

test("lock wait and destination text", () => {
  expect(waitText({ wait_minutes: 20, wait_range_minutes: [10, 35] })).toBe("about 20 min wait (likely 10–35 min)");
  expect(waitText({ wait_minutes: 0, wait_range_minutes: null })).toBe("no wait expected");
  expect(waitText({ wait_minutes: null })).toBe("");
  expect(nextLockLine({ name: "Lock 3", river_mile: 796.9, eta_at: null })).toBe("Lock 3 (RM 796.9)");
  expect(nextLockLine({ name: "Lock 3", river_mile: 796.9, eta_at: "2026-11-12T15:57:00Z" }))
    .toMatch(/^Lock 3 \(RM 796\.9\) · arrives about /);
  expect(destinationLine({ river_mile: 806.9, eta_at: null })).toMatch(/^RM 806\.9 · no ETA/);
  expect(destinationLine({ river_mile: 806.9, eta_at: "2026-11-12T17:15:00Z", eta_minutes: 135 }))
    .toMatch(/\(2 h 15 min\)$/);
  expect(destinationLine(null)).toBe("");
});

test("share url", () => {
  expect(shareUrl("https://river.example.com/", "a_b-C")).toBe("https://river.example.com/s/a_b-C");
});

test("river strip puts upriver at the top", () => {
  const marks = stripMarks({
    ...base, river_mile: 800, next_lock: { name: "Lock 3", river_mile: 796.9 },
    destination: { river_mile: 815 },
  });
  const top = Object.fromEntries(marks.map((m) => [m.kind, m.top]));
  expect(top.destination).toBeLessThan(top.boat);
  expect(top.boat).toBeLessThan(top.lock);
  marks.forEach((m) => { expect(m.top).toBeGreaterThanOrEqual(0); expect(m.top).toBeLessThanOrEqual(100); });
  expect(stripMarks({ ...base, river_mile: null })).toEqual([]);
  expect(stripMarks({ ...base })).toHaveLength(1);
});
