// Runs the alert rules in lib/alerts.js while alerts are on (per device,
// header bell -> components/AlertsPicker.jsx).
//
// - Tow approaching: checked on every vessel update (App.js WebSocket).
// - Lock ahead: GET /api/locks/board?scope=ahead&limit=1 every minute.
// - Best time to leave: GET /api/session/{mmsi}/departure-options every two
//   minutes, only while the boat is stopped.
// The two polls keep running while the tab is in the background (that is the
// point of an alert) but only when alerts are on. Alerts show as a toast while
// the page is visible and as a system notification otherwise.
//
// Nothing runs once the app is closed: that needs HTTPS hosting plus a Web
// Push backend, which is out of scope.
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { API } from "@/lib/api";
import { pageHidden } from "@/lib/visibility";
import { directionOf } from "@/lib/timingLock";
import { readPrefs } from "@/lib/departure";
import { hasRiverMile } from "@/utils/vesselDisplay";
import {
  readAlertSettings, onAlertSettingsChange, readAlertLog, saveAlertLog, dedupe,
  towAlerts, lockAlert, departAlert, findUserVessel, isStopped,
} from "@/lib/alerts";
import { showSystemNotification } from "@/lib/alertNotify";

const LOCK_POLL_MS = 60 * 1000;
const DEPART_POLL_MS = 2 * 60 * 1000;

export function useAlertSettings() {
  const [settings, setSettings] = useState(readAlertSettings);
  useEffect(() => onAlertSettingsChange(setSettings), []);
  return settings;
}

export default function useRiverAlerts({ vessels, userMmsi }) {
  const settings = useAlertSettings();
  const vesselsRef = useRef(vessels);
  vesselsRef.current = vessels;
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const towRefs = useRef({});
  const lockState = useRef(null);
  const departState = useRef(null);

  const fire = (alerts) => {
    if (!alerts.length) return;
    const { fresh, log } = dedupe(alerts, readAlertLog());
    if (!fresh.length) return;
    saveAlertLog(log);
    const inApp = (a) => toast(a.title, { description: a.body, duration: 10000 });
    for (const a of fresh) {
      if (!pageHidden()) {
        inApp(a);
      } else {
        // No notification permission: keep it as a toast for when they come back.
        showSystemNotification({ title: a.title, body: a.body, tag: a.key, sound: settingsRef.current.sound })
          .then((shown) => { if (!shown) inApp(a); });
      }
    }
  };
  const fireRef = useRef(fire);
  fireRef.current = fire;

  // Tow approaching
  useEffect(() => {
    if (!settings.enabled || !settings.tow || !userMmsi) { towRefs.current = {}; return; }
    const { alerts, refs } = towAlerts({ vessels, userMmsi, miles: settings.towMiles, refs: towRefs.current });
    towRefs.current = refs;
    fireRef.current(alerts);
  }, [vessels, userMmsi, settings.enabled, settings.tow, settings.towMiles]);

  // Lock ahead getting busy / clearing
  useEffect(() => {
    lockState.current = null;
    if (!settings.enabled || !settings.lock || !userMmsi) return undefined;
    let cancelled = false;
    const check = async () => {
      const me = findUserVessel(vesselsRef.current, userMmsi);
      if (!me || !hasRiverMile(me)) return;
      const stopped = isStopped(me);
      // A stopped boat has no heading: use the direction picked in the departure planner.
      const direction = directionOf(me) || (stopped ? readPrefs().direction : null);
      if (!direction) return;
      const rm = Number(me.river_mile);
      const p = new URLSearchParams({ from_rm: String(Math.round(rm * 2) / 2), direction, scope: "ahead", limit: "1", mmsi: String(userMmsi) });
      try {
        const r = await fetch(`${API}/locks/board?${p.toString()}`, { credentials: "include" });
        if (!r.ok || cancelled) return;
        const data = await r.json();
        // A cached board (no signal) is not news.
        if (cancelled || r.headers.get("X-RW-Cached-At")) return;
        const row = (data.locks || [])[0] || null;
        const userIsTow = !!(me.is_tow || Number(me.barge_count) > 0);
        const { alert, state } = lockAlert({
          row, prev: lockState.current, thresholdMinutes: settingsRef.current.lockWaitMinutes, userIsTow,
        });
        lockState.current = state;
        if (alert) fireRef.current([alert]);
      } catch { /* offline: try again next time */ }
    };
    check();
    const id = setInterval(check, LOCK_POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [settings.enabled, settings.lock, settings.lockWaitMinutes, userMmsi]);

  // Best time to leave (only while stopped)
  useEffect(() => {
    departState.current = null;
    if (!settings.enabled || !settings.depart || !userMmsi) return undefined;
    let cancelled = false;
    const check = async () => {
      const me = findUserVessel(vesselsRef.current, userMmsi);
      if (!me || !isStopped(me)) { departState.current = null; return; }
      const prefs = readPrefs();
      const p = new URLSearchParams({ direction: prefs.direction, cruise_mph: String(prefs.mph), max_locks: "5" });
      try {
        const r = await fetch(`${API}/session/${encodeURIComponent(userMmsi)}/departure-options?${p.toString()}`);
        if (!r.ok || cancelled) return;
        const data = await r.json();
        if (cancelled) return;
        // Changing direction or speed in the planner starts over (no alert for that).
        const plan = `${prefs.direction}|${prefs.mph}`;
        const prev = departState.current?.plan === plan ? departState.current.nowBest : null;
        const { alert, nowBest } = departAlert({ data, prevNowBest: prev });
        departState.current = { plan, nowBest };
        if (alert) fireRef.current([alert]);
      } catch { /* try again next time */ }
    };
    check();
    const id = setInterval(check, DEPART_POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [settings.enabled, settings.depart, userMmsi]);
}
