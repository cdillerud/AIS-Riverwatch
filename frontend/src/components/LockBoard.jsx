import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { API } from "@/lib/api";
import { fmtDuration } from "@/components/LockageRow";
import { fmtRiverTime } from "@/lib/riverTime";
import { aisNearLocks } from "@/lib/aisAtLocks";
import { getVesselDisplayName } from "@/utils/vesselDisplay";

// Lock-first view: every lock's status, queue, estimated wait and typical
// lockage times from USACE data. Works with no AIS feed. The boat's own
// position (phone GPS / AIS) narrows it to the locks ahead; live AIS boats
// near each lock are listed beside the USACE queue.

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

function Vessel({ v, locking, onOpen, aisMatch }) {
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
    <div className="text-xs py-1 cursor-pointer hover:bg-slate-800/50 rounded" data-testid="lock-queue-row"
         onClick={(e) => { e.stopPropagation(); onOpen?.(); }} title="Vessel details">
      <div className="flex justify-between gap-2">
        <span className="truncate text-slate-200 underline decoration-slate-600 underline-offset-2">
          {!locking && <span className="text-slate-500 mr-1">{v.position}.</span>}
          {v.vessel_name || "Unknown"} <span className={arrowCls}>{arrow}</span>
        </span>
        <span className="shrink-0 text-slate-400">
          {barges}{v.needs_double && <span className="text-amber-400"> · double lockage</span>}
        </span>
      </div>
      <div className="text-[11px] text-slate-500 pl-3">{state}</div>
      {aisMatch && (
        <div className="text-[11px] text-slate-500 pl-3" data-testid="lock-queue-ais">
          <span className="text-cyan-400/80">On AIS</span>
          {` · ${aisMatch.distance_mi < 0.3 ? "at the lock" : `${aisMatch.distance_mi} mi ${aisMatch.side}`}`}
          {aisMatch.moving ? ` · ${((Number(aisMatch.vessel.speed) || 0) * 1.15078).toFixed(1)} mph` : " · stopped"}
        </div>
      )}
    </div>
  );
}

// "C. MICHAEL REEVES" (AIS) and "C MICHAEL REEVES" (USACE) are the same boat
const normName = (x) => String(x || "").toUpperCase().replace(/[^A-Z0-9]/g, "");

// Live AIS boats at or heading for this lock - the boats Boat Beacon shows.
function AisRow({ a, onOpen }) {
  const v = a.vessel;
  const up = a.direction === "upbound";
  const arrow = a.direction ? (up ? "↑" : "↓") : "";
  const mph = (Number(v.speed) || 0) * 1.15078;
  const where = a.distance_mi < 0.3 ? "at the lock" : `${a.distance_mi} mi ${a.side}`;
  return (
    <div className="flex justify-between gap-2 text-xs py-0.5 text-slate-300 cursor-pointer hover:bg-slate-800/50 rounded"
         data-testid="lock-ais-row" onClick={(e) => { e.stopPropagation(); onOpen?.(); }} title="Vessel details">
      <span className="truncate">
        <span className="underline decoration-slate-600 underline-offset-2">{getVesselDisplayName(v)}</span> <span className={up ? "text-green-400" : "text-red-400"}>{arrow}</span>
        <span className="text-slate-500"> · {where}{a.moving ? ` · ${mph.toFixed(1)} mph` : " · stopped"}</span>
      </span>
      {a.moving && a.eta_minutes != null && (
        <span className="shrink-0 font-mono text-slate-300" title="At its current speed">≈ {fmtDuration(a.eta_minutes)}</span>
      )}
    </div>
  );
}

function LockCard({ lock, selected, onSelectLock, onLockDetails, onVesselDetails, ais = [] }) {
  const t = lock.typical || {};
  const wait = lock.wait_estimate_minutes;
  const busy = wait >= 60;
  // A boat in the USACE queue that is also on AIS is listed once, in the
  // queue, with its AIS position; "On AIS now" lists only the others.
  const aisMatch = (e) => ais.find(a => (e.mmsi && String(a.vessel.mmsi) === String(e.mmsi))
    || (normName(e.vessel_name) && normName(a.vessel.name) === normName(e.vessel_name)));
  const queued = [...(lock.locking || []), ...(lock.waiting || [])];
  const matched = new Set(queued.map(aisMatch).filter(Boolean));
  const aisOnly = ais.filter(a => !matched.has(a));
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
              <>
                <div className={`text-sm font-mono ${busy ? "text-amber-400" : "text-white"}`}>Tow ≈ {fmtDuration(wait)}</div>
                {lock.wait_range_minutes && lock.wait_range_minutes[1] > lock.wait_range_minutes[0] && (
                  <div className="text-[11px] text-slate-400 font-mono" data-testid="wait-range"
                       title="Where most tow waits at this lock have landed for estimates like this (middle 60%), learned from USACE records">
                    likely {fmtDuration(lock.wait_range_minutes[0])}–{fmtDuration(lock.wait_range_minutes[1])}
                  </div>
                )}
              </>
            ) : lock.queue_stale ? (
              <div className="text-sm font-mono text-slate-400">Queue unknown</div>
            ) : (
              <div className="text-sm font-mono text-green-400">No queue</div>
            )}
            <div className="text-[11px] text-slate-400 font-mono">
              {lock.queue_count > 0 ? "" : `tow ≈ ${fmtDuration(wait)} · `}pleasure ≈ {fmtDuration(lock.wait_estimate_recreational_minutes)}
              {lock.wait_range_recreational_minutes && lock.wait_range_recreational_minutes[1] > lock.wait_range_recreational_minutes[0]
                && ` (${fmtDuration(lock.wait_range_recreational_minutes[0])}–${fmtDuration(lock.wait_range_recreational_minutes[1])})`}
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
          {lock.locking.map((v, i) => { const m = aisMatch(v); return <Vessel key={`l${i}`} v={v} locking aisMatch={m} onOpen={() => onVesselDetails?.(m ? m.vessel : v, lock.name)} />; })}
          {lock.waiting.slice(0, 5).map((v, i) => { const m = aisMatch(v); return <Vessel key={`w${i}`} v={v} aisMatch={m} onOpen={() => onVesselDetails?.(m ? m.vessel : v, lock.name)} />; })}
          {lock.waiting.length > 5 && (
            <div className="text-[11px] text-slate-500">+{lock.waiting.length - 5} more waiting</div>
          )}
        </div>
      )}

      {aisOnly.length > 0 && (
        <div className="mt-2 border-t border-slate-800 pt-1.5" data-testid="lock-ais">
          <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-0.5"
               title="Live positions from your AIS feed (Boat Beacon): boats stopped within 3 mi of this lock, or under way toward it within 15 mi. A boat stopped near a lock may be moored or fleeting, not waiting.">
            On AIS now
          </div>
          {aisOnly.slice(0, 6).map((a, i) => (
            <AisRow key={a.vessel.mmsi || i} a={a} onOpen={() => onVesselDetails?.(a.vessel, lock.name)} />
          ))}
          {aisOnly.length > 6 && <div className="text-[11px] text-slate-500">+{aisOnly.length - 6} more</div>}
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

export default function LockBoard({ userVessel, selectedLockId, onSelectLock, onLockDetails, onVesselDetails, compact = false,
                                    aisVessels = [], allLocks = [] }) {
  // Live AIS boats (already filtered to fresh positions, not our own boat)
  const aisByLock = useMemo(() => aisNearLocks(aisVessels, allLocks), [aisVessels, allLocks]);
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
                    onSelectLock={onSelectLock} onLockDetails={onLockDetails} onVesselDetails={onVesselDetails}
                    ais={aisByLock[lock.lock_id] || []} />
        ))}
        {!loading && !error && locks.length === 0 && (
          <div className="text-xs text-slate-500 py-4 text-center">No locks in that direction from your position.</div>
        )}
      </div>
    </div>
  );
}
