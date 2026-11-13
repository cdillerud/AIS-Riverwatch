import { useEffect, useState } from "react";
import { Bell, BellOff } from "lucide-react";
import { toast } from "sonner";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { saveAlertSettings, TOW_MILE_CHOICES, LOCK_WAIT_CHOICES } from "@/lib/alerts";
import { useAlertSettings } from "@/hooks/useRiverAlerts";
import { usePushStatus } from "@/hooks/usePushAlerts";
import { pushStatusText, requestPushResync } from "@/lib/push";
import {
  notificationPermission, requestNotificationPermission, showSystemNotification,
} from "@/lib/alertNotify";

const PERMISSION_TEXT = {
  granted: null,
  default: "Allow notifications when asked, or alerts show only while River Watch is on screen.",
  denied: "Notifications are blocked for this site in your browser settings. Alerts show only while River Watch is on screen.",
  unsupported: "This browser can't show notifications. Alerts show only while River Watch is on screen.",
};

const selectCls = "bg-slate-800 border border-slate-700 rounded px-1 py-0.5 text-xs text-slate-200";

// Header bell: alerts for this phone (saved on this device only).
export default function AlertsPicker({ className = "" }) {
  const settings = useAlertSettings();
  const pushStatus = usePushStatus();
  const [perm, setPerm] = useState(notificationPermission);
  const [open, setOpen] = useState(false);
  useEffect(() => { if (open) setPerm(notificationPermission()); }, [open]);

  const update = (patch) => saveAlertSettings({ ...settings, ...patch });

  const toggleEnabled = async () => {
    if (settings.enabled) { update({ enabled: false }); return; }
    update({ enabled: true });
    if (notificationPermission() === "default") {
      setPerm(await requestNotificationPermission());
      requestPushResync();   // permission granted: sign up for alerts with the app closed
    }
  };

  const test = async () => {
    const shown = await showSystemNotification({
      title: "River Watch test alert", body: "Alerts will look like this.", tag: "test", sound: settings.sound,
    });
    if (!shown) toast("River Watch test alert", { description: "Alerts will show like this while the app is on screen." });
  };

  const Icon = settings.enabled ? Bell : BellOff;
  const row = "flex items-center gap-2 text-sm text-slate-200";
  const box = "accent-cyan-500 w-4 h-4";
  const dim = settings.enabled ? "" : "opacity-50 pointer-events-none";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`inline-flex items-center justify-center rounded-md hover:bg-cyan-500/10 w-8 h-8 sm:w-9 sm:h-9 ${settings.enabled ? "text-cyan-400 hover:text-cyan-300" : "text-slate-400 hover:text-cyan-300"} ${className}`}
          title={settings.enabled ? "Alerts on" : "Alerts off"}
          aria-label="Alerts"
          data-testid="alerts-picker"
        >
          <Icon className="w-4 h-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-3 bg-slate-900 border-slate-700 text-slate-200 space-y-3">
        <label className="flex items-center justify-between gap-3 cursor-pointer">
          <span>
            <span className="block text-sm font-semibold text-white">Alerts on this phone</span>
            <span className="block text-xs text-slate-400">Saved on this device only.</span>
          </span>
          <input type="checkbox" className={box} checked={settings.enabled} onChange={toggleEnabled} data-testid="alerts-enabled" />
        </label>

        {settings.enabled && PERMISSION_TEXT[perm] && (
          <div className="text-xs text-amber-300" data-testid="alerts-permission-note">
            {PERMISSION_TEXT[perm]}
            {perm === "default" && (
              <button type="button" className="ml-1 underline text-amber-200"
                onClick={async () => { setPerm(await requestNotificationPermission()); requestPushResync(); }}>
                Allow now
              </button>
            )}
          </div>
        )}

        <div className={`space-y-2 border-t border-slate-800 pt-3 ${dim}`}>
          <label className={row}>
            <input type="checkbox" className={box} checked={settings.tow} onChange={(e) => update({ tow: e.target.checked })} data-testid="alerts-tow" />
            <span className="flex-1">A tow is within</span>
            <select className={selectCls} value={settings.towMiles} onChange={(e) => update({ towMiles: Number(e.target.value) })} aria-label="Tow distance">
              {TOW_MILE_CHOICES.map((m) => <option key={m} value={m}>{m} mi</option>)}
            </select>
            <span>and closing</span>
          </label>
          <label className={row}>
            <input type="checkbox" className={box} checked={settings.lock} onChange={(e) => update({ lock: e.target.checked })} data-testid="alerts-lock" />
            <span className="flex-1">Wait at the next lock goes over or back under</span>
            <select className={selectCls} value={settings.lockWaitMinutes} onChange={(e) => update({ lockWaitMinutes: Number(e.target.value) })} aria-label="Lock wait threshold">
              {LOCK_WAIT_CHOICES.map((m) => <option key={m} value={m}>{m} min</option>)}
            </select>
          </label>
          <label className={row}>
            <input type="checkbox" className={box} checked={settings.depart} onChange={(e) => update({ depart: e.target.checked })} data-testid="alerts-depart" />
            <span className="flex-1">Leaving now becomes the best time (while stopped)</span>
          </label>
          <label className={row}>
            <input type="checkbox" className={box} checked={settings.sound} onChange={(e) => update({ sound: e.target.checked })} data-testid="alerts-sound" />
            <span className="flex-1">Sound and vibration</span>
          </label>
        </div>

        <div className="border-t border-slate-800 pt-2 text-[11px] text-slate-500 space-y-1">
          {settings.enabled ? (
            <p className={pushStatus === "active" ? "text-cyan-300" : ""} data-testid="alerts-push-status">
              {pushStatusText(pushStatus)}
            </p>
          ) : (
            <p>Alerts arrive while River Watch is open, and also when it's closed if this phone and server support it.</p>
          )}
          <p>The same alert won't repeat within 30 minutes.</p>
          {settings.enabled && (
            <button type="button" onClick={test} className="text-cyan-400 hover:text-cyan-300" data-testid="alerts-test">
              Send a test alert
            </button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
