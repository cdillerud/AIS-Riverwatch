import { departureLabel, readPrefs, savePrefs, clockIn } from "./departure";

test("labels departures relative to now", () => {
  const at = "2026-11-12T15:00:00Z";
  expect(departureLabel(0, at)).toBe("Now");
  expect(departureLabel(30, at)).toMatch(/^\+30m \(/);
  expect(departureLabel(120, at)).toMatch(/^\+2h \(/);
  expect(clockIn(90, at)).toBe(new Date(Date.parse(at) + 90 * 60000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }));
});

test("prefs round-trip and fall back to defaults", () => {
  localStorage.removeItem("departurePrefs");
  expect(readPrefs()).toEqual({ direction: "downbound", mph: 15 });
  savePrefs({ direction: "upbound", mph: 22 });
  expect(readPrefs()).toEqual({ direction: "upbound", mph: 22 });
  localStorage.setItem("departurePrefs", "{bad");
  expect(readPrefs()).toEqual({ direction: "downbound", mph: 15 });
});
