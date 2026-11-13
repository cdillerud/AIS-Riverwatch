import { riverPlaces, placesAhead, tripFor, validBoat } from "./firstRun";

const MARINAS = [{ osm_id: "w/1", name: "Hastings Marina", river_mile: 813.4, lat: 44.74, lon: -92.85 }, { name: "No RM" }];
const LOCKS = [{ id: "lock_2", name: "Lock & Dam #2 (Hastings)", river_mile: 815.2, lat: 44.76, lon: -92.87 },
  { id: "lock_1", name: "Lock & Dam #1 (Minneapolis)", river_mile: 847.6, lat: 44.9, lon: -93.2 }];

test("places merge marinas and locks, upriver first", () => {
  const p = riverPlaces(MARINAS, LOCKS);
  expect(p.map((x) => x.river_mile)).toEqual([847.6, 815.2, 813.4]);
  expect(p.at(-1).kind).toBe("marina");
});

test("places ahead in the chosen direction, nearest first", () => {
  const p = riverPlaces(MARINAS, LOCKS);
  expect(placesAhead(p, 830.3, "downbound").map((x) => x.river_mile)).toEqual([815.2, 813.4]);
  expect(placesAhead(p, 830.3, "upbound").map((x) => x.river_mile)).toEqual([847.6]);
});

test("trip and boat validation", () => {
  const dest = { name: "Hastings Marina", river_mile: 813.4 };
  expect(tripFor(830.3, dest, "downbound")).toMatchObject({ name: "To Hastings Marina", start_rm: 830.3, end_rm: 813.4, heading: "southbound" });
  expect(tripFor(830.3, null, "downbound")).toBeNull();
  expect(validBoat("", false)).toMatch(/name/);
  expect(validBoat("Sea Biscuit", false)).toBeNull();
  expect(validBoat("X", true, "12345")).toMatch(/9 digits/);
  expect(validBoat("X", true, "000123456")).toMatch(/valid/);
  expect(validBoat("X", true, "338414076")).toBeNull();
});
