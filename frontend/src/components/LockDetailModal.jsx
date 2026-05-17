import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Lock, Phone, Clock, AlertTriangle, CheckCircle2, XCircle,
  Users, ChevronUp, ChevronDown, Timer, Ship, Anchor,
  TrendingUp, Activity, RefreshCw, MapPin, Navigation
} from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL + '/api';

export default function LockDetailModal({ lockId, isOpen, onClose, onSelectOnMap }) {
  const [lockDetails, setLockDetails] = useState(null);
  const [waterConditions, setWaterConditions] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen && lockId) {
      fetchLockDetails();
      fetchWaterConditions();
    }
  }, [isOpen, lockId]);

  const fetchLockDetails = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API}/locks/${lockId}/details`);
      if (!response.ok) throw new Error('Failed to fetch lock details');
      const data = await response.json();
      setLockDetails(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchWaterConditions = async () => {
    try {
      const response = await fetch(`${API}/water-conditions/${lockId}`);
      if (response.ok) {
        const data = await response.json();
        setWaterConditions(data);
      }
    } catch (err) {
      console.error("Failed to fetch water conditions:", err);
    }
  };

  const getStatusColor = (status) => {
    switch (status?.toUpperCase()) {
      case 'OPEN': return 'bg-green-500/20 text-green-400 border-green-500/50';
      case 'CLOSED': return 'bg-red-500/20 text-red-400 border-red-500/50';
      case 'RESTRICTED': return 'bg-amber-500/20 text-amber-400 border-amber-500/50';
      default: return 'bg-slate-700 text-slate-300 border-slate-500/50';
    }
  };

  const getStatusIcon = (status) => {
    switch (status?.toUpperCase()) {
      case 'OPEN': return <CheckCircle2 className="w-4 h-4" />;
      case 'CLOSED': return <XCircle className="w-4 h-4" />;
      case 'RESTRICTED': return <AlertTriangle className="w-4 h-4" />;
      default: return <Lock className="w-4 h-4" />;
    }
  };

  const getConfidenceBadge = (confidence) => {
    switch (confidence) {
      case 'high': return <Badge className="bg-green-500/20 text-green-400 text-[10px]">High Confidence</Badge>;
      case 'medium': return <Badge className="bg-amber-500/20 text-amber-400 text-[10px]">Medium Confidence</Badge>;
      default: return <Badge className="bg-slate-500/20 text-slate-400 text-[10px]">Baseline Estimate</Badge>;
    }
  };

  const formatWaitTime = (minutes) => {
    if (!minutes || minutes === 0) return "No wait";
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  };

  const getFloodStageColor = (stage) => {
    switch (stage) {
      case 'major': return 'bg-purple-500/20 text-purple-400 border-purple-500/50';
      case 'moderate': return 'bg-red-500/20 text-red-400 border-red-500/50';
      case 'flood': return 'bg-orange-500/20 text-orange-400 border-orange-500/50';
      case 'action': return 'bg-amber-500/20 text-amber-400 border-amber-500/50';
      default: return 'bg-green-500/20 text-green-400 border-green-500/50';
    }
  };

  const getFloodStageLabel = (stage) => {
    switch (stage) {
      case 'major': return 'MAJOR FLOOD';
      case 'moderate': return 'MODERATE FLOOD';
      case 'flood': return 'FLOOD STAGE';
      case 'action': return 'ACTION STAGE';
      default: return 'NORMAL';
    }
  };

  const getDirectionLabel = (dir) => {
    if (dir === 'U') return { label: 'Upbound', icon: <ChevronUp className="w-3 h-3 text-green-400" /> };
    if (dir === 'D') return { label: 'Downbound', icon: <ChevronDown className="w-3 h-3 text-amber-400" /> };
    return { label: 'Unknown', icon: null };
  };

  if (!isOpen) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] bg-slate-900 border-slate-700 text-white p-0 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <RefreshCw className="w-8 h-8 animate-spin text-cyan-400" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-64 gap-4">
            <AlertTriangle className="w-12 h-12 text-red-400" />
            <p className="text-red-400">{error}</p>
            <Button onClick={fetchLockDetails} variant="outline">Retry</Button>
          </div>
        ) : lockDetails ? (
          <>
            {/* Header */}
            <DialogHeader className="p-4 pb-0">
              <div className="flex items-start justify-between">
                <div>
                  <DialogTitle className="text-xl font-bold text-white flex items-center gap-2">
                    <Lock className="w-5 h-5 text-cyan-400" />
                    Lock {lockDetails.lock_id.replace('lock_', '').toUpperCase()}
                  </DialogTitle>
                  <p className="text-sm text-slate-400 mt-1">{lockDetails.name}</p>
                  <p className="text-xs text-slate-500 font-mono">RM {lockDetails.river_mile}</p>
                </div>
                <Badge className={`${getStatusColor(lockDetails.status)} text-sm px-3 py-1`}>
                  {getStatusIcon(lockDetails.status)}
                  <span className="ml-1.5">{lockDetails.status || 'UNKNOWN'}</span>
                </Badge>
              </div>
            </DialogHeader>

            <ScrollArea className="flex-1 max-h-[calc(90vh-120px)]">
              <div className="p-4 space-y-4">
                {/* Closure Alert */}
                {lockDetails.closure_info && (
                  <Card className="bg-red-900/30 border-red-500/50">
                    <CardContent className="p-3 flex items-start gap-2">
                      <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="font-semibold text-red-400">Closure/Restriction Notice</p>
                        <p className="text-sm text-red-300 mt-1">{lockDetails.closure_info}</p>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Wait Time Prediction - Hero Section */}
                <Card className="bg-gradient-to-br from-cyan-900/30 to-slate-800/50 border-cyan-500/30">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-semibold text-white flex items-center gap-2">
                        <Timer className="w-4 h-4 text-cyan-400" />
                        Wait Time Prediction
                      </h3>
                      {getConfidenceBadge(lockDetails.prediction_confidence)}
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4">
                      <div className="text-center p-3 bg-slate-800/50 rounded-lg">
                        <p className="text-3xl font-bold text-cyan-400">
                          {formatWaitTime(lockDetails.estimated_wait_minutes)}
                        </p>
                        <p className="text-xs text-slate-400 mt-1">Estimated Wait</p>
                      </div>
                      <div className="text-center p-3 bg-slate-800/50 rounded-lg">
                        <p className="text-3xl font-bold text-white">
                          {lockDetails.total_queue || 0}
                        </p>
                        <p className="text-xs text-slate-400 mt-1">Vessels in Queue</p>
                      </div>
                    </div>

                    {/* Queue Breakdown */}
                    <div className="flex justify-center gap-6 mt-3 text-sm">
                      <span className="flex items-center gap-1 text-green-400">
                        <ChevronUp className="w-4 h-4" />
                        {lockDetails.upbound_queue || 0} upbound
                      </span>
                      <span className="flex items-center gap-1 text-amber-400">
                        <ChevronDown className="w-4 h-4" />
                        {lockDetails.downbound_queue || 0} downbound
                      </span>
                    </div>
                  </CardContent>
                </Card>

                {/* Water Conditions from USGS - always render so users see status if data is missing */}
                <Card data-testid="river-conditions-card" className="bg-gradient-to-br from-blue-900/30 to-slate-800/50 border-blue-500/30">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-semibold text-white flex items-center gap-2">
                        <Activity className="w-4 h-4 text-blue-400" />
                        River Conditions
                      </h3>
                      {waterConditions?.conditions ? (
                        <Badge className={getFloodStageColor(waterConditions.conditions.flood_stage)}>
                          {getFloodStageLabel(waterConditions.conditions.flood_stage)}
                        </Badge>
                      ) : (
                        <Badge className="bg-slate-700/50 text-slate-400 border-slate-500/40">
                          {waterConditions?.error ? "NO GAUGE" : "LOADING…"}
                        </Badge>
                      )}
                    </div>

                    {waterConditions?.conditions ? (
                      <>
                      
                      <div className="grid grid-cols-3 gap-3">
                        {/* Water Level */}
                        <div className="text-center p-2 bg-slate-800/50 rounded-lg">
                          <p className="text-2xl font-bold text-blue-400">
                            {waterConditions.conditions.gage_height_ft?.toFixed(1) || '--'}
                          </p>
                          <p className="text-[10px] text-slate-400">Water Level (ft)</p>
                        </div>
                        
                        {/* Water Temp */}
                        <div className="text-center p-2 bg-slate-800/50 rounded-lg">
                          <p className="text-2xl font-bold text-cyan-400">
                            {waterConditions.conditions.water_temp_f?.toFixed(0) || '--'}°
                          </p>
                          <p className="text-[10px] text-slate-400">Water Temp (°F)</p>
                        </div>
                        
                        {/* Current Speed */}
                        <div className="text-center p-2 bg-slate-800/50 rounded-lg">
                          <p className="text-2xl font-bold text-green-400">
                            {waterConditions.conditions.current_speed_mph?.toFixed(1) || '--'}
                          </p>
                          <p className="text-[10px] text-slate-400">Current (mph)</p>
                        </div>
                      </div>

                      {/* Gauge Info */}
                      <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                        <span>Gauge: {waterConditions.gauge?.name}</span>
                        <span>{waterConditions.gauge?.distance_from_lock?.toFixed(1)} mi from lock</span>
                      </div>

                      {/* Forecast if available */}
                      {waterConditions.forecast && waterConditions.forecast.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-slate-700">
                          <p className="text-xs text-slate-400 mb-2">48-Hour Forecast</p>
                          <div className="flex gap-2 overflow-x-auto pb-1">
                            {waterConditions.forecast.slice(0, 6).map((f, i) => (
                              <div key={i} className="flex-shrink-0 text-center p-1.5 bg-slate-800/30 rounded min-w-[60px]">
                                <p className="text-sm font-mono text-white">{f.stage_ft?.toFixed(1)} ft</p>
                                <p className="text-[9px] text-slate-500">{new Date(f.time).toLocaleDateString('en-US', { weekday: 'short' })}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Flood Stage Legend */}
                      {waterConditions.flood_stages && (
                        <div className="mt-3 pt-3 border-t border-slate-700">
                          <p className="text-xs text-slate-400 mb-2">Flood Stage Thresholds</p>
                          <div className="flex gap-2 text-[10px]">
                            <span className="text-amber-400">Action: {waterConditions.flood_stages.action} ft</span>
                            <span className="text-orange-400">Flood: {waterConditions.flood_stages.flood} ft</span>
                            <span className="text-red-400">Moderate: {waterConditions.flood_stages.moderate} ft</span>
                            <span className="text-purple-400">Major: {waterConditions.flood_stages.major} ft</span>
                          </div>
                        </div>
                      )}
                      </>
                    ) : (
                      <div data-testid="river-conditions-empty" className="py-4 text-center text-sm text-slate-400">
                        {waterConditions?.error
                          ? `Gauge data unavailable: ${waterConditions.error}`
                          : "Fetching latest gauge readings from USGS…"}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Currently Locking */}
                {lockDetails.vessels_locking?.length > 0 && (
                  <Card className="bg-amber-900/20 border-amber-500/30">
                    <CardContent className="p-3">
                      <h4 className="font-semibold text-amber-400 flex items-center gap-2 mb-2">
                        <Activity className="w-4 h-4" />
                        Currently Locking
                      </h4>
                      {lockDetails.vessels_locking.map((v, i) => (
                        <div key={i} className="flex items-center justify-between bg-slate-800/50 rounded p-2">
                          <div className="flex items-center gap-2">
                            <Ship className="w-4 h-4 text-amber-400" />
                            <span className="font-medium text-white">{v.name}</span>
                            {v.num_barges > 0 && (
                              <Badge variant="outline" className="text-[10px] border-amber-500/50 text-amber-400">
                                {v.num_barges} barges
                              </Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-1 text-xs text-slate-400">
                            {getDirectionLabel(v.direction).icon}
                            {getDirectionLabel(v.direction).label}
                          </div>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                {/* Waiting Queue */}
                {lockDetails.vessels_waiting?.length > 0 && (
                  <Card className="bg-slate-800/50 border-slate-600/30">
                    <CardContent className="p-3">
                      <h4 className="font-semibold text-white flex items-center gap-2 mb-2">
                        <Users className="w-4 h-4 text-cyan-400" />
                        Vessels Waiting ({lockDetails.vessels_waiting.length})
                      </h4>
                      <div className="space-y-1.5 max-h-40 overflow-y-auto">
                        {lockDetails.vessels_waiting.map((v, i) => (
                          <div key={i} className="flex items-center justify-between bg-slate-900/50 rounded p-2 text-sm">
                            <div className="flex items-center gap-2">
                              <span className="w-5 h-5 flex items-center justify-center bg-slate-700 rounded text-xs font-mono">
                                {v.position}
                              </span>
                              <span className="text-white">{v.name}</span>
                              {v.num_barges > 0 && (
                                <Badge variant="outline" className="text-[10px] border-slate-500/50">
                                  {v.num_barges} barges
                                </Badge>
                              )}
                            </div>
                            <div className="flex items-center gap-1 text-xs text-slate-400">
                              {getDirectionLabel(v.direction).icon}
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Average Lockage Times */}
                <Card className="bg-slate-800/50 border-slate-600/30">
                  <CardContent className="p-3">
                    <h4 className="font-semibold text-white flex items-center gap-2 mb-3">
                      <TrendingUp className="w-4 h-4 text-cyan-400" />
                      Average Lockage Times
                      {lockDetails.is_baseline_data && (
                        <span className="text-[10px] text-slate-500 font-normal">(baseline estimates)</span>
                      )}
                    </h4>
                    
                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-slate-900/50 rounded p-3">
                        <div className="flex items-center gap-2 mb-2">
                          <Ship className="w-4 h-4 text-amber-400" />
                          <span className="text-sm text-slate-300">Commercial Tows</span>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div>
                            <p className="text-slate-500">Lockage</p>
                            <p className="text-lg font-mono text-amber-400">
                              {lockDetails.avg_tow_lockage_minutes || '--'}m
                            </p>
                          </div>
                          <div>
                            <p className="text-slate-500">Wait</p>
                            <p className="text-lg font-mono text-amber-400">
                              {lockDetails.avg_tow_wait_minutes || '--'}m
                            </p>
                          </div>
                        </div>
                      </div>
                      
                      <div className="bg-slate-900/50 rounded p-3">
                        <div className="flex items-center gap-2 mb-2">
                          <Anchor className="w-4 h-4 text-cyan-400" />
                          <span className="text-sm text-slate-300">Recreational</span>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div>
                            <p className="text-slate-500">Lockage</p>
                            <p className="text-lg font-mono text-cyan-400">
                              {lockDetails.avg_recreational_lockage_minutes || '--'}m
                            </p>
                          </div>
                          <div>
                            <p className="text-slate-500">Wait</p>
                            <p className="text-lg font-mono text-cyan-400">
                              {lockDetails.avg_recreational_wait_minutes || '--'}m
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                    
                    {lockDetails.sample_count > 0 && !lockDetails.is_baseline_data && (
                      <p className="text-[10px] text-slate-500 mt-2 text-center">
                        Based on {lockDetails.sample_count} recorded lockages
                      </p>
                    )}
                  </CardContent>
                </Card>

                {/* Contact Info */}
                <div className="flex items-center justify-between p-3 bg-slate-800/30 rounded-lg">
                  <div className="flex items-center gap-2 text-sm text-slate-400">
                    <Phone className="w-4 h-4" />
                    <span>Lock Master: {lockDetails.phone || 'Not available'}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm text-slate-400">
                    <MapPin className="w-4 h-4" />
                    <span>{lockDetails.lat?.toFixed(4)}, {lockDetails.lon?.toFixed(4)}</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex gap-2 pt-2">
                  {lockDetails.phone && (
                    <Button 
                      variant="outline" 
                      className="flex-1 border-slate-600 hover:bg-slate-800"
                      onClick={() => window.open(`tel:${lockDetails.phone.replace(/[^0-9]/g, '')}`)}
                    >
                      <Phone className="w-4 h-4 mr-2" />
                      Call Lock
                    </Button>
                  )}
                  <Button 
                    variant="outline" 
                    className="flex-1 border-cyan-500/50 text-cyan-400 hover:bg-cyan-500/10"
                    onClick={() => {
                      onSelectOnMap?.(lockId);
                      onClose();
                    }}
                  >
                    <Navigation className="w-4 h-4 mr-2" />
                    View on Map
                  </Button>
                  <Button 
                    variant="ghost" 
                    size="icon"
                    onClick={fetchLockDetails}
                    className="text-slate-400 hover:text-white"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </ScrollArea>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
