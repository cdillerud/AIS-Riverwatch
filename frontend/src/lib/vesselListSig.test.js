import { sameVesselList } from "./vesselListSig";

const A = { mmsi: "1", lat: 44.7, lon: -92.8, speed: 5, river_mile: 815.2, timestamp: "t1", name: "A" };
const B = { mmsi: "2", lat: 44.6, lon: -92.7, speed: 0, river_mile: 800.1, timestamp: "t1", name: "B" };

test("identical lists are the same (no re-render)", () => {
  expect(sameVesselList([A, B], [{ ...A }, { ...B }])).toBe(true);
});

test("a moved boat, a new check-in, or a boat entering a lock is a change", () => {
  expect(sameVesselList([A, B], [{ ...A, lat: 44.71 }, B])).toBe(false);
  expect(sameVesselList([A, B], [{ ...A, timestamp: "t2" }, B])).toBe(false);
  expect(sameVesselList([A, B], [A, { ...B, in_lock: true, in_lock_id: "lock_3", in_lock_cut: 1 }])).toBe(false);
  expect(sameVesselList([A, B], [A, { ...B, barge_count: 15 }])).toBe(false);
});

test("same ends, different middle used to look unchanged", () => {
  const C = { ...B, mmsi: "3" };
  expect(sameVesselList([A, B, C], [A, { ...B, mmsi: "9" }, C])).toBe(false);
});
