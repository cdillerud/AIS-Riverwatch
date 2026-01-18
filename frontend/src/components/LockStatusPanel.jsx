import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  Lock, Phone, Clock, AlertTriangle, CheckCircle2, 
  XCircle, Users, ChevronUp, ChevronDown 
} from "lucide-react";

export const LockStatusPanel = ({ locks, lockStatus, selectedLock, onSelectLock, compact = false }) => {
  
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

  if (compact) {
    return (
      <Card className="glass-panel hud-border" data-testid="lock-status-panel-mobile">
        <CardHeader className="border-b border-white/10 pb-2 px-3 pt-3">
          <CardTitle className="text-base text-white flex items-center gap-2">
            <Lock className="w-4 h-4 text-cyan-400" />
            Lock Status (USACE)
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-[300px]">
            <div className="divide-y divide-white/5">
              {locks.map(lock => {
                const status = lockStatus[lock.id] || {};
                const isSelected = lock.id === selectedLock;
                
                return (
                  <button
                    key={lock.id}
                    onClick={() => onSelectLock(lock.id)}
                    className={`w-full p-3 text-left transition-colors ${
                      isSelected ? 'bg-cyan-500/10 border-l-2 border-l-cyan-500' : 'hover:bg-slate-800/50'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-white text-sm">
                        Lock {lock.id.replace('lock_', '').toUpperCase()}
                      </span>
                      <Badge className={`text-[10px] ${getStatusColor(status.status)}`}>
                        {getStatusIcon(status.status)}
                        <span className="ml-1">{status.status || 'UNKNOWN'}</span>
                      </Badge>
                    </div>
                    <div className="text-xs text-slate-500">RM {lock.river_mile}</div>
                    {status.avg_wait_minutes > 0 && (
                      <div className="text-xs text-amber-400 mt-1 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        ~{status.avg_wait_minutes} min wait
                      </div>
                    )}
                    {status.closure_info && (
                      <div className="text-xs text-red-400 mt-1">{status.closure_info}</div>
                    )}
                  </button>
                );
              })}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    );
  }

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
      
      <CardContent className="p-0">
        <ScrollArea className="h-[400px]">
          <div className="divide-y divide-white/5">
            {locks.map(lock => {
              const status = lockStatus[lock.id] || {};
              const isSelected = lock.id === selectedLock;
              const totalQueue = (status.upbound_queue || 0) + (status.downbound_queue || 0);
              
              return (
                <button
                  key={lock.id}
                  onClick={() => onSelectLock(lock.id)}
                  className={`w-full p-4 text-left transition-colors ${
                    isSelected ? 'bg-cyan-500/10 border-l-2 border-l-cyan-500' : 'hover:bg-slate-800/50'
                  }`}
                  data-testid={`lock-status-${lock.id}`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold text-white">
                          Lock {lock.id.replace('lock_', '').toUpperCase()}
                        </span>
                        <Badge className={`text-xs ${getStatusColor(status.status)}`}>
                          {getStatusIcon(status.status)}
                          <span className="ml-1">{status.status || 'UNKNOWN'}</span>
                        </Badge>
                      </div>
                      <div className="text-sm text-slate-400">{lock.name?.split('(')[1]?.replace(')', '') || ''}</div>
                      <div className="text-xs text-slate-500 font-mono">RM {lock.river_mile}</div>
                    </div>
                    
                    <div className="text-right">
                      {status.avg_wait_minutes !== undefined && status.avg_wait_minutes !== null && (
                        <div className={`text-lg font-mono ${status.avg_wait_minutes > 30 ? 'text-amber-400' : 'text-white'}`}>
                          {status.avg_wait_minutes}<span className="text-xs text-slate-500 ml-1">min</span>
                        </div>
                      )}
                      {totalQueue > 0 && (
                        <div className="text-xs text-slate-400 flex items-center gap-1 justify-end">
                          <Users className="w-3 h-3" />
                          {totalQueue} in queue
                        </div>
                      )}
                    </div>
                  </div>
                  
                  {/* Queue breakdown */}
                  {(status.upbound_queue > 0 || status.downbound_queue > 0) && (
                    <div className="flex gap-4 mt-2 text-xs">
                      <span className="flex items-center gap-1 text-slate-400">
                        <ChevronUp className="w-3 h-3 text-green-400" />
                        {status.upbound_queue || 0} up
                      </span>
                      <span className="flex items-center gap-1 text-slate-400">
                        <ChevronDown className="w-3 h-3 text-amber-400" />
                        {status.downbound_queue || 0} down
                      </span>
                    </div>
                  )}
                  
                  {/* Closure info */}
                  {status.closure_info && (
                    <div className="mt-2 p-2 rounded bg-red-900/20 border border-red-500/30 text-xs text-red-300">
                      {status.closure_info}
                    </div>
                  )}
                  
                  {/* Phone */}
                  {status.phone && (
                    <div className="mt-2 text-xs text-slate-500 flex items-center gap-1">
                      <Phone className="w-3 h-3" />
                      {status.phone}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
};

export default LockStatusPanel;
