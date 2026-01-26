import { useMemo, useState, useCallback, useRef, useEffect, memo } from "react";
import { MapPin, Lock, ChevronUp, ChevronDown, Minus, Anchor, X, Navigation, Gauge, Box, Timer, ExternalLink, ChevronRight, Radio, Compass, Ruler, Clock, History } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getVesselDisplayName, getVesselShortName } from "@/utils/vesselDisplay";

// Default River Mile range for Upper Mississippi (Lock 1 to Chain of Rocks)
const FULL_MIN_RM = 180;  // Chain of Rocks (RM 185) with buffer
const FULL_MAX_RM = 850;  // Lock 1 Minneapolis (RM 847.6) with buffer

const RiverVisualizationComponent = ({ 
  vessels, 
  userMmsi, 
  locks, 
  selectedLock,
  raceAnalysis,
  compact = false,
  zoomRange = 20, // Range in miles (10-500, 500+ = full view)
  onVesselClick = () => {},
  onVesselDetails = () => {}, // Callback to open full vessel detail modal
  onLockClick = () => {}, // Callback when lock is clicked for details
  onUserVesselEdit = () => {}, // Callback when user's vessel is clicked for editing
  showVesselNames = true,
  focusedVessel = null,
  onFocusClear = () => {}
}) => {
  // Scroll offset in river miles (positive = shifted north/up)
  const [scrollOffset, setScrollOffset] = useState(0);
  const mapRef = useRef(null);
  // Selected vessel for info overlay on map
  const [mapSelectedVessel, setMapSelectedVessel] = useState(null);
  
  // Get the selected lock's river mile for zoom center
  const selectedLockRM = useMemo(() => {
    const lock = locks.find(l => l.id === selectedLock);
    return lock?.river_mile || 815;
  }, [locks, selectedLock]);

  // When a focused vessel is set, calculate offset to center on it and show info
  useEffect(() => {
    if (focusedVessel && focusedVessel.river_mile !== undefined && focusedVessel.river_mile !== null) {
      const vesselRM = focusedVessel.river_mile;
      const offsetNeeded = vesselRM - selectedLockRM;
      
      // Update scroll offset to center on the vessel
      setScrollOffset(offsetNeeded);
      
      // Show info overlay for the vessel
      setMapSelectedVessel(focusedVessel);
      
      // Clear focus after a delay (so user can scroll freely after)
      const timer = setTimeout(() => {
        onFocusClear();
      }, 1000);
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedVessel, selectedLockRM, onFocusClear]);

  // Reset scroll offset when selected lock changes (but NOT when focusing on a vessel)
  const prevSelectedLock = useRef(selectedLock);
  useEffect(() => {
    // Only reset if lock changed and we're not focusing on a vessel
    if (prevSelectedLock.current !== selectedLock && !focusedVessel) {
      setScrollOffset(0);
    }
    prevSelectedLock.current = selectedLock;
  }, [selectedLock, focusedVessel]);

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

  // Calculate position percentage for a river mile
  const getRiverPosition = (riverMile) => {
    if (!riverMile) return 50;
    // Invert because higher RM is north (top of screen)
    const pct = ((riverMile - minRM) / (maxRM - minRM)) * 100;
    return Math.max(2, Math.min(98, 100 - pct)); // Invert so north is at top
  };

  // Check if a river mile is in view
  const isInView = useCallback((riverMile) => {
    if (!riverMile) return false;
    return riverMile >= minRM && riverMile <= maxRM;
  }, [minRM, maxRM]);

  // Find user vessel - ONLY match by MMSI
  const userVessel = useMemo(() => {
    if (!userMmsi) return null;
    return vessels.find(v => v.mmsi === userMmsi);
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
  }, [locks, isInView]);

  // Calculate horizontal offsets for vessels that are close together
  // This prevents overlapping markers on the map
  const vesselOffsets = useMemo(() => {
    const offsets = {};
    const visibleVessels = vessels.filter(v => isInView(v.river_mile));
    
    // Sort by river mile to process in order
    const sorted = [...visibleVessels].sort((a, b) => (b.river_mile || 0) - (a.river_mile || 0));
    
    // Calculate proximity threshold based on zoom level
    // At zoom 20 (40 mile range), 0.5 RM is close
    // At zoom 100 (200 mile range), need larger threshold
    const range = maxRM - minRM;
    const proximityThreshold = Math.max(0.3, range * 0.015); // ~1.5% of visible range
    
    // Group vessels by proximity
    const groups = [];
    let currentGroup = [];
    
    for (const vessel of sorted) {
      if (!vessel.river_mile) continue;
      
      if (currentGroup.length === 0) {
        currentGroup.push(vessel);
      } else {
        const lastRM = currentGroup[currentGroup.length - 1].river_mile;
        if (Math.abs(vessel.river_mile - lastRM) <= proximityThreshold) {
          currentGroup.push(vessel);
        } else {
          if (currentGroup.length > 0) groups.push(currentGroup);
          currentGroup = [vessel];
        }
      }
    }
    if (currentGroup.length > 0) groups.push(currentGroup);
    
    // Assign horizontal offsets within each group
    // User vessel always stays centered (offset 0)
    for (const group of groups) {
      if (group.length === 1) {
        offsets[group[0].mmsi] = 0;
      } else {
        // Sort group so user vessel is first (stays centered)
        const sortedGroup = [...group].sort((a, b) => {
          // ONLY match by MMSI
          const aIsUser = userMmsi && a.mmsi === userMmsi;
          const bIsUser = userMmsi && b.mmsi === userMmsi;
          if (aIsUser) return -1;
          if (bIsUser) return 1;
          return 0;
        });
        
        // Spread vessels horizontally: center, left, right, further left, further right...
        const spreadDistance = compact ? 25 : 35; // pixels
        sortedGroup.forEach((vessel, idx) => {
          // ONLY match by MMSI
          const isUser = userMmsi && vessel.mmsi === userMmsi;
          if (isUser) {
            offsets[vessel.mmsi] = 0;
          } else {
            // Alternate left (-) and right (+), increasing distance
            const position = idx; // 0 is user or first vessel
            const side = position % 2 === 1 ? -1 : 1; // odd = left, even = right
            const distance = Math.ceil(position / 2) * spreadDistance;
            offsets[vessel.mmsi] = side * distance;
          }
        });
      }
    }
    
    return offsets;
  }, [vessels, minRM, maxRM, userMmsi, compact, isInView]);

  // Get direction icon
  const getDirectionIcon = (heading) => {
    if (heading === "northbound") return <ChevronUp className="w-3 h-3" />;
    if (heading === "southbound") return <ChevronDown className="w-3 h-3" />;
    return <Minus className="w-3 h-3" />;
  };

  // Touch gesture state for mobile drag-to-pan
  const touchStartY = useRef(null);
  const lastTouchY = useRef(null);
  const lastScrollTime = useRef(0);
  const scrollThrottleMs = 16; // ~60fps max

  // Throttled scroll offset update to prevent excessive re-renders
  const updateScrollOffset = useCallback((delta) => {
    const now = Date.now();
    if (now - lastScrollTime.current < scrollThrottleMs) return;
    lastScrollTime.current = now;
    
    setScrollOffset(prev => {
      const newOffset = prev + delta;
      const maxScroll = FULL_MAX_RM - selectedLockRM - zoomRange;
      const minScroll = FULL_MIN_RM - selectedLockRM + zoomRange;
      return Math.max(minScroll, Math.min(maxScroll, newOffset));
    });
  }, [selectedLockRM, zoomRange]);

  // Handle mouse wheel scroll on map (throttled)
  const handleWheel = useCallback((e) => {
    if (zoomRange >= 500) return;
    e.preventDefault();
    
    const scrollSpeed = Math.max(1, zoomRange / 20);
    const delta = e.deltaY > 0 ? -scrollSpeed : scrollSpeed;
    updateScrollOffset(delta);
  }, [zoomRange, updateScrollOffset]);

  // Handle touch start for mobile drag
  const handleTouchStart = useCallback((e) => {
    if (zoomRange >= 500) return;
    touchStartY.current = e.touches[0].clientY;
    lastTouchY.current = e.touches[0].clientY;
  }, [zoomRange]);

  // Handle touch move for mobile drag-to-pan (throttled)
  const handleTouchMove = useCallback((e) => {
    if (zoomRange >= 500 || touchStartY.current === null) return;
    e.preventDefault();
    
    const currentY = e.touches[0].clientY;
    const deltaY = lastTouchY.current - currentY;
    lastTouchY.current = currentY;
    
    const mapHeight = mapRef.current?.clientHeight || 500;
    const milesPerPixel = (zoomRange * 2) / mapHeight;
    const deltaMiles = -deltaY * milesPerPixel * 2;
    updateScrollOffset(deltaMiles);
  }, [zoomRange, updateScrollOffset]);

  // Handle touch end
  const handleTouchEnd = useCallback(() => {
    touchStartY.current = null;
    lastTouchY.current = null;
  }, []);

  // Add wheel and touch event listeners
  useEffect(() => {
    const mapElement = mapRef.current;
    if (mapElement) {
      mapElement.addEventListener('wheel', handleWheel, { passive: false });
      mapElement.addEventListener('touchstart', handleTouchStart, { passive: true });
      mapElement.addEventListener('touchmove', handleTouchMove, { passive: false });
      mapElement.addEventListener('touchend', handleTouchEnd, { passive: true });
      return () => {
        mapElement.removeEventListener('wheel', handleWheel);
        mapElement.removeEventListener('touchstart', handleTouchStart);
        mapElement.removeEventListener('touchmove', handleTouchMove);
        mapElement.removeEventListener('touchend', handleTouchEnd);
      };
    }
  }, [handleWheel, handleTouchStart, handleTouchMove, handleTouchEnd]);

  return (
    <div 
      ref={mapRef}
      className="river-map relative w-full h-full min-h-[400px] md:min-h-[500px] overflow-hidden cursor-ns-resize touch-none" 
      data-testid="river-visualization"
    >
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
            className="absolute left-1/2 transform -translate-x-1/2 z-10 cursor-pointer"
            style={{ 
              top: `${getRiverPosition(lock.river_mile)}%`,
              transform: 'translate(-50%, -50%)'
            }}
            data-testid={`lock-marker-${lock.id}`}
            onClick={() => onLockClick(lock.id)}
            title={`Click for ${lock.name} details`}
          >
            <div 
              className={`lock-indicator text-[8px] md:text-[10px] w-12 md:w-[60px] h-5 md:h-6 hover:scale-110 transition-transform`}
              style={lockStyle}
            >
              <Lock className="w-2 h-2 md:w-3 md:h-3 mr-0.5 md:mr-1" />
              <span>{lock.id.replace('lock_', 'L')}</span>
            </div>
          </div>
        );
      })}

      {/* Vessels - dots spread horizontally when close together */}
      {vessels.filter(v => isInView(v.river_mile)).map((vessel, index) => {
        // ONLY match by MMSI
        const isUser = userMmsi && vessel.mmsi === userMmsi;
        const isFocused = focusedVessel?.mmsi === vessel.mmsi;
        const topPosition = getRiverPosition(vessel.river_mile);
        const speedMph = (vessel.speed * 1.15078).toFixed(1);
        const horizontalOffset = vesselOffsets[vessel.mmsi] || 0;
        const isOffset = horizontalOffset !== 0;

        return (
          <div
            key={vessel.mmsi}
            className={`absolute z-20 transition-all duration-500 ease-out cursor-pointer hover:z-30 ${isFocused ? 'z-40' : ''}`}
            style={{ 
              top: `${topPosition}%`,
              left: `calc(50% + ${horizontalOffset}px)`,
              transform: 'translateY(-50%)'
            }}
            data-testid={`vessel-marker-${vessel.mmsi}`}
            onClick={() => setMapSelectedVessel(mapSelectedVessel?.mmsi === vessel.mmsi ? null : vessel)}
          >
            {/* Focus ring for highlighted vessel */}
            {isFocused && (
              <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 w-8 h-8 rounded-full border-2 border-yellow-400 animate-ping" />
            )}
            {/* Connector line to centerline when offset */}
            {isOffset && (
              <div 
                className="absolute top-1/2 h-px bg-slate-600/50"
                style={{
                  left: horizontalOffset > 0 ? 'auto' : '0',
                  right: horizontalOffset > 0 ? '0' : 'auto',
                  width: `${Math.abs(horizontalOffset)}px`,
                  transform: horizontalOffset > 0 ? 'translateX(-100%)' : 'translateX(0)'
                }}
              />
            )}
            {/* Vessel pip */}
            <div 
              className={`
                vessel-pip absolute
                ${isUser ? 'user w-3 h-3 md:w-4 md:h-4 user-vessel-pulse' : 'commercial w-2 h-2 md:w-3 md:h-3'}
                ${isFocused || mapSelectedVessel?.mmsi === vessel.mmsi ? 'ring-2 ring-yellow-400 ring-offset-2 ring-offset-slate-900' : ''}
                hover:scale-125 transition-transform
              `}
              style={{ 
                left: '0', 
                top: '50%', 
                transform: isUser ? 'translate(-50%, -50%)' : 'translate(-50%, -50%) rotate(45deg)'
              }}
            />

            {/* Vessel info label - position based on offset direction */}
            <div 
              className={`
                absolute px-1.5 py-1 rounded text-[10px] leading-tight flex items-center gap-1 whitespace-nowrap
                ${isUser ? 'bg-cyan-950/95 border border-cyan-500/50 text-cyan-400' : 'bg-slate-900/95 border border-amber-500/30 text-amber-400'}
              `}
              style={{ 
                left: horizontalOffset >= 0 ? (compact ? '15px' : '20px') : 'auto',
                right: horizontalOffset < 0 ? (compact ? '15px' : '20px') : 'auto',
                top: '50%', 
                transform: 'translateY(-50%)'
              }}
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
        <div className="absolute top-2 left-2 glass-panel px-3 py-2 rounded text-xs text-slate-400">
          <div className="font-mono font-semibold text-slate-300">RM {minRM.toFixed(0)} – {maxRM.toFixed(0)}</div>
          <div className="text-[10px] text-slate-500 mt-0.5 hidden md:block">Scroll to pan</div>
          <div className="text-[10px] text-slate-500 mt-0.5 md:hidden">Drag to pan</div>
        </div>
      )}

      {/* Scroll indicators on edges when not at boundary */}
      {zoomRange < 500 && maxRM < FULL_MAX_RM && (
        <div className="absolute top-8 left-1/2 -translate-x-1/2 text-slate-600 animate-pulse">
          <ChevronUp className="w-4 h-4" />
        </div>
      )}
      {zoomRange < 500 && minRM > FULL_MIN_RM && (
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 text-slate-600 animate-pulse">
          <ChevronDown className="w-4 h-4" />
        </div>
      )}

      {/* Out of view vessels indicator */}
      {vessels.length > 0 && vessels.filter(v => isInView(v.river_mile)).length < vessels.length && (
        <div className="absolute bottom-2 left-2 glass-panel px-2 py-1 rounded text-xs text-amber-400">
          {vessels.length - vessels.filter(v => isInView(v.river_mile)).length} vessel(s) outside view
        </div>
      )}

      {/* Vessel Info Overlay - appears when a vessel is selected on the map */}
      {mapSelectedVessel && (
        <VesselInfoPanel 
          vessel={mapSelectedVessel}
          userMmsi={userMmsi}
          showVesselNames={showVesselNames}
          onClose={() => setMapSelectedVessel(null)}
          onUserVesselEdit={onUserVesselEdit}
        />
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

// Memoize the component to prevent unnecessary re-renders
// Only re-render when vessels actually change position or when zoom/lock changes
export const RiverVisualization = memo(RiverVisualizationComponent, (prevProps, nextProps) => {
  // Custom comparison - only re-render if these actually changed
  if (prevProps.selectedLock !== nextProps.selectedLock) return false;
  if (prevProps.zoomRange !== nextProps.zoomRange) return false;
  if (prevProps.compact !== nextProps.compact) return false;
  if (prevProps.showVesselNames !== nextProps.showVesselNames) return false;
  if (prevProps.userMmsi !== nextProps.userMmsi) return false;
  
  // Check if focused vessel changed - important for centering from list clicks
  if (prevProps.focusedVessel?.mmsi !== nextProps.focusedVessel?.mmsi) return false;
  
  // Compare vessels array - only re-render if positions changed
  if (prevProps.vessels.length !== nextProps.vessels.length) return false;
  
  // Quick check on first vessel position to detect changes
  if (prevProps.vessels.length > 0 && nextProps.vessels.length > 0) {
    const prevFirst = prevProps.vessels[0];
    const nextFirst = nextProps.vessels[0];
    if (prevFirst.lat !== nextFirst.lat || prevFirst.lon !== nextFirst.lon) return false;
  }
  
  // Compare race analysis
  if (prevProps.raceAnalysis?.analysis?.threatening_vessel?.mmsi !== 
      nextProps.raceAnalysis?.analysis?.threatening_vessel?.mmsi) return false;
  
  return true; // Props are equal, don't re-render
});

export default RiverVisualization;
