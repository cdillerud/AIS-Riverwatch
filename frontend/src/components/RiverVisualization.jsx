import { useMemo } from "react";
import { MapPin, Lock, ChevronUp, ChevronDown, Minus, Anchor } from "lucide-react";
import { getVesselDisplayName, getVesselShortName } from "@/utils/vesselDisplay";

// Default River Mile range for Upper Mississippi (Lock 1 to Chain of Rocks)
const FULL_MIN_RM = 180;  // Chain of Rocks (RM 185) with buffer
const FULL_MAX_RM = 850;  // Lock 1 Minneapolis (RM 847.6) with buffer

export const RiverVisualization = ({ 
  vessels, 
  userMmsi, 
  locks, 
  selectedLock,
  raceAnalysis,
  compact = false,
  zoomed = false,
  zoomRange = 25,
  onVesselClick = () => {},
  showVesselNames = true
}) => {
  // Get the selected lock's river mile for zoom center
  const selectedLockRM = useMemo(() => {
    const lock = locks.find(l => l.id === selectedLock);
    return lock?.river_mile || 815;
  }, [locks, selectedLock]);

  // Calculate the visible river mile range
  // When zoomed, center on the selected lock with ±zoomRange miles
  // If we hit the river boundary, shift the window to show the full zoom range
  const { minRM, maxRM } = useMemo(() => {
    if (zoomed) {
      // Use smaller range for mobile/compact view
      const effectiveRange = compact ? Math.min(zoomRange, 15) : zoomRange;
      const totalRange = effectiveRange * 2; // Total miles to show
      let min = selectedLockRM - effectiveRange;
      let max = selectedLockRM + effectiveRange;
      
      // If we exceed the north boundary (high RM), shift window south
      if (max > FULL_MAX_RM) {
        max = FULL_MAX_RM;
        min = Math.max(FULL_MIN_RM, FULL_MAX_RM - totalRange);
      }
      // If we exceed the south boundary (low RM), shift window north
      else if (min < FULL_MIN_RM) {
        min = FULL_MIN_RM;
        max = Math.min(FULL_MAX_RM, FULL_MIN_RM + totalRange);
      }
      
      return { minRM: min, maxRM: max };
    }
    return { minRM: FULL_MIN_RM, maxRM: FULL_MAX_RM };
  }, [zoomed, compact, selectedLockRM, zoomRange]);

  // Calculate position percentage for a river mile
  const getRiverPosition = (riverMile) => {
    if (!riverMile) return 50;
    // Invert because higher RM is north (top of screen)
    const pct = ((riverMile - minRM) / (maxRM - minRM)) * 100;
    return Math.max(2, Math.min(98, 100 - pct)); // Invert so north is at top
  };

  // Check if a river mile is in view
  const isInView = (riverMile) => {
    if (!riverMile) return false;
    return riverMile >= minRM && riverMile <= maxRM;
  };

  // Find user vessel
  const userVessel = useMemo(() => {
    return vessels.find(v => v.mmsi === userMmsi || v.is_user_vessel);
  }, [vessels, userMmsi]);

  // Check if user vessel is outside visible range
  const userOutOfRange = useMemo(() => {
    if (!userVessel?.river_mile) return null;
    const rm = userVessel.river_mile;
    if (rm > maxRM) return 'north';
    if (rm < minRM) return 'south';
    return null;
  }, [userVessel, minRM, maxRM]);

  // Generate river mile markers - adaptive based on range
  const rmMarkers = useMemo(() => {
    const markers = [];
    const range = maxRM - minRM;
    const step = compact ? (range > 100 ? 50 : 25) : (range > 100 ? 25 : 10);
    const start = Math.ceil(minRM / step) * step;
    for (let rm = start; rm <= maxRM; rm += step) {
      markers.push(rm);
    }
    return markers;
  }, [compact, minRM, maxRM]);

  // Filter locks in view
  const visibleLocks = useMemo(() => {
    return locks.filter(lock => isInView(lock.river_mile));
  }, [locks, minRM, maxRM]);

  // Get direction icon
  const getDirectionIcon = (heading) => {
    if (heading === "northbound") return <ChevronUp className="w-3 h-3" />;
    if (heading === "southbound") return <ChevronDown className="w-3 h-3" />;
    return <Minus className="w-3 h-3" />;
  };

  return (
    <div className="river-map relative w-full h-full min-h-[400px] md:min-h-[500px] overflow-hidden" data-testid="river-visualization">
      {/* Radar sweep effect */}
      <div className="absolute inset-0 radar-sweep opacity-30 pointer-events-none" />
      
      {/* River centerline with gradient */}
      <div className="absolute left-1/2 top-0 bottom-0 w-16 md:w-24 -translate-x-1/2 river-viz" />
      
      {/* User vessel off-screen indicator - NORTH */}
      {userOutOfRange === 'north' && userVessel && (
        <div 
          className="absolute top-1 left-1/2 -translate-x-1/2 z-30 animate-pulse"
          data-testid="user-offscreen-north"
        >
          <div className="glass-panel border border-cyan-500/50 px-3 py-2 rounded-lg">
            <div className="flex items-center gap-2">
              <ChevronUp className="w-4 h-4 text-cyan-400" />
              <div className="text-xs">
                <div className="text-cyan-400 font-semibold">
                  {showVesselNames && userVessel.name ? userVessel.name : 'YOUR BOAT'}
                </div>
                <div className="text-slate-400 font-mono">
                  RM {userVessel.river_mile?.toFixed(1)} • {(userVessel.river_mile - maxRM).toFixed(1)} mi north
                </div>
              </div>
              <div className="w-3 h-3 rounded-full bg-cyan-400 user-vessel-pulse" />
            </div>
          </div>
        </div>
      )}
      
      {/* User vessel off-screen indicator - SOUTH */}
      {userOutOfRange === 'south' && userVessel && (
        <div 
          className="absolute bottom-1 left-1/2 -translate-x-1/2 z-30 animate-pulse"
          data-testid="user-offscreen-south"
        >
          <div className="glass-panel border border-cyan-500/50 px-3 py-2 rounded-lg">
            <div className="flex items-center gap-2">
              <ChevronDown className="w-4 h-4 text-cyan-400" />
              <div className="text-xs">
                <div className="text-cyan-400 font-semibold">
                  {showVesselNames && userVessel.name ? userVessel.name : 'YOUR BOAT'}
                </div>
                <div className="text-slate-400 font-mono">
                  RM {userVessel.river_mile?.toFixed(1)} • {(minRM - userVessel.river_mile).toFixed(1)} mi south
                </div>
              </div>
              <div className="w-3 h-3 rounded-full bg-cyan-400 user-vessel-pulse" />
            </div>
          </div>
        </div>
      )}
      
      {/* North indicator */}
      <div className="absolute top-2 md:top-4 left-1/2 -translate-x-1/2 flex flex-col items-center text-slate-500 text-xs">
        <ChevronUp className="w-3 h-3 md:w-4 md:h-4" />
        <span className="font-mono text-[10px] md:text-xs">N</span>
      </div>
      
      {/* South indicator */}
      <div className="absolute bottom-2 md:bottom-4 left-1/2 -translate-x-1/2 flex flex-col items-center text-slate-500 text-xs">
        <span className="font-mono text-[10px] md:text-xs">S</span>
        <ChevronDown className="w-3 h-3 md:w-4 md:h-4" />
      </div>

      {/* River Mile markers on left side */}
      <div className="absolute left-1 md:left-4 top-0 bottom-0 flex flex-col justify-between py-8 md:py-16">
        {rmMarkers.map(rm => (
          <div 
            key={rm} 
            className="flex items-center gap-1 md:gap-2 text-slate-600"
            style={{ position: 'absolute', top: `${getRiverPosition(rm)}%`, transform: 'translateY(-50%)' }}
          >
            <span className="font-mono text-[10px] md:text-xs">{compact ? rm : `RM ${rm}`}</span>
            <div className="w-6 md:w-16 h-px bg-slate-800" />
          </div>
        ))}
      </div>

      {/* Locks */}
      {visibleLocks.map(lock => (
        <div
          key={lock.id}
          className="absolute left-1/2 transform -translate-x-1/2 z-10"
          style={{ top: `${getRiverPosition(lock.river_mile)}%` }}
          data-testid={`lock-marker-${lock.id}`}
        >
          <div className={`
            lock-indicator text-[8px] md:text-[10px] w-12 md:w-[60px] h-5 md:h-6
            ${lock.id === selectedLock ? 'border-cyan-400 bg-cyan-500/20' : ''}
          `}>
            <Lock className="w-2 h-2 md:w-3 md:h-3 mr-0.5 md:mr-1" />
            <span>{lock.id.replace('lock_', 'L')}</span>
          </div>
          
          {/* Lock info tooltip - hide on compact */}
          {!compact && (
            <div className="absolute left-full ml-2 md:ml-4 top-1/2 -translate-y-1/2 whitespace-nowrap hidden md:block">
              <div className="glass-panel px-2 md:px-3 py-1 md:py-2 rounded text-xs">
                <div className="font-semibold text-white">{lock.name}</div>
                <div className="text-slate-400 font-mono">RM {lock.river_mile}</div>
              </div>
            </div>
          )}
        </div>
      ))}

      {/* Vessels */}
      {vessels.filter(v => isInView(v.river_mile)).map(vessel => {
        const isUser = vessel.mmsi === userMmsi || vessel.is_user_vessel;
        const topPosition = getRiverPosition(vessel.river_mile);
        const speedMph = (vessel.speed * 1.15078).toFixed(1);
        
        // Calculate lateral offset based on heading to show direction
        const lateralOffset = vessel.heading === "northbound" ? -15 : 
                            vessel.heading === "southbound" ? 15 : 0;

        return (
          <div
            key={vessel.mmsi}
            className="absolute transform -translate-x-1/2 -translate-y-1/2 z-20 transition-all duration-1000 ease-out cursor-pointer hover:z-30"
            style={{ 
              top: `${topPosition}%`,
              left: `calc(50% + ${lateralOffset}px)`
            }}
            data-testid={`vessel-marker-${vessel.mmsi}`}
            onClick={() => onVesselClick(vessel)}
          >
            {/* Vessel pip */}
            <div className={`
              vessel-pip relative
              ${isUser ? 'user w-3 h-3 md:w-4 md:h-4 user-vessel-pulse' : 'commercial w-2 h-2 md:w-3 md:h-3'}
              hover:scale-125 transition-transform
            `}>
              {/* Direction indicator */}
              <div className={`
                absolute -top-3 md:-top-4 left-1/2 -translate-x-1/2
                ${isUser ? 'text-cyan-400' : 'text-amber-400'}
              `}>
                {getDirectionIcon(vessel.heading)}
              </div>
            </div>

            {/* Vessel info card - simplified on compact */}
            <div className={`
              absolute top-full mt-1 md:mt-2 whitespace-nowrap
              ${isUser ? 'left-1/2 -translate-x-1/2' : '-left-1 md:-left-2'}
            `}>
              <div className={`
                glass-panel px-1.5 md:px-2 py-0.5 md:py-1 rounded text-[10px] md:text-xs
                ${isUser ? 'border border-cyan-500/50' : 'border border-amber-500/30'}
              `}>
                <div className={`font-semibold ${isUser ? 'text-cyan-400' : 'text-amber-400'}`}>
                  {compact ? getVesselShortName(vessel, showVesselNames, 8) : getVesselDisplayName(vessel, showVesselNames)}
                </div>
                <div className="flex items-center gap-1 md:gap-2 text-slate-300">
                  <span className="font-mono">{speedMph}</span>
                  {!compact && <span className="text-slate-500">|</span>}
                  {!compact && <span className="font-mono">RM {vessel.river_mile?.toFixed(1)}</span>}
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {/* Race path indicator - shows path from user to lock */}
      {raceAnalysis?.user_vessel && raceAnalysis?.target_lock_rm && (
        <div 
          className="absolute left-1/2 w-0.5 md:w-1 bg-gradient-to-b from-cyan-500/50 to-transparent -translate-x-1/2"
          style={{
            top: `${Math.min(getRiverPosition(raceAnalysis.user_vessel.river_mile), getRiverPosition(raceAnalysis.target_lock_rm))}%`,
            height: `${Math.abs(getRiverPosition(raceAnalysis.user_vessel.river_mile) - getRiverPosition(raceAnalysis.target_lock_rm))}%`
          }}
        />
      )}

      {/* Legend - hide on compact */}
      {!compact && (
        <div className="absolute bottom-2 md:bottom-4 right-2 md:right-4 glass-panel px-2 md:px-4 py-2 md:py-3 rounded-lg">
          <div className="text-[10px] md:text-xs text-slate-400 uppercase tracking-wider mb-1 md:mb-2">Legend</div>
          <div className="space-y-1 md:space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 md:w-3 md:h-3 rounded-full bg-cyan-400 user-vessel-pulse" />
              <span className="text-[10px] md:text-xs text-slate-300">Your Vessel</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 md:w-2.5 md:h-2.5 bg-amber-400 rotate-45" />
              <span className="text-[10px] md:text-xs text-slate-300">Commercial</span>
            </div>
            <div className="flex items-center gap-2">
              <Lock className="w-2 h-2 md:w-3 md:h-3 text-white" />
              <span className="text-[10px] md:text-xs text-slate-300">Lock & Dam</span>
            </div>
          </div>
        </div>
      )}

      {/* View range indicator */}
      {zoomed && !compact && (
        <div className="absolute top-2 left-2 glass-panel px-2 py-1 rounded text-xs text-slate-400">
          <span className="font-mono">RM {minRM.toFixed(0)} - {maxRM.toFixed(0)}</span>
        </div>
      )}

      {/* Out of view vessels indicator */}
      {vessels.length > 0 && vessels.filter(v => isInView(v.river_mile)).length < vessels.length && (
        <div className="absolute bottom-2 left-2 glass-panel px-2 py-1 rounded text-xs text-amber-400">
          {vessels.length - vessels.filter(v => isInView(v.river_mile)).length} vessel(s) outside view
        </div>
      )}

      {/* Empty state */}
      {vessels.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-slate-500">
            <Anchor className="w-8 h-8 md:w-12 md:h-12 mx-auto mb-2 md:mb-4 opacity-50" />
            <p className="text-sm md:text-lg">No vessels detected</p>
            <p className="text-xs md:text-sm mt-1">Waiting for AIS data...</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default RiverVisualization;
