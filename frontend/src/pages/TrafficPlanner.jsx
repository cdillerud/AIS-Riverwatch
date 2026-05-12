import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Route,
  Lock as LockIcon,
  Users as UsersIcon,
  AlertTriangle,
  ArrowLeft,
  Compass,
  Anchor,
  Clock,
  RefreshCw,
  Gauge,
  Navigation as NavIcon,
  TrendingUp,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

function fmtMinutes(min) {
  if (min == null) return "—";
  const m = Math.round(min);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r ? `${h}h ${r}m` : `${h}h`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function severityBadge(sev) {
  if (sev === "high") return "bg-red-500/20 text-red-300 border-red-500/40";
  if (sev === "moderate") return "bg-amber-500/20 text-amber-300 border-amber-500/40";
  return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
}

export default function TrafficPlanner() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [tab, setTab] = useState("trip");
  const [locks, setLocks] = useState([]);

  // Trip planner state
  const [originRm, setOriginRm] = useState("");
  const [destRm, setDestRm] = useState("");
  const [etd, setEtd] = useState(() => {
    const d = new Date();
    d.setSeconds(0, 0);
    return d.toISOString().slice(0, 16);
  });
  const [baseSpeed, setBaseSpeed] = useState("");
  const [mmsi, setMmsi] = useState("");
  const [tripPlan, setTripPlan] = useState(null);
  const [planning, setPlanning] = useState(false);

  // Queue state
  const [queueLockId, setQueueLockId] = useState("");
  const [queueLookahead, setQueueLookahead] = useState(6);
  const [queue, setQueue] = useState(null);
  const [queueLoading, setQueueLoading] = useState(false);

  // Meetings state
  const [meetingsLookahead, setMeetingsLookahead] = useState(4);
  const [meetings, setMeetings] = useState(null);
  const [meetingsLoading, setMeetingsLoading] = useState(false);

  // Bottlenecks state
  const [bottleneckHours, setBottleneckHours] = useState(6);
  const [bottlenecks, setBottlenecks] = useState(null);
  const [bottleneckLoading, setBottleneckLoading] = useState(false);

  // Pre-load primary vessel's mmsi/speed
  useEffect(() => {
    if (!user) return;
    const primary = (user.vessels || []).find((v) => v.is_primary) || (user.vessels || [])[0];
    if (primary && primary.mmsi) setMmsi(primary.mmsi);
  }, [user]);

  // Load lock list once
  useEffect(() => {
    fetch(`${API}/planning/locks`)
      .then((r) => r.json())
      .then((d) => {
        setLocks(d.locks || []);
        if (d.locks?.length && !queueLockId) setQueueLockId(d.locks[Math.floor(d.locks.length / 2)].lock_id);
      })
      .catch(() => toast.error("Failed to load locks"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // If mmsi is set, prefill AIS speed
  useEffect(() => {
    if (!mmsi) return;
    fetch(`${API}/user-vessel/simulation/${mmsi}`)
      .then((r) => r.json())
      .then((d) => {
        if (d && d.speed_knots && !baseSpeed) {
          setBaseSpeed(String(d.speed_knots));
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mmsi]);

  const submitTrip = useCallback(async () => {
    if (!originRm || !destRm) {
      toast.error("Please enter origin and destination river miles");
      return;
    }
    if (parseFloat(originRm) === parseFloat(destRm)) {
      toast.error("Origin and destination must differ");
      return;
    }
    setPlanning(true);
    try {
      const body = {
        origin_rm: parseFloat(originRm),
        destination_rm: parseFloat(destRm),
        etd: new Date(etd).toISOString(),
      };
      if (baseSpeed) body.base_speed_knots = parseFloat(baseSpeed);
      if (mmsi) body.mmsi = mmsi;
      const r = await fetch(`${API}/planning/trip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error("Trip planning failed");
      const d = await r.json();
      setTripPlan(d);
      toast.success(`Trip planned: ${fmtMinutes(d.total_minutes)}`);
    } catch (e) {
      toast.error("Failed to plan trip");
    } finally {
      setPlanning(false);
    }
  }, [originRm, destRm, etd, baseSpeed, mmsi]);

  const loadQueue = useCallback(async () => {
    if (!queueLockId) return;
    setQueueLoading(true);
    try {
      const r = await fetch(`${API}/planning/lock-queue/${queueLockId}?lookahead_hours=${queueLookahead}`);
      const d = await r.json();
      setQueue(d);
    } catch {
      toast.error("Failed to load queue");
    } finally {
      setQueueLoading(false);
    }
  }, [queueLockId, queueLookahead]);

  const loadMeetings = useCallback(async () => {
    setMeetingsLoading(true);
    try {
      const r = await fetch(`${API}/planning/meetings?lookahead_hours=${meetingsLookahead}`);
      const d = await r.json();
      setMeetings(d);
    } catch {
      toast.error("Failed to load meetings");
    } finally {
      setMeetingsLoading(false);
    }
  }, [meetingsLookahead]);

  const loadBottlenecks = useCallback(async () => {
    setBottleneckLoading(true);
    try {
      const r = await fetch(`${API}/planning/bottlenecks?hours=${bottleneckHours}`);
      const d = await r.json();
      setBottlenecks(d);
    } catch {
      toast.error("Failed to load bottlenecks");
    } finally {
      setBottleneckLoading(false);
    }
  }, [bottleneckHours]);

  useEffect(() => {
    if (tab === "queue") loadQueue();
    if (tab === "meetings") loadMeetings();
    if (tab === "bottlenecks") loadBottlenecks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const speedSourceLabel = useMemo(() => {
    if (!tripPlan) return null;
    if (tripPlan.speed_source === "ais") return "from AIS";
    if (tripPlan.speed_source === "user") return "manual";
    return "default";
  }, [tripPlan]);

  return (
    <div className="min-h-screen bg-slate-950 text-white font-sans" data-testid="traffic-planner-page">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-slate-950/90 backdrop-blur-md border-b border-white/5">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate("/dashboard")}
              className="text-slate-400 hover:text-white"
              data-testid="planner-back-btn"
              title="Back to dashboard"
            >
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <Compass className="w-5 h-5 text-cyan-400" />
            <div>
              <h1 className="text-base sm:text-lg font-bold uppercase tracking-wider">
                Traffic <span className="text-cyan-400">Planning</span>
              </h1>
              <p className="text-[10px] text-slate-500 uppercase tracking-widest">
                Trip ETA · Lock queue · Meeting predictor · Bottleneck forecast
              </p>
            </div>
          </div>
          <Badge className="bg-cyan-500/10 text-cyan-300 border-cyan-500/30 text-[10px]">
            BETA
          </Badge>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6 max-w-6xl">
        <Tabs value={tab} onValueChange={setTab} className="w-full">
          <TabsList className="grid w-full grid-cols-4 bg-slate-900/60 border border-white/5">
            <TabsTrigger value="trip" data-testid="planner-tab-trip" className="data-[state=active]:bg-cyan-500/20 data-[state=active]:text-cyan-300">
              <Route className="w-4 h-4 mr-1.5" /> Trip
            </TabsTrigger>
            <TabsTrigger value="queue" data-testid="planner-tab-queue" className="data-[state=active]:bg-cyan-500/20 data-[state=active]:text-cyan-300">
              <LockIcon className="w-4 h-4 mr-1.5" /> Lock Queue
            </TabsTrigger>
            <TabsTrigger value="meetings" data-testid="planner-tab-meetings" className="data-[state=active]:bg-cyan-500/20 data-[state=active]:text-cyan-300">
              <UsersIcon className="w-4 h-4 mr-1.5" /> Meetings
            </TabsTrigger>
            <TabsTrigger value="bottlenecks" data-testid="planner-tab-bottlenecks" className="data-[state=active]:bg-cyan-500/20 data-[state=active]:text-cyan-300">
              <AlertTriangle className="w-4 h-4 mr-1.5" /> Bottlenecks
            </TabsTrigger>
          </TabsList>

          {/* TRIP PLANNER */}
          <TabsContent value="trip" className="mt-4">
            <Card className="bg-slate-900/50 border-white/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm uppercase tracking-wider text-slate-300">
                  <Route className="w-4 h-4 text-cyan-400" /> Plan a Trip
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-400">Origin (RM)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      placeholder="e.g. 820.0"
                      value={originRm}
                      onChange={(e) => setOriginRm(e.target.value)}
                      data-testid="planner-origin-rm"
                      className="bg-slate-950/60 border-white/10"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-400">Destination (RM)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      placeholder="e.g. 600.0"
                      value={destRm}
                      onChange={(e) => setDestRm(e.target.value)}
                      data-testid="planner-destination-rm"
                      className="bg-slate-950/60 border-white/10"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-400">Departure</Label>
                    <Input
                      type="datetime-local"
                      value={etd}
                      onChange={(e) => setEtd(e.target.value)}
                      data-testid="planner-etd"
                      className="bg-slate-950/60 border-white/10"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-400 flex items-center gap-1">
                      <Gauge className="w-3 h-3" /> Speed (kn)
                    </Label>
                    <Input
                      type="number"
                      step="0.1"
                      placeholder="prefill from AIS"
                      value={baseSpeed}
                      onChange={(e) => setBaseSpeed(e.target.value)}
                      data-testid="planner-speed"
                      className="bg-slate-950/60 border-white/10"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-400">MMSI (optional)</Label>
                    <Input
                      type="text"
                      placeholder="for AIS prefill"
                      value={mmsi}
                      onChange={(e) => setMmsi(e.target.value)}
                      data-testid="planner-mmsi"
                      className="bg-slate-950/60 border-white/10"
                    />
                  </div>
                </div>

                <div className="mt-4 flex items-center gap-2 flex-wrap">
                  <Button onClick={submitTrip} disabled={planning} data-testid="planner-plan-btn" className="bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold">
                    {planning ? <RefreshCw className="w-4 h-4 animate-spin mr-1.5" /> : <Compass className="w-4 h-4 mr-1.5" />}
                    Plan Trip
                  </Button>
                  {locks.length > 0 && (
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <span>Quick pick:</span>
                      <Button variant="ghost" size="sm" className="h-7 text-[11px] text-slate-400 hover:text-cyan-300" onClick={() => { setOriginRm("847.6"); setDestRm("185.0"); }}>
                        Minneapolis → Chain of Rocks
                      </Button>
                      <Button variant="ghost" size="sm" className="h-7 text-[11px] text-slate-400 hover:text-cyan-300" onClick={() => { setOriginRm("815.2"); setDestRm("615.1"); }}>
                        L&D 2 → L&D 10
                      </Button>
                    </div>
                  )}
                </div>

                {tripPlan && (
                  <div className="mt-6 space-y-4" data-testid="planner-result">
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                      <Stat label="Total" value={fmtMinutes(tripPlan.total_minutes)} accent="text-cyan-300" />
                      <Stat label="Transit" value={fmtMinutes(tripPlan.total_transit_minutes)} />
                      <Stat label="Lock Wait" value={fmtMinutes(tripPlan.total_wait_minutes)} accent="text-amber-300" />
                      <Stat label="Locks" value={tripPlan.lock_count} />
                      <Stat label="Distance" value={`${tripPlan.total_distance_miles} mi`} />
                    </div>
                    <div className="text-xs text-slate-400 flex items-center gap-2 flex-wrap">
                      <Clock className="w-3 h-3" /> ETD {fmtTime(tripPlan.etd)} → ETA <span className="text-cyan-300 font-medium">{fmtTime(tripPlan.eta)}</span>
                      <span className="text-slate-600">•</span>
                      <span>{tripPlan.base_speed_knots} kn ({tripPlan.base_speed_mph} mph) {speedSourceLabel}</span>
                      <span className="text-slate-600">•</span>
                      <span className="uppercase tracking-wider">{tripPlan.direction}</span>
                    </div>

                    <div className="rounded-md border border-white/5 overflow-hidden">
                      <table className="w-full text-xs">
                        <thead className="bg-slate-900/80 text-slate-400 uppercase text-[10px] tracking-wider">
                          <tr>
                            <th className="text-left p-2.5">Stop</th>
                            <th className="text-right p-2.5">Distance</th>
                            <th className="text-right p-2.5">Transit</th>
                            <th className="text-right p-2.5">Wait</th>
                            <th className="text-right p-2.5">Lockage</th>
                            <th className="text-right p-2.5">Arrive</th>
                            <th className="text-right p-2.5">Depart</th>
                          </tr>
                        </thead>
                        <tbody>
                          {tripPlan.legs.map((leg, idx) => (
                            <tr key={idx} className="border-t border-white/5 hover:bg-slate-800/30" data-testid={`planner-leg-${idx}`}>
                              <td className="p-2.5">
                                {leg.type === "lock" ? (
                                  <div className="flex items-center gap-1.5">
                                    <LockIcon className="w-3 h-3 text-cyan-400" />
                                    <span>{leg.lock_name}</span>
                                    <span className="text-slate-500">RM {leg.lock_rm}</span>
                                  </div>
                                ) : (
                                  <div className="flex items-center gap-1.5">
                                    <Anchor className="w-3 h-3 text-emerald-400" />
                                    <span className="text-emerald-300 font-medium">Destination</span>
                                    <span className="text-slate-500">RM {leg.to_rm}</span>
                                  </div>
                                )}
                              </td>
                              <td className="text-right p-2.5 font-mono text-slate-300">{leg.distance_miles} mi</td>
                              <td className="text-right p-2.5 font-mono text-slate-300">{fmtMinutes(leg.transit_minutes)}</td>
                              <td className="text-right p-2.5 font-mono text-amber-300">{leg.wait_minutes != null ? fmtMinutes(leg.wait_minutes) : "—"}</td>
                              <td className="text-right p-2.5 font-mono text-slate-300">{leg.lockage_minutes != null ? fmtMinutes(leg.lockage_minutes) : "—"}</td>
                              <td className="text-right p-2.5 font-mono text-slate-400">{leg.arrive_at ? fmtTime(leg.arrive_at) : "—"}</td>
                              <td className="text-right p-2.5 font-mono text-cyan-300">{leg.depart_at ? fmtTime(leg.depart_at) : "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* LOCK QUEUE */}
          <TabsContent value="queue" className="mt-4">
            <Card className="bg-slate-900/50 border-white/5">
              <CardHeader>
                <CardTitle className="flex items-center justify-between text-sm uppercase tracking-wider text-slate-300">
                  <span className="flex items-center gap-2">
                    <LockIcon className="w-4 h-4 text-cyan-400" /> Lock Queue
                  </span>
                  <Button variant="ghost" size="sm" onClick={loadQueue} disabled={queueLoading} data-testid="queue-refresh-btn">
                    <RefreshCw className={`w-3 h-3 mr-1 ${queueLoading ? "animate-spin" : ""}`} /> Refresh
                  </Button>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-end gap-3 mb-4">
                  <div className="flex-1 space-y-1.5">
                    <Label className="text-xs text-slate-400">Lock</Label>
                    <Select value={queueLockId} onValueChange={setQueueLockId}>
                      <SelectTrigger data-testid="queue-lock-select" className="bg-slate-950/60 border-white/10">
                        <SelectValue placeholder="Choose lock" />
                      </SelectTrigger>
                      <SelectContent className="bg-slate-900 border-white/10">
                        {locks.map((l) => (
                          <SelectItem key={l.lock_id} value={l.lock_id}>
                            {l.name} (RM {l.river_mile})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="w-32 space-y-1.5">
                    <Label className="text-xs text-slate-400">Lookahead (h)</Label>
                    <Input
                      type="number"
                      min="0.5"
                      step="0.5"
                      max="24"
                      value={queueLookahead}
                      onChange={(e) => setQueueLookahead(parseFloat(e.target.value) || 6)}
                      data-testid="queue-lookahead"
                      className="bg-slate-950/60 border-white/10"
                    />
                  </div>
                  <Button onClick={loadQueue} disabled={queueLoading} className="bg-cyan-500 hover:bg-cyan-400 text-slate-950">
                    Load
                  </Button>
                </div>

                {queue && (
                  <div data-testid="queue-result">
                    <div className="mb-3 flex items-center gap-3 flex-wrap text-xs">
                      <span className="text-slate-400">
                        <span className="font-semibold text-cyan-300">{queue.queue_size}</span> approaching {queue.lock_name} (RM {queue.lock_rm})
                      </span>
                    </div>
                    {queue.queue?.length === 0 ? (
                      <div className="py-10 text-center text-slate-500 text-sm">No vessels approaching within {queue.lookahead_hours}h.</div>
                    ) : (
                      <div className="rounded-md border border-white/5 overflow-hidden">
                        <table className="w-full text-xs">
                          <thead className="bg-slate-900/80 text-slate-400 uppercase text-[10px] tracking-wider">
                            <tr>
                              <th className="text-left p-2.5">Slot</th>
                              <th className="text-left p-2.5">Vessel</th>
                              <th className="text-right p-2.5">RM</th>
                              <th className="text-right p-2.5">Distance</th>
                              <th className="text-right p-2.5">Speed</th>
                              <th className="text-right p-2.5">Direction</th>
                              <th className="text-right p-2.5">ETA</th>
                            </tr>
                          </thead>
                          <tbody>
                            {queue.queue.map((v) => (
                              <tr key={v.mmsi} className="border-t border-white/5 hover:bg-slate-800/30" data-testid={`queue-row-${v.mmsi}`}>
                                <td className="p-2.5">
                                  <Badge className="bg-cyan-500/15 text-cyan-300 border-cyan-500/30 font-mono">{v.slot}</Badge>
                                </td>
                                <td className="p-2.5">
                                  <div className="flex items-center gap-1.5">
                                    <Anchor className="w-3 h-3 text-slate-500" />
                                    <span className="text-slate-200">{v.name}</span>
                                    {v.is_tow && v.barge_count != null && (
                                      <Badge className="bg-amber-500/15 text-amber-300 border-amber-500/30 text-[10px] ml-1">
                                        {v.barge_count} barges
                                      </Badge>
                                    )}
                                  </div>
                                  <div className="text-[10px] text-slate-500 font-mono">{v.mmsi}</div>
                                </td>
                                <td className="text-right p-2.5 font-mono text-slate-300">{v.river_mile}</td>
                                <td className="text-right p-2.5 font-mono text-slate-300">{v.distance_miles} mi</td>
                                <td className="text-right p-2.5 font-mono text-slate-300">{v.speed_knots} kn</td>
                                <td className="text-right p-2.5">
                                  <span className={v.direction === "upstream" ? "text-emerald-400" : "text-red-400"}>
                                    {v.direction === "upstream" ? "↑ Up" : "↓ Down"}
                                  </span>
                                </td>
                                <td className="text-right p-2.5 font-mono text-amber-300">{fmtMinutes(v.eta_minutes)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* MEETINGS */}
          <TabsContent value="meetings" className="mt-4">
            <Card className="bg-slate-900/50 border-white/5">
              <CardHeader>
                <CardTitle className="flex items-center justify-between text-sm uppercase tracking-wider text-slate-300">
                  <span className="flex items-center gap-2">
                    <UsersIcon className="w-4 h-4 text-cyan-400" /> Predicted Encounters
                  </span>
                  <Button variant="ghost" size="sm" onClick={loadMeetings} disabled={meetingsLoading} data-testid="meetings-refresh-btn">
                    <RefreshCw className={`w-3 h-3 mr-1 ${meetingsLoading ? "animate-spin" : ""}`} /> Refresh
                  </Button>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-end gap-3 mb-4">
                  <div className="w-40 space-y-1.5">
                    <Label className="text-xs text-slate-400">Lookahead (h)</Label>
                    <Input
                      type="number"
                      min="0.5"
                      step="0.5"
                      max="12"
                      value={meetingsLookahead}
                      onChange={(e) => setMeetingsLookahead(parseFloat(e.target.value) || 4)}
                      data-testid="meetings-lookahead"
                      className="bg-slate-950/60 border-white/10"
                    />
                  </div>
                  <Button onClick={loadMeetings} disabled={meetingsLoading} className="bg-cyan-500 hover:bg-cyan-400 text-slate-950">
                    Load
                  </Button>
                </div>

                {meetings && (
                  <div data-testid="meetings-result">
                    <div className="mb-3 text-xs text-slate-400">
                      <span className="font-semibold text-cyan-300">{meetings.count}</span> predicted in next {meetings.lookahead_hours}h
                    </div>
                    {meetings.encounters?.length === 0 ? (
                      <div className="py-10 text-center text-slate-500 text-sm">No encounters predicted.</div>
                    ) : (
                      <div className="space-y-2">
                        {meetings.encounters.map((e, idx) => (
                          <div
                            key={idx}
                            className="p-3 rounded-md border border-white/5 bg-slate-950/40 flex items-start gap-3"
                            data-testid={`meeting-row-${idx}`}
                          >
                            <div className="flex-shrink-0 mt-0.5">
                              {e.type === "head_on" ? (
                                <NavIcon className="w-4 h-4 text-red-400" />
                              ) : (
                                <NavIcon className="w-4 h-4 text-amber-400" />
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap text-sm">
                                <span className="text-slate-200 font-medium">{e.vessel_a.name}</span>
                                <span className="text-slate-500">{e.type === "head_on" ? "head-on" : "overtake"}</span>
                                <span className="text-slate-200 font-medium">{e.vessel_b.name}</span>
                                <Badge className="bg-cyan-500/15 text-cyan-300 border-cyan-500/30 text-[10px] ml-auto">
                                  RM {e.meeting_rm}
                                </Badge>
                                <Badge className="bg-amber-500/15 text-amber-300 border-amber-500/30 text-[10px]">
                                  {fmtMinutes(e.time_minutes)}
                                </Badge>
                              </div>
                              <p className="mt-1 text-[11px] text-slate-400">{e.advice}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* BOTTLENECKS */}
          <TabsContent value="bottlenecks" className="mt-4">
            <Card className="bg-slate-900/50 border-white/5">
              <CardHeader>
                <CardTitle className="flex items-center justify-between text-sm uppercase tracking-wider text-slate-300">
                  <span className="flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-cyan-400" /> Bottleneck Forecast
                  </span>
                  <Button variant="ghost" size="sm" onClick={loadBottlenecks} disabled={bottleneckLoading} data-testid="bottlenecks-refresh-btn">
                    <RefreshCw className={`w-3 h-3 mr-1 ${bottleneckLoading ? "animate-spin" : ""}`} /> Refresh
                  </Button>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-end gap-3 mb-4">
                  <div className="w-40 space-y-1.5">
                    <Label className="text-xs text-slate-400">Window (h)</Label>
                    <Select value={String(bottleneckHours)} onValueChange={(v) => setBottleneckHours(parseFloat(v))}>
                      <SelectTrigger className="bg-slate-950/60 border-white/10" data-testid="bottlenecks-window">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-slate-900 border-white/10">
                        <SelectItem value="6">Next 6h</SelectItem>
                        <SelectItem value="12">Next 12h</SelectItem>
                        <SelectItem value="24">Next 24h</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <Button onClick={loadBottlenecks} disabled={bottleneckLoading} className="bg-cyan-500 hover:bg-cyan-400 text-slate-950">
                    Load
                  </Button>
                </div>

                {bottlenecks && (
                  <div data-testid="bottlenecks-result">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {bottlenecks.forecast.map((b) => (
                        <div
                          key={b.lock_id}
                          className="p-3 rounded-md border border-white/5 bg-slate-950/40 flex items-center gap-3"
                          data-testid={`bottleneck-${b.lock_id}`}
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <LockIcon className="w-3 h-3 text-slate-500" />
                              <span className="text-sm text-slate-200 truncate">{b.lock_name}</span>
                              <Badge className={`${severityBadge(b.severity)} text-[10px] uppercase`}>{b.severity}</Badge>
                            </div>
                            <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-2 flex-wrap">
                              <span>RM {b.lock_rm}</span>
                              <span className="text-slate-700">•</span>
                              <span>Queue: <span className="text-amber-300 font-mono">{b.current_queue}</span></span>
                              <span className="text-slate-700">•</span>
                              <span>Arrivals: <span className="text-cyan-300 font-mono">{b.arrivals_in_window}</span> (↑{b.arrivals_upstream} ↓{b.arrivals_downstream})</span>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="text-xs text-slate-500 uppercase">Demand</div>
                            <div className="font-mono text-cyan-300 text-sm">{fmtMinutes(b.cumulative_demand_minutes)}</div>
                            <div className="text-[10px] text-slate-500">{(b.utilization * 100).toFixed(0)}% util</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}

function Stat({ label, value, accent }) {
  return (
    <div className="p-3 rounded-md bg-slate-950/60 border border-white/5">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`text-lg font-semibold font-mono ${accent || "text-slate-200"}`}>{value}</div>
    </div>
  );
}
