// Keeps this browser's Web Push subscription in step with the header bell
// (lib/push.js): subscribes when alerts are on, re-sends the settings when they
// change, unsubscribes when alerts go off or there's no boat. While the app is
// on screen it tells the server so (the open app toasts; no push needed).
import { useEffect, useState } from "react";
import {
  syncPush, onPushResync, reportPresence, getPushStatus, onPushStatusChange,
} from "@/lib/push";
import { pageHidden } from "@/lib/visibility";

const PRESENCE_MS = 60 * 1000;

export function usePushStatus() {
  const [s, setS] = useState(getPushStatus);
  useEffect(() => onPushStatusChange(setS), []);
  return s;
}

export default function usePushAlerts({ settings, userMmsi }) {
  const status = usePushStatus();
  const { enabled, tow, towMiles, lock, lockWaitMinutes, depart, sound } = settings;

  useEffect(() => {
    const s = { enabled, tow, towMiles, lock, lockWaitMinutes, depart, sound };
    const run = () => { syncPush(s, userMmsi); };
    run();
    // Again when coming back to the app (picks up departure planner changes)
    // and when asked (notification permission just granted).
    const onVis = () => { if (!pageHidden()) run(); };
    document.addEventListener("visibilitychange", onVis);
    const offResync = onPushResync(run);
    return () => { document.removeEventListener("visibilitychange", onVis); offResync(); };
  }, [enabled, tow, towMiles, lock, lockWaitMinutes, depart, sound, userMmsi]);

  // On screen: the server holds back pushes (no duplicate of the toast).
  useEffect(() => {
    if (status !== "active") return undefined;
    const beat = () => reportPresence(!pageHidden());
    beat();
    const id = setInterval(() => { if (!pageHidden()) beat(); }, PRESENCE_MS);
    const gone = () => reportPresence(false);
    document.addEventListener("visibilitychange", beat);
    window.addEventListener("pagehide", gone);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", beat);
      window.removeEventListener("pagehide", gone);
    };
  }, [status]);

  return status;
}
