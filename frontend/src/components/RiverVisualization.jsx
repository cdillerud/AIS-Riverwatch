import { useMemo, useState, useCallback, useRef, useEffect, memo } from "react";
import { MapPin, Lock, ChevronUp, ChevronDown, Minus, Anchor, X, Navigation, Gauge, Box, Timer, ExternalLink, ChevronRight, Radio, Compass, Ruler, Clock, History, Edit3, Hash } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { fmtRiverTime } from "@/lib/riverTime";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getVesselDisplayName, getVesselShortName, hasRiverMile, formatRiverMile, isUpbound, isDownbound, directionLabel, isVesselStale, lastSeenLabel, getLastSeenMs } from "@/utils/vesselDisplay";
import { API } from "@/lib/api";
import LockageRow from "@/components/LockageRow";
import { inLockInfo, queueEntryInLock } from "@/lib/inLock";

// Default River Mile range for Upper Mississippi (Lock 1 to Chain of Rocks)
const FULL_MIN_RM = 180;  // Chain of Rocks (RM 185) with buffer
const FULL_MAX_RM = 850;  // Lock 1 Minneapolis (RM 847.6) with buffer

// Ship type descriptions
const SHIP_TYPES = {
  0: "Not available", 20: "Wing in ground", 30: "Fishing", 31: "Towing", 32: "Towing (large)",
  33: "Dredging", 34: "Diving ops", 35: "Military ops", 36: "Sailing", 37: "Pleasure craft",
  40: "High speed craft", 50: "Pilot vessel", 51: "Search & rescue", 52: "Tug", 53: "Port tender",
  54: "Anti-pollution", 55: "Law enforcement", 60: "Passenger", 70: "Cargo", 80: "Tanker", 90: "Other",
};

const getShipTypeDescription = (code) => {
  if (!code) return "Unknown";
  if (SHIP_TYPES[code]) return SHIP_TYPES[code];
  const base = Math.floor(code / 10) * 10;
  return SHIP_TYPES[base] || `Type ${code}`;
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
  if (!parsed) return "AIS --";

  const ageSeconds = Math.max(0, Math.floor((nowMs - parsed.getTime()) / 1000));

  if (ageSeconds < 10) return "AIS now";
  if (ageSeconds < 60) return `AIS ${ageSeconds}s`;

  const ageMinutes = Math.floor(ageSeconds / 60);
  if (ageMinutes < 60) return `AIS ${ageMinutes}m`;

  const ageHours = Math.floor(ageMinutes / 60);
  if (ageHours < 24) return `AIS ${ageHours}h`;

  const ageDays = Math.floor(ageHours / 24);
  return `AIS ${ageDays}d`;
};

const formatLastCheckInLong = (vessel, nowMs) => {
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
  if (!parsed) return "text-slate-500";

  const ageSeconds = Math.max(0, Math.floor((nowMs - parsed.getTime()) / 1000));

  if (ageSeconds <= 120) return "text-emerald-400";
  if (ageSeconds <= 300) return "text-amber-400";
  return "text-red-400";
};

// Expandable Vessel Info Panel Component - Shows ALL data with one click
// Clean, organized layout matching the original modal design
const VesselInfoPanel = ({ vessel, userMmsi, showVesselNames, onClose, onUserVesselEdit, onVesselDetails }) => {
  const [lockageHistory, setLockageHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [nowTick, setNowTick] = useState(() => Date.now());
  
  const isUser = userMmsi && vessel.mmsi === userMmsi;
  const isTow = vessel.is_tow || vessel.barge_count > 0;
  const speedMph = Number.isFinite(Number(vessel.speed)) ? (Number(vessel.speed) * 1.15078).toFixed(1) : '--';
  const direction = vessel.direction || vessel.heading_direction || vessel.heading;
  const stale = isVesselStale(vessel, nowTick);
  const lastCheckInDisplay = stale ? lastSeenLabel(vessel, nowTick) : formatLastCheckInLong(vessel, nowTick);
  const lastCheckInClass = getCheckInTextClass(vessel, nowTick);

  useEffect(() => {
    const intervalId = window.setInterval(() => setNowTick(Date.now()), 30000);
    return () => window.clearInterval(intervalId);
  }, []);

  // Fetch lockage history on mount
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API}/vessels/history/${vessel.mmsi}`);
        if (response.ok) {
          const data = await response.json();
          setLockageHistory(data.lockage_history || []);
        }
      } catch (error) {
        console.error("Failed to fetch vessel data:", error);
      } finally {
        setLoading(false);
      }
    };
    if (vessel?.mmsi) fetchData();
  }, [vessel?.mmsi]);

  return (
    <div 
      className="absolute top-2 right-2 z-50 glass-panel border border-slate-600 rounded-lg shadow-xl w-[min(420px,calc(100%-1rem))]"
      data-testid="vessel-info-overlay"
    >
      {/* HEADER */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700 bg-slate-900/90">
        <div className="flex items-center gap-2">
          {isUser ? (
            <div className="w-3 h-3 rounded-full bg-cyan-400 animate-pulse" />
          ) : isTow ? (
            <Box className="w-4 h-4 text-amber-400" />
          ) : (
            <div className="w-2.5 h-2.5 bg-slate-400 rotate-45" />
          )}
          <span className={`font-semibold text-sm truncate max-w-[220px] ${isUser ? 'text-cyan-400' : 'text-white'}`}>
            {getVesselDisplayName(vessel, showVesselNames)}
          </span>
          {isTow && <Badge className="bg-amber-900/50 text-amber-400 text-[9px] px-1.5">TOW</Badge>}
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white p-1">
          <X className="w-4 h-4" />
        </button>
      </div>
      
      {/* ALL CONTENT - No scroll, compact layout */}
      <div className="p-3 space-y-3">
        
        {/* ROW 1: Identification + Position side by side */}
        <div className="grid grid-cols-2 gap-3">
          {/* IDENTIFICATION */}
          <div className="glass-panel p-2 rounded border border-slate-700">
            <h3 className="text-[10px] font-semibold text-slate-500 mb-1.5 flex items-center gap-1">
              <Hash className="w-3 h-3" /> IDENTIFICATION
            </h3>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500">MMSI</span>
                <span className="font-mono text-white">{vessel.mmsi}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Type</span>
                <span className="text-white truncate ml-2">{getShipTypeDescription(vessel.ship_type)}</span>
              </div>
            </div>
          </div>

          {/* POSITION */}
          <div className="glass-panel p-2 rounded border border-slate-700">
            <h3 className="text-[10px] font-semibold text-slate-500 mb-1.5 flex items-center gap-1">
              <MapPin className="w-3 h-3" /> {stale ? 'LAST KNOWN POSITION' : 'POSITION'}
            </h3>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500">River Mile</span>
                <span className="font-mono text-cyan-400 font-bold">{formatRiverMile(vessel.river_mile)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Coords</span>
                <span className="font-mono text-white text-[10px]">{vessel.lat?.toFixed(4)}°, {vessel.lon?.toFixed(4)}°</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-500 flex items-center gap-1">
                  <Clock className="w-3 h-3" /> AIS Check-In
                </span>
                <span className={`font-mono text-[10px] font-bold ${lastCheckInClass}`}>{lastCheckInDisplay}</span>
              </div>
            </div>
          </div>
        </div>

        {/* ROW 2: Navigation + Next Lock side by side */}
        <div className="grid grid-cols-2 gap-3">
          {/* NAVIGATION */}
          <div className="glass-panel p-2 rounded border border-slate-700">
            <h3 className="text-[10px] font-semibold text-slate-500 mb-1.5 flex items-center gap-1">
              <Compass className="w-3 h-3" /> NAVIGATION
            </h3>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between items-center">
                <span className="text-slate-500">Speed</span>
                <span className="font-mono text-white font-bold">{speedMph} <span className="text-slate-500 font-normal">mph</span></span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Course</span>
                <span className="font-mono text-white">{vessel.course?.toFixed(0)}°</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-500">Direction</span>
                <span className={`flex items-center gap-1 ${
                  isUpbound(direction) ? 'text-green-400' :
                  isDownbound(direction) ? 'text-red-400' : 'text-slate-400'
                }`}>
                  {isUpbound(direction) ? '↑' : isDownbound(direction) ? '↓' : '—'}
                  <span>{directionLabel(direction)}</span>
                </span>
              </div>
            </div>
          </div>

          {/* NEXT LOCK ETA */}
          <div className={`glass-panel p-2 rounded border ${vessel.next_lock ? 'border-cyan-500/30 bg-cyan-900/10' : 'border-slate-700'}`}>
            <h3 className="text-[10px] font-semibold text-cyan-400 mb-1.5 flex items-center gap-1">
              <Lock className="w-3 h-3" /> NEXT LOCK
            </h3>
            {vessel.next_lock ? (
              <div className="space-y-1 text-xs">
                <div className="text-white font-medium truncate">{vessel.next_lock.next_lock_name}</div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Distance</span>
                  <span className="text-white">{vessel.next_lock.distance_miles} mi</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">ETA</span>
                  <span className="font-mono text-cyan-400 font-bold">{vessel.next_lock.eta_display}</span>
                </div>
              </div>
            ) : (
              <div className="text-slate-500 text-xs italic">No lock ahead</div>
            )}
          </div>
        </div>

        {/* ROW 3: Tow Info + USACE Data side by side (conditional) */}
        {(isTow || vessel.usace_source || vessel.usace_status) && (
          <div className="grid grid-cols-2 gap-3">
            {/* TOW INFO */}
            {isTow ? (
              <div className="glass-panel p-2 rounded border border-amber-500/30 bg-amber-900/10">
                <h3 className="text-[10px] font-semibold text-amber-400 mb-1.5 flex items-center gap-1">
                  <Box className="w-3 h-3" /> TOW INFO
                </h3>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Barges</span>
                    <span className="font-mono text-amber-400 font-bold">{vessel.barge_count || '?'}</span>
                  </div>
                  {vessel.tow_config && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Config</span>
                      <span className="text-white">{vessel.tow_config}</span>
                    </div>
                  )}
                  {vessel.estimated_lockage_time && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Lock Time</span>
                      <span className="text-white">~{vessel.estimated_lockage_time}min</span>
                    </div>
                  )}
                  {vessel.is_double_lockage && (
                    <Badge className="bg-red-900/30 text-red-400 border-red-500/30 text-[9px] mt-1">DOUBLE LOCK</Badge>
                  )}
                </div>
              </div>
            ) : <div />}

            {/* USACE DATA */}
            {(vessel.usace_source || vessel.usace_status) ? (
              <div className="glass-panel p-2 rounded border border-green-500/30 bg-green-900/10">
                <h3 className="text-[10px] font-semibold text-green-400 mb-1.5 flex items-center gap-1">
                  <Radio className="w-3 h-3" /> USACE DATA
                </h3>
                <div className="space-y-1 text-xs">
                  {vessel.usace_source && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Source</span>
                      <span className="text-white truncate ml-2">{vessel.usace_source}</span>
                    </div>
                  )}
                  {vessel.usace_status && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Status</span>
                      <span className="text-white capitalize">{vessel.usace_status}</span>
                    </div>
                  )}
                  {vessel.usace_lock && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">At Lock</span>
                      <span className="text-white">{vessel.usace_lock}</span>
                    </div>
                  )}
                </div>
              </div>
            ) : <div />}
          </div>
        )}

        {/* ROW 4: Lockage History (full width) */}
        <div className="glass-panel p-2 rounded border border-slate-700">
          <h3 className="text-[10px] font-semibold text-slate-500 mb-1.5 flex items-center gap-1">
            <History className="w-3 h-3" /> LOCKAGE HISTORY
            {loading && <span className="text-slate-600">(loading...)</span>}
          </h3>
          {lockageHistory.length > 0 ? (
            <div className="space-y-1">
              {lockageHistory.slice(0, 4).map((l, i) => (
                <LockageRow key={i} lockage={l} />
              ))}
            </div>
          ) : !loading ? (
            <p className="text-slate-500 text-xs italic" data-testid="no-recorded-lockages">No recorded lockages yet.</p>
          ) : null}
        </div>

        {/* ACTION BUTTONS */}
        <div className="flex gap-2">
          {isUser && (
            <Button size="sm" className="flex-1 bg-cyan-600 hover:bg-cyan-500 text-white h-7 text-xs"
              onClick={() => { onUserVesselEdit(vessel); onClose(); }}>
              <MapPin className="w-3 h-3 mr-1" /> Edit Position
            </Button>
          )}
          <Button size="sm" variant="outline" className="flex-1 border-slate-600 text-slate-300 h-7 text-xs"
            onClick={() => { onVesselDetails(vessel); onClose(); }}>
            <Edit3 className="w-3 h-3 mr-1" /> Edit Name
          </Button>
        </div>
      </div>
    </div>
  );
};

const RiverVisualizationComponent = ({ 
  vessels, 
  userMmsi, 
  locks, 
  selectedLock,
  raceAnalysis,
  maxSpeedMph = 25, // user's configured max speed (Settings)
  compact = false,
  zoomRange = 20, // Range in miles (10-500, 500+ = full view)
  onVesselClick = () => {},
  onVesselDetails = () => {}, // Callback to open full vessel detail modal
  onLockClick = () => {}, // Callback when lock is clicked for details
  onUserVesselEdit = () => {}, // Callback when user's vessel is clicked for editing
  showVesselNames = true,
  focusedVessel = null,
  onFocusClear = () => {},
  // USACE lock queues {lock_id: [{vessel_name, mmsi, direction, barges, ...}]}:
  // boats known to be at a lock even when no AIS position is available.
  lockQueues = {}
}) => {
  // Scroll offset in river miles (positive = shifted north/up)
  const [scrollOffset, setScrollOffset] = useState(0);
  const mapRef = useRef(null);
  // Selected vessel for info overlay on map
  const [mapSelectedVessel, setMapSelectedVessel] = useState(null);
  const [mapNowTick, setMapNowTick] = useState(() => Date.now());
  
  useEffect(() => {
    const intervalId = window.setInterval(() => setMapNowTick(Date.now()), 30000);
    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    if (!mapSelectedVessel?.mmsi) return;
    const updatedSelectedVessel = vessels.find(v => v.mmsi === mapSelectedVessel.mmsi);
    if (updatedSelectedVessel) {
      setMapSelectedVessel(updatedSelectedVessel);
    }
  }, [vessels, mapSelectedVessel?.mmsi]);
  
  // Get the selected lock's river mile for zoom center
  const selectedLockRM = useMemo(() => {
    const lock = locks.find(l => l.id === selectedLock);
    return lock?.river_mile || 815;
  }, [locks, selectedLock]);

  // When a focused vessel is set, calculate offset to center on it and show info
  useEffect(() => {
    if (focusedVessel && hasRiverMile(focusedVessel)) {
      const vesselRM = Number(focusedVessel.river_mile);
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
  // Map height in px, for laying out vessel labels without overlap
  const [mapHeightPx, setMapHeightPx] = useState(500);
  useEffect(() => {
    const el = mapRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => setMapHeightPx(el.clientHeight || 500));
    ro.observe(el);
    setMapHeightPx(el.clientHeight || 500);
    return () => ro.disconnect();
  }, []);
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

  // Find user vessel - ONLY match by MMSI
  const userVessel = useMemo(() => {
    if (!userMmsi) return null;
    return vessels.find(v => v.mmsi === userMmsi);
  }, [vessels, userMmsi]);

  // Check if user vessel is outside visible range
  const userOutOfRange = useMemo(() => {
    if (!hasRiverMile(userVessel)) return null;
    const rm = Number(userVessel.river_mile);
    if (rm > maxRM) return 'north';
    if (rm < minRM) return 'south';
    return null;
  }, [userVessel, minRM, maxRM]);

  // While the "your boat is off-screen" badge shows, the strip is laid out in
  // the space beside it, so the badge never sits on top of a lock or boat.
  const BADGE_BAND_PX = 64;
  const bandPct = (BADGE_BAND_PX / (mapHeightPx || 500)) * 100;
  const topPct = userOutOfRange === 'north' ? bandPct : 2;
  const bottomPct = userOutOfRange === 'south' ? 100 - bandPct : 98;

  // Calculate position percentage for a river mile
  // Memoized: a new function every render re-ran the label layout below on
  // every render of the map (incl. the 30 s clock tick).
  const getRiverPosition = useCallback((riverMile) => {
    if (riverMile == null || !Number.isFinite(Number(riverMile))) return 50;
    // Fraction of the way from the north (top) edge; higher RM is north.
    const f = Math.max(0, Math.min(1, (maxRM - riverMile) / (maxRM - minRM)));
    return topPct + f * (bottomPct - topPct);
  }, [minRM, maxRM, topPct, bottomPct]);

  // Check if a river mile is in view
  const isInView = useCallback((riverMile) => {
    // Null river_mile (off-river / unknown) is never drawn on the strip.
    if (riverMile == null || !Number.isFinite(Number(riverMile))) return false;
    return riverMile >= minRM && riverMile <= maxRM;
  }, [minRM, maxRM]);

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
      if (!hasRiverMile(vessel)) continue;
      
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

  // Vertical label shifts (px) so labels on the same side of the river line
  // don't overlap: boats 1-3 mi apart weren't close enough to be spread
  // sideways, but each label is ~3 mi tall at the default zoom, so they
  // stacked on top of each other. Sweep top-to-bottom per side and push each
  // label below the previous one; a leader line joins a moved label to its boat.
  const labelShifts = useMemo(() => {
    const shifts = {};
    const H = mapHeightPx || 500;
    const LH = compact ? 34 : 48;   // label height incl. spacing
    // Each label goes to whichever side of the river line keeps it closest to
    // its boat (a dense reach fills both columns instead of one long one).
    const sides = { left: [], right: [] };
    const last = { left: -Infinity, right: -Infinity };
    const items = vessels
      .filter(v => hasRiverMile(v) && isInView(v.river_mile))
      .map(v => ({ id: v.mmsi, y: (getRiverPosition(v.river_mile) / 100) * H,
                   pref: (vesselOffsets[v.mmsi] || 0) < 0 ? "left" : "right" }))
      .sort((a, b) => a.y - b.y);
    for (const it of items) {
      const other = it.pref === "left" ? "right" : "left";
      const dPref = Math.max(it.y, last[it.pref] + LH) - it.y;
      const dOther = Math.max(it.y, last[other] + LH) - it.y;
      const side = dOther + LH / 4 < dPref ? other : it.pref;
      last[side] = Math.max(it.y, last[side] + LH);
      sides[side].push(it);
    }
    for (const list of Object.values(sides)) {
      list.sort((a, b) => a.y - b.y);
      // Forward pass pushes labels down; then each run of touching labels is
      // re-centred on its boats so a cluster spreads both up and down.
      const pos = list.map(l => l.y);
      for (let i = 1; i < pos.length; i++) pos[i] = Math.max(pos[i], pos[i - 1] + LH);
      let start = 0;
      for (let i = 1; i <= pos.length; i++) {
        if (i === pos.length || pos[i] > pos[i - 1] + LH + 0.5) {
          const run = list.slice(start, i);
          const drift = run.reduce((acc, l, k) => acc + (pos[start + k] - l.y), 0) / run.length;
          const lo = LH / 2 - pos[start];                 // keep inside the map
          const hi = H - LH / 2 - pos[i - 1];
          const shift = Math.min(Math.max(-drift, lo), Math.max(hi, lo));
          for (let k = start; k < i; k++) pos[k] += shift;
          start = i;
        }
      }
      list.forEach((l, k) => { shifts[l.id] = { dy: Math.round(pos[k] - l.y), side: list === sides.left ? "left" : "right" }; });
    }
    return shifts;
  }, [vessels, vesselOffsets, isInView, getRiverPosition, mapHeightPx, compact]);


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
                  RM {formatRiverMile(userVessel.river_mile)} • {(Number(userVessel.river_mile) - maxRM).toFixed(1)} mi upriver
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
                  RM {formatRiverMile(userVessel.river_mile)} • {(minRM - Number(userVessel.river_mile)).toFixed(1)} mi downriver
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
          if (analysis.required_speed_mph > maxSpeedMph) {
            // Required speed exceeds the user's max - red
            lockStyle = { borderColor: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.2)', boxShadow: '0 0 12px rgba(239, 68, 68, 0.5)' };
          } else if (analysis.threatening_vessel && Number.isFinite(analysis.required_speed_mph) && analysis.required_speed_mph <= maxSpeedMph) {
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
        // A boat in the chamber now (live AIS boat or USACE queue entry).
        const occupied = vessels.some(v => v.in_lock && v.in_lock_id === lock.id)
          || (lockQueues[lock.id] || []).some(queueEntryInLock);

        return (
          <div
            key={lock.id}
            className="absolute left-1/2 transform -translate-x-1/2 z-10 cursor-pointer"
            style={{ 
              top: `${getRiverPosition(lock.river_mile)}%`,
              transform: 'translate(-50%, -50%)'
            }}
            data-testid={`lock-marker-${lock.id}`}
            data-occupied={occupied ? 'true' : undefined}
            onClick={() => onLockClick(lock.id)}
            title={occupied ? `${lock.name}: a vessel is in the lock - click for details` : `Click for ${lock.name} details`}
          >
            <div
              className={`lock-indicator text-[8px] md:text-[10px] w-12 md:w-[60px] h-5 md:h-6 hover:scale-110 transition-transform ${occupied ? 'ring-2 ring-cyan-300/80' : ''}`}
              style={lockStyle}
            >
              <Lock className="w-2 h-2 md:w-3 md:h-3 mr-0.5 md:mr-1" />
              <span>{lock.id.replace('lock_', 'L')}</span>
            </div>
          </div>
        );
      })}

      {/* USACE queue at each lock: drawn beside the lock, dashed, so they read
          as "reported at this lock" rather than a live AIS position. Boats that
          also have a live AIS position are left to their live marker. */}
      {visibleLocks.map(lock => {
        // Match by MMSI, or by name for a boat near this lock: USACE sometimes
        // has an old MMSI (MARGIT B: 368371860 in USACE, 366975420 on AIS).
        const norm = (x) => String(x || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
        const liveMmsis = new Set(vessels.map(v => String(v.mmsi)));
        const liveNamesHere = new Set(vessels
          .filter(v => v.river_mile != null && Math.abs(Number(v.river_mile) - lock.river_mile) <= 3)
          .map(v => norm(v.name)).filter(Boolean));
        const entries = (lockQueues[lock.id] || []).filter(e =>
          !(e.mmsi && liveMmsis.has(String(e.mmsi))) && !liveNamesHere.has(norm(e.vessel_name)));
        if (!entries.length) return null;
        const shown = entries.slice(0, compact ? 2 : 3);
        return (
          <div
            key={`queue-${lock.id}`}
            className="absolute z-20 flex flex-col items-end gap-0.5 cursor-pointer"
            style={{ top: `${getRiverPosition(lock.river_mile)}%`, right: 'calc(50% + 40px)', maxWidth: 'calc(50% - 44px)', transform: 'translateY(-50%)' }}
            onClick={() => onLockClick(lock.id)}
            title={`Reported by USACE at ${lock.name} - click a boat for its details`}
            data-testid={`lock-queue-${lock.id}`}
          >
            {shown.map((e, i) => {
              const up = e.direction === 'upbound';
              const inChamber = queueEntryInLock(e);
              return (
                <div key={i} className={`border rounded px-1.5 py-0.5 text-[9px] md:text-[10px] max-w-full truncate hover:bg-slate-900 ${inChamber
                       ? 'border-solid border-cyan-400/80 bg-cyan-950/90 hover:border-cyan-200'
                       : 'border-dashed border-amber-500/60 bg-slate-950/90 hover:border-amber-300'}`}
                     data-in-lock={inChamber ? 'true' : undefined}
                     onClick={(ev) => { ev.stopPropagation(); onVesselDetails(e, lock.name); }}
                     title={`${e.vessel_name || 'Vessel'} - click for vessel details`}
                     data-testid="lock-queue-vessel">
                  {inChamber
                    ? <Lock className="inline w-2.5 h-2.5 mr-1 -mt-0.5 text-cyan-300" />
                    : <span className="text-slate-500 mr-1">USACE</span>}
                  <span className="text-slate-100">{e.vessel_name || 'Unknown'}</span>
                  <span className={`ml-1 ${up ? 'text-green-400' : 'text-red-400'}`}>{up ? '↑' : '↓'}</span>
                  {!compact && <span className="text-slate-400">{e.barges ? ` ${e.barges}b` : ' light'}</span>}
                  <span className={e.started_at ? 'text-cyan-300 font-semibold' : 'text-slate-400'}>
                    {e.started_at
                      ? ` · in lock${e.cuts_completed ? `, cut ${e.cuts_completed + 1}` : ''}`
                      : (e.waiting_minutes != null ? ` · at lock ${e.waiting_minutes >= 60 ? `${Math.floor(e.waiting_minutes / 60)}h${e.waiting_minutes % 60 ? ` ${e.waiting_minutes % 60}m` : ''}` : `${e.waiting_minutes}m`}` : '')}
                  </span>
                </div>
              );
            })}
            {entries.length > shown.length && (
              <div className="text-[9px] text-slate-500">+{entries.length - shown.length} more at lock</div>
            )}
          </div>
        );
      })}

      {/* Vessels - dots spread horizontally when close together */}
      {vessels.filter(v => isInView(v.river_mile)).map((vessel, index) => {
        // ONLY match by MMSI
        const isUser = userMmsi && vessel.mmsi === userMmsi;
        const isFocused = focusedVessel?.mmsi === vessel.mmsi;
        const topPosition = getRiverPosition(vessel.river_mile);
        const speedMph = Number.isFinite(Number(vessel.speed)) ? (Number(vessel.speed) * 1.15078).toFixed(1) : '--';
        const stale = isVesselStale(vessel, mapNowTick);
        const lastCheckInDisplay = stale ? lastSeenLabel(vessel, mapNowTick) : formatLastCheckIn(vessel, mapNowTick);
        const lastCheckInClass = getCheckInTextClass(vessel, mapNowTick);
        const horizontalOffset = vesselOffsets[vessel.mmsi] || 0;
        const isOffset = horizontalOffset !== 0;
        const labelShift = labelShifts[vessel.mmsi]?.dy || 0;
        const labelLeft = (labelShifts[vessel.mmsi]?.side || (horizontalOffset < 0 ? "left" : "right")) === "left";
        const labelGap = compact ? 15 : 20;
        const inLock = inLockInfo(vessel, mapNowTick);

        return (
          <div
            key={vessel.mmsi}
            className={`absolute z-20 transition-all duration-500 ease-out cursor-pointer hover:z-30 ${isFocused ? 'z-40' : ''} ${stale ? 'opacity-40' : ''}`}
            title={stale ? `Stale position — ${lastSeenLabel(vessel, mapNowTick)}` : undefined}
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
            {/* Vessel pip - a lock chamber with the boat in it while it's locking */}
            {inLock ? (
              <div
                className={`
                  absolute flex items-center justify-center rounded-[3px] border-2 border-cyan-300 bg-cyan-500/35
                  shadow-[0_0_10px_rgba(34,211,238,0.65)] w-6 h-4 md:w-7 md:h-[18px]
                  ${isFocused || mapSelectedVessel?.mmsi === vessel.mmsi ? 'ring-2 ring-yellow-400 ring-offset-2 ring-offset-slate-900' : ''}
                  hover:scale-125 transition-transform
                `}
                style={{ left: '0', top: '50%', transform: 'translate(-50%, -50%)' }}
                data-testid="in-lock-marker"
                title={inLock.label}
              >
                <div className={`${isUser ? 'w-2 h-2 rounded-full bg-cyan-200' : 'w-1.5 h-1.5 md:w-2 md:h-2 bg-amber-300 rotate-45'}`} />
              </div>
            ) : (
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
            )}

            {/* Leader line when the label was moved to avoid overlapping another */}
            {Math.abs(labelShift) > 6 && (
              <svg className="absolute pointer-events-none overflow-visible" style={{ left: 0, top: '50%', width: 1, height: 1 }}>
                <line x1="0" y1="0" x2={labelLeft ? -labelGap : labelGap} y2={labelShift}
                      stroke={isUser ? 'rgba(34,211,238,0.5)' : 'rgba(245,158,11,0.45)'} strokeWidth="1" />
              </svg>
            )}
            {/* Vessel info label - position based on offset direction */}
            <div 
              className={`
                absolute px-1.5 py-1 rounded text-[10px] leading-tight flex items-center gap-1 whitespace-nowrap
                ${isUser ? 'bg-cyan-950/95 border border-cyan-500/50 text-cyan-400'
                  : inLock ? 'bg-slate-900/95 border border-cyan-400/70 text-amber-400'
                  : 'bg-slate-900/95 border border-amber-500/30 text-amber-400'}
              `}
              style={{ 
                left: labelLeft ? 'auto' : `${labelGap}px`,
                right: labelLeft ? `${labelGap}px` : 'auto',
                top: `calc(50% + ${labelShift}px)`, 
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
                {inLock && (
                  <div className="text-cyan-300 font-semibold text-[9px] flex items-center gap-0.5" data-testid="in-lock-label">
                    <Lock className="w-2.5 h-2.5" />
                    {inLock.label}
                  </div>
                )}
                <div className="text-slate-400 font-mono text-[9px]">
                  {speedMph} mph {!compact && `• RM ${formatRiverMile(vessel.river_mile)}`}
                </div>
                <div className={`font-mono text-[9px] font-semibold flex items-center gap-0.5 ${lastCheckInClass}`}>
                  <Clock className="w-2.5 h-2.5" />
                  {lastCheckInDisplay}
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {/* Arrival path indicator - shows path from user to lock */}
      {hasRiverMile(raceAnalysis?.user_vessel) && raceAnalysis?.target_lock_rm && (
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
            <div className="flex items-center gap-2">
              <div className="w-4 h-2.5 md:w-5 md:h-3 rounded-[2px] border-2 border-cyan-300 bg-cyan-500/35 flex items-center justify-center">
                <div className="w-1 h-1 bg-amber-300 rotate-45" />
              </div>
              <span className="text-[10px] md:text-xs text-slate-300">In the lock</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-2 md:w-4 md:h-2.5 border border-dashed border-amber-500/70 rounded-sm" />
              <span className="text-[10px] md:text-xs text-slate-300">At lock (USACE)</span>
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

      {/* Out of view vessels indicator. Phones have no legend, so it goes
          bottom-right there: bottom-left is where the lowest lock's USACE tags sit. */}
      {vessels.length > 0 && vessels.filter(v => isInView(v.river_mile)).length < vessels.length && (
        <div className={`absolute bottom-2 ${compact ? 'right-2' : 'left-2'} glass-panel px-2 py-1 rounded text-xs text-amber-400`}>
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
          onVesselDetails={onVesselDetails}
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
  if (prevProps.locks !== nextProps.locks) return false;
  if (prevProps.maxSpeedMph !== nextProps.maxSpeedMph) return false;
  if (prevProps.lockQueues !== nextProps.lockQueues) return false;   // USACE queue refresh
  
  // Check if focused vessel changed - important for centering from list clicks
  if (prevProps.focusedVessel?.mmsi !== nextProps.focusedVessel?.mmsi) return false;
  
  // Compare vessels array. Re-render if position, speed, heading, or AIS check-in freshness changes.
  if (prevProps.vessels.length !== nextProps.vessels.length) return false;

  for (let i = 0; i < prevProps.vessels.length; i += 1) {
    const prevVessel = prevProps.vessels[i];
    const nextVessel = nextProps.vessels[i];

    if (prevVessel?.mmsi !== nextVessel?.mmsi) return false;
    if (prevVessel?.lat !== nextVessel?.lat) return false;
    if (prevVessel?.lon !== nextVessel?.lon) return false;
    if (prevVessel?.river_mile !== nextVessel?.river_mile) return false;
    if (prevVessel?.speed !== nextVessel?.speed) return false;
    if (prevVessel?.course !== nextVessel?.course) return false;
    if (prevVessel?.heading !== nextVessel?.heading) return false;
    if (getLastCheckInValue(prevVessel) !== getLastCheckInValue(nextVessel)) return false;
  }
  
  // Compare race analysis
  if (prevProps.raceAnalysis?.analysis?.threatening_vessel?.mmsi !== 
      nextProps.raceAnalysis?.analysis?.threatening_vessel?.mmsi) return false;
  if (prevProps.raceAnalysis?.analysis?.required_speed_mph !==
      nextProps.raceAnalysis?.analysis?.required_speed_mph) return false;
  
  return true; // Props are equal, don't re-render
});

export default RiverVisualization;
