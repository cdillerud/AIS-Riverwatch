import { getConnectivity, noteApiResponse, noteApiFailure, noteBrowserOnline, offlineText, onConnectivityChange } from "./connectivity";

const fmt = (ms) => new Date(ms).toISOString().slice(11, 16);

test("live answers mean online; a failure shows the last live time", () => {
  const live = Date.parse("2026-11-12T14:41:00Z");
  noteApiResponse(null, live);
  expect(getConnectivity()).toMatchObject({ offline: false, dataAt: live });
  expect(offlineText(getConnectivity(), fmt)).toBeNull();
  noteApiFailure();
  expect(offlineText(getConnectivity(), fmt)).toBe("Offline — showing data from 14:41");
});

test("a copy served from the service worker cache shows its own time", () => {
  noteApiResponse(null, Date.parse("2026-11-12T14:00:00Z"));
  noteApiResponse("2026-11-12T14:30:00Z");
  // jsdom reports navigator.onLine = true: cached while "online" is weak signal
  expect(offlineText(getConnectivity(), fmt)).toBe("Weak signal — showing data from 14:30");
  noteApiResponse(null, Date.parse("2026-11-12T14:35:00Z"));
  expect(getConnectivity().offline).toBe(false);
});

test("browser offline/online events and listeners", () => {
  const seen = [];
  const off = onConnectivityChange((s) => seen.push(s.offline));
  noteBrowserOnline(false);
  noteBrowserOnline(true);
  off();
  expect(seen).toEqual([true, false]);
  expect(offlineText({ offline: true, weak: false, dataAt: null })).toBe("Offline — no saved data yet");
});
