import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Route,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Zap,
  XCircle,
  Navigation,
  RefreshCw,
  Anchor,
} from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const STATUS_META = {
  clear: {
    label: "CLEAR",
    badge: "bg-green-900/40 text-green-300 border-green-500",
    icon: CheckCircle2,
    iconColor: "text-green-400",
    rowBorder: "border-green-500/30",
  },
  on_pace: {
    label: "ON PACE",
    badge: "bg-green-900/40 text-green-300 border-green-500",
    icon: CheckCircle2,
    iconColor: "text-green-400",
    rowBorder: "border-green-500/30",
  },
  speed_up: {
    label: "SPEED UP",
    badge: "bg-amber-900/40 text-amber-300 border-amber-500",
    icon: Zap,
    iconColor: "text-amber-400",
    rowBorder: "border-amber-500/40",
  },
  cant_beat: {
    label: "CAN'T BEAT",
    badge: "bg-red-900/40 text-red-300 border-red-500",
    icon: XCircle,
    iconColor: "text-red-400",
    rowBorder: "border-red-500/50",
  },
  no_data: {
    label: "NO DATA",
    badge: "bg-slate-700 text-slate-300 border-slate-600",
    icon: AlertTriangle,
    iconColor: "text-slate-400",
    rowBorder: "border-slate-700",
  },
};

const OVERALL_META = {
  clear: { text: "All Clear", color: "text-green-400", badge: "bg-green-900/50 text-green-300 border-green-500" },
  speed_up: { text: "Adjust Speed", color: "text-amber-400", badge: "bg-amber-900/50 text-amber-300 border-amber-500" },
  cant_beat: { text: "Traffic Conflict", color: "text-red-400", badge: "bg-red-900/50 text-red-300 border-red-500" },
  no_data: { text: "Awaiting Data", color: "text-slate-400", badge: "bg-slate-700 text-slate-300" },
  no_user: { text: "No User Vessel", color: "text-slate-400", badge: "bg-slate-700 text-slate-300" },
};

const fmtMinutes = (m) => {
  if (m === null || m === undefined) return "--";
  if (m < 60) return `${Math.round(m)}m`;
  const h = Math.floor(m / 60);
  const min = Math.round(m % 60);
  return `${h}h ${min}m`;
};

export default function TripPlanPanel({ userMmsi, maxLocks = 5, bufferMinutes = 20, compact = false }) {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchPlan = useCallback(async () => {
    if (!userMmsi) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API}/session/${userMmsi}/trip-plan?max_locks=${maxLocks}&buffer_minutes=${bufferMinutes}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setPlan(data);
    } catch (e) {
      setError(e.message || "Failed to fetch trip plan");
    } finally {
      setLoading(false);
    }
  }, [userMmsi, maxLocks, bufferMinutes]);

  useEffect(() => {
    fetchPlan();
    const id = setInterval(fetchPlan, 30000);
    return () => clearInterval(id);
  }, [fetchPlan]);

  const summary = plan?.summary;
  const legs = plan?.legs || [];
  const overall = OVERALL_META[summary?.overall_status] || OVERALL_META.no_data;

  return (
    <Card className="glass-panel hud-border" data-testid="trip-plan-panel">
      <CardHeader className="border-b border-white/10 pb-3">
        <CardTitle className="text-lg text-white flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Route className="w-5 h-5 text-cyan-400" />
            Trip Plan
          </span>
          <div className="flex items-center gap-2">
            <Badge className={overall.badge} data-testid="trip-plan-overall-status">
              {overall.text}
            </Badge>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-slate-400 hover:text-white"
              onClick={fetchPlan}
              disabled={loading}
              data-testid="trip-plan-refresh-btn"
              title="Refresh"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </CardTitle>
      </CardHeader>

      <CardContent className="p-4 space-y-3">
        {!userMmsi && (
          <div className="text-center py-6 text-sm text-slate-400" data-testid="trip-plan-no-user">
            <Anchor className="w-6 h-6 mx-auto mb-2 text-slate-500" />
            Set your vessel MMSI in Settings to see your trip plan.
          </div>
        )}

        {userMmsi && error && (
          <div className="text-center py-4 text-sm text-red-400" data-testid="trip-plan-error">
            {error}
          </div>
        )}

        {userMmsi && !error && plan && summary?.overall_status === "no_user" && (
          <div className="text-center py-6 text-sm text-slate-400" data-testid="trip-plan-no-vessel">
            <Navigation className="w-6 h-6 mx-auto mb-2 text-slate-500" />
            Waiting for live position data for your vessel ({userMmsi}).
          </div>
        )}

        {userMmsi && legs.length > 0 && (
          <>
            {/* Summary header */}
            <div className="grid grid-cols-3 gap-2 text-center" data-testid="trip-plan-summary">
              <div className="p-2 rounded bg-slate-900/50 border border-slate-700">
                <div className="text-[10px] text-slate-500 uppercase">Locks Ahead</div>
                <div className="text-lg font-mono text-white">{summary.legs_count}</div>
              </div>
              <div className="p-2 rounded bg-slate-900/50 border border-slate-700">
                <div className="text-[10px] text-slate-500 uppercase">Total Dist.</div>
                <div className="text-lg font-mono text-white">
                  {summary.total_distance_mi?.toFixed?.(1) ?? summary.total_distance_mi} <span className="text-xs text-slate-400">mi</span>
                </div>
              </div>
              <div className="p-2 rounded bg-slate-900/50 border border-slate-700">
                <div className="text-[10px] text-slate-500 uppercase">Final ETA</div>
                <div className="text-lg font-mono text-white">{fmtMinutes(summary.cumulative_eta_minutes)}</div>
              </div>
            </div>

            <div className="flex items-center justify-between text-xs text-slate-400 px-1">
              <span>
                Heading:{" "}
                <span className={`font-mono ${plan.heading === "northbound" ? "text-blue-400" : "text-orange-400"}`}>
                  {plan.heading === "northbound" ? "↑ NB" : plan.heading === "southbound" ? "↓ SB" : plan.heading || "--"}
                </span>
              </span>
              <span>
                Current:{" "}
                <span className="font-mono text-white">{plan.user_speed_mph?.toFixed?.(1) ?? "--"} mph</span>
              </span>
            </div>

            {/* Leg list */}
            <ScrollArea className={compact ? "max-h-[280px]" : "max-h-[420px]"}>
              <div className="space-y-2 pr-2" data-testid="trip-plan-legs">
                {legs.map((leg, idx) => {
                  const meta = STATUS_META[leg.status] || STATUS_META.no_data;
                  const StatusIcon = meta.icon;
                  return (
                    <div
                      key={leg.lock_id}
                      className={`p-3 rounded-lg bg-slate-900/40 border ${meta.rowBorder}`}
                      data-testid={`trip-plan-leg-${leg.lock_id}`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-2 min-w-0">
                          <StatusIcon className={`w-4 h-4 flex-shrink-0 ${meta.iconColor}`} />
                          <span className="text-sm font-semibold text-white truncate">
                            {idx + 1}. {leg.lock_name}
                          </span>
                        </div>
                        <Badge className={`text-[10px] ${meta.badge}`}>{meta.label}</Badge>
                      </div>

                      <div className="grid grid-cols-3 gap-2 text-xs">
                        <div>
                          <div className="text-slate-500">RM</div>
                          <div className="text-white font-mono">{leg.lock_rm}</div>
                        </div>
                        <div>
                          <div className="text-slate-500">Your ETA</div>
                          <div className="text-white font-mono flex items-center gap-1">
                            <Clock className="w-3 h-3 text-cyan-400" />
                            {fmtMinutes(leg.user_eta_minutes)}
                          </div>
                        </div>
                        <div>
                          <div className="text-slate-500">Need</div>
                          <div
                            className={`font-mono ${
                              leg.status === "cant_beat"
                                ? "text-red-400"
                                : leg.status === "speed_up"
                                ? "text-amber-400"
                                : "text-slate-300"
                            }`}
                          >
                            {leg.required_speed_mph ? `${leg.required_speed_mph.toFixed(1)} mph` : "--"}
                          </div>
                        </div>
                      </div>

                      {leg.threatening_vessel && (
                        <div className="mt-2 pt-2 border-t border-slate-700/50 text-xs flex items-center justify-between flex-wrap gap-1">
                          <span className="text-amber-400 flex items-center gap-1 min-w-0">
                            <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                            <span className="truncate">
                              Threat: {leg.threatening_vessel.name || leg.threatening_vessel.mmsi}
                            </span>
                          </span>
                          <span className="text-slate-400 font-mono">
                            ETA {fmtMinutes(leg.threatening_vessel.eta_minutes)}
                            {leg.threatening_vessel.distance_to_lock != null && (
                              <> · {leg.threatening_vessel.distance_to_lock} mi</>
                            )}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </ScrollArea>
          </>
        )}

        {userMmsi && plan && legs.length === 0 && summary?.overall_status !== "no_user" && (
          <div className="text-center py-6 text-sm text-slate-400" data-testid="trip-plan-no-legs">
            No locks ahead in your direction of travel.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
