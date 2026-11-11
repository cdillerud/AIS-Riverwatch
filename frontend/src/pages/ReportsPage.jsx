import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { ArrowLeft, FileText, Download, Mail, Printer, Table2, Send } from "lucide-react";

import { API } from "@/lib/api";
import { reportDates } from "@/lib/reportDates";

// Daily Traffic Report: the server renders the report (one file that works as
// an email body, a download and a printout); this page shows it and offers the
// ways to take it away.
export default function ReportsPage() {
  const navigate = useNavigate();
  const dates = useMemo(() => reportDates(new Date(), 30), []);
  const [day, setDay] = useState(dates[1].value); // yesterday: the last full day
  const [html, setHtml] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sub, setSub] = useState(null);
  const [busy, setBusy] = useState("");
  const frameRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/reports/traffic?date=${day}&format=html`, { credentials: "include" });
      if (res.status === 401) { navigate("/login"); return; }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Couldn't load the report (${res.status})`);
      }
      setHtml(await res.text());
    } catch (e) {
      setError(e.message);
      setHtml("");
    } finally {
      setLoading(false);
    }
  }, [day, navigate]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    fetch(`${API}/reports/traffic/subscription`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setSub)
      .catch(() => setSub(null));
  }, []);

  // Grow the frame to the report's height so the page scrolls, not the frame.
  const fitFrame = () => {
    const f = frameRef.current;
    const doc = f?.contentDocument;
    if (f && doc?.body) f.style.height = `${doc.documentElement.scrollHeight + 8}px`;
  };

  const download = async (format) => {
    setBusy(format);
    try {
      const res = await fetch(`${API}/reports/traffic?date=${day}&format=${format}&download=true`, { credentials: "include" });
      if (!res.ok) throw new Error(`Download failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = format === "tows" ? `riverwatch-tows-${day}.csv` : `riverwatch-traffic-${day}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      if (format === "eml") toast.success("Email saved - open it to address and send it");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy("");
    }
  };

  const print = () => frameRef.current?.contentWindow?.print();

  const emailMe = async () => {
    setBusy("email");
    try {
      const res = await fetch(`${API}/reports/traffic/email-me?date=${day}`, { method: "POST", credentials: "include" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't send it");
      toast.success(`Sent to ${data.sent_to}`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy("");
    }
  };

  const toggleDaily = async (on) => {
    const prev = sub;
    setSub((s) => ({ ...s, daily_email: on }));
    try {
      const res = await fetch(`${API}/reports/traffic/subscription`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ daily_email: on }),
      });
      if (!res.ok) throw new Error();
      toast.success(on ? "You'll get the report every morning" : "Daily email off");
    } catch {
      setSub(prev);
      toast.error("Couldn't save that");
    }
  };

  const hour = sub?.send_hour_central ?? 6;
  const sendTime = `${hour % 12 || 12} ${hour < 12 ? "AM" : "PM"}`;

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="max-w-5xl mx-auto px-4 py-5 sm:p-6 space-y-4">
        <div className="flex items-center gap-3 flex-wrap">
          <Button variant="ghost" size="sm" onClick={() => navigate("/dashboard")}
                  className="text-slate-300 hover:text-white" data-testid="reports-back-btn">
            <ArrowLeft className="w-4 h-4 mr-1" />
            Dashboard
          </Button>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="w-6 h-6 text-cyan-400" />
            Traffic Report
          </h1>
        </div>

        <div className="glass-panel border border-slate-800 rounded-lg p-3 sm:p-4 space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <label htmlFor="report-day" className="text-sm text-slate-400">Day</label>
            <select id="report-day" value={day} onChange={(e) => setDay(e.target.value)}
                    className="bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm"
                    data-testid="report-day-select">
              {dates.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
            </select>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Button size="sm" onClick={() => download("html")} disabled={!!busy || !html}
                    className="bg-cyan-600 hover:bg-cyan-500" data-testid="report-download-html">
              <Download className="w-4 h-4 mr-1" /> Download
            </Button>
            <Button size="sm" variant="outline" onClick={print} disabled={!html}
                    className="border-slate-700 text-slate-200" data-testid="report-print">
              <Printer className="w-4 h-4 mr-1" /> Print / PDF
            </Button>
            <Button size="sm" variant="outline" onClick={() => download("eml")} disabled={!!busy || !html}
                    className="border-slate-700 text-slate-200" data-testid="report-download-eml"
                    title="A ready-to-send email (report + spreadsheet attached) that opens in Outlook or Mail">
              <Mail className="w-4 h-4 mr-1" /> Email draft
            </Button>
            <Button size="sm" variant="outline" onClick={() => download("csv")} disabled={!!busy || !html}
                    className="border-slate-700 text-slate-200" data-testid="report-download-csv">
              <Table2 className="w-4 h-4 mr-1" /> Spreadsheet (CSV)
            </Button>
            <Button size="sm" variant="outline" onClick={() => download("tows")} disabled={!!busy || !html}
                    className="border-slate-700 text-slate-200" data-testid="report-download-tows"
                    title="Every tow at every lock: barges, wait, lockage time, single/double">
              <Table2 className="w-4 h-4 mr-1" /> Tow detail (CSV)
            </Button>
            {sub?.email_available && (
              <Button size="sm" variant="outline" onClick={emailMe} disabled={!!busy || !html}
                      className="border-slate-700 text-slate-200" data-testid="report-email-me">
                <Send className="w-4 h-4 mr-1" /> Email to me
              </Button>
            )}
          </div>
          {sub && (
            <div className="flex items-center gap-3 pt-1 text-sm">
              <Switch checked={!!sub.daily_email} onCheckedChange={toggleDaily}
                      disabled={!sub.email_available} data-testid="report-daily-switch" />
              <span className={sub.email_available ? "text-slate-300" : "text-slate-500"}>
                {sub.email_available
                  ? `Email me yesterday's report every morning at ${sendTime} Central${sub.email ? ` (${sub.email})` : ""}`
                  : "Daily email isn't set up on this server yet. Use Email draft to send it from your own mail."}
              </span>
            </div>
          )}
        </div>

        {loading && <div className="text-center py-12 text-slate-400">Loading report…</div>}
        {error && <div className="text-center py-12 text-red-400" data-testid="report-error">{error}</div>}
        {!loading && !error && html && (
          <iframe ref={frameRef} title="Traffic Report" srcDoc={html} onLoad={fitFrame}
                  className="w-full rounded-lg bg-white border border-slate-800"
                  style={{ minHeight: 600 }} data-testid="report-frame" />
        )}
      </div>
    </div>
  );
}
