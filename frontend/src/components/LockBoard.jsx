import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { API } from "@/lib/api";
import { fmtDuration } from "@/components/LockageRow";
import { fmtRiverTime } from "@/lib/riverTime";

// Lock-first view: every lock's status, queue, estimated wait and typical
// lockage times from USACE data. Works with no AIS feed. The boat's own
// position (phone GPS / AIS) only narrows it to the locks ahead.

const POLL_MS = 60000;

export const WAIT_TOOLTIP =
  "Estimated wait for a boat arriving now, from the USACE queue. The model is re-checked nightly " +
  "against recent USACE lockages and only updated when it gets more accurate. Pleasure boats are " +
  "usually fit in around tows, so they wait less. Long queues are the least predictable.";

function headingToDirection(heading) {
  if (heading === "northbound" || heading === "upbound" || heading === "upstream") return "upbound";
  if (heading === "southbound" || heading === "downbound" || heading === "downstream") return "downbound";
  return null;
}

function lockLabel(lockId) {
  if (lockId === "melvin_price") return "Mel Price";
  if (lockId === "chain_of_rocks") return "L27";
  return (lockId || "").replace("lock_", "L").toUpperCase();
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : fmtRiverTime(d);   // Central time, like the locks
}

function StatusBadge({ lock }) {
  const s = lock.status || "UNKNOWN";
  const cls = s === "OPEN" ? "text-green-400 border-green-500/40"
    : s === "CLOSED" ? "text-red-400 border-red-500/40"
    : s === "RESTRICTED" ? "text-amber-400 border-amber-500/40"
    : "text-slate-400 border-slate-600";
  const title = lock.status_source === "recent_lockage"
    ? `${lock.closure_info || "Recent lockage reported"} - not an official status`
    : lock.closure_info || (s === "UNKNOWN" ? "No current status from USACE" : "USACE district status");
  return (
    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${cls}`} title={title}>
      {s === "UNKNOWN" ? "STATUS ?" : s}{lock.status_source === "recent_lockage" ? "*" : ""}
    </span>
  );
}

// A vessel at the lock. USACE posts a lockage only once it has ended, so a
// vessel "at lock" may be waiting or already in the chamber; the time shown
// is since it checked in (USACE arrival time). "Locking now" appears only if
// USACE ever reports a start time without an end.
function minutesSince(iso) {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.max(0, Math.round((Date.now() - t) / 60000));
}

function Vessel({ v, locking }) {
  const arrow = v.direction === "upbound" ? "↑" : v.direction === "downbound" ? "↓" : "";
  const arrowCls = v.direction === "upbound" ? "text-green-400" : "text-red-400";
  const barges = v.barges ? `${v.barges} ${v.barges === 1 ? "barge" : "barges"}` : "light boat";
  let state;
  if (locking) {
    const inLock = minutesSince(v.started_at);
    state = (
      <>
        <span className="text-cyan-400">Locking now</span>
        {v.cuts_completed > 0 && ` · cut ${v.cuts_completed} of ${v.cuts_completed + 1} done`}
        {v.started_at && ` · started ${fmtTime(v.started_at)}${inLock != null ? ` (${fmtDuration(inLock)} in)` : ""}`}
      </>
    );
  } else {
    state = (
      <>
        <span className="text-slate-300">At lock{v.waiting_minutes != null ? ` ${fmtDuration(v.waiting_minutes)}` : ""}</span>
        {v.arrived_at && ` · arrived ${fmtTime(v.arrived_at)}`}
      </>
    );
  }
  return (
    <div className="text-xs py-1">
      <div className="flex justify-between gap-2">
        <span className="truncate text-slate-200">
          {!locking && <span className="text-slate-500 mr-1">{v.position}.</span>}
          {v.vessel_name || "Unknown"} <span className={arrowCls}>{arrow}</span>
        </span>
        <span className="shrink-0 text-slate-400">
          {barges}{v.needs_double && <span className="text-amber-400"> · double lockage</span>}
        </span>
      </div>
      <div className="text-[11px] text-slate-500 pl-3">{state}</div>
    </div>
  );
}

function LockCard({ lock, selected, onSelectLock, onLockDetails }) {
  const t = lock.typical || {};
  const wait = lock.wait_estimate_minutes;
  const busy = wait >= 60;
  return (
    <div
      className={`rounded border p-3 cursor-pointer ${selected ? "border-cyan-500/70 bg-cyan-500/5" : "border-slate-700 bg-slate-900/40 hover:border-slate-500"}`}
      onClick={() => onSelectLock?.(lock.lock_id)}
      aria-selected={selected}
      data-testid="lock-board-card"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm text-white font-medium break-words">{lock.name}</div>
          <div className="text-[11px] text-slate-500 font-mono">
            RM {lock.river_mile}{lock.distance_mi != null ? ` · ${lock.distance_mi} mi away` : ""}
          </div>
        </div>
        <div className="text-right shrink-0">
          <StatusBadge lock={lock} />
          <div className="mt-1 text-right" title={WAIT_TOOLTIP}>
            {lock.queue_count > 0 ? (
              <div className={`text-sm font-mono ${busy ? "text-amber-400" : "text-white"}`}>Tow ≈ {fmtDuration(wait)}</div>
            ) : lock.queue_stale ? (
              <div className="text-sm font-mono text-slate-400">Queue unknown</div>
            ) : (
              <div className="text-sm font-mono text-green-400">No queue</div>
            )}
            <div className="text-[11px] text-slate-400 font-mono">
              {lock.queue_count > 0 ? "" : `tow ≈ ${fmtDuration(wait)} · `}pleasure ≈ {fmtDuration(lock.wait_estimate_recreational_minutes)}
            </div>
            {lock.queue_stale && (
              <div className="text-[11px] text-amber-400/90" data-testid="queue-stale"
                   title="USACE queue data for this lock hasn't updated recently; the queue and waits may be out of date">
                {lock.queue_age_minutes != null ? `Queue data ${fmtDuration(lock.queue_age_minutes)} old` : "Waiting for USACE data"}
              </div>
            )}
          </div>
        </div>
      </div>

      {(lock.locking?.length > 0 || lock.waiting?.length > 0) && (
        <div className="mt-2 border-t border-slate-800 pt-1.5">
          {lock.locking.map((v, i) => <Vessel key={`l${i}`} v={v} locking />)}
          {lock.waiting.slice(0, 5).map((v, i) => <Vessel key={`w${i}`} v={v} />)}
          {lock.waiting.length > 5 && (
            <div className="text-[11px] text-slate-500">+{lock.waiting.length - 5} more waiting</div>
          )}
        </div>
      )}

      {lock.approaching?.length > 0 && (
        <div className="mt-2 border-t border-slate-800 pt-1.5" data-testid="lock-approaching">
          <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-0.5"
               title="Predicted from each vessel's last USACE lockage and typical transit times between these locks (typically within ~45 min)">
            Approaching · predicted
          </div>
          {lock.approaching.slice(0, 4).map((a, i) => {
            const up = a.direction === "upbound";
            return (
              <div key={i} className="flex justify-between gap-2 text-xs py-0.5 text-slate-300">
                <span className="truncate">
                  {a.vessel_name || "Unknown"} <span className={up ? "text-green-400" : "text-red-400"}>{up ? "↑" : "↓"}</span>
                  <span className="text-slate-500"> {a.barges ? `${a.barges}b` : "light"} · from {lockLabel(a.from_lock)}{a.via_lock ? ` via ${lockLabel(a.via_lock)}` : ""}</span>
                </span>
                {a.probability != null && a.probability < 0.8 && (
                  <span className="shrink-0 text-[10px] text-slate-500"
                        title="Share of tows on this stretch that continue to this lock (others stop at harbors or fleeting areas)">
                    likely {Math.round(a.probability * 100)}%
                  </span>
                )}
                <span className={`shrink-0 font-mono ${a.overdue ? "text-slate-500" : "text-slate-300"}`}
                      title={`Expected ${fmtTime(a.eta_earliest)}–${fmtTime(a.eta_latest)}`}>
                  {a.overdue ? `due ${fmtTime(a.eta)}` : `≈ ${fmtTime(a.eta)}`}
                </span>
              </div>
            );
          })}
          {lock.approaching.length > 4 && (
            <div className="text-[11px] text-slate-500">+{lock.approaching.length - 4} more</div>
          )}
        </div>
      )}

      <div className="mt-2 flex flex-wrap gap-x-3 text-[11px] text-slate-500">
        {t.sample_count > 0 && !t.is_baseline ? (
          <>
            <span>Single <span className="text-slate-300 font-mono">{fmtDuration(t.avg_single_lockage_minutes)}</span></span>
            {t.avg_double_lockage_minutes != null ? (
              <>
                <span>Double <span className="text-slate-300 font-mono">{fmtDuration(t.avg_double_lockage_minutes)}</span></span>
                {t.double_share != null && <span>{Math.round(t.double_share * 100)}% doubles</span>}
              </>
            ) : (
              <span>No double lockages</span>
            )}
            <span>Tow wait avg <span className="text-slate-300 font-mono">{fmtDuration(t.avg_tow_wait_minutes)}</span></span>
          </>
        ) : (
          <span>No recorded lockage history yet</span>
        )}
        {lock.last_lockage_minutes_ago != null && <span>Last lockage {fmtDuration(lock.last_lockage_minutes_ago)} ago</span>}
        <button
          className="ml-auto text-cyan-400 hover:text-cyan-300"
          onClick={(e) => { e.stopPropagation(); onLockDetails?.(lock.lock_id); }}
        >
          Details
        </button>
      </div>
    </div>
  );
}

export default function LockBoard({ userVessel, selectedLockId, onSelectLock, onLockDetails, compact = false }) {
  const autoDirection = headingToDirection(userVessel?.heading || userVessel?.heading_direction);
  const position = Number.isFinite(Number(userVessel?.river_mile)) ? Number(userVessel.river_mile) : null;

  const [directionChoice, setDirectionChoice] = useState("auto"); // auto | downbound | upbound
  const [scope, setScope] = useState("ahead");                     // ahead | all
  const [sort, setSort] = useState("river");                       // river | delay
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const direction = directionChoice === "auto" ? autoDirection : directionChoice;
  const canShowAhead = position != null && !!direction;
  const effectiveScope = canShowAhead ? scope : "all";

  const query = useMemo(() => {
    const p = new URLSearchParams({ scope: effectiveScope, sort });
    if (position != null) p.set("from_rm", String(position));
    if (direction) p.set("direction", direction);
    if (effectiveScope === "ahead") p.set("limit", "6");
    return p.toString();
  }, [effectiveScope, sort, position, direction]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/locks/board?${query}`, { credentials: "include" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
      setError(null);
    } catch (e) {
      setError(e.message || "Could not load the lock board");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const locks = data?.locks || [];
  const btn = (active) =>
    `px-2 py-0.5 rounded text-[11px] ${active ? "bg-slate-700 text-white" : "text-slate-400 hover:text-white"}`;

  return (
    <div className={`h-full flex flex-col ${compact ? "" : "p-3"}`} data-testid="lock-board">
      <div className="flex flex-wrap items-center gap-2 pb-2 border-b border-slate-800">
        <div className="flex items-center gap-1">
          <button className={btn(directionChoice === "auto")} onClick={() => setDirectionChoice("auto")}
                  title={autoDirection ? `From your position: ${autoDirection}` : "Direction unknown until you're under way"}>
            Auto{autoDirection ? ` (${autoDirection === "upbound" ? "↑" : "↓"})` : ""}
          </button>
          <button className={btn(directionChoice === "downbound")} onClick={() => setDirectionChoice("downbound")}>↓ Down</button>
          <button className={btn(directionChoice === "upbound")} onClick={() => setDirectionChoice("upbound")}>↑ Up</button>
        </div>
        <div className="flex items-center gap-1">
          <button className={btn(effectiveScope === "ahead")} disabled={!canShowAhead}
                  onClick={() => setScope("ahead")}
                  title={canShowAhead ? "Locks ahead of you" : "Needs your position and direction"}>
            Ahead of me
          </button>
          <button className={btn(effectiveScope === "all")} onClick={() => setScope("all")}>All locks</button>
        </div>
        <div className="flex items-center gap-1">
          <button className={btn(sort === "river")} onClick={() => setSort("river")}>River order</button>
          <button className={btn(sort === "delay")} onClick={() => setSort("delay")}>Longest wait</button>
        </div>
        <button className="ml-auto text-slate-500 hover:text-white" onClick={load} title="Refresh">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      <div className="text-[11px] text-slate-500 py-1.5">
        {effectiveScope === "ahead"
          ? `Next locks ${direction === "upbound" ? "upbound" : "downbound"} from RM ${position}`
          : "All Upper Mississippi locks"}
        {" · "}USACE lock queue data, refreshed every few minutes · waits are estimates
        {data?.wait_model?.typical_error_minutes?.tow != null &&
          ` (typically within ~${Math.round(data.wait_model.typical_error_minutes.tow)} min for tows, ~${Math.round(data.wait_model.typical_error_minutes.recreational ?? 10)} min for pleasure boats)`}
        {" · "}"At lock" = checked in; USACE reports a lockage only when it ends
        {data?.generated_at && ` · ${fmtTime(data.generated_at)}`}
      </div>

      {error && <div className="text-xs text-red-400 py-2">{error}</div>}
      {data?.usace && data.usace.status !== "ok" && (
        <div className="text-xs text-amber-400 border border-amber-500/30 bg-amber-500/5 rounded px-2 py-1.5 mb-2" data-testid="usace-delayed">
          {data.usace.status === "down"
            ? "USACE lock queue data is not coming through right now - queues and waits may be out of date. Call the lock to confirm."
            : `USACE queue data is delayed for ${data.usace.stale_locks.length} lock${data.usace.stale_locks.length === 1 ? "" : "s"} - those are marked below.`}
        </div>
      )}

      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {locks.map((lock) => (
          <LockCard key={lock.lock_id} lock={lock} selected={lock.lock_id === selectedLockId}
                    onSelectLock={onSelectLock} onLockDetails={onLockDetails} />
        ))}
        {!loading && !error && locks.length === 0 && (
          <div className="text-xs text-slate-500 py-4 text-center">No locks in that direction from your position.</div>
        )}
      </div>
    </div>
  );
}
