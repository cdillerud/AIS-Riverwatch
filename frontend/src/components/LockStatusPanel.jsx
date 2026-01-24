import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { 
  Lock, Phone, Clock, AlertTriangle, CheckCircle2, 
  XCircle, Users, ChevronUp, ChevronDown, Timer, Info, ExternalLink
} from "lucide-react";
import { memo } from "react";

const LockStatusPanelComponent = ({ locks, lockStatus, lockageTimes = {}, selectedLock, onSelectLock, onLockDetails, compact = false }) => {
  
  const getStatusColor = (status) => {
    switch (status?.toUpperCase()) {
      case 'OPEN': return 'bg-green-900/50 text-green-400 border-green-500/50';
      case 'CLOSED': return 'bg-red-900/50 text-red-400 border-red-500/50';
      case 'RESTRICTED': return 'bg-amber-900/50 text-amber-400 border-amber-500/50';
      default: return 'bg-slate-700 text-slate-300 border-slate-500/50';
    }
  };

  const getStatusIcon = (status) => {
    switch (status?.toUpperCase()) {
      case 'OPEN': return <CheckCircle2 className="w-3 h-3" />;
      case 'CLOSED': return <XCircle className="w-3 h-3" />;
      case 'RESTRICTED': return <AlertTriangle className="w-3 h-3" />;
      default: return null;
    }
  };

  // Get the currently selected lock's data
  const currentLock = locks.find(l => l.id === selectedLock);
  const currentStatus = lockStatus[selectedLock] || {};
  const currentLockageTimes = lockageTimes[selectedLock];
  const totalQueue = (currentStatus.upbound_queue || 0) + (currentStatus.downbound_queue || 0);

  // Format lock label for dropdown
  const getLockLabel = (lock) => {
    const status = lockStatus[lock.id];
    const lockNum = lock.id.replace('lock_', '').toUpperCase();
    const location = lock.name?.split('(')[1]?.replace(')', '') || '';
    return `L${lockNum} - ${location}`;
  };

  // Compact mobile version
  if (compact) {
    return (
      <Card className="glass-panel hud-border" data-testid="lock-status-panel-mobile">
        <CardHeader className="border-b border-white/10 pb-2 px-3 pt-3">
          <CardTitle className="text-base text-white flex items-center gap-2">
            <Lock className="w-4 h-4 text-cyan-400" />
            Lock Status
          </CardTitle>
        </CardHeader>
        <CardContent className="p-3 space-y-3">
          {/* Lock Selector Dropdown */}
          <Select value={selectedLock} onValueChange={onSelectLock}>
            <SelectTrigger className="w-full bg-slate-800/50 border-slate-600 text-white">
              <SelectValue placeholder="Select a lock" />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-600 max-h-[300px]">
              {locks.map(lock => {
                const status = lockStatus[lock.id];
                return (
                  <SelectItem 
                    key={lock.id} 
                    value={lock.id}
                    className="text-white hover:bg-slate-700 focus:bg-slate-700"
                  >
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${
                        status?.status?.toUpperCase() === 'OPEN' ? 'bg-green-400' :
                        status?.status?.toUpperCase() === 'CLOSED' ? 'bg-red-400' :
                        status?.status?.toUpperCase() === 'RESTRICTED' ? 'bg-amber-400' :
                        'bg-slate-400'
                      }`} />
                      <span>{getLockLabel(lock)}</span>
                      <span className="text-slate-500 text-xs ml-auto">RM {lock.river_mile}</span>
                    </div>
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>

          {/* Selected Lock Details */}
          {currentLock && (
            <div className="space-y-3">
              {/* Status Badge */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Status</span>
                <Badge className={`${getStatusColor(currentStatus.status)}`}>
                  {getStatusIcon(currentStatus.status)}
                  <span className="ml-1">{currentStatus.status || 'UNKNOWN'}</span>
                </Badge>
              </div>

              {/* Queue Info */}
              {totalQueue > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Queue</span>
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1 text-green-400">
                      <ChevronUp className="w-3 h-3" />
                      {currentStatus.upbound_queue || 0}
                    </span>
                    <span className="flex items-center gap-1 text-amber-400">
                      <ChevronDown className="w-3 h-3" />
                      {currentStatus.downbound_queue || 0}
                    </span>
                  </div>
                </div>
              )}

              {/* Wait Time */}
              {currentStatus.avg_wait_minutes > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Avg Wait</span>
                  <span className="text-amber-400 font-mono">{currentStatus.avg_wait_minutes} min</span>
                </div>
              )}

              {/* Closure Info */}
              {currentStatus.closure_info && (
                <div className="p-2 rounded bg-red-900/20 border border-red-500/30 text-xs text-red-300">
                  <AlertTriangle className="w-3 h-3 inline mr-1" />
                  {currentStatus.closure_info}
                </div>
              )}

              {/* View Details Button */}
              {onLockDetails && (
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full border-cyan-500/50 text-cyan-400 hover:bg-cyan-500/10"
                  onClick={() => onLockDetails(selectedLock)}
                >
                  <Info className="w-3 h-3 mr-2" />
                  Full Details & Wait Prediction
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    );
  }

  // Desktop version
  return (
    <Card className="glass-panel hud-border" data-testid="lock-status-panel">
      <CardHeader className="border-b border-white/10 pb-3">
        <CardTitle className="text-lg text-white flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Lock className="w-5 h-5 text-cyan-400" />
            Lock Status
          </span>
          <Badge variant="outline" className="border-cyan-500/50 text-cyan-400 text-xs">
            USACE Live
          </Badge>
        </CardTitle>
      </CardHeader>
      
      <CardContent className="p-4 space-y-4">
        {/* Lock Selector Dropdown */}
        <Select value={selectedLock} onValueChange={onSelectLock}>
          <SelectTrigger className="w-full bg-slate-800/50 border-slate-600 text-white h-10">
            <SelectValue placeholder="Select a lock" />
          </SelectTrigger>
          <SelectContent className="bg-slate-800 border-slate-600 max-h-[400px]">
            {locks.map(lock => {
              const status = lockStatus[lock.id];
              const queue = (status?.upbound_queue || 0) + (status?.downbound_queue || 0);
              return (
                <SelectItem 
                  key={lock.id} 
                  value={lock.id}
                  className="text-white hover:bg-slate-700 focus:bg-slate-700 py-2"
                >
                  <div className="flex items-center gap-2 w-full">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                      status?.status?.toUpperCase() === 'OPEN' ? 'bg-green-400' :
                      status?.status?.toUpperCase() === 'CLOSED' ? 'bg-red-400' :
                      status?.status?.toUpperCase() === 'RESTRICTED' ? 'bg-amber-400' :
                      'bg-slate-400'
                    }`} />
                    <span className="flex-1">{getLockLabel(lock)}</span>
                    {queue > 0 && (
                      <span className="text-amber-400 text-xs flex items-center gap-0.5">
                        <Users className="w-3 h-3" />
                        {queue}
                      </span>
                    )}
                  </div>
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>

        {/* Selected Lock Details */}
        {currentLock && (
          <div className="space-y-4">
            {/* Lock Name & Status */}
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-white">
                  Lock {currentLock.id.replace('lock_', '').toUpperCase()}
                </h3>
                <p className="text-sm text-slate-400">
                  {currentLock.name?.split('(')[1]?.replace(')', '') || currentLock.name}
                </p>
                <p className="text-xs text-slate-500 font-mono">RM {currentLock.river_mile}</p>
              </div>
              <Badge className={`${getStatusColor(currentStatus.status)} text-sm`}>
                {getStatusIcon(currentStatus.status)}
                <span className="ml-1">{currentStatus.status || 'UNKNOWN'}</span>
              </Badge>
            </div>

            {/* Closure Alert */}
            {currentStatus.closure_info && (
              <div className="p-3 rounded bg-red-900/20 border border-red-500/30 text-sm text-red-300">
                <AlertTriangle className="w-4 h-4 inline mr-2" />
                {currentStatus.closure_info}
              </div>
            )}

            {/* Queue & Wait Info */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-slate-800/50 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-white">{totalQueue}</div>
                <div className="text-xs text-slate-400">In Queue</div>
                {totalQueue > 0 && (
                  <div className="flex justify-center gap-2 mt-1 text-xs">
                    <span className="text-green-400">{currentStatus.upbound_queue || 0}↑</span>
                    <span className="text-amber-400">{currentStatus.downbound_queue || 0}↓</span>
                  </div>
                )}
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3 text-center">
                <div className={`text-2xl font-bold ${currentStatus.avg_wait_minutes > 30 ? 'text-amber-400' : 'text-white'}`}>
                  {currentStatus.avg_wait_minutes || 0}
                </div>
                <div className="text-xs text-slate-400">Min Wait</div>
              </div>
            </div>

            {/* Avg Lockage Times */}
            {currentLockageTimes && (
              <div className="bg-slate-800/30 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Timer className="w-4 h-4 text-cyan-400" />
                  <span className="text-sm text-slate-300">Average Times</span>
                  {currentLockageTimes.is_baseline && (
                    <span className="text-[10px] text-slate-500">(baseline)</span>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <div className="text-xs text-slate-500 mb-1">Commercial Tows</div>
                    <div className="flex gap-3">
                      <span className="text-amber-400 font-mono">
                        {currentLockageTimes.avg_tow_lockage_minutes}m lock
                      </span>
                      <span className="text-slate-400 font-mono">
                        {currentLockageTimes.avg_tow_wait_minutes}m wait
                      </span>
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500 mb-1">Recreational</div>
                    <div className="flex gap-3">
                      <span className="text-cyan-400 font-mono">
                        {currentLockageTimes.avg_recreational_lockage_minutes}m lock
                      </span>
                      <span className="text-slate-400 font-mono">
                        {currentLockageTimes.avg_recreational_wait_minutes}m wait
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Phone */}
            {currentLock.phone && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-400 flex items-center gap-2">
                  <Phone className="w-4 h-4" />
                  Lock Master
                </span>
                <a 
                  href={`tel:${currentLock.phone.replace(/[^0-9]/g, '')}`}
                  className="text-cyan-400 hover:text-cyan-300"
                >
                  {currentLock.phone}
                </a>
              </div>
            )}

            {/* View Full Details Button */}
            {onLockDetails && (
              <Button
                variant="outline"
                className="w-full border-cyan-500/50 text-cyan-400 hover:bg-cyan-500/10"
                onClick={() => onLockDetails(selectedLock)}
              >
                <ExternalLink className="w-4 h-4 mr-2" />
                Full Details & Wait Prediction
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// Memoize to prevent unnecessary re-renders
export const LockStatusPanel = memo(LockStatusPanelComponent);

export default LockStatusPanel;
