// Shown in the Trip Plan while the boat is stopped: pick a direction and a
// cruising speed, and compare leaving now vs later - expected wait at each
// lock when you'd get there (same model as the trip plan, including tows
// predicted to arrive) and when you'd arrive. Backend: /departure-options.
import { useEffect, useState, useCallback } from "react";
import { API } from "../lib/api";
import { whenVisible } from "../lib/visibility";
import { departureLabel, clockIn, readPrefs, savePrefs } from "../lib/departure";
import { darkCheck, isDark, sunTimes, positionAtRm } from "../lib/sun";
import useLocks from "../hooks/useLocks";

const fmtMin = (m) => {
  if (m == null) return "—";
  if (m < 60) return `${Math.round(m)}m`;
  const h = Math.floor(m / 60);
  const r = Math.round(m % 60);
  return r ? `${h}h ${r}m` : `${h}h`;
};

export default function DeparturePlanner({ userMmsi, destinationRm }) {
  const [prefs, setPrefs] = useState(readPrefs);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const allLocks = useLocks();

  const load = useCallback(async () => {
    if (!userMmsi) return;
    setLoading(true);
    setError(null);
    try {
      const p = new URLSearchParams({ direction: prefs.direction, cruise_mph: String(prefs.mph), max_locks: "5" });
      if (destinationRm != null) p.set("destination_rm", String(destinationRm));
      const res = await fetch(`${API}/session/${userMmsi}/departure-options?${p.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e.message || "Could not load departure options");
    } finally {
      setLoading(false);
    }
  }, [userMmsi, prefs, destinationRm]);

  useEffect(() => {
    load();
    const id = setInterval(whenVisible(load), 120000);
    return () => clearInterval(id);
  }, [load]);

  const update = (patch) => {
    const next = { ...prefs, ...patch };
    setPrefs(next);
    savePrefs(next);
  };

  const opts = data?.options || [];
  const locks = data?.locks || [];
  // Arrival point: the destination, else the last lock in the table.
  const lastLock = locks.length ? allLocks.find((l) => l.id === locks.at(-1).lock_id) : null;
  const finishRm = data?.destination_rm ?? (lastLock ? lastLock.river_mile : data?.start_rm);
  const dark = data ? darkCheck(opts, data.generated_at, finishRm, allLocks) : null;
  const darkAt = (i) => Boolean(dark && dark.rows.at(i) && dark.rows.at(i).dark);
  const nowDark = data ? isDark(new Date(data.generated_at), ...Object.values(positionAtRm(data.start_rm, allLocks))) : false;
  const clock = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  let darkNote = null;
  if (dark && dark.anyDark) {
    if (nowDark) {
      const here = positionAtRm(data.start_rm, allLocks);
      const t = new Date(data.generated_at);
      let rise = sunTimes(t, here.lat, here.lon)[0];
      if (rise < t.getTime()) rise = sunTimes(new Date(t.getTime() + 864e5), here.lat, here.lon)[0];
      darkNote = `It's dark now. Sunrise is about ${clock(new Date(rise))}.`;
    } else if (dark.latestBeforeDark != null) {
      darkNote = `Sunset about ${clock(dark.sunset)}. Leave ${dark.latestBeforeDark ? `by ${departureLabel(dark.latestBeforeDark, data.generated_at)}` : "now"} to arrive before dark.`;
    } else {
      darkNote = `Sunset about ${clock(dark.sunset)}: every option here arrives after dark. Consider a closer stop.`;
    }
  }

  return (
    <div className="space-y-2" data-testid="departure-planner">
      <div className="text-xs text-slate-400">
        Your boat is stopped. Planning a trip? Compare leaving now or later:
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {["downbound", "upbound"].map((d) => (
          <button
            key={d}
            onClick={() => update({ direction: d })}
            className={`px-2 py-1 rounded border ${prefs.direction === d ? "border-cyan-500 bg-cyan-900/40 text-cyan-200" : "border-slate-700 text-slate-400 hover:text-white"}`}
            data-testid={`departure-dir-${d}`}
          >
            {d === "downbound" ? "↓ Downriver" : "↑ Upriver"}
          </button>
        ))}
        <label className="flex items-center gap-1 text-slate-400">
          at
          <input
            type="number"
            min={1}
            max={60}
            value={prefs.mph}
            onChange={(e) => update({ mph: Math.max(1, Math.min(60, Number(e.target.value) || 1)) })}
            className="w-14 bg-slate-900 border border-slate-700 rounded px-1 py-0.5 text-white font-mono"
            data-testid="departure-mph"
          />
          mph
        </label>
        {loading && <span className="text-slate-500">…</span>}
      </div>

      {error && <div className="text-xs text-red-400">{error}</div>}

      {data && locks.length === 0 && !error && (
        <div className="text-xs text-slate-500">No locks ahead {prefs.direction === "downbound" ? "downriver" : "upriver"} of RM {data.start_rm}.</div>
      )}

      {locks.filter((l) => l.note).map((l) => (
        <div key={l.lock_id} className="text-[11px] text-amber-400" data-testid={`lock-note-${l.lock_id}`}>
          ! {l.name}: {l.note}
        </div>
      ))}

      {locks.length > 0 && opts.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" data-testid="departure-table">
            <thead>
              <tr className="text-slate-500 text-[10px] uppercase">
                <th className="text-left font-normal py-1">Leave</th>
                {locks.map((l) => (
                  <th key={l.lock_id} className={`text-right font-normal ${l.note ? "text-amber-400" : ""}`} title={l.note ? `${l.name}: ${l.note}` : l.name}>
                    {l.lock_id.replace("lock_", "L").replace("melvin_price", "Mel").replace("chain_of_rocks", "CoR")}{l.note && "!"}
                  </th>
                ))}
                <th className="text-right font-normal">At locks</th>
                <th className="text-right font-normal">Arrive</th>
              </tr>
            </thead>
            <tbody>
              {opts.map((o, i) => (
                <tr key={o.depart_in_minutes}
                    className={i === data.best ? "text-cyan-200 bg-cyan-900/20" : "text-slate-300"}
                    data-testid={`departure-row-${o.depart_in_minutes}`}>
                  <td className="py-1">{departureLabel(o.depart_in_minutes, data.generated_at)}{i === data.best && " ★"}</td>
                  {o.locks.map((l) => (
                    <td key={l.lock_id} className="text-right font-mono" title={`arrive ${clockIn(o.depart_in_minutes + l.arrive_minutes, data.generated_at)}`}>
                      {fmtMin(l.wait_minutes)}
                    </td>
                  ))}
                  <td className="text-right font-mono">{fmtMin(o.time_at_locks_minutes)}</td>
                  <td className={`text-right font-mono ${darkAt(i) ? "text-amber-400" : ""}`} title={darkAt(i) ? "Arrives after dark" : undefined} data-testid={darkAt(i) ? "arrive-dark" : undefined}>
                    {clockIn(o.finish_in_minutes, data.generated_at)}{darkAt(i) && " ☾"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="text-[10px] text-slate-500 mt-1">
            Lock columns: expected wait when you'd get there. At locks: waits plus your own lockages.
            Arrive: {data.destination_rm != null ? `at RM ${data.destination_rm}` : "through the last lock shown"}. ★ least time at locks.
          </div>
          {darkNote && <div className="text-[11px] text-amber-400 mt-1" data-testid="dark-note">☾ {darkNote}</div>}
        </div>
      )}
    </div>
  );
}
