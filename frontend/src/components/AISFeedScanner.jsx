import { useEffect, useState, useCallback, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Radar,
  RefreshCw,
  Wifi,
  WifiOff,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL + "/api/ais-scan";

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function statusColor(s) {
  if (s === "ais_detected") return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
  if (s === "nmea_detected") return "bg-cyan-500/20 text-cyan-300 border-cyan-500/40";
  if (s === "data_received") return "bg-amber-500/20 text-amber-300 border-amber-500/40";
  if (s === "socket_open") return "bg-slate-700 text-slate-300 border-slate-500/40";
  return "bg-slate-800 text-slate-400 border-slate-600/40";
}

export default function AISFeedScanner() {
  const [status, setStatus] = useState(null);
  const [results, setResults] = useState([]);
  const [subnet, setSubnet] = useState("");
  const [loading, setLoading] = useState(false);
  const [selecting, setSelecting] = useState(null);
  const [scannerError, setScannerError] = useState(null);
  const pollRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([
        fetch(`${API}/status`).then((x) => x.json()),
        fetch(`${API}/results`).then((x) => x.json()),
      ]);
      setStatus(s);
      setResults(r?.results || []);
      setScannerError(null);
    } catch (e) {
      setScannerError(e?.message || "Failed to reach relay");
    }
  }, []);

  // Initial + light polling while a scan is in progress
  useEffect(() => {
    refresh();
    pollRef.current = setInterval(() => {
      if (status?.scan_status?.state === "running") refresh();
    }, 2000);
    return () => clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.scan_status?.state]);

  const startScan = useCallback(async () => {
    setLoading(true);
    try {
      const body = subnet ? { subnet } : {};
      const r = await fetch(`${API}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(d.detail || "scan failed");
      }
      toast.success("Scan started" + (subnet ? ` on ${subnet}` : ""));
      // Quick refresh + start polling
      await refresh();
    } catch (e) {
      toast.error(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }, [subnet, refresh]);

  const selectFeed = useCallback(async (c) => {
    setSelecting(`${c.ip}:${c.port}`);
    try {
      const r = await fetch(`${API}/select`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ip: c.ip, port: c.port }),
      });
      if (!r.ok) throw new Error("select failed");
      toast.success(`Selected ${c.ip}:${c.port} as Boat Beacon feed`);
      await refresh();
    } catch (e) {
      toast.error(String(e.message || e));
    } finally {
      setSelecting(null);
    }
  }, [refresh]);

  const clearFeed = useCallback(async () => {
    try {
      const r = await fetch(`${API}/clear`, { method: "POST" });
      if (!r.ok) throw new Error("clear failed");
      toast.success("Cleared selected feed");
      await refresh();
    } catch (e) {
      toast.error(String(e.message || e));
    }
  }, [refresh]);

  const selected = status?.selected_feed;
  const upstream = status?.upstream;
  const scanState = status?.scan_status?.state || "idle";
  const lastScan = status?.last_scan;

  return (
    <Card className="bg-slate-900/60 border-white/10" data-testid="ais-scanner-panel">
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-sm uppercase tracking-wider text-slate-200">
          <span className="flex items-center gap-2">
            <Radar className="w-4 h-4 text-cyan-400" />
            AIS Feed Scanner
          </span>
          <Badge className="bg-cyan-500/10 text-cyan-300 border-cyan-500/30 text-[10px]">
            Boat Beacon discovery
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Currently selected feed + upstream health */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="p-3 rounded-md border border-white/5 bg-slate-950/50">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Selected feed</div>
            {selected ? (
              <div className="mt-1 flex items-center gap-2 flex-wrap">
                <div className="font-mono text-cyan-300 text-base" data-testid="selected-feed">
                  {selected.selected_ip}:{selected.selected_port}
                </div>
                <Badge className="bg-cyan-500/15 text-cyan-300 border-cyan-500/30 text-[10px] uppercase">
                  {selected.source || "scanner"}
                </Badge>
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto text-slate-500 hover:text-red-300"
                  onClick={clearFeed}
                  data-testid="scanner-clear-btn"
                  title="Clear selection"
                >
                  <Trash2 className="w-3 h-3 mr-1" /> Clear
                </Button>
                <div className="w-full text-[10px] text-slate-500 mt-1">
                  Selected {fmtTime(selected.selected_at)}
                </div>
                {selected.last_successful_sample && (
                  <div className="w-full text-[10px] text-slate-500 font-mono truncate">
                    Sample: {selected.last_successful_sample}
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-1 text-amber-300 text-sm" data-testid="no-feed-selected">
                No Boat Beacon feed selected
              </div>
            )}
          </div>
          <div className="p-3 rounded-md border border-white/5 bg-slate-950/50">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Upstream</div>
            <div className="mt-1 flex items-center gap-2">
              {upstream?.connected ? (
                <>
                  <Wifi className="w-4 h-4 text-emerald-400" />
                  <span className="text-emerald-300 text-sm" data-testid="upstream-status-connected">Connected</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-4 h-4 text-slate-500" />
                  <span className="text-slate-400 text-sm" data-testid="upstream-status-disconnected">Disconnected</span>
                </>
              )}
              <span className="ml-auto text-[10px] text-slate-500 font-mono">
                {upstream?.lines_received ?? 0} lines
              </span>
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              Last line: {fmtTime(upstream?.last_line_at)}
              {upstream?.last_error && (
                <span className="block text-red-400/80">err: {upstream.last_error}</span>
              )}
            </div>
          </div>
        </div>

        {/* Scan controls */}
        <div className="flex items-end gap-3 flex-wrap">
          <div className="flex-1 min-w-[200px] space-y-1.5">
            <Label className="text-xs text-slate-400">Optional subnet override</Label>
            <Input
              type="text"
              placeholder="e.g. 192.168.1.0/24"
              value={subnet}
              onChange={(e) => setSubnet(e.target.value)}
              disabled={scanState === "running"}
              data-testid="scanner-subnet-input"
              className="bg-slate-950/60 border-white/10 font-mono text-xs"
            />
          </div>
          <Button
            onClick={startScan}
            disabled={loading || scanState === "running"}
            className="bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold"
            data-testid="scanner-start-btn"
          >
            {scanState === "running" ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> Scanning…
              </>
            ) : (
              <>
                <Radar className="w-4 h-4 mr-1.5" /> Scan
              </>
            )}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={refresh}
            className="text-slate-400 hover:text-cyan-300"
            data-testid="scanner-refresh-btn"
          >
            <RefreshCw className="w-3 h-3 mr-1" /> Refresh
          </Button>
        </div>

        {/* Scan progress */}
        {scanState === "running" && status?.scan_status && (
          <div className="text-xs text-slate-400" data-testid="scanner-progress">
            Scanning {status.scan_status.subnet || "local subnet"}:{" "}
            <span className="font-mono text-cyan-300">
              {status.scan_status.scanned}/{status.scan_status.total}
            </span>{" "}
            ({Math.round((status.scan_status.progress || 0) * 100)}%)
          </div>
        )}

        {scannerError && (
          <div className="text-xs text-red-400 flex items-center gap-1" data-testid="scanner-error">
            <AlertTriangle className="w-3 h-3" /> {scannerError}
          </div>
        )}

        {lastScan && (
          <div className="text-[11px] text-slate-500">
            Last scan: {fmtTime(lastScan.finished_at)} — {lastScan.candidates_count} candidate
            {lastScan.candidates_count === 1 ? "" : "s"} on {lastScan.subnet || "local subnet"}
          </div>
        )}

        {/* Results table */}
        {results.length > 0 ? (
          <div className="rounded-md border border-white/5 overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-slate-900/80 text-slate-400 uppercase text-[10px] tracking-wider">
                <tr>
                  <th className="text-left p-2.5">Candidate</th>
                  <th className="text-left p-2.5">Status</th>
                  <th className="text-right p-2.5">Score</th>
                  <th className="text-left p-2.5">Sample</th>
                  <th className="text-right p-2.5">Action</th>
                </tr>
              </thead>
              <tbody>
                {results.map((c) => {
                  const key = `${c.ip}:${c.port}`;
                  const isSelected =
                    selected &&
                    selected.selected_ip === c.ip &&
                    Number(selected.selected_port) === Number(c.port);
                  return (
                    <tr key={key} className="border-t border-white/5 hover:bg-slate-800/30" data-testid={`candidate-${c.ip}-${c.port}`}>
                      <td className="p-2.5 font-mono text-slate-200">
                        {c.ip}:{c.port}
                      </td>
                      <td className="p-2.5">
                        <Badge className={`${statusColor(c.status)} text-[10px] uppercase`}>
                          {c.status}
                        </Badge>
                      </td>
                      <td className="text-right p-2.5 font-mono text-slate-300">{c.score}</td>
                      <td className="p-2.5 text-slate-500 font-mono truncate max-w-[260px]" title={c.sample || ""}>
                        {c.sample ? c.sample.slice(0, 80) : "—"}
                      </td>
                      <td className="text-right p-2.5">
                        {isSelected ? (
                          <Badge className="bg-emerald-500/15 text-emerald-300 border-emerald-500/30 text-[10px] uppercase">
                            <CheckCircle2 className="w-3 h-3 mr-1" /> Selected
                          </Badge>
                        ) : (
                          <Button
                            size="sm"
                            onClick={() => selectFeed(c)}
                            disabled={selecting === key}
                            className="h-7 px-2 bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-[11px]"
                            data-testid={`use-feed-${c.ip}-${c.port}`}
                          >
                            {selecting === key ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              "Use this feed"
                            )}
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          scanState !== "running" && (
            <div className="py-6 text-center text-slate-500 text-sm" data-testid="scanner-empty">
              {lastScan
                ? "No candidates discovered on the last scan."
                : "Run a scan to discover Boat Beacon feeds on the LAN."}
            </div>
          )
        )}
      </CardContent>
    </Card>
  );
}
