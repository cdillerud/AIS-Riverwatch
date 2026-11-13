import { useEffect, useMemo, useState } from "react";
import { Ship, MapPin, Navigation, ArrowRight, ArrowLeft, Locate, Anchor, Lock } from "lucide-react";
import { toast } from "sonner";
import { API } from "../lib/api";
import useLocks from "../hooks/useLocks";
import { riverPlaces, placesAhead, tripFor, validBoat } from "../lib/firstRun";
import { savePrefs } from "../lib/departure";

const STEPS = ["Your boat", "Where it is", "Where you're headed"];

// New-boater setup in three short steps, ending on the dashboard's
// "best time to leave". No MMSI needed: boats without AIS get an app ID and
// use this phone's GPS while River Watch is open.
export default function FirstRunWizard({ onDone, onBack, onAdvanced }) {
  const locks = useLocks();
  const [marinas, setMarinas] = useState([]);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("");
  const [hasAis, setHasAis] = useState(false);
  const [mmsi, setMmsi] = useState("");
  const [boat, setBoat] = useState(null);          // {mmsi, boat_name} once saved

  const [here, setHere] = useState(null);          // {river_mile, name}
  const [placeKey, setPlaceKey] = useState("");

  const [direction, setDirection] = useState("downbound");
  const [mph, setMph] = useState(15);
  const [destKey, setDestKey] = useState("");

  useEffect(() => {
    fetch(`${API}/marinas`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => j && setMarinas(j.marinas || []))
      .catch(() => {});
  }, []);
  const places = useMemo(() => riverPlaces(marinas, locks), [marinas, locks]);
  const ahead = useMemo(() => (here ? placesAhead(places, here.river_mile, direction).slice(0, 40) : []), [places, here, direction]);

  const saveBoat = async () => {
    const err = validBoat(name, hasAis, mmsi);
    if (err) { toast.error(err); return; }
    setBusy(true);
    try {
      const res = await fetch(`${API}/user/vessels`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ mmsi: hasAis ? mmsi : null, boat_name: name.trim(), is_primary: true }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Couldn't save your boat");
      setBoat({ mmsi: body.vessel.mmsi, boat_name: body.vessel.boat_name });
      setStep(1);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const setBerth = async (lat, lon, label) => {
    setBusy(true);
    try {
      const res = await fetch(`${API}/user/vessels/${boat.mmsi}/home-berth`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ lat, lon }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Couldn't place your boat there");
      setHere({ river_mile: body.home_berth.river_mile, name: label });
      setStep(2);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const usePhone = () => {
    if (!navigator.geolocation) { toast.error("This device can't share its location"); return; }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (p) => setBerth(p.coords.latitude, p.coords.longitude, "your location"),
      () => { setBusy(false); toast.error("Location not available - pick a marina or lock instead"); },
      { enableHighAccuracy: true, timeout: 15000 },
    );
  };

  const usePlace = () => {
    const p = places.find((x) => x.key === placeKey);
    if (!p || p.lat == null) { toast.error("Pick a marina or lock"); return; }
    setBerth(p.lat, p.lon, p.name);
  };

  const finish = (skipPlan) => {
    if (!skipPlan) {
      savePrefs({ direction, mph: Math.max(1, Math.min(60, Number(mph) || 15)) });
      const dest = ahead.find((p) => p.key === destKey);
      try {
        const trip = tripFor(here?.river_mile, dest, direction);
        if (trip) localStorage.setItem("activeTrip", JSON.stringify(trip));
      } catch (e) { /* storage unavailable */ }
    }
    onDone({ user_mmsi: boat.mmsi, boat_name: boat.boat_name });
  };

  const sel = "w-full bg-slate-800/50 border border-slate-600 rounded px-2 py-2 text-white text-sm";
  const btn = "w-full inline-flex items-center justify-center gap-2 rounded-md bg-cyan-600 hover:bg-cyan-700 text-white py-2 text-sm disabled:opacity-50";

  return (
    <div className="space-y-5" data-testid="first-run">
      <ol className="flex gap-2 text-[11px]">
        {STEPS.map((s, i) => (
          <li key={s} className={`flex-1 border-t-2 pt-1 ${i <= step ? "border-cyan-500 text-cyan-300" : "border-slate-700 text-slate-500"}`}>{s}</li>
        ))}
      </ol>

      {step === 0 && (
        <div className="space-y-4">
          <label className="block space-y-1">
            <span className="text-sm text-slate-300 flex items-center gap-2"><Ship className="w-4 h-4 text-cyan-400" /> Boat name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Sea Biscuit" className={sel} data-testid="fr-name" />
          </label>
          <label className="flex items-start gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={hasAis} onChange={(e) => setHasAis(e.target.checked)} className="mt-1" data-testid="fr-has-ais" />
            <span>My boat has AIS or a DSC radio with an MMSI</span>
          </label>
          {hasAis ? (
            <input value={mmsi} onChange={(e) => setMmsi(e.target.value.replace(/\D/g, "").slice(0, 9))} placeholder="9-digit MMSI"
                   className={`${sel} font-mono`} data-testid="fr-mmsi" />
          ) : (
            <p className="text-xs text-slate-400">No problem. River Watch will use this phone's GPS while the app is open.</p>
          )}
          <button className={btn} onClick={saveBoat} disabled={busy} data-testid="fr-next-boat">Next <ArrowRight className="w-4 h-4" /></button>
          <div className="flex justify-between text-xs">
            <button onClick={onBack} className="text-slate-400 hover:text-white">← Back</button>
            {onAdvanced && <button onClick={onAdvanced} className="text-slate-500 hover:text-slate-300">I run my own AIS receiver</button>}
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          <p className="text-sm text-slate-300 flex items-center gap-2"><MapPin className="w-4 h-4 text-cyan-400" /> Where is {boat?.boat_name} now?</p>
          <button className={btn} onClick={usePhone} disabled={busy} data-testid="fr-use-phone"><Locate className="w-4 h-4" /> Use this phone's location</button>
          <div className="text-center text-xs text-slate-500">or pick its marina or nearest lock</div>
          <select value={placeKey} onChange={(e) => setPlaceKey(e.target.value)} className={sel} data-testid="fr-place">
            <option value="">Choose…</option>
            {places.map((p) => <option key={p.key} value={p.key}>{p.name} · RM {p.river_mile}</option>)}
          </select>
          <button className={btn} onClick={usePlace} disabled={busy || !placeKey} data-testid="fr-use-place">Use this place</button>
          <div className="flex justify-between text-xs">
            <button onClick={() => setStep(0)} className="text-slate-400 hover:text-white"><ArrowLeft className="w-3 h-3 inline" /> Back</button>
            <button onClick={() => finish(true)} className="text-slate-500 hover:text-slate-300">Skip for now</button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <p className="text-sm text-slate-300 flex items-center gap-2"><Navigation className="w-4 h-4 text-cyan-400" /> From {here?.name} (RM {here?.river_mile}), which way?</p>
          <div className="grid grid-cols-2 gap-2">
            {["downbound", "upbound"].map((d) => (
              <button key={d} onClick={() => { setDirection(d); setDestKey(""); }}
                      className={`rounded border py-2 text-sm ${direction === d ? "border-cyan-500 bg-cyan-900/40 text-cyan-200" : "border-slate-700 text-slate-300"}`}
                      data-testid={`fr-dir-${d}`}>
                {d === "downbound" ? "↓ Downriver" : "↑ Upriver"}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            Cruising at
            <input type="number" min={1} max={60} value={mph} onChange={(e) => setMph(e.target.value)} className="w-16 bg-slate-800/50 border border-slate-600 rounded px-2 py-1 text-white font-mono" />
            mph
          </label>
          <select value={destKey} onChange={(e) => setDestKey(e.target.value)} className={sel} data-testid="fr-dest">
            <option value="">Destination (optional)</option>
            {ahead.map((p) => (
              <option key={p.key} value={p.key}>{p.name} · RM {p.river_mile} · {Math.abs(p.river_mile - here.river_mile).toFixed(0)} mi</option>
            ))}
          </select>
          <button className={btn} onClick={() => finish(false)} data-testid="fr-finish">
            Show me the best time to leave <ArrowRight className="w-4 h-4" />
          </button>
          <div className="flex justify-between text-xs text-slate-500">
            <span className="flex items-center gap-1"><Anchor className="w-3 h-3" /> marinas · <Lock className="w-3 h-3" /> locks</span>
            <button onClick={() => finish(true)} className="hover:text-slate-300">Skip</button>
          </div>
        </div>
      )}
    </div>
  );
}
