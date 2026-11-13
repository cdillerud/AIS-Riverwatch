import { seasonLine, fmtHm } from "./season";

test("season line", () => {
  expect(seasonLine({ miles: 412.4, hours_underway: 38.5, days_out: 9, locks_passed: 11, minutes_at_locks: 200 }))
    .toBe("412 river miles · 38.5 h under way · 9 days out · 11 locks · 3 h 20 min at locks");
  expect(seasonLine({ miles: 0, hours_underway: 0, days_out: 0, locks_passed: 0, minutes_at_locks: 0 }))
    .toBe("0 river miles · 0 h under way · 0 locks");
  expect(fmtHm(45)).toBe("45 min");
});
