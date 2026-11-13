import { waitHeadline, collectingNote, signedMinutes, modelTestLine, MIN_SCORED } from "./accuracy";

const S = { n: 40, median_abs_error_minutes: 12.4, within_30_pct: 81, in_range_pct: 63 };

test("headline only once enough lockages are scored", () => {
  expect(waitHeadline({ ...S, n: MIN_SCORED - 1 }, "Tows")).toBeNull();
  expect(waitHeadline(null, "Tows")).toBeNull();
  expect(waitHeadline(S, "Tows")).toEqual({ label: "Tows", typical: "12 min", within30: "81%", inRange: "63%", n: 40 });
});

test("collecting note while the live record is small", () => {
  expect(collectingNote({ overall: null, logged: 3 })).toMatch(/3 arrivals logged and 0 scored/);
  expect(collectingNote({ overall: { n: 25 }, logged: 30 })).toBeNull();
});

test("signed error wording", () => {
  expect(signedMinutes(12.2)).toBe("12 min high");
  expect(signedMinutes(-7.6)).toBe("8 min low");
  expect(signedMinutes(0.3)).toBe("on time");
});

test("model test line", () => {
  expect(modelTestLine({ score: { all: { n: 1736, mae: 32.8, median_abs_error: 11.8 } } }))
    .toMatch(/1,736 recent lockages .* 12 min\./);
  expect(modelTestLine({ score: { all: { n: 1726, median_abs_error: 11.8 },
    tow: { median_abs_error: 12.9, within_30: 0.73 }, recreational: { median_abs_error: 0.7 } } }))
    .toMatch(/13 min for tows \(73% within 30 min\) and 1 min for pleasure boats/);
  expect(modelTestLine(null)).toBeNull();
});
