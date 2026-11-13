import { feedBanner, fmtDowntime } from "./feedStatus";

const NOW = new Date("2026-11-13T02:00:00Z");

test("no banner while the feed is up, unconfigured, or only briefly down", () => {
  expect(feedBanner(null, NOW)).toBeNull();
  expect(feedBanner({ ais_feed: { status: "ok" } }, NOW)).toBeNull();
  expect(feedBanner({ ais_feed: { status: "not_configured" } }, NOW)).toBeNull();
  expect(feedBanner({ ais_feed: { status: "down", last_message_minutes_ago: 2 } }, NOW)).toBeNull();
});

test("banner uses the outage start when the server knows it", () => {
  const b = feedBanner({ ais_feed: { status: "down", last_message_minutes_ago: 3, down_since: "2026-11-12T19:58:00Z" } }, NOW);
  expect(b.title).toBe("Tow positions are not updating (6 h 2 min)");
  expect(b.detail).toMatch(/since .*\. Lock queues/);
});

test("banner without history falls back to the last message age", () => {
  const b = feedBanner({ ais_feed: { status: "down", last_message_minutes_ago: 45 } }, NOW);
  expect(b.title).toBe("Tow positions are not updating (45 min)");
});

test("durations", () => {
  expect(fmtDowntime(59)).toBe("59 min");
  expect(fmtDowntime(120)).toBe("2 h");
  expect(fmtDowntime(60 * 26)).toBe("1 day 2 h");
});
