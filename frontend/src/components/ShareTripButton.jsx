import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Share2, Link2, XCircle } from "lucide-react";

import { API } from "@/lib/api";
import { SHARE_HOURS, shareText, shareUrl, untilLine } from "@/lib/tripShare";

// "Share my trip": a link family and friends open without signing in
// (/s/:token). Shows the active link with copy / stop actions.
export default function ShareTripButton({ userMmsi, boatName, destinationRm = null }) {
  const [share, setShare] = useState(null);
  const [hours, setHours] = useState(24);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!userMmsi) return;
    try {
      const r = await fetch(`${API}/share`);
      if (!r.ok) return;
      const data = await r.json();
      setShare((data.shares || []).find((s) => String(s.mmsi) === String(userMmsi)) || null);
    } catch {
      /* offline: the button still works */
    }
  }, [userMmsi]);

  useEffect(() => { load(); }, [load]);

  const url = share ? shareUrl(window.location.origin, share.token) : "";

  const copy = async (link) => {
    try {
      await navigator.clipboard.writeText(link);
      toast.success("Trip link copied");
    } catch {
      toast.message("Trip link", { description: link, duration: 15000 });
    }
  };

  const send = async (link, name) => {
    if (navigator.share) {
      try {
        await navigator.share({ title: "River Watch trip", text: shareText(name), url: link });
        return;
      } catch (e) {
        if (e && e.name === "AbortError") return; // closed the share sheet
      }
    }
    await copy(link);
  };

  const create = async () => {
    setBusy(true);
    try {
      const body = { mmsi: String(userMmsi), hours };
      if (destinationRm !== null && destinationRm !== undefined && destinationRm !== "") {
        body.destination_rm = Number(destinationRm);
      }
      const r = await fetch(`${API}/share`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${r.status}`);
      setShare(data);
      await send(shareUrl(window.location.origin, data.token), data.boat_name || boatName);
    } catch (e) {
      toast.error(`Couldn't create a trip link: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (!share) return;
    setBusy(true);
    try {
      const r = await fetch(`${API}/share/${encodeURIComponent(share.token)}`, { method: "DELETE" });
      if (!r.ok && r.status !== 404) throw new Error(`HTTP ${r.status}`);
      setShare(null);
      toast.success("Stopped sharing your trip");
    } catch (e) {
      toast.error(`Couldn't stop sharing: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  if (!userMmsi) return null;

  if (share) {
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 p-2 rounded-md border border-cyan-700/50 bg-cyan-900/20 text-xs"
           data-testid="share-trip-active">
        <span className="text-cyan-300 flex items-center gap-1"><Link2 className="w-3.5 h-3.5" /> Sharing your trip</span>
        <span className="text-slate-400">{untilLine(share.expires_at)}</span>
        <span className="flex items-center gap-3 ml-auto">
          <button type="button" className="text-cyan-300 hover:text-white" onClick={() => send(url, share.boat_name || boatName)}
                  disabled={busy} data-testid="share-trip-resend">Send link</button>
          <button type="button" className="text-slate-400 hover:text-white" onClick={() => copy(url)}
                  disabled={busy} data-testid="share-trip-copy">Copy</button>
          <button type="button" className="text-amber-300 hover:text-amber-200 flex items-center gap-1" onClick={stop}
                  disabled={busy} data-testid="share-trip-stop"><XCircle className="w-3.5 h-3.5" /> Stop sharing</button>
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 text-xs" data-testid="share-trip">
      <button type="button" onClick={create} disabled={busy}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-cyan-700/60 text-cyan-300 hover:text-white hover:border-cyan-500 disabled:opacity-50"
              title="Send family and friends a link showing where your boat is and when it should arrive"
              data-testid="share-trip-btn">
        <Share2 className="w-3.5 h-3.5" /> {busy ? "Creating link..." : "Share trip"}
      </button>
      <label className="text-slate-500 flex items-center gap-1">
        for
        <select value={hours} onChange={(e) => setHours(Number(e.target.value))}
                className="bg-slate-900 border border-slate-700 rounded px-1 py-0.5 text-slate-300"
                data-testid="share-trip-hours">
          {SHARE_HOURS.map((h) => <option key={h} value={h}>{h} h</option>)}
        </select>
      </label>
    </div>
  );
}
