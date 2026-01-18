import { Ship, Navigation, Gauge, Clock, ChevronUp, ChevronDown, Minus, Box, Timer } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export const VesselList = ({ vessels, userMmsi, selectedLock, compact = false }) => {
  if (vessels.length === 0) {
    return (
      <div className="empty-state py-8 md:py-12">
        <Ship className="w-8 h-8 md:w-10 md:h-10 mx-auto mb-3 opacity-30" />
        <p className="text-sm">No vessels in range</p>
      </div>
    );
  }

  // Calculate ETA for each vessel to selected lock
  const calculateETA = (vessel) => {
    if (!selectedLock || !vessel.river_mile || vessel.speed < 0.1) return null;
    
    const distance = Math.abs(vessel.river_mile - selectedLock.river_mile);
    const speedMph = vessel.speed * 1.15078;
    
    // Check if vessel is heading toward lock
    const isHeadingToward = (
      (vessel.heading === "northbound" && vessel.river_mile < selectedLock.river_mile) ||
      (vessel.heading === "southbound" && vessel.river_mile > selectedLock.river_mile)
    );
    
    if (!isHeadingToward) return null;
    
    const etaMinutes = (distance / speedMph) * 60;
    return etaMinutes;
  };

  const getDirectionIcon = (heading) => {
    if (heading === "northbound") return <ChevronUp className="w-3 h-3 text-green-400" />;
    if (heading === "southbound") return <ChevronDown className="w-3 h-3 text-amber-400" />;
    return <Minus className="w-3 h-3 text-slate-500" />;
  };

  const formatETA = (minutes) => {
    if (!minutes) return "--";
    if (minutes < 60) return `${Math.round(minutes)}m`;
    const hours = Math.floor(minutes / 60);
    const mins = Math.round(minutes % 60);
    return `${hours}h ${mins}m`;
  };

  // Sort: user first, then by ETA to lock
  const sortedVessels = [...vessels].sort((a, b) => {
    const isAUser = a.mmsi === userMmsi || a.is_user_vessel;
    const isBUser = b.mmsi === userMmsi || b.is_user_vessel;
    
    if (isAUser && !isBUser) return -1;
    if (!isAUser && isBUser) return 1;
    
    const etaA = calculateETA(a) || Infinity;
    const etaB = calculateETA(b) || Infinity;
    return etaA - etaB;
  });

  // Compact mobile version
  if (compact) {
    return (
      <div className="divide-y divide-white/5" data-testid="vessel-list">
        {sortedVessels.map(vessel => {
          const isUser = vessel.mmsi === userMmsi || vessel.is_user_vessel;
          const speedMph = (vessel.speed * 1.15078).toFixed(1);
          const eta = calculateETA(vessel);
          const isTow = vessel.is_tow || vessel.barge_count > 0;

          return (
            <div
              key={vessel.mmsi}
              className={`p-3 ${isUser ? 'bg-cyan-500/5 border-l-2 border-l-cyan-500' : ''}`}
              data-testid={`vessel-item-${vessel.mmsi}`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {isUser ? (
                    <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                  ) : isTow ? (
                    <Box className="w-3 h-3 text-amber-400" />
                  ) : (
                    <div className="w-2 h-2 bg-amber-400 rotate-45" />
                  )}
                  <span className={`font-medium text-sm ${isUser ? 'text-cyan-400' : 'text-white'}`}>
                    {vessel.name || vessel.mmsi}
                  </span>
                  {isUser && (
                    <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/50 text-[10px] px-1">
                      YOU
                    </Badge>
                  )}
                </div>
                <span className={`font-mono text-sm ${eta ? 'text-white' : 'text-slate-600'}`}>
                  {formatETA(eta)}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                <span className="font-mono">RM {vessel.river_mile?.toFixed(1)}</span>
                <span className="font-mono">{speedMph} mph</span>
                <span className="flex items-center gap-0.5">
                  {getDirectionIcon(vessel.heading)}
                  {vessel.heading?.slice(0,1).toUpperCase()}
                </span>
              </div>
              {/* Barge info for tows */}
              {isTow && (
                <div className="flex items-center gap-3 mt-1.5">
                  {vessel.barge_count && (
                    <Badge className="bg-amber-900/30 text-amber-400 border-amber-500/30 text-[10px]">
                      <Box className="w-2.5 h-2.5 mr-1" />
                      {vessel.barge_count} barges
                      {vessel.tow_config && ` (${vessel.tow_config})`}
                    </Badge>
                  )}
                  {vessel.estimated_lockage_time && (
                    <span className="text-[10px] text-slate-500 flex items-center gap-1">
                      <Timer className="w-2.5 h-2.5" />
                      ~{vessel.estimated_lockage_time}min lock
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="divide-y divide-white/5" data-testid="vessel-list">
      {sortedVessels.map(vessel => {
        const isUser = vessel.mmsi === userMmsi || vessel.is_user_vessel;
        const speedMph = (vessel.speed * 1.15078).toFixed(1);
        const eta = calculateETA(vessel);
        const isTow = vessel.is_tow || vessel.barge_count > 0;

        return (
          <div
            key={vessel.mmsi}
            className={`
              vessel-item p-4 
              ${isUser ? 'user-vessel border-l-2 border-l-cyan-500' : 'hover:bg-slate-800/50'}
            `}
            data-testid={`vessel-item-${vessel.mmsi}`}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                {/* Vessel name and badges */}
                <div className="flex items-center gap-2 mb-1">
                  {isUser ? (
                    <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                  ) : isTow ? (
                    <Box className="w-4 h-4 text-amber-400" />
                  ) : (
                    <div className="w-2 h-2 bg-amber-400 rotate-45" />
                  )}
                  <span className={`font-semibold ${isUser ? 'text-cyan-400' : 'text-white'}`}>
                    {vessel.name || `MMSI: ${vessel.mmsi}`}
                  </span>
                  {isUser && (
                    <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/50 text-xs">
                      YOU
                    </Badge>
                  )}
                  {isTow && !isUser && (
                    <Badge className="bg-amber-900/30 text-amber-400 border-amber-500/30 text-xs">
                      TOW
                    </Badge>
                  )}
                </div>

                {/* Vessel details */}
                <div className="flex items-center gap-4 text-xs text-slate-400 mt-2">
                  <span className="flex items-center gap-1">
                    <Navigation className="w-3 h-3" />
                    <span className="font-mono">RM {vessel.river_mile?.toFixed(1) || '--'}</span>
                  </span>
                  
                  <span className="flex items-center gap-1">
                    <Gauge className="w-3 h-3" />
                    <span className="font-mono">{speedMph} mph</span>
                  </span>
                  
                  <span className="flex items-center gap-1">
                    {getDirectionIcon(vessel.heading)}
                    <span className="capitalize">{vessel.heading || 'stationary'}</span>
                  </span>
                </div>

                {/* Barge info for tows */}
                {isTow && (
                  <div className="flex items-center gap-3 mt-2">
                    {vessel.barge_count && (
                      <Badge className="bg-amber-900/30 text-amber-400 border-amber-500/30 text-xs">
                        <Box className="w-3 h-3 mr-1" />
                        {vessel.barge_count} barges
                        {vessel.tow_config && ` (${vessel.tow_config})`}
                      </Badge>
                    )}
                    {vessel.estimated_lockage_time && (
                      <span className="text-xs text-slate-500 flex items-center gap-1">
                        <Timer className="w-3 h-3" />
                        ~{vessel.estimated_lockage_time} min lockage
                      </span>
                    )}
                    {vessel.barge_count > 15 && (
                      <Badge className="bg-red-900/30 text-red-400 border-red-500/30 text-xs">
                        DOUBLE LOCK
                      </Badge>
                    )}
                  </div>
                )}
              </div>

              {/* ETA to lock */}
              <div className="text-right ml-4">
                <div className="text-xs text-slate-500 uppercase">ETA to Lock</div>
                <div className={`font-mono text-lg ${eta ? 'text-white' : 'text-slate-600'}`}>
                  {formatETA(eta)}
                </div>
                {isTow && vessel.estimated_lockage_time && (
                  <div className="text-xs text-slate-500 mt-1">
                    +{vessel.estimated_lockage_time}min lock
                  </div>
                )}
              </div>
            </div>

            {/* Progress bar for ETA */}
            {eta && eta < 120 && (
              <div className="mt-2">
                <div className="eta-bar">
                  <div 
                    className={`eta-bar-fill ${isUser ? 'bg-cyan-500' : 'bg-amber-500'}`}
                    style={{ width: `${Math.max(5, 100 - (eta / 120) * 100)}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default VesselList;
