import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Target } from "lucide-react";

import { API } from "@/lib/api";
import { fmtRiverDateTime } from "@/lib/riverTime";
import { waitHeadline, collectingNote, signedMinutes, modelTestLine } from "@/lib/accuracy";

// Public: how close River Watch's lock-wait estimates came to what USACE
// recorded. No sign-in; aggregates only, pleasure boats are not named.
export default function AccuracyPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API}/accuracy?days=30`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const waits = data && data.waits;
  const heads = waits
    ? [waitHeadline(waits.by_kind.tow, "Tows"), waitHeadline(waits.by_kind.recreational, "Pleasure boats")].filter(Boolean)
    : [];
  const note = waits && collectingNote(waits);
  const model = data && modelTestLine(data.model_test);
  const usaceEta = data && data.arrivals && data.arrivals.usace_prediction;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <header className="border-b border-white/5">
        <div className="container mx-auto px-4 py-3 flex items-center gap-3">
          <Link to="/" className="text-slate-400 hover:text-cyan-300" aria-label="Back"><ArrowLeft className="w-5 h-5" /></Link>
          <Target className="w-5 h-5 text-cyan-400" />
          <h1 className="font-heading font-bold uppercase tracking-wider text-white">How accurate is River Watch?</h1>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6 max-w-3xl space-y-8">
        <p className="text-slate-300">
          Every time a boat joins a lock queue, River Watch records the wait it is predicting. When USACE records
          the boat's actual wait, the two are compared here. Nothing is hand-picked: every scored lockage from the
          last 30 days counts.
        </p>

        {error && <p className="text-red-400">Couldn't load the accuracy record ({error}).</p>}
        {!data && !error && <p className="text-slate-500">Loading...</p>}

        {note && <p className="text-amber-200/90 bg-amber-500/10 border border-amber-500/30 rounded p-3 text-sm">{note}</p>}

        {heads.length > 0 && (
          <section className="grid sm:grid-cols-2 gap-4" data-testid="accuracy-headlines">
            {heads.map((h) => (
              <div key={h.label} className="rounded border border-white/10 p-4">
                <div className="text-xs uppercase tracking-wider text-slate-400">{h.label} · {h.n} lockages</div>
                <div className="mt-2 text-2xl font-semibold text-white">{h.typical}</div>
                <div className="text-sm text-slate-400">typical miss on the wait</div>
                <div className="mt-3 text-sm text-slate-300">{h.within30} within 30 minutes</div>
                {h.inRange && <div className="text-sm text-slate-300">{h.inRange} inside the "likely" range shown</div>}
              </div>
            ))}
          </section>
        )}

        {model && (
          <section>
            <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">Model test</h2>
            <p className="text-slate-300">{model} The model is retrained nightly and a new version is used only if it beats the current one on lockages it has not seen.</p>
          </section>
        )}

        {usaceEta && (
          <section>
            <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">Arrival times</h2>
            <p className="text-slate-300">
              Of {usaceEta.predictions.toLocaleString()} tows predicted to reach a lock, {usaceEta.arrived.toLocaleString()} did;
              their arrival time was off by {Math.round(usaceEta.mae_minutes)} min on average. Tows that stop at a fleeting area or
              terminal before the lock are the main source of error.
            </p>
          </section>
        )}

        {waits && waits.by_lock.length > 0 && (
          <section>
            <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">By lock</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-slate-400 text-left">
                  <tr><th className="py-1 pr-3">Lock</th><th className="py-1 pr-3 text-right">Lockages</th><th className="py-1 pr-3 text-right">Typical miss</th><th className="py-1 text-right">Within 30 min</th></tr>
                </thead>
                <tbody>
                  {waits.by_lock.map((r) => (
                    <tr key={r.lock_id} className="border-t border-white/5">
                      <td className="py-1 pr-3">{r.lock_name}</td>
                      <td className="py-1 pr-3 text-right">{r.n}</td>
                      <td className="py-1 pr-3 text-right">{Math.round(r.median_abs_error_minutes)} min</td>
                      <td className="py-1 text-right">{r.within_30_pct}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {waits && waits.recent.length > 0 && (
          <section>
            <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">Latest</h2>
            <ul className="space-y-1 text-sm">
              {waits.recent.map((s, i) => (
                <li key={i} className="flex flex-wrap gap-x-2 border-t border-white/5 pt-1">
                  <span className="text-slate-400">{fmtRiverDateTime(s.arrived_at)}</span>
                  <span>{s.lock_name}</span>
                  <span className="text-slate-400">{s.vessel_name || "Pleasure boat"}</span>
                  <span className="ml-auto">predicted {Math.round(s.predicted)} min, waited {Math.round(s.actual)} min</span>
                  <span className="text-slate-500">({signedMinutes(s.error)})</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <p className="text-xs text-slate-500">
          Source: U.S. Army Corps of Engineers lock performance data. Estimates are advisory, not for navigation.
          {data && ` Updated ${fmtRiverDateTime(data.generated_at)}.`}
        </p>
      </main>
    </div>
  );
}
