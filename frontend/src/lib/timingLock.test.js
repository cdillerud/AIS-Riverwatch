import { nextLockAhead, directionOf } from "./timingLock";

const LOCKS = [
  { id: "lock_2", river_mile: 815.2 },
  { id: "lock_3", river_mile: 796.9 },
  { id: "lock_4", river_mile: 752.8 },
];

test("under way: the next lock downstream / upstream", () => {
  expect(nextLockAhead(LOCKS, 799.3, "downbound", 20).id).toBe("lock_3");
  expect(nextLockAhead(LOCKS, 799.3, "upbound", 20).id).toBe("lock_2");
});

test("stopped at the lock keeps it as the target (was: jumped to Lock 4)", () => {
  expect(nextLockAhead(LOCKS, 796.9, "downbound", 0).id).toBe("lock_3");
  expect(nextLockAhead(LOCKS, 796.75, "downbound", 0).id).toBe("lock_3");   // in the chamber
  expect(nextLockAhead(LOCKS, 796.9, "upbound", 0).id).toBe("lock_3");
});

test("under way past the lock moves on to the next", () => {
  expect(nextLockAhead(LOCKS, 796.7, "downbound", 20).id).toBe("lock_4");
  expect(nextLockAhead(LOCKS, 797.1, "upbound", 20).id).toBe("lock_2");
});

test("no direction or position: no target", () => {
  expect(nextLockAhead(LOCKS, 796.9, null, 0)).toBeNull();
  expect(nextLockAhead(LOCKS, NaN, "downbound", 0)).toBeNull();
  expect(nextLockAhead(LOCKS, 700, "downbound", 10)).toBeNull();
});

test("direction from the vessel's heading fields", () => {
  expect(directionOf({ heading: "southbound" })).toBe("downbound");
  expect(directionOf({ heading_direction: "upriver" })).toBe("upbound");
  expect(directionOf({ heading: "stationary" })).toBeNull();
});
