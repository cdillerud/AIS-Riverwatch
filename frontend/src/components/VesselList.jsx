import { memo, useState, useMemo } from "react";
import { Ship, Navigation, Gauge, Clock, ChevronUp, ChevronDown, Minus, Box, Timer, Lock, Search, MapPin, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { getVesselDisplayName } from "@/utils/vesselDisplay";

// Lock positions for "At Lock" detection
const LOCK_POSITIONS = {
  lock_1: 847.6, lock_2: 815.2, lock_3: 796.9, lock_4: 752.8,
  lock_5: 738.1, lock_5a: 728.3, lock_6: 714.2, lock_7: 702.4,
  lock_8: 679.1, lock_9: 647.8, lock_10: 615.1, lock_11: 583.0,
  lock_12: 556.6, lock_13: 522.4, lock_14: 493.2, lock_15: 482.9,
  lock_16: 457.2, lock_17: 437.1, lock_18: 410.5, lock_19: 364.2,
  lock_20: 343.2, lock_21: 324.9, lock_22: 301.2, lock_24: 273.4,
  lock_25: 241.4, lock_26: 202.9, lock_27: 185.0
};

// Check if a vessel is "at" any lock (within 0.5 miles)
const getVesselLockStatus = (vessel) => {
  if (!vessel.river_mile) return null;
  
  const AT_LOCK_DISTANCE = 0.5; // miles
  
  for (const [lockId, lockRM] of Object.entries(LOCK_POSITIONS)) {
    const distance = Math.abs(vessel.river_mile - lockRM);
    if (distance <= AT_LOCK_DISTANCE) {
      const lockNum = lockId.replace('lock_', '').toUpperCase();
      return {
        lockId,
        lockNum,
        distance: distance.toFixed(2)
      };
    }
  }
  return null;
};

const VesselListComponent = ({ vessels, userMmsi, selectedLock, compact = false, onVesselClick = () => {}, showVesselNames = true }) => {
  const [searchQuery, setSearchQuery] = useState("");

  // Filter vessels based on search query (MMSI or name)
  const filteredVessels = useMemo(() => {
    if (!searchQuery.trim()) return vessels;
    
    const query = searchQuery.toLowerCase().trim();
    return vessels.filter(vessel => {
      const mmsiMatch = vessel.mmsi?.toLowerCase().includes(query);
      const nameMatch = (vessel.name || '').toLowerCase().includes(query);
      return mmsiMatch || nameMatch;
    });
  }, [vessels, searchQuery]);

  // Check if a vessel matches the search (for highlighting)
  const isSearchMatch = (vessel) => {
    if (!searchQuery.trim()) return false;
    const query = searchQuery.toLowerCase().trim();
    return vessel.mmsi?.toLowerCase().includes(query) || 
           (vessel.name || '').toLowerCase().includes(query);
  };

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

  // Sort: user first, then by ETA to lock (use filteredVessels)
  const sortedVessels = [...filteredVessels].sort((a, b) => {
    const isAUser = a.mmsi === userMmsi || a.is_user_vessel;
    const isBUser = b.mmsi === userMmsi || b.is_user_vessel;
    
    if (isAUser && !isBUser) return -1;
    if (!isAUser && isBUser) return 1;
    
    const etaA = calculateETA(a) || Infinity;
    const etaB = calculateETA(b) || Infinity;
    return etaA - etaB;
  });

  // Reusable search bar JSX
  const searchBarJSX = (
    <div className="relative mb-3">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
      <Input
        type="text"
        placeholder="Search by MMSI or name..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="pl-9 pr-9 bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 text-sm"
        data-testid="vessel-search-input"
      />
      {searchQuery && (
        <button
          onClick={() => setSearchQuery("")}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );

  // Results count JSX
  const resultsCountJSX = searchQuery.trim() ? (
    <div className="text-xs text-slate-500 mb-2 px-1">
      Found {filteredVessels.length} of {vessels.length} vessels
    </div>
  ) : null;

  // Compact mobile version
  if (compact) {
    return (
      <div data-testid="vessel-list">
        {searchBarJSX}
        {resultsCountJSX}
        {sortedVessels.length === 0 ? (
          <div className="text-center py-8 text-slate-500">
            <Search className="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">No vessels match &quot;{searchQuery}&quot;</p>
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {sortedVessels.map(vessel => {
              const isUser = vessel.mmsi === userMmsi || vessel.is_user_vessel;
              const speedMph = (vessel.speed * 1.15078).toFixed(1);
              const eta = calculateETA(vessel);
              const isTow = vessel.is_tow || vessel.barge_count > 0;
              const lockStatus = getVesselLockStatus(vessel);
              const isMatch = isSearchMatch(vessel);

              return (
                <div
                  key={vessel.mmsi}
                  className={`p-3 ${isUser ? 'bg-cyan-500/5 border-l-2 border-l-cyan-500' : ''} ${isMatch ? 'bg-yellow-500/10 border-l-2 border-l-yellow-500' : ''}`}
                  data-testid={`vessel-item-${vessel.mmsi}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      {isUser ? (
                        <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse flex-shrink-0" />
                      ) : isTow ? (
                        <Box className="w-3 h-3 text-amber-400 flex-shrink-0" />
                      ) : (
                        <div className="w-2 h-2 bg-amber-400 rotate-45 flex-shrink-0" />
                      )}
                      <span className={`font-medium text-sm truncate ${isUser ? 'text-cyan-400' : 'text-white'}`}>
                        {getVesselDisplayName(vessel, showVesselNames)}
                      </span>
                      {isUser && (
                        <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/50 text-[10px] px-1 flex-shrink-0">
                          YOU
                        </Badge>
                      )}
                      {lockStatus && (
                        <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/50 text-[10px] px-1 flex-shrink-0">
                          <Lock className="w-2.5 h-2.5 mr-0.5" />
                          L{lockStatus.lockNum}
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-slate-400 hover:text-cyan-400"
                        onClick={(e) => {
                          e.stopPropagation();
                          setMiniMapVessel(vessel);
                        }}
                        title="Show on map"
                      >
                        <MapPin className="w-4 h-4" />
                      </Button>
                      <span className={`font-mono text-sm ${eta ? 'text-white' : 'text-slate-600'}`}>
                        {lockStatus ? 'AT LOCK' : formatETA(eta)}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                    <span className="font-mono">RM {vessel.river_mile?.toFixed(1)}</span>
                    <span className="font-mono">{speedMph} mph</span>
                    <span className="flex items-center gap-0.5">
                      {getDirectionIcon(vessel.heading)}
                      {vessel.heading?.slice(0,1).toUpperCase()}
                    </span>
                  </div>
                  {isTow && (
                    <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                      {vessel.barge_count && (
                        <Badge className="bg-amber-900/30 text-amber-400 border-amber-500/30 text-[10px]">
                          <Box className="w-2.5 h-2.5 mr-1" />
                          {vessel.barge_count} barges
                          {vessel.tow_config && ` (${vessel.tow_config})`}
                        </Badge>
                      )}
                      {vessel.barge_count > 9 && (
                        <Badge className="bg-red-900/30 text-red-400 border-red-500/30 text-[10px]">
                          DOUBLE LOCK
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
        )}
        <VesselMiniMap
          vessel={miniMapVessel}
          isOpen={!!miniMapVessel}
          onClose={() => setMiniMapVessel(null)}
        />
      </div>
    );
  }

  return (
    <div data-testid="vessel-list">
      {searchBarJSX}
      {resultsCountJSX}
      {sortedVessels.length === 0 ? (
        <div className="text-center py-8 text-slate-500">
          <Search className="w-8 h-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">No vessels match &quot;{searchQuery}&quot;</p>
        </div>
      ) : (
        <div className="divide-y divide-white/5">
          {sortedVessels.map(vessel => {
            const isUser = vessel.mmsi === userMmsi || vessel.is_user_vessel;
            const speedMph = (vessel.speed * 1.15078).toFixed(1);
            const eta = calculateETA(vessel);
            const isTow = vessel.is_tow || vessel.barge_count > 0;
            const lockStatus = getVesselLockStatus(vessel);
            const isMatch = isSearchMatch(vessel);

            return (
              <div
                key={vessel.mmsi}
                className={`
                  vessel-item p-4 cursor-pointer transition-colors
                  ${isUser ? 'user-vessel border-l-2 border-l-cyan-500' : 'hover:bg-slate-800/50'}
                  ${lockStatus ? 'bg-purple-500/5' : ''}
                  ${isMatch ? 'bg-yellow-500/10 border-l-2 border-l-yellow-500' : ''}
                `}
                data-testid={`vessel-item-${vessel.mmsi}`}
                onClick={() => onVesselClick(vessel)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    {/* Vessel name and badges */}
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      {isUser ? (
                        <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                      ) : isTow ? (
                        <Box className="w-4 h-4 text-amber-400" />
                      ) : (
                        <div className="w-2 h-2 bg-amber-400 rotate-45" />
                      )}
                      <span className={`font-semibold ${isUser ? 'text-cyan-400' : 'text-white'}`}>
                        {getVesselDisplayName(vessel, showVesselNames)}
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
                      {/* At Lock Badge */}
                      {lockStatus && (
                        <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/50 text-xs">
                          <Lock className="w-3 h-3 mr-1" />
                          AT LOCK {lockStatus.lockNum}
                        </Badge>
                      )}
                      {vessel.nav_status_text && vessel.nav_status !== 0 && !lockStatus && (
                        <Badge className="bg-slate-700 text-slate-300 text-xs">
                          {vessel.nav_status_text}
                        </Badge>
                      )}
                      {/* Mini map button */}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0 text-slate-400 hover:text-cyan-400 ml-auto"
                        onClick={(e) => {
                          e.stopPropagation();
                          setMiniMapVessel(vessel);
                        }}
                        title="Show on map"
                      >
                        <MapPin className="w-4 h-4" />
                      </Button>
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

                    {/* Additional AIS info (destination, ETA) */}
                    {(vessel.destination || vessel.eta || vessel.callsign) && (
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-500">
                        {vessel.destination && (
                          <span>→ {vessel.destination}</span>
                        )}
                        {vessel.eta && (
                          <span>ETA: {vessel.eta}</span>
                        )}
                        {vessel.callsign && (
                          <span className="font-mono">{vessel.callsign}</span>
                        )}
                      </div>
                    )}

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
                        {vessel.barge_count > 9 && (
                          <Badge className="bg-red-900/30 text-red-400 border-red-500/30 text-xs">
                            DOUBLE LOCK
                          </Badge>
                        )}
                      </div>
                    )}
                  </div>

                  {/* ETA to lock or "At Lock" status */}
                  <div className="text-right ml-4">
                    {lockStatus ? (
                      <>
                        <div className="text-xs text-purple-400 uppercase">At Lock</div>
                        <div className="font-mono text-lg text-purple-400">
                          L{lockStatus.lockNum}
                        </div>
                        <div className="text-xs text-slate-500 mt-1">
                          {lockStatus.distance}mi away
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="text-xs text-slate-500 uppercase">ETA to Lock</div>
                        <div className={`font-mono text-lg ${eta ? 'text-white' : 'text-slate-600'}`}>
                          {formatETA(eta)}
                        </div>
                        {isTow && vessel.estimated_lockage_time && (
                          <div className="text-xs text-slate-500 mt-1">
                            +{vessel.estimated_lockage_time}min lock
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>

                {/* Progress bar for ETA (only when not at lock) */}
                {!lockStatus && eta && eta < 120 && (
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
      )}
      <VesselMiniMap
        vessel={miniMapVessel}
        isOpen={!!miniMapVessel}
        onClose={() => setMiniMapVessel(null)}
      />
    </div>
  );
};

// Memoize to prevent unnecessary re-renders
export const VesselList = memo(VesselListComponent);

export default VesselList;
