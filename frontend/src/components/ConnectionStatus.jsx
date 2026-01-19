import { Wifi, WifiOff, Signal, Play } from "lucide-react";

export const ConnectionStatus = ({ isConnected, config, compact = false, demoMode = false }) => {
  if (compact) {
    return (
      <div className="flex items-center gap-1.5">
        <div className={`status-dot ${demoMode ? 'demo' : isConnected ? 'connected' : 'disconnected'}`} />
        {demoMode ? (
          <span className="text-xs text-amber-400">Demo</span>
        ) : !isConnected ? (
          <span className="text-xs text-red-400">Offline</span>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/80 border border-slate-700">
      <div className={`status-dot ${demoMode ? 'demo' : isConnected ? 'connected' : 'disconnected'}`} />
      
      <span className="text-xs text-slate-400">
        {demoMode ? 'Demo Mode' : isConnected ? 'Connected' : 'Disconnected'}
      </span>
      
      {config && !demoMode && (
        <>
          <span className="text-slate-600">|</span>
          <span className="text-xs font-mono text-slate-500">
            {config.ip_address}:{config.port}
          </span>
        </>
      )}
      
      {demoMode ? (
        <Play className="w-3 h-3 text-amber-400" />
      ) : isConnected ? (
        <Signal className="w-3 h-3 text-green-400" />
      ) : (
        <WifiOff className="w-3 h-3 text-red-400" />
      )}
    </div>
  );
};

export default ConnectionStatus;
