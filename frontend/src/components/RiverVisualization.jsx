import { useMemo, useState, useCallback, useRef, useEffect } from "react";
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
  zoomRange = 20, // Range in miles (10-500, 500+ = full view)
  onVesselClick = () => {},
  showVesselNames = true
}) => {
  // Scroll offset in river miles (positive = shifted north/up)
  const [scrollOffset, setScrollOffset] = useState(0);
  const mapRef = useRef(null);
  
  // Get the selected lock's river mile for zoom center
  const selectedLockRM = useMemo(() => {
    const lock = locks.find(l => l.id === selectedLock);
    return lock?.river_mile || 815;
  }, [locks, selectedLock]);

  // Reset scroll offset when selected lock changes
  useEffect(() => {
    setScrollOffset(0);
  }, [selectedLock]);

  // Calculate the visible river mile range based on zoomRange and scroll offset
  const { minRM, maxRM } = useMemo(() => {
    // If zoomRange >= 500, show full river (no scrolling needed)
    if (zoomRange >= 500) {
      return { minRM: FULL_MIN_RM, maxRM: FULL_MAX_RM };
    }
    
    // Center on selected lock with ±zoomRange miles, then apply scroll offset
    const centerRM = selectedLockRM + scrollOffset;
    const effectiveRange = zoomRange;
    const totalRange = effectiveRange * 2;
    let min = centerRM - effectiveRange;
    let max = centerRM + effectiveRange;
    
    // Clamp to river boundaries
    if (max > FULL_MAX_RM) {
      max = FULL_MAX_RM;
      min = Math.max(FULL_MIN_RM, FULL_MAX_RM - totalRange);
    }
    if (min < FULL_MIN_RM) {
      min = FULL_MIN_RM;
      max = Math.min(FULL_MAX_RM, FULL_MIN_RM + totalRange);
    }
    
    return { minRM: min, maxRM: max };
  }, [selectedLockRM, zoomRange, scrollOffset]);
  }, [selectedLockRM, zoomRange]);

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
    // Adaptive step sizes based on zoom level and screen size
    let step;
    if (range <= 30) {
      step = compact ? 10 : 5;  // Zoomed in tight
    } else if (range <= 100) {
      step = compact ? 25 : 10;  // Moderately zoomed
    } else if (range <= 300) {
      step = compact ? 100 : 50;  // Wide view
    } else {
      step = compact ? 150 : 100;  // Full river view - much wider spacing
    }
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

      {/* Locks - positioned in CENTER of map */}
      {visibleLocks.map(lock => {
        // Determine lock border color based on timing status (only for selected lock)
        const isSelected = lock.id === selectedLock;
        const analysis = raceAnalysis?.analysis;
        let lockStyle = {};
        
        if (isSelected && analysis) {
          if (analysis.required_speed_mph > 25) {
            // Can't beat - red
            lockStyle = { borderColor: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.2)', boxShadow: '0 0 12px rgba(239, 68, 68, 0.5)' };
          } else if (analysis.can_beat_at_25mph && analysis.threatening_vessel) {
            // Can arrive first - green
            lockStyle = { borderColor: '#22c55e', backgroundColor: 'rgba(34, 197, 94, 0.2)', boxShadow: '0 0 12px rgba(34, 197, 94, 0.5)' };
          } else if (!analysis.threatening_vessel) {
            // No traffic - amber
            lockStyle = { borderColor: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.2)', boxShadow: '0 0 12px rgba(245, 158, 11, 0.5)' };
          }
        } else if (isSelected) {
          // Selected but no analysis yet - cyan
          lockStyle = { borderColor: '#22d3ee', backgroundColor: 'rgba(34, 211, 238, 0.2)' };
        }
        
        return (
          <div
            key={lock.id}
            className="absolute left-1/2 transform -translate-x-1/2 z-10"
            style={{ 
              top: `${getRiverPosition(lock.river_mile)}%`,
              transform: 'translate(-50%, -50%)'
            }}
            data-testid={`lock-marker-${lock.id}`}
          >
            <div 
              className={`lock-indicator text-[8px] md:text-[10px] w-12 md:w-[60px] h-5 md:h-6`}
              style={lockStyle}
            >
              <Lock className="w-2 h-2 md:w-3 md:h-3 mr-0.5 md:mr-1" />
              <span>{lock.id.replace('lock_', 'L')}</span>
            </div>
          </div>
        );
      })}

      {/* Vessels - dots on CENTER, labels offset to the RIGHT with gap */}
      {vessels.filter(v => isInView(v.river_mile)).map((vessel, index) => {
        const isUser = vessel.mmsi === userMmsi || vessel.is_user_vessel;
        const topPosition = getRiverPosition(vessel.river_mile);
        const speedMph = (vessel.speed * 1.15078).toFixed(1);

        return (
          <div
            key={vessel.mmsi}
            className="absolute z-20 transition-all duration-1000 ease-out cursor-pointer hover:z-30"
            style={{ 
              top: `${topPosition}%`,
              left: '50%',
              transform: 'translateY(-50%)'
            }}
            data-testid={`vessel-marker-${vessel.mmsi}`}
            onClick={() => onVesselClick(vessel)}
          >
            {/* Vessel pip - exactly on centerline */}
            <div 
              className={`
                vessel-pip absolute
                ${isUser ? 'user w-3 h-3 md:w-4 md:h-4 user-vessel-pulse' : 'commercial w-2 h-2 md:w-3 md:h-3'}
                hover:scale-125 transition-transform
              `}
              style={{ 
                left: '0', 
                top: '50%', 
                transform: isUser ? 'translate(-50%, -50%)' : 'translate(-50%, -50%) rotate(45deg)'
              }}
            />

            {/* Vessel info label - clearly to the right with gap */}
            <div 
              className={`
                absolute px-1.5 py-1 rounded text-[10px] leading-tight flex items-center gap-1 whitespace-nowrap
                ${isUser ? 'bg-cyan-950/95 border border-cyan-500/50 text-cyan-400' : 'bg-slate-900/95 border border-amber-500/30 text-amber-400'}
              `}
              style={{ left: compact ? '15px' : '20px', top: '50%', transform: 'translateY(-50%)' }}
            >
              {/* Direction arrow */}
              <div className={`flex-shrink-0 ${vessel.heading === 'northbound' ? 'text-green-400' : vessel.heading === 'southbound' ? 'text-red-400' : 'text-slate-500'}`}>
                {vessel.heading === 'northbound' ? (
                  <ChevronUp className="w-3 h-3" />
                ) : vessel.heading === 'southbound' ? (
                  <ChevronDown className="w-3 h-3" />
                ) : (
                  <Minus className="w-3 h-3" />
                )}
              </div>
              <div>
                <div className="font-semibold">
                  {compact ? getVesselShortName(vessel, showVesselNames, 10) : getVesselDisplayName(vessel, showVesselNames)}
                </div>
                <div className="text-slate-400 font-mono text-[9px]">
                  {speedMph} mph {!compact && `• RM ${vessel.river_mile?.toFixed(1)}`}
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
      {zoomRange < 500 && !compact && (
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
