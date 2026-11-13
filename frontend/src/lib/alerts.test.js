import {
  ALERT_DEFAULTS, DEDUPE_MS, normalizeSettings, readAlertSettings, saveAlertSettings, onAlertSettingsChange,
  dedupe, isCommercialTow, towAlerts, lockWait, lockAlert, departAlert, isStopped,
} from "./alerts";

const NOW = Date.parse("2026-11-12T18:00:00Z");
const fresh = "2026-11-12T17:59:00Z";
const me = { mmsi: "338000001", river_mile: 700, speed: 0, heading: "stationary", last_ais_checkin: fresh, is_user_vessel: true };
const tow = (over = {}) => ({ mmsi: "367000001", name: "SHOW ME STATE", river_mile: 702, speed: 5, heading: "southbound", is_tow: true, last_ais_checkin: fresh, ...over });

describe("settings", () => {
  beforeEach(() => localStorage.clear());

  test("quiet by default: off, no sound", () => {
    expect(readAlertSettings()).toEqual(ALERT_DEFAULTS);
    expect(ALERT_DEFAULTS.enabled).toBe(false);
    expect(ALERT_DEFAULTS.sound).toBe(false);
  });

  test("saved per device and broadcast; junk values fall back to defaults", () => {
    const seen = [];
    const off = onAlertSettingsChange((s) => seen.push(s));
    saveAlertSettings({ ...ALERT_DEFAULTS, enabled: true, towMiles: 5, lockWaitMinutes: 45 });
    off();
    expect(readAlertSettings()).toMatchObject({ enabled: true, towMiles: 5, lockWaitMinutes: 45 });
    expect(seen[0]).toMatchObject({ enabled: true });
    expect(normalizeSettings({ towMiles: 99, lockWaitMinutes: "x", enabled: "yes" })).toEqual(ALERT_DEFAULTS);
    localStorage.setItem("rw-alerts", "{not json");
    expect(readAlertSettings()).toEqual(ALERT_DEFAULTS);
  });

  test("storage that throws doesn't break anything", () => {
    const spy = jest.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readAlertSettings()).toEqual(ALERT_DEFAULTS);
    spy.mockRestore();
  });
});

describe("dedupe", () => {
  test("same key within 30 minutes is dropped, later it fires again", () => {
    const a = [{ key: "tow:1" }];
    const first = dedupe(a, {}, NOW);
    expect(first.fresh).toHaveLength(1);
    expect(dedupe(a, first.log, NOW + DEDUPE_MS - 1000).fresh).toHaveLength(0);
    expect(dedupe(a, first.log, NOW + DEDUPE_MS + 1000).fresh).toHaveLength(1);
  });

  test("a different vessel or lock is not held back; duplicates in one batch collapse", () => {
    const { fresh, log } = dedupe([{ key: "tow:1" }, { key: "tow:2" }, { key: "tow:1" }], {}, NOW);
    expect(fresh.map((x) => x.key)).toEqual(["tow:1", "tow:2"]);
    expect(Object.keys(log)).toEqual(["tow:1", "tow:2"]);
  });
});

describe("tow approaching", () => {
  test("commercial tows only", () => {
    expect(isCommercialTow({ is_tow: true })).toBe(true);
    expect(isCommercialTow({ barge_count: 9 })).toBe(true);
    expect(isCommercialTow({ ship_type: 31 })).toBe(true);
    expect(isCommercialTow({ ship_type: 37, is_tow: true })).toBe(false);   // pleasure craft named "Miss ..."
    expect(isCommercialTow({ ship_type: 37 })).toBe(false);
    expect(isCommercialTow({ ship_type: 70 })).toBe(false);
  });

  test("a tow upriver coming down within range alerts", () => {
    const { alerts } = towAlerts({ vessels: [me, tow()], userMmsi: me.mmsi, miles: 3, now: NOW });
    expect(alerts).toHaveLength(1);
    expect(alerts[0].key).toBe("tow:367000001");
    expect(alerts[0].body).toMatch(/SHOW ME STATE, 2\.0 mi upriver/);
  });

  test("out of range, heading away, stale, or the user's own boat: no alert", () => {
    const run = (v, extra = {}) => towAlerts({ vessels: [me, v], userMmsi: me.mmsi, miles: 3, now: NOW, ...extra }).alerts;
    expect(run(tow({ river_mile: 704 }))).toHaveLength(0);
    expect(run(tow({ heading: "northbound" }))).toHaveLength(0);
    expect(run(tow({ last_ais_checkin: "2026-11-12T17:00:00Z" }))).toHaveLength(0);
    expect(run(tow({ ship_type: 37, is_tow: true }))).toHaveLength(0);
    expect(towAlerts({ vessels: [{ ...me, is_tow: true }], userMmsi: me.mmsi, now: NOW }).alerts).toHaveLength(0);
  });

  test("closing is also seen from the distance shrinking (no heading)", () => {
    const v = tow({ heading: "unknown", speed: 0.5, river_mile: 702.5 });
    const r1 = towAlerts({ vessels: [me, v], userMmsi: me.mmsi, now: NOW });
    expect(r1.alerts).toHaveLength(0);
    expect(r1.refs["367000001"]).toBeCloseTo(2.5);
    const r2 = towAlerts({ vessels: [me, { ...v, river_mile: 702.3 }], userMmsi: me.mmsi, refs: r1.refs, now: NOW });
    expect(r2.alerts).toHaveLength(1);
    expect(r2.alerts[0].body).toMatch(/2\.3 mi upriver/);
  });

  test("no own boat position: nothing", () => {
    expect(towAlerts({ vessels: [tow()], userMmsi: me.mmsi, now: NOW }).alerts).toEqual([]);
    expect(towAlerts({ vessels: [{ ...me, river_mile: null }, tow()], userMmsi: me.mmsi, now: NOW }).alerts).toEqual([]);
  });
});

describe("lock ahead busy / clearing", () => {
  const row = (wait, over = {}) => ({ lock_id: "lock_10", name: "Lock 10", wait_estimate_minutes: wait + 20, wait_estimate_recreational_minutes: wait, queue_stale: false, ...over });

  test("uses the wait at arrival when the board has one, tow wait for tows", () => {
    expect(lockWait(row(10))).toBe(10);
    expect(lockWait(row(10), true)).toBe(30);
    expect(lockWait(row(10, { wait_at_arrival: { tow: 70, recreational: 50 } }))).toBe(50);
  });

  test("first look is silent; crossing over then back under alerts", () => {
    let r = lockAlert({ row: row(10), prev: null, thresholdMinutes: 30 });
    expect(r.alert).toBeNull();
    expect(r.state).toEqual({ lockId: "lock_10", level: "clear" });
    r = lockAlert({ row: row(45), prev: r.state, thresholdMinutes: 30 });
    expect(r.alert.key).toBe("lock-busy:lock_10");
    expect(r.alert.title).toBe("Lock 10: wait going up");
    expect(r.alert.body).toMatch(/about 45 min/);
    r = lockAlert({ row: row(28), prev: r.state, thresholdMinutes: 30 });   // within hysteresis
    expect(r.alert).toBeNull();
    r = lockAlert({ row: row(20), prev: r.state, thresholdMinutes: 30 });
    expect(r.alert.key).toBe("lock-clear:lock_10");
  });

  test("a new lock ahead or a stale queue doesn't alert", () => {
    const prev = { lockId: "lock_9", level: "clear" };
    expect(lockAlert({ row: row(90), prev, thresholdMinutes: 30 }).alert).toBeNull();
    const busyPrev = { lockId: "lock_10", level: "clear" };
    const stale = lockAlert({ row: row(90, { queue_stale: true }), prev: busyPrev, thresholdMinutes: 30 });
    expect(stale.alert).toBeNull();
    expect(stale.state).toBe(busyPrev);
  });
});

describe("best time to leave", () => {
  const data = (best) => ({
    best,
    options: [
      { depart_in_minutes: 0, time_at_locks_minutes: 25 },
      { depart_in_minutes: 30, time_at_locks_minutes: 40 },
      { depart_in_minutes: 60, time_at_locks_minutes: 55 },
    ],
  });

  test("alerts once when leaving now becomes best after it wasn't", () => {
    let r = departAlert({ data: data(1), prevNowBest: null });
    expect(r).toEqual({ alert: null, nowBest: false });
    r = departAlert({ data: data(0), prevNowBest: r.nowBest });
    expect(r.alert.key).toBe("depart:now");
    expect(r.alert.body).toBe("Leaving now has the least time at locks: about 25 min vs 40 min if you wait.");
    r = departAlert({ data: data(0), prevNowBest: r.nowBest });
    expect(r.alert).toBeNull();
  });

  test("best on the first check is not news", () => {
    expect(departAlert({ data: data(0), prevNowBest: null }).alert).toBeNull();
    expect(departAlert({ data: { options: [] }, prevNowBest: false }).alert).toBeNull();
  });

  test("stopped means under 2 knots", () => {
    expect(isStopped({ speed: 0.4 })).toBe(true);
    expect(isStopped({ speed: 6 })).toBe(false);
    expect(isStopped({})).toBe(true);
  });
});
