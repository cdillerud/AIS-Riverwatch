import { aisNearLocks } from "./aisAtLocks";

const LOCKS = [
  { id: "lock_1", river_mile: 847.6 },
  { id: "lock_2", river_mile: 815.2 },
  { id: "lock_3", river_mile: 796.9 },
];

test("a stopped boat at a lock is listed there", () => {
  const r = aisNearLocks([{ mmsi: "1", river_mile: 815.2, speed: 0 }], LOCKS);
  expect(r.lock_2).toHaveLength(1);
  expect(r.lock_2[0].moving).toBe(false);
});

test("a stopped boat far from any lock is not listed", () => {
  const r = aisNearLocks([{ mmsi: "1", river_mile: 833.5, speed: 0 }], LOCKS);
  expect(r).toEqual({});
});

test("a downbound boat goes to the next lock below it, with an ETA", () => {
  const r = aisNearLocks([{ mmsi: "1", river_mile: 823, speed: 5.2, heading: "southbound" }], LOCKS);
  expect(Object.keys(r)).toEqual(["lock_2"]);
  expect(r.lock_2[0].side).toBe("above");
  expect(r.lock_2[0].eta_minutes).toBe(Math.round((7.8 / (5.2 * 1.15078)) * 60));
});

test("an upbound boat goes to the next lock above it", () => {
  const r = aisNearLocks([{ mmsi: "1", river_mile: 805, speed: 5, heading: "northbound" }], LOCKS);
  expect(Object.keys(r)).toEqual(["lock_2"]);
  expect(r.lock_2[0].side).toBe("below");
});

test("a moving boat more than 15 miles from its next lock is not listed", () => {
  const r = aisNearLocks([{ mmsi: "1", river_mile: 830, speed: 5, heading: "northbound" }], LOCKS);
  expect(r).toEqual({});
});
