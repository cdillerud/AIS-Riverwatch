import { reportDates } from "./reportDates";

test("dates are Central-time days: 03:30 UTC is still the previous evening in Chicago", () => {
  const d = reportDates(new Date(Date.UTC(2026, 10, 11, 3, 30)), 30);
  expect(d[0].value).toBe("2026-11-10");
  expect(d[0].label).toMatch(/^Today so far/);
  expect(d[1].value).toBe("2026-11-09");
  expect(d[1].label).toMatch(/^Yesterday/);
  expect(d).toHaveLength(31);
});

test("crosses month ends", () => {
  const d = reportDates(new Date(Date.UTC(2026, 2, 1, 18)), 2);
  expect(d.map((x) => x.value)).toEqual(["2026-03-01", "2026-02-28", "2026-02-27"]);
});
