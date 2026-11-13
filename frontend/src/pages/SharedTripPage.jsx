import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Anchor, Navigation, Flag, Ship } from "lucide-react";

import { API } from "@/lib/api";
import { whenVisible, onVisible } from "@/lib/visibility";
import {
  REFRESH_MS, statusLine, waitText, nextLockLine, destinationLine, untilLine, isStale, stripMarks,
} from "@/lib/tripShare";

const MARK_STYLE = {
  boat: { dot: "bg-cyan-400 ring-4 ring-cyan-400/20", text: "text-cyan-300", Icon: Ship },
  lock: { dot: "bg-amber-400", text: "text-amber-300", Icon: Anchor },
  destination: { dot: "bg-slate-300", text: "text-slate-300", Icon: Flag },
};

// Public: a boater's "Share my trip" link. No sign-in; phone first.
export default function SharedTripPage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/public/share/${encodeURIComponent(token)}`);
      if (r.status === 404) { setError("gone"); setData(null); return; }
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
      setError(null);
    } catch (e) {
      setError((prev) => (prev === "gone" ? prev : e.message || "offline"));
    }
  }, [token]);

  useEffect(() => {
    load();
    const id = setInterval(whenVisible(load), REFRESH_MS);
    const off = onVisible(load);
    return () => { clearInterval(id); off(); };
  }, [load]);

  const now = Date.now();
  const marks = stripMarks(data);
  const stale = data && data.has_position && isStale(data.updated_at, now);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 flex flex-col">
      <header className="border-b border-white/5">
        <div className="max-w-md mx-auto px-4 py-3 flex items-center gap-2">
          <Navigation className="w-4 h-4 text-cyan-400" />
          <span className="font-heading font-bold uppercase tracking-wider text-sm text-white">River Watch</span>
          <span className="text-xs text-slate-500">· shared trip</span>
        </div>
      </header>

      <main className="flex-1 w-full max-w-md mx-auto px-4 py-6 space-y-6">
        {error === "gone" && (
          <div className="space-y-2" data-testid="shared-trip-gone">
            <h1 className="text-xl font-semibold text-white">This trip link isn't active</h1>
            <p className="text-slate-400 text-sm">It has expired or the boater stopped sharing. Ask them for a new link.</p>
          </div>
        )}
        {!data && !error && <p className="text-slate-500" data-testid="shared-trip-loading">Loading...</p>}
        {!data && error && error !== "gone" && (
          <p className="text-amber-300 text-sm">Couldn't reach River Watch ({error}). Trying again in a minute.</p>
        )}

        {data && (
          <>
            <section className="space-y-1" data-testid="shared-trip">
              <h1 className="text-2xl font-semibold text-white" data-testid="shared-trip-name">{data.boat_name}</h1>
              <p className="text-slate-300" data-testid="shared-trip-status">{statusLine(data, now)}</p>
              {stale && (
                <p className="text-amber-300 text-sm" data-testid="shared-trip-stale">
                  No recent position. The boat may be out of signal range.
                </p>
              )}
              {error && <p className="text-xs text-slate-500">Couldn't refresh just now; showing the last update.</p>}
            </section>

            {data.next_lock && (
              <section className="rounded-lg border border-white/10 p-4 space-y-1" data-testid="shared-trip-next-lock">
                <div className="text-xs uppercase tracking-wider text-slate-500">Next lock</div>
                <div className="text-white">{nextLockLine(data.next_lock)}</div>
                {waitText(data.next_lock) && <div className="text-amber-300 text-sm">{waitText(data.next_lock)}</div>}
              </section>
            )}

            {data.destination && (
              <section className="rounded-lg border border-white/10 p-4 space-y-1" data-testid="shared-trip-destination">
                <div className="text-xs uppercase tracking-wider text-slate-500">Destination</div>
                <div className="text-white">{destinationLine(data.destination)}</div>
              </section>
            )}

            {marks.length > 1 && (
              <section aria-label="River strip, upriver at the top" data-testid="shared-trip-strip">
                <div className="text-xs uppercase tracking-wider text-slate-500 mb-2">Upriver ↑</div>
                <div className="relative h-56 ml-3">
                  <div className="absolute left-0 top-0 bottom-0 w-1 rounded bg-cyan-900/60" />
                  {marks.map((m) => {
                    const s = MARK_STYLE[m.kind];
                    return (
                      <div key={m.kind} className="absolute left-0 flex items-center gap-3 -translate-y-1/2"
                           style={{ top: `${m.top}%` }}>
                        <span className={`-ml-1 w-3 h-3 rounded-full ${s.dot}`} />
                        <span className={`text-sm ${s.text} flex items-center gap-1`}>
                          <s.Icon className="w-3.5 h-3.5" /> {m.label}
                          <span className="text-slate-500">· RM {m.rm.toFixed(1)}</span>
                        </span>
                      </div>
                    );
                  })}
                </div>
                <div className="text-xs uppercase tracking-wider text-slate-500 mt-2">Downriver ↓</div>
              </section>
            )}

            {data.has_position && data.lat !== null && data.lon !== null && (
              <p className="text-xs text-slate-500">
                Position {data.lat.toFixed(4)}, {data.lon.toFixed(4)}
                {data.heading !== null && data.heading !== undefined ? ` · heading ${Math.round(data.heading)}°` : ""}
              </p>
            )}
            <p className="text-xs text-slate-500">{untilLine(data.expires_at)} · refreshes every minute</p>
          </>
        )}
      </main>

      <footer className="border-t border-white/5">
        <div className="max-w-md mx-auto px-4 py-4 text-xs text-slate-500 space-y-1">
          <p>Advisory only, not for navigation. Times are estimates.</p>
          <p>
            Lock waits on the Upper Mississippi, predicted live.{" "}
            <Link to="/" className="text-cyan-400 hover:text-cyan-300" data-testid="shared-trip-landing-link">
              Try River Watch
            </Link>
          </p>
        </div>
      </footer>
    </div>
  );
}
