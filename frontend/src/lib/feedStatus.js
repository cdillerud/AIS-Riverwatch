// Banner text when the live AIS feed is down: tow positions stop updating,
// while lock queues and waits (USACE) keep working. Shown after a few minutes
// so a brief reconnect doesn't flash it.
import { fmtRiverTime, fmtRiverDateTime } from "./riverTime";

export const BANNER_AFTER_MINUTES = 5;

export function fmtDowntime(minutes) {
  if (minutes == null) return "";
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60), m = minutes % 60;
  if (h < 24) return m ? `${h} h ${m} min` : `${h} h`;
  const d = Math.floor(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ${h % 24} h`;
}

// health = GET /api/health body. Returns null when no banner is needed.
export function feedBanner(health, now = new Date()) {
  const feed = health && health.ais_feed;
  if (!feed || feed.status !== "down") return null;
  let minutes = feed.last_message_minutes_ago;
  let since = null;
  if (feed.down_since) {
    const t = new Date(feed.down_since);
    if (!Number.isNaN(t.getTime())) {
      since = t;
      minutes = Math.max(0, Math.floor((now - t) / 60000));
    }
  }
  if (minutes != null && minutes < BANNER_AFTER_MINUTES) return null;
  const sameDay = since && now - since < 12 * 3600 * 1000;
  const when = since ? ` since ${sameDay ? fmtRiverTime(since) : fmtRiverDateTime(since)}` : "";
  const dur = minutes != null ? ` (${fmtDowntime(minutes)})` : "";
  return {
    title: `Tow positions are not updating${dur}`,
    detail: `The live AIS feed has been down${when}. Lock queues, waits and lockage times are still current from USACE.`,
  };
}
