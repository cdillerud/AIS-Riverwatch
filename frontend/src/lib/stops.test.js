import { stopsAhead, anchorsFromOption, anchorsFromLegs } from "./stops";

const M = [
  { osm_id: "a", name: "Twin City Marina", river_mile: 830.3 },
  { osm_id: "b", name: "Hastings Marina", river_mile: 813.4 },
  { osm_id: "c", name: "Red Wing Yacht Club", river_mile: 791.8 },
  { osm_id: "d", name: "Watergate Marina", river_mile: 844.9 },
];
const NOW = new Date("2026-11-12T16:00:00Z"); // 10 am CST

test("downriver from RM 828: marinas ahead only, nearest first, lock time counted", () => {
  // Lock 2 at 815.2: leave it 30 min later than cruising alone would
  const anchors = [{ rm: 815.2, departMinutes: (12.8 / 10) * 60 + 30 }];
  const rows = stopsAhead(M, { fromRm: 828, direction: "downbound", mph: 10, anchors, now: NOW });
  expect(rows.map((r) => r.name)).toEqual(["Hastings Marina", "Red Wing Yacht Club"]);
  // both are below Lock 2 (Hastings Marina is just downstream of it): lock time counted
  expect(Math.round(rows[0].etaMinutes)).toBe(Math.round((14.6 / 10) * 60 + 30));
  expect(Math.round(rows[1].etaMinutes)).toBe(Math.round((36.2 / 10) * 60 + 30));
  const none = stopsAhead(M, { fromRm: 828, direction: "downbound", mph: 10, now: NOW });
  expect(Math.round(none[0].etaMinutes)).toBe(Math.round((14.6 / 10) * 60)); // no locks given: cruising only
  expect(rows[0].dark).toBe(false);
});

test("upriver picks the other side", () => {
  const rows = stopsAhead(M, { fromRm: 828, direction: "upbound", mph: 10, now: NOW });
  expect(rows.map((r) => r.name)).toEqual(["Twin City Marina", "Watergate Marina"]);
});

test("anchors from a departure option and from trip-plan legs", () => {
  const opt = { depart_in_minutes: 0, time_at_locks_minutes: 50, locks: [{ lock_id: "lock_2", arrive_minutes: 80, wait_minutes: 30 }] };
  expect(anchorsFromOption(opt, [{ id: "lock_2", river_mile: 815.2 }])).toEqual([{ rm: 815.2, departMinutes: 130 }]);
  expect(anchorsFromLegs([{ lock_rm: 815.2, depart_eta_minutes: 95 }, { lock_rm: null }])).toEqual([{ rm: 815.2, departMinutes: 95 }]);
  expect(stopsAhead(null, { fromRm: 1, direction: "upbound", mph: 5 })).toEqual([]);
});
