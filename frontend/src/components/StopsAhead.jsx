import { useEffect, useState } from "react";
import { Anchor, Fuel, Phone, Globe } from "lucide-react";
import { API } from "../lib/api";
import { stopsAhead } from "../lib/stops";

let cache = null;

function useMarinas() {
  const [data, setData] = useState(cache);
  useEffect(() => {
    if (cache) return undefined;
    let alive = true;
    fetch(`${API}/marinas`)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (j && alive) {
          cache = j;
          setData(j);
        }
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);
  return data;
}

const fmtEta = (m) => {
  if (m < 60) return `${Math.round(m)} min`;
  const h = Math.floor(m / 60), r = Math.round(m % 60);
  return r ? `${h} h ${r} min` : `${h} h`;
};

// "Stops ahead": the next marinas in the direction of travel, with arrival
// estimates (lock time included) and an after-dark flag.
export default function StopsAhead({ fromRm, direction, mph, anchors, locks, startAt }) {
  const data = useMarinas();
  if (!data || fromRm == null || !direction) return null;
  const rows = stopsAhead(data.marinas, { fromRm, direction, mph, anchors, locks, now: startAt ? new Date(startAt) : new Date() });
  if (!rows.length) return null;
  const clock = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return (
    <div className="mt-2" data-testid="stops-ahead">
      <div className="text-[10px] uppercase text-slate-500 mb-1">Marinas ahead</div>
      <ul className="space-y-1">
        {rows.map((m) => (
          <li key={m.osm_id} className="flex items-center gap-2 text-xs">
            {m.fuel ? <Fuel className="w-3 h-3 text-amber-400 shrink-0" /> : <Anchor className="w-3 h-3 text-cyan-400 shrink-0" />}
            <span className="text-slate-200 truncate">{m.name}</span>
            <span className="text-slate-500 font-mono shrink-0">RM {m.river_mile} · {m.miles.toFixed(0)} mi</span>
            {m.phone && (
              <a href={`tel:${m.phone.replace(/[^0-9+]/g, "")}`} className="text-slate-400 hover:text-cyan-300" title={m.phone}>
                <Phone className="w-3 h-3" />
              </a>
            )}
            {m.website && (
              <a href={m.website} target="_blank" rel="noreferrer" className="text-slate-400 hover:text-cyan-300" title="Website">
                <Globe className="w-3 h-3" />
              </a>
            )}
            <span className={`ml-auto font-mono shrink-0 ${m.dark ? "text-amber-400" : "text-slate-300"}`}
                  title={`about ${fmtEta(m.etaMinutes)} incl. locks`}>
              {clock(m.arriveAt)}{m.dark && " ☾"}
            </span>
          </li>
        ))}
      </ul>
      <div className="text-[10px] text-slate-500 mt-1">
        {data.credit}. Missing one? <a href={data.add_url} target="_blank" rel="noreferrer" className="underline">Add it on OpenStreetMap</a>.
      </div>
    </div>
  );
}
