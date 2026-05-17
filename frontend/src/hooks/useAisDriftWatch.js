/**
 * useAisDriftWatch
 * --------------------------------------------------------------------------
 * Cross-deployment NMEA-stall detector. Works identically on the
 * Cloud VM (Docker / Nginx / Let's Encrypt) and the Raspberry Pi native
 * install (systemd + native Nginx) - both expose the same
 * `GET /api/connection/status` endpoint.
 *
 * Behaviour:
 *   - Polls /api/connection/status every `pollMs` (default 10 s).
 *   - If we have observed fresh data at least once AND `last_data_time` is
 *     older than `staleMs` (default 30 s), fires ONE warning toast.
 *   - When fresh data returns, fires ONE recovery toast.
 *   - Skips entirely when no connection has ever been configured.
 *
 * Why a hook and not a useEffect inside MainApp? The Settings page also
 * polls /api/connection/status every 3 s for the live status strip; this
 * hook intentionally runs at 10 s so the two pollers don't pile on the
 * backend but the user still gets timely alerts while underway.
 */
import { useEffect, useRef } from "react";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function useAisDriftWatch({
  enabled = true,
  pollMs = 10000,
  staleMs = 30000,
} = {}) {
  const lastSeenAtRef = useRef(null); // wall-clock ms of last fresh NMEA observation
  const everFreshRef = useRef(false); // has the feed ever been LIVE in this session?
  const stalledRef = useRef(false); // currently in stalled state?

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;

    const tick = async () => {
      try {
        const r = await fetch(`${API}/connection/status`);
        if (!r.ok || cancelled) return;
        const data = await r.json();

        // Only watch once a real connection has been configured.
        const ip = data?.config?.ip_address;
        if (!ip || ip === "ais-relay" || ip === "push://relay") {
          return;
        }

        const last = data?.last_data_time ? Date.parse(data.last_data_time) : null;
        const now = Date.now();

        if (last && (!lastSeenAtRef.current || last > lastSeenAtRef.current)) {
          lastSeenAtRef.current = last;
          everFreshRef.current = true;

          // Recovery toast
          if (stalledRef.current) {
            stalledRef.current = false;
            toast.success("AIS feed restored", {
              description: `Last NMEA: ${new Date(last).toLocaleTimeString()}`,
              duration: 4000,
            });
          }
        }

        if (!everFreshRef.current) return; // never warn before first good frame

        const age = now - (lastSeenAtRef.current || 0);
        if (!stalledRef.current && age > staleMs) {
          stalledRef.current = true;
          toast.warning("AIS feed has stalled", {
            description: `No NMEA sentences for ${Math.round(age / 1000)} s. Check phone / Boat Beacon.`,
            duration: 8000,
          });
        }
      } catch {
        /* network blip - ignore, keep state */
      }
    };

    tick();
    const interval = setInterval(tick, pollMs);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [enabled, pollMs, staleMs]);
}
