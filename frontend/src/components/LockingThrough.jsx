import { useState } from "react";
import { Phone, Radio, ChevronDown, ChevronUp, BookOpen } from "lucide-react";
import { vhfFor, telHref, lockingSteps, CFR_URL } from "../lib/lockInfo";

// "Locking through" card in the lock detail: how to call this lock (VHF,
// phone) up top, the steps and signals one tap away.
export default function LockingThrough({ lockId, phone, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const vhf = vhfFor(lockId);
  const tel = telHref(phone);
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/30" data-testid="locking-through">
      <div className="p-3 flex flex-wrap items-center gap-2">
        <span className="font-semibold text-white text-sm mr-auto flex items-center gap-1.5">
          <BookOpen className="w-4 h-4 text-cyan-400" /> Locking through
        </span>
        <span className="inline-flex items-center gap-1 rounded border border-cyan-500/40 px-2 py-1 text-sm text-cyan-300 font-mono" data-testid="lock-vhf">
          <Radio className="w-3.5 h-3.5" /> VHF {vhf.channel}
        </span>
        {tel && (
          <a href={tel} className="inline-flex items-center gap-1 rounded border border-slate-600 px-2 py-1 text-sm text-slate-200 hover:bg-slate-800 font-mono" data-testid="lock-phone">
            <Phone className="w-3.5 h-3.5" /> {phone}
          </a>
        )}
      </div>
      {vhf.note && <p className="px-3 -mt-1 pb-2 text-xs text-amber-400">{vhf.note}</p>}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 border-t border-slate-700 text-xs text-slate-400 hover:text-white"
        data-testid="locking-steps-toggle"
      >
        <span>{open ? "Hide" : "Show"} steps and signals for pleasure boats</span>
        {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>
      {open && (
        <div className="px-3 pb-3">
          <ol className="space-y-2 text-sm" data-testid="locking-steps">
            {lockingSteps(lockId).map((s, i) => (
              <li key={s.title} className="flex gap-2">
                <span className="text-cyan-400 font-mono">{i + 1}.</span>
                <span><span className="font-semibold text-white">{s.title}.</span> <span className="text-slate-300">{s.text}</span></span>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-[11px] text-slate-500">
            From the federal lock rules (<a href={CFR_URL} target="_blank" rel="noreferrer" className="underline">33 CFR 207.300</a>) and
            USACE district guidance. The lock staff's instructions always come first.
          </p>
        </div>
      )}
    </div>
  );
}
