import { inLockInfo, shortLockName, queueEntryInLock } from "./inLock";

const NOW = Date.parse("2026-11-11T22:00:00Z");

test("not in a lock -> null", () => {
  expect(inLockInfo({ in_lock: false }, NOW)).toBeNull();
  expect(inLockInfo(null, NOW)).toBeNull();
});

test("label: lock, time in the chamber, cut of a double", () => {
  const v = { in_lock: true, in_lock_id: "lock_14", in_lock_since: "2026-11-11T21:35:00+00:00", in_lock_cut: 1 };
  expect(inLockInfo(v, NOW).label).toBe("In lock L14 · 25m");
  expect(inLockInfo({ ...v, in_lock_since: "2026-11-11T20:50:00Z", in_lock_cut: 2 }, NOW).label)
    .toBe("In lock L14 · 1h 10m · cut 2");
  expect(inLockInfo({ ...v, in_lock_since: null }, NOW).label).toBe("In lock L14");
});

test("short names", () => {
  expect(shortLockName("lock_5a")).toBe("L5A");
  expect(shortLockName("melvin_price")).toBe("Mel Price");
});

test("queue entries with a lockage start are in the chamber", () => {
  expect(queueEntryInLock({ started_at: "2026-11-11T21:00:00Z" })).toBe(true);
  expect(queueEntryInLock({ started_at: null })).toBe(false);
});
