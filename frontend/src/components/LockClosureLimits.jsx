// River level vs this lock's published closure limit (backend
// services/lock_limits.py). Computed lines appear only when the reading is the
// same quantity on the district's own gauge; otherwise the published limits
// are shown as reference text. Never says the lock is open or closed.
export default function LockClosureLimits({ limits }) {
  if (!limits || !limits.district) return null;
  const comparisons = limits.comparisons || [];
  const references = limits.references || [];
  if (!comparisons.length && !references.length) return null;
  return (
    <div className="mb-3 text-xs" data-testid="lock-closure-limits">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Closure limits</div>
      {comparisons.map((c) => (
        <p
          key={`${c.kind}-${c.limit_kind}`}
          className={c.near ? "text-amber-300" : "text-slate-200"}
          title={`${c.gauge}${c.observed_at ? ` · ${new Date(c.observed_at).toLocaleString()}` : ""}`}
          data-testid="lock-limit-comparison"
        >
          {c.text}
        </p>
      ))}
      {references.map((r) => (
        <p key={r} className="text-slate-400" data-testid="lock-limit-reference">{r}</p>
      ))}
      <p className="text-[10px] text-slate-500 mt-1">
        <a href={limits.source_url} target="_blank" rel="noreferrer" className="hover:underline">
          {limits.district}
        </a>
        {limits.checked ? `, limits checked ${limits.checked}` : ""}
        {comparisons.length ? " · current readings: USACE water management data" : ""}
      </p>
    </div>
  );
}
