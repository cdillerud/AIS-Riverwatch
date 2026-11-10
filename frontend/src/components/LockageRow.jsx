// One completed lockage: where, when, and how long it took.
// Shared by the vessel detail views and a lock's recent-lockages list.

export function fmtDuration(minutes) {
  const m = Number(minutes);
  if (!Number.isFinite(m) || m < 0) return "—";
  if (m < 60) return `${Math.round(m)}m`;
  const h = Math.floor(m / 60);
  const rest = Math.round(m - h * 60);
  return rest ? `${h}h ${rest}m` : `${h}h`;
}

function fmtWhen(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function cutsLabel(lockage) {
  const cuts = Number(lockage?.cuts) || (lockage?.is_double_lockage ? 2 : 1);
  if (cuts <= 1) return "Single";
  if (cuts === 2) return "Double";
  return `${cuts} cuts`;
}

// title: what the row is about - the lock (vessel views) or the vessel (lock views).
export default function LockageRow({ lockage, title }) {
  const l = lockage || {};
  const up = l.direction === "upbound";
  const down = l.direction === "downbound";
  const cuts = cutsLabel(l);
  const barges = Number.isFinite(Number(l.barge_count)) && l.barge_count !== null ? Number(l.barge_count) : null;
  return (
    <div className="py-1 border-b border-slate-800 last:border-0 text-xs" data-testid="lockage-row">
      <div className="flex justify-between items-center gap-2">
        <span className="text-white truncate">
          {title || l.lock_name || l.lock_id}
          {(up || down) && (
            <span className={`ml-1 ${up ? "text-green-400" : "text-red-400"}`}>{up ? "↑" : "↓"}</span>
          )}
        </span>
        <span className="text-slate-500 shrink-0">{fmtWhen(l.entry_time || l.recorded_at)}</span>
      </div>
      <div className="flex flex-wrap gap-x-3 text-slate-400 mt-0.5">
        <span>Wait <span className="text-slate-200 font-mono">{fmtDuration(l.wait_time_minutes)}</span></span>
        <span>Lockage <span className="text-slate-200 font-mono">{fmtDuration(l.lockage_duration_minutes)}</span></span>
        <span className={cuts === "Single" ? "text-slate-400" : "text-amber-400"}>{cuts}</span>
        {barges !== null && <span>{barges} {barges === 1 ? "barge" : "barges"}</span>}
      </div>
    </div>
  );
}
