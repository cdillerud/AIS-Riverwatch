import { sunTimes, isDaylight, resolveTheme, applyTheme, setTheme, storedTheme } from "./theme";

test("sunrise and sunset on the river are about right", () => {
  // Guttenberg IA, Nov 12: sunrise ~6:55 CST (12:55Z), sunset ~16:40 CST (22:40Z)
  const [rise, set] = sunTimes(new Date("2026-11-12T18:00:00Z"));
  const hm = (ms) => new Date(ms).toISOString().slice(11, 16);
  expect(Math.abs(new Date(rise).getUTCHours() * 60 + new Date(rise).getUTCMinutes() - (12 * 60 + 55))).toBeLessThan(15);
  expect(Math.abs(new Date(set).getUTCHours() * 60 + new Date(set).getUTCMinutes() - (22 * 60 + 40))).toBeLessThan(15);
  expect(hm(rise) < hm(set)).toBe(true);
});

test("auto follows daylight", () => {
  expect(isDaylight(new Date("2026-11-12T18:00:00Z"))).toBe(true);   // noon CST
  expect(isDaylight(new Date("2026-11-13T02:00:00Z"))).toBe(false);  // 8 pm CST
  expect(resolveTheme("auto", new Date("2026-11-12T18:00:00Z"))).toBe("sun");
  expect(resolveTheme("auto", new Date("2026-11-13T02:00:00Z"))).toBe("dark");
  expect(resolveTheme("bogus")).toBe("dark");
});

test("choosing a theme sets the page attribute and remembers it", () => {
  setTheme("sun");
  expect(document.documentElement.dataset.theme).toBe("sun");
  expect(storedTheme()).toBe("sun");
  setTheme("night");
  expect(document.documentElement.dataset.theme).toBe("night");
  applyTheme("dark");
  expect(document.documentElement.dataset.theme).toBeUndefined();
});
