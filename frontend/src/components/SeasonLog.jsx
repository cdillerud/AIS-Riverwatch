import { useEffect, useState } from "react";
import { API } from "../lib/api";
import { seasonLine, fmtHm } from "../lib/season";

// "Your season" on the Trips page: miles, hours under way, locks passed and
// time spent at them, recorded while the boat moves.
export default function SeasonLog() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetch(`${API}/me/season`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setData)
      .catch(() => {});
  }, []);
  if (!data || !data.boats || !data.boats.length) return null;
  return (
    <div className="space-y-3" data-testid="season-log">
      {data.boats.map((b) => (
        <div key={b.mmsi} className="rounded-lg border border-slate-700 bg-slate-900/50 p-4">
          <div className="text-xs uppercase tracking-wider text-slate-400">{data.year} season · {b.boat_name || b.mmsi}</div>
          <div className="mt-1 text-lg text-white">{seasonLine(b)}</div>
          {b.passages.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm">
              {b.passages.slice(0, 8).map((p, i) => (
                <li key={i} className="flex gap-2 text-slate-300">
                  <span className="text-slate-500 w-24 shrink-0">{new Date(p.at).toLocaleDateString([], { month: "short", day: "numeric" })}</span>
                  <span className="truncate">{p.name}</span>
                  <span className="text-slate-500">{p.direction === "upbound" ? "↑" : "↓"}</span>
                  <span className="ml-auto font-mono">{fmtHm(p.minutes_at_lock)}</span>
                </li>
              ))}
            </ul>
          )}
          {b.miles === 0 && (
            <p className="mt-2 text-xs text-slate-500">Recording started. Trips show up here once your boat is under way with River Watch open or its AIS on.</p>
          )}
        </div>
      ))}
    </div>
  );
}
