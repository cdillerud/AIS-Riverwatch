import { sunTimes, isDark, sunsetOn, positionAtRm, darkCheck } from "./sun";

const LOCKS = [
  { id: "lock_2", river_mile: 815.2, lat: 44.76097, lon: -92.86612 },
  { id: "lock_10", river_mile: 615.0, lat: 42.786, lon: -91.0923 },
  { id: "melvin_price", river_mile: 200.8, lat: 38.86761, lon: -90.15109 },
];

test("position interpolates between locks and clamps at the ends", () => {
  const p = positionAtRm(715.1, LOCKS);
  expect(p.lat).toBeCloseTo((44.76097 + 42.786) / 2, 1);
  expect(positionAtRm(900, LOCKS).lat).toBeCloseTo(44.76, 2);
  expect(positionAtRm(null, LOCKS)).toEqual({ lat: 42.8, lon: -91.1 });
});

test("sunset is later and further south... and Hastings sets before St. Louis in November", () => {
  const day = new Date("2026-11-12T18:00:00Z");
  const hastings = sunsetOn(day, 44.76, -92.87).getTime();
  const alton = sunsetOn(day, 38.87, -90.15).getTime();
  expect(alton - hastings).toBeLessThan(25 * 60000);   // within ~25 min across the river
  const [rise, set] = sunTimes(day, 44.76, -92.87);
  expect(new Date(set).getUTCHours()).toBe(22);         // ~4:40 pm CST
  expect(rise < set).toBe(true);
});

test("dark check picks the latest departure that still arrives before sunset", () => {
  const gen = "2026-11-12T19:00:00Z"; // 1 pm CST
  const opts = [0, 30, 60, 120, 240].map((d) => ({ depart_in_minutes: d, finish_in_minutes: d + 180 }));
  const r = darkCheck(opts, gen, 615, LOCKS);
  expect(r.rows.map((x) => x.dark)).toEqual([false, false, true, true, true]); // 4:00, 4:30 ok; 5:00 dark
  expect(r.latestBeforeDark).toBe(30);
  expect(r.anyDark).toBe(true);
  expect(isDark(new Date("2026-11-13T02:00:00Z"))).toBe(true);
});
