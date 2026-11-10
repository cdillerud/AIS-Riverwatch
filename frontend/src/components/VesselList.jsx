import { memo, useState, useMemo, useEffect } from "react";
import { Ship, Navigation, Gauge, Clock, ChevronUp, ChevronDown, Minus, Box, Timer, Lock, Search, MapPin, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { getVesselDisplayName, hasRiverMile, formatRiverMile, directionLabel, isVesselStale, lastSeenLabel, getLastSeenMs } from "@/utils/vesselDisplay";
import useLocks from "@/hooks/useLocks";

// Check if a vessel is "at" any lock (within 0.5 miles). Locks come from GET /api/locks.
const getVesselLockStatus = (vessel, locks) => {
  if (!hasRiverMile(vessel)) return null;
  const rm = Number(vessel.river_mile);

  const AT_LOCK_DISTANCE = 0.5; // miles

  for (const lock of locks) {
    const lockRM = Number(lock.river_mile);
    if (!Number.isFinite(lockRM)) continue;
    const distance = Math.abs(rm - lockRM);
    if (distance <= AT_LOCK_DISTANCE) {
      const lockNum = lock.id === 'melvin_price' ? 'MP' : lock.id === 'chain_of_rocks' ? 'CR' : lock.id.replace('lock_', '').toUpperCase();
      return {
        lockId: lock.id,
        lockNum,
        distance: distance.toFixed(2)
      };
    }
  }
  return null;
};

const getLastCheckInValue = (vessel) => (
  vessel?.last_ais_checkin || vessel?.timestamp || vessel?.last_update || null
);

const parseCheckInTime = (value) => {
  const ms = getLastSeenMs({ timestamp: value });
  return ms === null ? null : new Date(ms);
};

const formatLastCheckIn = (vessel, nowMs) => {
  const parsed = parseCheckInTime(getLastCheckInValue(vessel));
  if (!parsed) return "--";

  const ageSeconds = Math.max(0, Math.floor((nowMs - parsed.getTime()) / 1000));

  if (ageSeconds < 10) return "just now";
  if (ageSeconds < 60) return `${ageSeconds}s ago`;

  const ageMinutes = Math.floor(ageSeconds / 60);
  if (ageMinutes < 60) return `${ageMinutes}m ago`;

  const ageHours = Math.floor(ageMinutes / 60);
  if (ageHours < 24) return `${ageHours}h ago`;

  const ageDays = Math.floor(ageHours / 24);
  return `${ageDays}d ago`;
};

const getCheckInTextClass = (vessel, nowMs) => {
  const parsed = parseCheckInTime(getLastCheckInValue(vessel));
  if (!parsed) return "text-slate-600";

  const ageSeconds = Math.max(0, Math.floor((nowMs - parsed.getTime()) / 1000));

  if (ageSeconds <= 120) return "text-emerald-400";
  if (ageSeconds <= 300) return "text-amber-400";
  return "text-red-400";
};

const VesselListComponent = ({ vessels, userMmsi, selectedLock, compact = false, onVesselClick = () => {}, showVesselNames = true }) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [nowTick, setNowTick] = useState(() => Date.now());
  const locks = useLocks();

  // Keep the "last check-in" age moving even when no new vessel data arrives.
  useEffect(() => {
    const intervalId = window.setInterval(() => setNowTick(Date.now()), 30000);
    return () => window.clearInterval(intervalId);
  }, []);

  // Filter vessels based on search query (MMSI or name)
  const filteredVessels = useMemo(() => {
    if (!searchQuery.trim()) return vessels;
    
    const query = searchQuery.toLowerCase().trim();
    return vessels.filter(vessel => {
      const mmsiMatch = String(vessel.mmsi ?? '').toLowerCase().includes(query);
      const nameMatch = (vessel.name || '').toLowerCase().includes(query);
      return mmsiMatch || nameMatch;
    });
  }, [vessels, searchQuery]);

  // Check if a vessel matches the search (for highlighting)
  const isSearchMatch = (vessel) => {
    if (!searchQuery.trim()) return false;
    const query = searchQuery.toLowerCase().trim();
    return String(vessel.mmsi ?? '').toLowerCase().includes(query) || 
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
    // No ETA for unknown river mile, stopped, or stale (not-live) positions.
    if (!selectedLock || !hasRiverMile(vessel) || !Number.isFinite(Number(selectedLock.river_mile))) return null;
    if (!(Number(vessel.speed) >= 0.1) || isVesselStale(vessel, nowTick)) return null;

    const rm = Number(vessel.river_mile);
    const lockRM = Number(selectedLock.river_mile);
    const distance = Math.abs(rm - lockRM);
    const speedMph = Number(vessel.speed) * 1.15078;

    // Check if vessel is heading toward lock (northbound = upbound = increasing RM)
    const isHeadingToward = (
      (vessel.heading === "northbound" && rm < lockRM) ||
      (vessel.heading === "southbound" && rm > lockRM)
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
    // ONLY match by MMSI
    const isAUser = userMmsi && a.mmsi === userMmsi;
    const isBUser = userMmsi && b.mmsi === userMmsi;
    
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
              // ONLY match by MMSI
              const isUser = userMmsi && vessel.mmsi === userMmsi;
              const speedMph = Number.isFinite(Number(vessel.speed)) ? (Number(vessel.speed) * 1.15078).toFixed(1) : '--';
              const stale = isVesselStale(vessel, nowTick);
              const eta = calculateETA(vessel);
              const isTow = vessel.is_tow || vessel.barge_count > 0;
              const lockStatus = getVesselLockStatus(vessel, locks);
              const isMatch = isSearchMatch(vessel);
              const lastCheckInDisplay = stale ? lastSeenLabel(vessel, nowTick) : formatLastCheckIn(vessel, nowTick);
              const lastCheckInClass = getCheckInTextClass(vessel, nowTick);

              return (
                <div
                  key={vessel.mmsi}
                  className={`p-3 ${isUser ? 'bg-cyan-500/5 border-l-2 border-l-cyan-500' : ''} ${isMatch ? 'bg-yellow-500/10 border-l-2 border-l-yellow-500' : ''} ${stale ? 'opacity-50' : ''}`}
                  title={stale ? `Stale position — ${lastSeenLabel(vessel, nowTick)}` : undefined}
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
                          onVesselClick(vessel);
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
                    <span className="font-mono">RM {formatRiverMile(vessel.river_mile)}</span>
                    <span className="font-mono">{speedMph} mph</span>
                    <span className="flex items-center gap-0.5">
                      {getDirectionIcon(vessel.heading)}
                      {vessel.heading === 'northbound' ? 'U' : vessel.heading === 'southbound' ? 'D' : ''}
                    </span>
                    <span className={`flex items-center gap-0.5 ${lastCheckInClass}`}>
                      <Clock className="w-3 h-3" />
                      {lastCheckInDisplay}
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
            // ONLY match by MMSI
            const isUser = userMmsi && vessel.mmsi === userMmsi;
            const speedMph = Number.isFinite(Number(vessel.speed)) ? (Number(vessel.speed) * 1.15078).toFixed(1) : '--';
            const stale = isVesselStale(vessel, nowTick);
            const eta = calculateETA(vessel);
            const isTow = vessel.is_tow || vessel.barge_count > 0;
            const lockStatus = getVesselLockStatus(vessel, locks);
            const isMatch = isSearchMatch(vessel);
            const lastCheckInDisplay = stale ? lastSeenLabel(vessel, nowTick) : formatLastCheckIn(vessel, nowTick);
            const lastCheckInClass = getCheckInTextClass(vessel, nowTick);

            return (
              <div
                key={vessel.mmsi}
                className={`
                  vessel-item p-4 cursor-pointer transition-colors
                  ${isUser ? 'user-vessel border-l-2 border-l-cyan-500' : 'hover:bg-slate-800/50'}
                  ${lockStatus ? 'bg-purple-500/5' : ''}
                  ${isMatch ? 'bg-yellow-500/10 border-l-2 border-l-yellow-500' : ''}
                  ${stale ? 'opacity-50' : ''}
                `}
                title={stale ? `Stale position — ${lastSeenLabel(vessel, nowTick)}` : undefined}
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
                    </div>

                    {/* Vessel details */}
                    <div className="flex items-center gap-4 text-xs text-slate-400 mt-2">
                      <span className="flex items-center gap-1">
                        <Navigation className="w-3 h-3" />
                        <span className="font-mono">RM {formatRiverMile(vessel.river_mile)}</span>
                      </span>
                      
                      <span className="flex items-center gap-1">
                        <Gauge className="w-3 h-3" />
                        <span className="font-mono">{speedMph} mph</span>
                      </span>
                      
                      <span className="flex items-center gap-1">
                        {getDirectionIcon(vessel.heading)}
                        <span>{directionLabel(vessel.heading)}</span>
                      </span>

                      <span className={`flex items-center gap-1 ${lastCheckInClass}`}>
                        <Clock className="w-3 h-3" />
                        <span className="font-mono">{lastCheckInDisplay}</span>
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
    </div>
  );
};

// Memoize to prevent unnecessary re-renders
export const VesselList = memo(VesselListComponent);

export default VesselList;
