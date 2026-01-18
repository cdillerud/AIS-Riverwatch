import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { 
  Target, AlertTriangle, Gauge, Clock, TrendingUp, 
  CheckCircle2, XCircle, Zap, Navigation 
} from "lucide-react";

export const RaceAnalysisPanel = ({ raceAnalysis, userVessel, isDangerous, compact = false }) => {
  const analysis = raceAnalysis?.analysis;
  const threat = analysis?.threatening_vessel;

  // Calculate speed gauge percentage (max 30 mph for display)
  const requiredSpeedPct = analysis?.required_speed_mph 
    ? Math.min((analysis.required_speed_mph / 30) * 100, 100) 
    : 0;

  const currentSpeedPct = analysis?.user_current_speed_mph
    ? Math.min((analysis.user_current_speed_mph / 30) * 100, 100)
    : 0;

  // Determine gauge color
  const getGaugeColor = (speed) => {
    if (!speed) return 'safe';
    if (speed > 25) return 'danger';
    if (speed > 20) return 'warning';
    return 'safe';
  };

  // Compact mobile version
  if (compact) {
    return (
      <Card 
        className={`glass-panel ${isDangerous ? 'border-2 border-red-500 alert-pulse' : 'hud-border'}`}
        data-testid="race-analysis-panel-mobile"
      >
        <CardContent className="p-3">
          {/* Header with status */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Target className="w-4 h-4 text-cyan-400" />
              <span className="font-semibold text-white text-sm">Race to Lock</span>
            </div>
            {isDangerous ? (
              <Badge className="bg-red-900/50 text-red-300 border border-red-500 text-xs">
                CAN'T BEAT
              </Badge>
            ) : analysis?.can_beat_at_25mph ? (
              <Badge className="bg-green-900/50 text-green-300 border border-green-500 text-xs">
                CAN BEAT
              </Badge>
            ) : (
              <Badge className="bg-slate-700 text-slate-300 text-xs">
                NO THREAT
              </Badge>
            )}
          </div>

          {/* Target Lock */}
          <div className="text-xs text-slate-400 mb-2">
            Target: <span className="text-white font-mono">{raceAnalysis?.target_lock_name}</span>
          </div>

          {/* Speed Required - Big Display */}
          {analysis?.required_speed_mph && (
            <div className={`text-center py-3 rounded-lg mb-3 ${isDangerous ? 'bg-red-900/20' : 'bg-cyan-900/20'}`}>
              <div className="text-xs text-slate-400 uppercase mb-1">Speed Needed</div>
              <div className={`text-4xl font-mono font-bold ${isDangerous ? 'text-red-400' : 'text-green-400'}`}>
                {analysis.required_speed_mph?.toFixed(1)}
                <span className="text-lg ml-1">MPH</span>
              </div>
              <div className="mt-2 speed-gauge mx-4">
                <div 
                  className={`speed-gauge-fill ${getGaugeColor(analysis.required_speed_mph)}`}
                  style={{ width: `${requiredSpeedPct}%` }}
                />
              </div>
              <div className="text-xs text-slate-500 mt-1">Max: 25 mph</div>
            </div>
          )}

          {/* Threat Info */}
          {threat && (
            <div className="p-2 rounded bg-amber-900/20 border border-amber-500/30">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1 text-amber-400 text-xs">
                  <AlertTriangle className="w-3 h-3" />
                  <span className="font-semibold">{threat.name || threat.mmsi}</span>
                </div>
                <span className="text-amber-400 text-xs font-mono">
                  ETA: {threat.eta_minutes?.toFixed(0)}min
                </span>
              </div>
            </div>
          )}

          {/* No threat state */}
          {!threat && (
            <div className="p-3 rounded-lg bg-green-900/20 border border-green-500/30 text-center">
              <CheckCircle2 className="w-6 h-6 text-green-400 mx-auto mb-1" />
              <div className="text-green-400 text-sm font-semibold">Clear Path</div>
            </div>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card 
      className={`glass-panel ${isDangerous ? 'border-2 border-red-500 alert-pulse' : 'hud-border'}`}
      data-testid="race-analysis-panel"
    >
      <CardHeader className="border-b border-white/10 pb-3">
        <CardTitle className="text-lg text-white flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Target className="w-5 h-5 text-cyan-400" />
            Race to Lock
          </span>
          {isDangerous ? (
            <Badge className="bg-red-900/50 text-red-300 border border-red-500">
              <AlertTriangle className="w-3 h-3 mr-1" />
              Cannot Beat
            </Badge>
          ) : analysis?.can_beat_at_25mph ? (
            <Badge className="bg-green-900/50 text-green-300 border border-green-500">
              <CheckCircle2 className="w-3 h-3 mr-1" />
              Can Beat
            </Badge>
          ) : (
            <Badge className="bg-slate-700 text-slate-300">
              No Threat
            </Badge>
          )}
        </CardTitle>
      </CardHeader>

      <CardContent className="p-4 space-y-4">
        {/* Target Lock Info */}
        <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-700">
          <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Target</div>
          <div className="text-white font-semibold">{raceAnalysis?.target_lock_name}</div>
          <div className="text-slate-400 font-mono text-sm">River Mile {raceAnalysis?.target_lock_rm}</div>
        </div>

        {/* User Stats */}
        {analysis && (
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-700">
              <div className="text-xs text-slate-500 uppercase mb-1">Your Distance</div>
              <div className="text-2xl font-mono text-white">
                {analysis.user_distance_to_lock?.toFixed(1)}
                <span className="text-sm text-slate-400 ml-1">mi</span>
              </div>
            </div>
            <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-700">
              <div className="text-xs text-slate-500 uppercase mb-1">Your ETA</div>
              <div className="text-2xl font-mono text-white">
                {analysis.user_eta_minutes?.toFixed(0) || '--'}
                <span className="text-sm text-slate-400 ml-1">min</span>
              </div>
            </div>
          </div>
        )}

        {/* Threatening Vessel */}
        {threat && (
          <div className="p-3 rounded-lg bg-amber-900/20 border border-amber-500/30">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              <span className="text-xs text-amber-400 uppercase tracking-wider">Threatening Vessel</span>
            </div>
            <div className="text-white font-semibold">{threat.name || threat.mmsi}</div>
            <div className="flex items-center gap-4 mt-2 text-sm">
              <span className="text-slate-400">
                <Navigation className="w-3 h-3 inline mr-1" />
                RM {threat.river_mile?.toFixed(1)}
              </span>
              <span className="text-slate-400">
                <Gauge className="w-3 h-3 inline mr-1" />
                {(threat.speed * 1.15078).toFixed(1)} mph
              </span>
              <span className="text-amber-400 font-mono">
                <Clock className="w-3 h-3 inline mr-1" />
                ETA: {threat.eta_minutes?.toFixed(0)} min
              </span>
            </div>
          </div>
        )}

        {/* Required Speed */}
        {analysis?.required_speed_mph && (
          <div className={`p-4 rounded-lg ${isDangerous ? 'bg-red-900/20 border border-red-500/30' : 'bg-cyan-900/20 border border-cyan-500/30'}`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs uppercase tracking-wider text-slate-400">
                Speed Needed to Beat
              </span>
              <span className={`text-xs font-mono ${isDangerous ? 'text-red-400' : 'text-cyan-400'}`}>
                Max: 25 mph
              </span>
            </div>
            
            <div className={`text-4xl font-mono font-bold ${isDangerous ? 'speed-danger' : 'speed-ok'}`}>
              {analysis.required_speed_mph?.toFixed(1)}
              <span className="text-lg text-slate-400 ml-2">MPH</span>
            </div>

            {/* Speed gauge */}
            <div className="mt-3 speed-gauge">
              <div 
                className={`speed-gauge-fill ${getGaugeColor(analysis.required_speed_mph)}`}
                style={{ width: `${requiredSpeedPct}%` }}
              />
            </div>
            
            {/* Current vs Required comparison */}
            <div className="mt-3 flex items-center justify-between text-sm">
              <div className="text-slate-400">
                <span className="text-slate-500">Current:</span>{' '}
                <span className="font-mono text-white">{analysis.user_current_speed_mph?.toFixed(1)} mph</span>
              </div>
              <div className={isDangerous ? 'text-red-400' : 'text-green-400'}>
                {isDangerous ? (
                  <span className="flex items-center gap-1">
                    <XCircle className="w-4 h-4" />
                    Too slow!
                  </span>
                ) : analysis.required_speed_mph > analysis.user_current_speed_mph ? (
                  <span className="flex items-center gap-1">
                    <TrendingUp className="w-4 h-4" />
                    Speed up!
                  </span>
                ) : (
                  <span className="flex items-center gap-1">
                    <CheckCircle2 className="w-4 h-4" />
                    On pace!
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* No threat state */}
        {!threat && (
          <div className="p-4 rounded-lg bg-green-900/20 border border-green-500/30 text-center">
            <CheckCircle2 className="w-8 h-8 text-green-400 mx-auto mb-2" />
            <div className="text-green-400 font-semibold">Clear Path to Lock</div>
            <div className="text-sm text-slate-400 mt-1">
              No commercial vessels threatening your approach
            </div>
          </div>
        )}

        {/* Competitors count */}
        {raceAnalysis?.competitors?.length > 0 && (
          <div className="text-xs text-slate-500 text-center">
            {raceAnalysis.competitors.length} vessel(s) heading to this lock
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default RaceAnalysisPanel;
