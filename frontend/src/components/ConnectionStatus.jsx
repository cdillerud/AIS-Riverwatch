import { Wifi, WifiOff, Signal } from "lucide-react";

export const ConnectionStatus = ({ isConnected, config }) => {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/80 border border-slate-700">
      <div className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
      
      <span className="text-xs text-slate-400">
        {isConnected ? 'Connected' : 'Disconnected'}
      </span>
      
      {config && (
        <>
          <span className="text-slate-600">|</span>
          <span className="text-xs font-mono text-slate-500">
            {config.ip_address}:{config.port}
          </span>
        </>
      )}
      
      {isConnected ? (
        <Signal className="w-3 h-3 text-green-400" />
      ) : (
        <WifiOff className="w-3 h-3 text-red-400" />
      )}
    </div>
  );
};

export default ConnectionStatus;
