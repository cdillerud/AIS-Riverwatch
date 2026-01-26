import { useState, useMemo, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { 
  Anchor, Ship, Gauge, Clock, MapPin, AlertTriangle, 
  Wifi, WifiOff, ChevronDown, Navigation, Lock, Settings,
  Zap, Target, Menu, X, ChevronUp, ZoomIn, ZoomOut, Terminal,
  Edit3, Check, RefreshCw, RotateCcw, Compass, Route, Timer, Users, History, Info,
  LogOut, Radio, User
} from "lucide-react";
import { toast } from "sonner";
import RiverVisualization from "@/components/RiverVisualization";
import RaceAnalysisPanel from "@/components/RaceAnalysisPanel";
import VesselList from "@/components/VesselList";
import ConnectionStatus from "@/components/ConnectionStatus";
import LockStatusPanel from "@/components/LockStatusPanel";
import VesselDetailModal from "@/components/VesselDetailModal";
import LockDetailModal from "@/components/LockDetailModal";
import RawDataPanel from "@/components/RawDataPanel";
import Speedometer from "@/components/Speedometer";
import { getVesselDisplayName } from "@/utils/vesselDisplay";
import { useAuth } from "@/context/AuthContext";

const API = process.env.REACT_APP_BACKEND_URL + '/api';

export default function Dashboard({ 
  isConnected, 
  vessels, 
  userMmsi, 
  locks, 
  lockStatus,
  lockageTimes = {},
  raceAnalysis,
  selectedLock,
  onSelectLock,
  onDisconnect,
  onResetConnection,
  onReconnect,
  onOpenSettings,
  connectionConfig,
  userSettings = {},
  onRefresh,
  onFullRefresh,
  lastRefresh
}) {
  const { user, logout } = useAuth();
  const [mobilePanel, setMobilePanel] = useState("race"); // "race" | "vessels" | "map" | "locks" | "debug"
  const [desktopPanel, setDesktopPanel] = useState("timing"); // "map" | "timing" | "vessels" | "locks" | "debug"
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(20); // Zoom range in miles (10-500)
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Handle logout
  const handleLogout = async () => {
    try {
      await logout();
      // The AuthProvider will clear user state and ProtectedRoute will redirect to login
    } catch (error) {
      toast.error("Failed to logout");
    }
  };

  // Handle manual refresh with visual feedback
  const handleRefresh = async () => {
    setIsRefreshing(true);
    toast.info("Refreshing data...");
    
    if (onRefresh) {
      await onRefresh();
    }
    
    setTimeout(() => {
      setIsRefreshing(false);
      toast.success("Data refreshed");
    }, 1000);
  };

  // Handle full page refresh
  const handleFullRefresh = () => {
    toast.info("Performing full refresh...");
    if (onFullRefresh) {
      onFullRefresh();
    }
  };

  // Format time since last refresh
  const getTimeSinceRefresh = () => {
    if (!lastRefresh) return "";
    const seconds = Math.floor((Date.now() - lastRefresh) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  };
  const [selectedVessel, setSelectedVessel] = useState(null); // For vessel detail modal
  const [selectedLockDetail, setSelectedLockDetail] = useState(null); // For lock detail modal
  
  // Quick position editor state
  const [showPositionEditor, setShowPositionEditor] = useState(false);
  const [editRM, setEditRM] = useState("");
  const [editSpeed, setEditSpeed] = useState("");
  const [editCourse, setEditCourse] = useState("");
  
  // Auto next lock tracking
  const [autoNextLock, setAutoNextLock] = useState(false);
  
  // Alert dismissal - tracks which threat was dismissed
  const [dismissedThreatMmsi, setDismissedThreatMmsi] = useState(null);

  // Find user vessel - ONLY match by MMSI, not is_user_vessel flag
  // (is_user_vessel from server can be stale/wrong if multiple sessions exist)
  const userVessel = useMemo(() => {
    if (!userMmsi) return null;
    return vessels.find(v => v.mmsi === userMmsi);
  }, [vessels, userMmsi]);

  // Calculate next lock based on vessel position and heading
  const nextLock = useMemo(() => {
    if (!userVessel || !userVessel.river_mile || !locks.length) return null;
    
    const userRM = userVessel.river_mile;
    const heading = userVessel.heading;
    
    // Sort locks by river mile
    const sortedLocks = [...locks].sort((a, b) => a.river_mile - b.river_mile);
    
    if (heading === 'southbound') {
      // Going downriver (decreasing RM) - find nearest lock with RM < user's RM
      for (let i = sortedLocks.length - 1; i >= 0; i--) {
        if (sortedLocks[i].river_mile < userRM) {
          return sortedLocks[i];
        }
      }
    } else if (heading === 'northbound') {
      // Going upriver (increasing RM) - find nearest lock with RM > user's RM
      for (let i = 0; i < sortedLocks.length; i++) {
        if (sortedLocks[i].river_mile > userRM) {
          return sortedLocks[i];
        }
      }
    }
    
    // If no lock found in heading direction, return closest lock
    let closest = sortedLocks[0];
    let minDist = Math.abs(sortedLocks[0].river_mile - userRM);
    for (const lock of sortedLocks) {
      const dist = Math.abs(lock.river_mile - userRM);
      if (dist < minDist) {
        minDist = dist;
        closest = lock;
      }
    }
    return closest;
  }, [userVessel, locks]);

  // Auto-update selected lock when autoNextLock is enabled
  useEffect(() => {
    if (autoNextLock && nextLock && nextLock.id !== selectedLock) {
      onSelectLock(nextLock.id);
    }
  }, [autoNextLock, nextLock, selectedLock, onSelectLock]);

  // Commercial vessels (non-user) - ONLY exclude by MMSI match
  const commercialVessels = useMemo(() => {
    if (!userMmsi) return vessels;
    return vessels.filter(v => v.mmsi !== userMmsi);
  }, [vessels, userMmsi]);

  // Check if speed requirement is dangerous
  const isDangerous = raceAnalysis?.analysis?.required_speed_mph && 
                      raceAnalysis.analysis.required_speed_mph > 25;
  
  // Track current threatening vessel to reset alert when it changes
  const currentThreatMmsi = raceAnalysis?.analysis?.threatening_vessel?.mmsi;

  // Get the selected lock object for the modal
  const selectedLockObj = useMemo(() => {
    return locks.find(l => l.id === selectedLock);
  }, [locks, selectedLock]);

  // Calculate distance to selected lock and travel time
  const lockTravelInfo = useMemo(() => {
    if (!userVessel?.river_mile || !selectedLockObj?.river_mile) {
      return { distance: null, travelMinutes: null, estimatedWait: null };
    }
    
    const distance = Math.abs(userVessel.river_mile - selectedLockObj.river_mile);
    const speedMph = userVessel.speed * 1.15078; // knots to mph
    const travelMinutes = speedMph > 0 ? (distance / speedMph) * 60 : null;
    
    // Estimate wait time based on lockage times data
    const avgLockageTime = lockageTimes?.[selectedLock]?.avg_minutes || 20; // default 20 min
    
    return {
      distance: distance.toFixed(1),
      travelMinutes: travelMinutes?.toFixed(0),
      estimatedWait: avgLockageTime,
      totalMinutes: travelMinutes ? (parseFloat(travelMinutes) + avgLockageTime).toFixed(0) : null
    };
  }, [userVessel, selectedLockObj, selectedLock, lockageTimes]);

  // Get vessels near the target lock (within 5 RM, heading towards it)
  const lockQueue = useMemo(() => {
    if (!selectedLockObj?.river_mile) return [];
    
    const lockRM = selectedLockObj.river_mile;
    const queueRange = 10; // vessels within 10 miles of lock
    
    return vessels
      .filter(v => {
        // ONLY exclude by MMSI match, not is_user_vessel flag
        if (userMmsi && v.mmsi === userMmsi) return false;
        if (!v.river_mile) return false;
        
        const distToLock = Math.abs(v.river_mile - lockRM);
        if (distToLock > queueRange) return false;
        
        // Check if heading towards lock
        if (v.river_mile > lockRM && v.heading === 'southbound') return true;
        if (v.river_mile < lockRM && v.heading === 'northbound') return true;
        // Include stationary vessels very close to lock
        if (distToLock < 2) return true;
        
        return false;
      })
      .sort((a, b) => {
        // Sort by distance to lock
        const distA = Math.abs(a.river_mile - lockRM);
        const distB = Math.abs(b.river_mile - lockRM);
        return distA - distB;
      })
      .slice(0, 5); // Max 5 vessels in queue view
  }, [vessels, selectedLockObj, userMmsi]);

  // Get last lockage info from lockageTimes
  const lastLockage = useMemo(() => {
    const lockData = lockageTimes?.[selectedLock];
    if (!lockData?.last_lockage) return null;
    
    return {
      vesselName: lockData.last_lockage.vessel_name || 'Unknown',
      bargeCount: lockData.last_lockage.barge_count || 0,
      minutesAgo: lockData.last_lockage.minutes_ago || null,
      direction: lockData.last_lockage.direction || null
    };
  }, [lockageTimes, selectedLock]);

  // Focused vessel - when set, map will center on this vessel
  const [focusedVessel, setFocusedVessel] = useState(null);

  // Find the nearest lock to a given vessel based on its heading
  const findNearestLock = (vessel) => {
    if (!vessel?.river_mile || !locks.length) return null;
    
    const vesselRM = vessel.river_mile;
    const heading = vessel.heading;
    const sortedLocks = [...locks].sort((a, b) => a.river_mile - b.river_mile);
    
    // If vessel has a heading, find the next lock in that direction
    if (heading === 'southbound') {
      for (let i = sortedLocks.length - 1; i >= 0; i--) {
        if (sortedLocks[i].river_mile < vesselRM) {
          return sortedLocks[i];
        }
      }
    } else if (heading === 'northbound') {
      for (let i = 0; i < sortedLocks.length; i++) {
        if (sortedLocks[i].river_mile > vesselRM) {
          return sortedLocks[i];
        }
      }
    }
    
    // Fallback: find the closest lock regardless of direction
    let closest = sortedLocks[0];
    let minDist = Math.abs(sortedLocks[0].river_mile - vesselRM);
    for (const lock of sortedLocks) {
      const dist = Math.abs(lock.river_mile - vesselRM);
      if (dist < minDist) {
        minDist = dist;
        closest = lock;
      }
    }
    return closest;
  };

  // Handle vessel click from map (no longer used - map handles its own overlay)
  const handleVesselClick = (vessel) => {
    // Map now handles its own info overlay, but we keep this for backwards compatibility
  };

  // Handle vessel click specifically from list (switches to map and centers)
  const handleVesselClickFromList = (vessel) => {
    // First switch to map tab
    setDesktopPanel("map");
    setMobilePanel("map");
    
    // Auto-select the nearest lock to this vessel
    const nearestLock = findNearestLock(vessel);
    if (nearestLock) {
      setAutoNextLock(false); // Disable auto-tracking since we're manually selecting
      onSelectLock(nearestLock.id);
    }
    
    // Then set focused vessel after a brief delay to ensure map component is mounted
    setTimeout(() => {
      setFocusedVessel(vessel);
    }, 100);
  };

  // Open position editor with current values
  const openPositionEditor = () => {
    if (userVessel) {
      setEditRM(userVessel.river_mile?.toFixed(1) || "");
      setEditSpeed((userVessel.speed * 1.15078).toFixed(1) || "");
      setEditCourse(userVessel.course?.toFixed(0) || "180");
    }
    setShowPositionEditor(true);
  };

  // Handle user vessel edit from map click
  const handleUserVesselEdit = (vessel) => {
    // Pre-fill the form with current vessel data
    setEditRM(vessel.river_mile?.toFixed(1) || "");
    setEditSpeed((vessel.speed * 1.15078).toFixed(1) || "");
    setEditCourse(vessel.course?.toFixed(0) || "180");
    setShowPositionEditor(true);
  };

  // Update position from quick editor
  const updateQuickPosition = async () => {
    const rm = parseFloat(editRM);
    const speed = parseFloat(editSpeed);
    const course = parseFloat(editCourse);
    
    if (isNaN(rm) || rm < 100 || rm > 900) {
      toast.error("River Mile must be between 100 and 900");
      return;
    }
    
    try {
      // First convert RM to lat/lon
      const coordsResponse = await fetch(`${API}/river-mile-to-coords/${rm}`);
      if (!coordsResponse.ok) {
        toast.error("Failed to convert River Mile");
        return;
      }
      const coords = await coordsResponse.json();
      
      // Convert speed from MPH to knots
      const speedKnots = (speed || 0) * 0.868976;
      
      // Update position
      const response = await fetch(`${API}/user-position`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lat: coords.lat,
          lon: coords.lon,
          speed: speedKnots,
          course: course || 0,
          source: "manual",
          mmsi: userMmsi || userVessel?.mmsi,
          name: userSettings.boat_name || userVessel?.name || "Your Vessel"
        })
      });
      
      if (response.ok) {
        toast.success(`Position updated to RM ${rm}`);
        setShowPositionEditor(false);
      } else {
        toast.error("Failed to update position");
      }
    } catch (error) {
      console.error("Position update error:", error);
      toast.error("Failed to update position");
    }
  };

  // Quick stats for mobile header
  const requiredSpeed = raceAnalysis?.analysis?.required_speed_mph;
  const userEta = raceAnalysis?.analysis?.user_eta_minutes;

  return (
    <div className="min-h-screen bg-slate-950 font-sans" data-testid="dashboard">
      {/* Clean Header */}
      <header className="bg-slate-950/95 backdrop-blur-xl border-b border-white/5 sticky top-0 z-50">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            {/* Left: Logo + Status */}
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <Radio className="w-5 h-5 text-cyan-400" />
                <span className="font-heading font-bold text-base sm:text-lg uppercase tracking-wider text-white">
                  RiverWatch<span className="text-cyan-400 ml-1">AIS</span>
                </span>
              </div>
              
              {/* Connection Status - Minimal */}
              <div className={`flex items-center gap-1.5 px-2 py-1 rounded-sm ${isConnected ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-green-400' : 'bg-red-400'} ${isConnected ? 'animate-pulse' : ''}`} />
                <span className="text-xs font-mono uppercase">{isConnected ? 'Live' : 'Offline'}</span>
              </div>
            </div>
            
            {/* Right: Actions */}
            <div className="flex items-center gap-2">
              {/* Settings - Icon only */}
              <Button
                variant="ghost"
                size="icon"
                onClick={onOpenSettings}
                className="text-slate-400 hover:text-white hover:bg-white/5 w-9 h-9"
                data-testid="settings-btn"
                title="Settings"
              >
                <Settings className="w-4 h-4" />
              </Button>
              
              {/* Refresh - Icon only */}
              <Button
                variant="ghost"
                size="icon"
                onClick={handleRefresh}
                disabled={isRefreshing}
                className="text-slate-400 hover:text-white hover:bg-white/5 w-9 h-9"
                data-testid="refresh-btn"
                title={`Refresh (${getTimeSinceRefresh()})`}
              >
                <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              </Button>
              
              {/* User Menu */}
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-slate-400 hover:text-white hover:bg-white/5 gap-2"
                    data-testid="user-menu-btn"
                  >
                    <User className="w-4 h-4" />
                    <span className="hidden lg:inline text-sm">{user?.name || 'Account'}</span>
                    <ChevronDown className="w-3 h-3 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-56 bg-slate-900 border-slate-700 p-2" align="end">
                  <div className="space-y-1">
                    <div className="px-2 py-1.5 border-b border-slate-700 mb-2">
                      <p className="text-xs text-slate-500 uppercase tracking-wider font-heading">Signed in as</p>
                      <p className="text-sm text-white truncate">{user?.email}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={onResetConnection}
                      className="w-full justify-start text-slate-400 hover:text-white hover:bg-white/5"
                    >
                      <Wifi className="w-4 h-4 mr-2" />
                      Change Connection
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleLogout}
                      className="w-full justify-start text-red-400 hover:text-red-300 hover:bg-red-500/10"
                      data-testid="logout-btn"
                    >
                      <LogOut className="w-4 h-4 mr-2" />
                      Sign Out
                    </Button>
                  </div>
                </PopoverContent>
              </Popover>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-2 md:px-4 py-3 md:py-6">
        
        {/* Mobile Tab Navigation */}
        <div className="md:hidden mb-3">
          <div className="flex bg-slate-900/80 rounded-lg p-1 gap-1">
            <button
              onClick={() => setMobilePanel("race")}
              className={`flex-1 py-2 px-2 rounded-md text-xs font-medium transition-colors ${
                mobilePanel === "race" 
                  ? "bg-cyan-500/20 text-cyan-400" 
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Target className="w-4 h-4 mx-auto mb-0.5" />
              Timing
            </button>
            <button
              onClick={() => setMobilePanel("map")}
              className={`flex-1 py-2 px-2 rounded-md text-xs font-medium transition-colors ${
                mobilePanel === "map" 
                  ? "bg-cyan-500/20 text-cyan-400" 
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Navigation className="w-4 h-4 mx-auto mb-0.5" />
              Map
            </button>
            <button
              onClick={() => setMobilePanel("vessels")}
              className={`flex-1 py-2 px-2 rounded-md text-xs font-medium transition-colors ${
                mobilePanel === "vessels" 
                  ? "bg-cyan-500/20 text-cyan-400" 
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Ship className="w-4 h-4 mx-auto mb-0.5" />
              <span className="relative">
                Boats
                {vessels.length > 0 && (
                  <span className="absolute -top-1 -right-2 bg-cyan-500 text-black text-[8px] w-3 h-3 rounded-full flex items-center justify-center">
                    {vessels.length}
                  </span>
                )}
              </span>
            </button>
            <button
              onClick={() => setMobilePanel("locks")}
              className={`flex-1 py-2 px-2 rounded-md text-xs font-medium transition-colors ${
                mobilePanel === "locks" 
                  ? "bg-cyan-500/20 text-cyan-400" 
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Lock className="w-4 h-4 mx-auto mb-0.5" />
              Locks
            </button>
            <button
              onClick={() => setMobilePanel("debug")}
              className={`flex-1 py-2 px-2 rounded-md text-xs font-medium transition-colors ${
                mobilePanel === "debug" 
                  ? "bg-cyan-500/20 text-cyan-400" 
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Terminal className="w-4 h-4 mx-auto mb-0.5" />
              Raw
            </button>
          </div>
        </div>

        {/* Desktop Split-View Layout */}
        <div className="hidden md:block">
          {/* Desktop Split-View Layout - Map always visible with sidebar */}
          <div className="grid grid-cols-12 gap-4" style={{ height: 'calc(100vh - 220px)', minHeight: '500px' }}>
            {/* Main Map Area - Takes 8 columns */}
            <div className="col-span-8">
              <Card className="glass-panel hud-border h-full" data-testid="river-map-card">
                {/* Compact Map Header */}
                <div className="flex items-center justify-between px-4 py-2 border-b border-white/10">
                  <div className="flex items-center gap-3">
                    <Navigation className="w-4 h-4 text-cyan-400" />
                    <span className="text-sm font-medium text-white">River Map</span>
                    {autoNextLock && (
                      <Badge className="bg-green-500/20 text-green-400 border-green-500/50 text-[10px]">AUTO</Badge>
                    )}
                  </div>
                  
                  <div className="flex items-center gap-3">
                    {/* Auto Next Lock Toggle */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setAutoNextLock(!autoNextLock);
                        if (!autoNextLock && nextLock) {
                          onSelectLock(nextLock.id);
                          toast.success(`Auto-tracking: ${nextLock.name}`);
                        }
                      }}
                      className={`h-7 px-2 ${autoNextLock ? 'bg-green-500/20 text-green-400' : 'text-slate-400 hover:text-white'}`}
                      title={nextLock ? `Next lock: ${nextLock.name}` : 'No heading detected'}
                    >
                      <Target className="w-3 h-3 mr-1" />
                      {autoNextLock ? 'Auto' : 'Next'}
                    </Button>
                    
                    {/* Zoom Controls */}
                    <div className="flex items-center gap-1">
                      <ZoomOut className="w-3 h-3 text-slate-500" />
                      <input
                        type="range"
                        min="10"
                        max="500"
                        step="10"
                        value={zoomLevel}
                        onChange={(e) => setZoomLevel(parseInt(e.target.value))}
                        className="w-20 h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-500"
                      />
                      <ZoomIn className="w-3 h-3 text-slate-500" />
                      <span className="text-[10px] text-slate-500 w-8">{zoomLevel < 500 ? `${zoomLevel}mi` : 'Full'}</span>
                    </div>
                    
                    {/* Lock Selector */}
                    <select
                      value={selectedLock}
                      onChange={(e) => {
                        setAutoNextLock(false);
                        onSelectLock(e.target.value);
                      }}
                      disabled={autoNextLock}
                      className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-white text-xs font-mono"
                    >
                      {locks.map(lock => (
                        <option key={lock.id} value={lock.id}>
                          L{lock.id.replace('lock_', '')} (RM {lock.river_mile})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                
                {/* Map Content with Floating Overlays */}
                <div className="relative h-[calc(100%-44px)]">
                  <RiverVisualization
                    vessels={vessels}
                    userMmsi={userMmsi}
                    locks={locks}
                    selectedLock={selectedLock}
                    raceAnalysis={raceAnalysis}
                    zoomRange={zoomLevel}
                    onVesselClick={handleVesselClick}
                    onLockClick={setSelectedLockDetail}
                    onUserVesselEdit={handleUserVesselEdit}
                    showVesselNames={userSettings.show_vessel_names !== false}
                    focusedVessel={focusedVessel}
                    onFocusClear={() => setFocusedVessel(null)}
                    onVesselDetails={(vessel) => setSelectedVessel(vessel)}
                  />
                  
                  {/* Feature #4: Mini Compass/Heading Indicator - Top Right */}
                  {userVessel && (
                    <div className="absolute top-3 right-3 z-30 glass-panel border border-slate-600 rounded-lg p-2">
                      <div className="flex items-center gap-2">
                        <div className="relative w-10 h-10">
                          {/* Compass circle */}
                          <div className="absolute inset-0 rounded-full border border-slate-500 bg-slate-900/80">
                            {/* Cardinal directions */}
                            <span className="absolute top-0 left-1/2 -translate-x-1/2 text-[8px] text-red-400 font-bold">N</span>
                            <span className="absolute bottom-0 left-1/2 -translate-x-1/2 text-[8px] text-slate-500">S</span>
                            <span className="absolute left-0 top-1/2 -translate-y-1/2 text-[8px] text-slate-500">W</span>
                            <span className="absolute right-0 top-1/2 -translate-y-1/2 text-[8px] text-slate-500">E</span>
                          </div>
                          {/* Heading needle */}
                          <div 
                            className="absolute inset-0 flex items-center justify-center"
                            style={{ 
                              transform: `rotate(${userVessel.course || 0}deg)`,
                              transition: 'transform 0.5s ease-out'
                            }}
                          >
                            <div className="w-0.5 h-4 bg-gradient-to-t from-transparent via-cyan-400 to-cyan-400 rounded-full" />
                          </div>
                          {/* Center dot */}
                          <div className="absolute inset-0 flex items-center justify-center">
                            <div className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-[10px] text-slate-500 uppercase">Heading</div>
                          <div className="text-sm font-mono text-white">
                            {userVessel.course ? `${Math.round(userVessel.course)}°` : '--'}
                          </div>
                          <div className={`text-[10px] font-semibold ${
                            userVessel.heading === 'northbound' ? 'text-green-400' : 
                            userVessel.heading === 'southbound' ? 'text-red-400' : 'text-slate-400'
                          }`}>
                            {userVessel.heading === 'northbound' ? '↑ UPRIVER' : 
                             userVessel.heading === 'southbound' ? '↓ DOWNRIVER' : 'STATIONARY'}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  
                  {/* Integrated HUD - Bottom of Map */}
                  <div className="absolute bottom-0 left-0 right-0 z-30 pointer-events-none">
                    <div className="flex justify-center pb-2 md:pb-3 px-2">
                      <div className="pointer-events-auto bg-slate-950/95 backdrop-blur-md border border-white/10 rounded-lg shadow-2xl overflow-hidden max-w-full">
                        {/* Main HUD Content */}
                        <div className="flex items-stretch flex-wrap md:flex-nowrap justify-center">
                          {/* Your Position */}
                          {userVessel && (
                            <div className="flex items-center gap-2 px-2 md:px-4 py-1.5 md:py-2 border-r border-white/10">
                              <div className="w-2 h-2 md:w-2.5 md:h-2.5 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_10px_rgba(6,182,212,0.5)]" />
                              <div>
                                <div className="text-[8px] md:text-[9px] font-heading uppercase tracking-widest text-slate-500">Pos</div>
                                <div className="font-mono text-sm md:text-lg text-cyan-400 font-semibold leading-tight">
                                  {userVessel.river_mile?.toFixed(1)}
                                </div>
                              </div>
                            </div>
                          )}
                          
                          {/* Your Speed */}
                          {userVessel && (
                            <div className="flex items-center px-2 md:px-4 py-1.5 md:py-2 border-r border-white/10">
                              <div>
                                <div className="text-[8px] md:text-[9px] font-heading uppercase tracking-widest text-slate-500">Spd</div>
                                <div className="font-mono text-sm md:text-lg text-white font-semibold leading-tight">
                                  {(userVessel.speed * 1.15078).toFixed(0)}
                                </div>
                              </div>
                            </div>
                          )}

                          {/* Divider with glow - hidden on mobile */}
                          <div className="hidden md:block w-px bg-gradient-to-b from-transparent via-cyan-500/50 to-transparent" />

                          {/* ETA to Lock */}
                          <div className="flex items-center px-2 md:px-4 py-1.5 md:py-2 border-r border-white/10">
                            <div>
                              <div className="text-[8px] md:text-[9px] font-heading uppercase tracking-widest text-slate-500">ETA</div>
                              <div className="font-mono text-sm md:text-lg text-amber-400 font-semibold leading-tight">
                                {userEta ? `${Math.round(userEta)}m` : '--'}
                              </div>
                            </div>
                          </div>

                          {/* Required Speed */}
                          <div className="flex items-center px-2 md:px-4 py-1.5 md:py-2 border-r border-white/10">
                            <div>
                              <div className="text-[8px] md:text-[9px] font-heading uppercase tracking-widest text-slate-500">Need</div>
                              <div className={`font-mono text-sm md:text-lg font-bold leading-tight ${isDangerous ? 'text-red-400' : 'text-green-400'}`}>
                                {requiredSpeed?.toFixed(0) || '--'}
                              </div>
                            </div>
                          </div>

                          {/* Status */}
                          <div className={`flex items-center px-2 md:px-4 py-1.5 md:py-2 ${isDangerous ? 'bg-red-500/10' : 'bg-green-500/10'}`}>
                            <div className={`font-heading text-xs md:text-sm font-bold uppercase tracking-wider leading-tight ${isDangerous ? 'text-red-400' : 'text-green-400'}`}>
                              {isDangerous ? 'DELAY' : 'CLEAR'}
                            </div>
                            {isDangerous && (
                              <AlertTriangle className="w-3 h-3 md:w-4 md:h-4 text-red-400 ml-1 animate-pulse" />
                            )}
                          </div>
                        </div>
                        
                        {/* Target Lock indicator - hidden on mobile */}
                        <div className="hidden md:flex bg-slate-900/50 px-4 py-1 border-t border-white/5 items-center justify-center gap-2">
                          <Lock className="w-3 h-3 text-slate-500" />
                          <span className="text-[10px] font-heading uppercase tracking-wider text-slate-500">
                            Target: {selectedLockObj?.name || 'Select Lock'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Floating Position Editor - Shows when editing from map click */}
                  {showPositionEditor && (
                    <div className="absolute top-3 left-3 z-50 glass-panel border border-cyan-500/50 rounded-lg shadow-xl w-64" data-testid="map-position-editor">
                      <div className="px-3 py-2 border-b border-slate-700 flex items-center justify-between">
                        <h4 className="text-sm font-medium text-white flex items-center gap-2">
                          <MapPin className="w-4 h-4 text-cyan-400" />
                          Edit Position
                        </h4>
                        <button 
                          onClick={() => setShowPositionEditor(false)}
                          className="text-slate-400 hover:text-white p-1"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                      <div className="p-3 space-y-3">
                        <div>
                          <Label className="text-xs text-slate-400">River Mile</Label>
                          <Input
                            type="number"
                            placeholder="e.g., 830"
                            value={editRM}
                            onChange={(e) => setEditRM(e.target.value)}
                            className="bg-slate-950 border-slate-700 text-white font-mono h-9"
                            data-testid="map-edit-rm"
                          />
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <Label className="text-xs text-slate-400">Speed (MPH)</Label>
                            <Input
                              type="number"
                              placeholder="15"
                              value={editSpeed}
                              onChange={(e) => setEditSpeed(e.target.value)}
                              className="bg-slate-950 border-slate-700 text-white font-mono h-9"
                              data-testid="map-edit-speed"
                            />
                          </div>
                          <div>
                            <Label className="text-xs text-slate-400">Course (°)</Label>
                            <Input
                              type="number"
                              placeholder="180"
                              value={editCourse}
                              onChange={(e) => setEditCourse(e.target.value)}
                              className="bg-slate-950 border-slate-700 text-white font-mono h-9"
                              data-testid="map-edit-course"
                            />
                          </div>
                        </div>
                        
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setShowPositionEditor(false)}
                            className="flex-1 border-slate-600 text-slate-400 hover:bg-slate-800"
                          >
                            Cancel
                          </Button>
                          <Button
                            size="sm"
                            onClick={updateQuickPosition}
                            className="flex-1 bg-cyan-600 hover:bg-cyan-700 text-white"
                            data-testid="map-edit-save-btn"
                          >
                            <Check className="w-4 h-4 mr-1" />
                            Update
                          </Button>
                        </div>
                        
                        <p className="text-[10px] text-slate-500">
                          0°=North, 180°=South (downriver)
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            </div>
            
            {/* Sidebar - Takes 4 columns, matches map height */}
            <div className="col-span-4 flex flex-col gap-4 h-full">
              {/* Lock Timing Card - Enhanced */}
              <Card className="glass-panel hud-border flex-shrink-0" data-testid="timing-sidebar">
                <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Target className="w-4 h-4 text-cyan-400" />
                    <span className="text-sm font-medium text-white">Lock Timing</span>
                  </div>
                  <Badge className={`text-[10px] ${
                    isDangerous 
                      ? 'bg-red-500/20 text-red-400 border-red-500/50' 
                      : raceAnalysis?.analysis?.threatening_vessel 
                        ? 'bg-amber-500/20 text-amber-400 border-amber-500/50'
                        : 'bg-green-500/20 text-green-400 border-green-500/50'
                  }`}>
                    {isDangerous ? 'DELAY' : raceAnalysis?.analysis?.threatening_vessel ? 'TRAFFIC' : 'CLEAR'}
                  </Badge>
                </div>
                <div className="p-3 space-y-3">
                  {/* Target Lock Info */}
                  <div className="pb-2 border-b border-slate-700">
                    <div className="text-[10px] text-slate-500 uppercase">Target Lock</div>
                    <div className="text-white font-semibold">{selectedLockObj?.name || 'Lock 2'}</div>
                    <div className="text-xs text-slate-400">River Mile {selectedLockObj?.river_mile}</div>
                  </div>
                  
                  {/* Feature #1: Distance & Time Breakdown */}
                  {lockTravelInfo.distance && (
                    <div className="grid grid-cols-2 gap-2 text-xs pb-2 border-b border-slate-700">
                      <div className="flex items-center gap-1.5">
                        <Route className="w-3 h-3 text-slate-500" />
                        <span className="text-slate-400">Distance:</span>
                        <span className="text-white font-mono">{lockTravelInfo.distance} mi</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Timer className="w-3 h-3 text-slate-500" />
                        <span className="text-slate-400">Travel:</span>
                        <span className="text-white font-mono">{lockTravelInfo.travelMinutes || '--'} min</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Clock className="w-3 h-3 text-slate-500" />
                        <span className="text-slate-400">Est. Wait:</span>
                        <span className="text-amber-400 font-mono">~{lockTravelInfo.estimatedWait} min</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Gauge className="w-3 h-3 text-slate-500" />
                        <span className="text-slate-400">Total:</span>
                        <span className="text-cyan-400 font-mono font-semibold">~{lockTravelInfo.totalMinutes || '--'} min</span>
                      </div>
                    </div>
                  )}
                  
                  {/* Feature #2: Lock Queue Preview */}
                  {lockQueue.length > 0 && (
                    <div className="pb-2 border-b border-slate-700">
                      <div className="flex items-center gap-1.5 mb-2">
                        <Users className="w-3 h-3 text-amber-400" />
                        <span className="text-[10px] text-amber-400 uppercase font-semibold">
                          Queue ({lockQueue.length} vessel{lockQueue.length > 1 ? 's' : ''})
                        </span>
                      </div>
                      <div className="space-y-1">
                        {lockQueue.map((vessel, idx) => (
                          <div 
                            key={vessel.mmsi}
                            className="flex items-center justify-between text-[10px] py-1 px-1.5 rounded bg-slate-800/50"
                          >
                            <span className="text-slate-300 truncate max-w-[120px]">
                              {idx + 1}. {getVesselDisplayName(vessel, userSettings.show_vessel_names !== false)}
                            </span>
                            <div className="flex items-center gap-2">
                              {vessel.barge_count > 0 && (
                                <Badge className="bg-amber-900/30 text-amber-400 border-amber-500/30 text-[8px] px-1 py-0">
                                  {vessel.barge_count}B
                                </Badge>
                              )}
                              <span className="text-slate-500 font-mono">
                                {Math.abs(vessel.river_mile - selectedLockObj.river_mile).toFixed(1)}mi
                              </span>
                            </div>
                          </div>
                        ))}
                        {userVessel && (
                          <div className="flex items-center justify-between text-[10px] py-1 px-1.5 rounded bg-cyan-900/30 border border-cyan-500/30">
                            <span className="text-cyan-400 font-semibold">
                              {lockQueue.length + 1}. You
                            </span>
                            <span className="text-cyan-400 font-mono">
                              {lockTravelInfo.distance}mi
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  
                  {/* Threat Info / Clear Status */}
                  {raceAnalysis?.analysis?.threatening_vessel ? (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-amber-400">
                        <AlertTriangle className="w-4 h-4" />
                        <span className="text-sm font-semibold">Traffic Ahead</span>
                      </div>
                      <div className="bg-slate-800/50 rounded p-2 text-xs">
                        <div className="font-medium text-white mb-1">
                          {getVesselDisplayName(raceAnalysis.analysis.threatening_vessel, userSettings.show_vessel_names !== false)}
                        </div>
                        <div className="grid grid-cols-2 gap-1 text-slate-400">
                          <span>ETA: {raceAnalysis.analysis.threat_eta_minutes?.toFixed(0)}m</span>
                          <span>RM: {raceAnalysis.analysis.threatening_vessel.river_mile?.toFixed(1)}</span>
                        </div>
                      </div>
                      <div className="text-center py-2">
                        <div className="text-[10px] text-slate-500 uppercase">Speed to Beat</div>
                        <div className={`text-2xl font-mono font-bold ${isDangerous ? 'text-red-400' : 'text-green-400'}`}>
                          {raceAnalysis.analysis.required_speed_mph?.toFixed(1)} mph
                        </div>
                        {isDangerous && (
                          <div className="text-[10px] text-red-400 mt-1">Exceeds max speed (25 mph)</div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-3">
                      <div className="w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-1">
                        <Check className="w-4 h-4 text-green-400" />
                      </div>
                      <div className="text-green-400 font-semibold text-sm">No Traffic</div>
                      <div className="text-[10px] text-slate-400">Clear path to lock</div>
                    </div>
                  )}
                  
                  {/* Feature #8: Last Lockage Info */}
                  {lastLockage && (
                    <div className="pt-2 border-t border-slate-700">
                      <div className="flex items-center gap-1.5 mb-1">
                        <History className="w-3 h-3 text-slate-500" />
                        <span className="text-[10px] text-slate-500 uppercase">Last Through</span>
                      </div>
                      <div className="text-xs">
                        <span className="text-slate-300">{lastLockage.vesselName}</span>
                        {lastLockage.bargeCount > 0 && (
                          <span className="text-amber-400 ml-1">({lastLockage.bargeCount} barges)</span>
                        )}
                        {lastLockage.minutesAgo && (
                          <span className="text-slate-500 ml-1">• {lastLockage.minutesAgo} min ago</span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </Card>
              
              {/* Nearby Vessels Card - Compact */}
              <Card className="glass-panel hud-border flex-shrink-0" data-testid="vessels-sidebar">
                <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Ship className="w-4 h-4 text-cyan-400" />
                    <span className="text-sm font-medium text-white">Nearby Vessels</span>
                  </div>
                  <Badge variant="outline" className="border-cyan-500/50 text-cyan-400 text-[10px]">
                    {vessels.length}
                  </Badge>
                </div>
                <ScrollArea className="h-[140px]">
                  <div className="p-2 space-y-1">
                    {vessels.length === 0 ? (
                      <div className="text-center py-4 text-slate-500 text-sm">No vessels in range</div>
                    ) : (
                      vessels.slice(0, 8).map(vessel => {
                        // ONLY match by MMSI, not is_user_vessel flag
                        const isUser = userMmsi && vessel.mmsi === userMmsi;
                        return (
                          <div 
                            key={vessel.mmsi}
                            className={`p-2 rounded cursor-pointer transition-colors ${
                              isUser ? 'bg-cyan-500/10 border-l-2 border-cyan-500' : 'hover:bg-slate-800/50'
                            }`}
                            onClick={() => handleVesselClickFromList(vessel)}
                          >
                            <div className="flex items-center justify-between">
                              <span className={`text-xs font-medium truncate ${isUser ? 'text-cyan-400' : 'text-white'}`}>
                                {getVesselDisplayName(vessel, userSettings.show_vessel_names !== false)}
                              </span>
                              <span className="text-[10px] text-slate-400 font-mono">
                                RM {vessel.river_mile?.toFixed(1)}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 mt-0.5 text-[10px] text-slate-500">
                              <span>{(vessel.speed * 1.15078).toFixed(1)} mph</span>
                              <span className={vessel.heading === 'northbound' ? 'text-green-400' : vessel.heading === 'southbound' ? 'text-red-400' : ''}>
                                {vessel.heading === 'northbound' ? '↑N' : vessel.heading === 'southbound' ? '↓S' : '—'}
                              </span>
                              {vessel.barge_count > 0 && (
                                <Badge className="bg-amber-900/30 text-amber-400 border-amber-500/30 text-[8px] px-1 py-0">
                                  {vessel.barge_count}B
                                </Badge>
                              )}
                            </div>
                          </div>
                        );
                      })
                    )}
                    {vessels.length > 8 && (
                      <div className="text-center py-2 text-xs text-slate-500">
                        +{vessels.length - 8} more vessels
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </Card>
              
              {/* Secondary Tabs for Locks/Debug - Fills remaining height */}
              <Card className="glass-panel hud-border flex-1 flex flex-col min-h-0">
                <Tabs defaultValue="locks" className="w-full h-full flex flex-col">
                  <TabsList className="w-full bg-slate-900/50 border-b border-white/10 rounded-none rounded-t-lg flex-shrink-0">
                    <TabsTrigger value="locks" className="flex-1 text-xs data-[state=active]:bg-cyan-500/10">
                      <Lock className="w-3 h-3 mr-1" />
                      Locks
                    </TabsTrigger>
                    <TabsTrigger value="debug" className="flex-1 text-xs data-[state=active]:bg-cyan-500/10">
                      <Terminal className="w-3 h-3 mr-1" />
                      Raw
                    </TabsTrigger>
                  </TabsList>
                  <TabsContent value="locks" className="mt-0 flex-1 min-h-0 p-2">
                    {/* Lock Selector Dropdown */}
                    <Select value={selectedLock} onValueChange={(value) => {
                      setAutoNextLock(false);
                      onSelectLock(value);
                    }}>
                      <SelectTrigger className="w-full bg-slate-800/50 border-slate-600 text-white text-xs h-8">
                        <SelectValue placeholder="Select a lock" />
                      </SelectTrigger>
                      <SelectContent className="bg-slate-800 border-slate-600 max-h-[250px]">
                        {locks.map(lock => {
                          const status = lockStatus[lock.id];
                          const statusStr = typeof status === 'string' ? status : status?.status;
                          return (
                            <SelectItem 
                              key={lock.id} 
                              value={lock.id}
                              className="text-white hover:bg-slate-700 focus:bg-slate-700 text-xs py-1.5"
                            >
                              <div className="flex items-center gap-2">
                                <span className={`w-1.5 h-1.5 rounded-full ${
                                  statusStr?.toUpperCase() === 'OPEN' ? 'bg-green-400' :
                                  statusStr?.toUpperCase() === 'CLOSED' ? 'bg-red-400' :
                                  statusStr?.toUpperCase() === 'RESTRICTED' ? 'bg-amber-400' :
                                  'bg-slate-400'
                                }`} />
                                <span>L{lock.id.replace('lock_', '').toUpperCase()}</span>
                                <span className="text-slate-500">
                                  {lock.name?.split('(')[1]?.replace(')', '') || ''}
                                </span>
                              </div>
                            </SelectItem>
                          );
                        })}
                      </SelectContent>
                    </Select>

                    {/* Selected Lock Info */}
                    {selectedLock && locks.find(l => l.id === selectedLock) && (
                      <div className="mt-2 p-2 bg-slate-800/30 rounded text-xs space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-slate-400">Status</span>
                          {(() => {
                            const status = lockStatus[selectedLock];
                            const statusStr = typeof status === 'string' ? status : status?.status || 'unknown';
                            const isOpen = statusStr.toLowerCase() === 'open';
                            return (
                              <Badge className={`text-[10px] ${
                                isOpen ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'
                              }`}>
                                {statusStr.toUpperCase()}
                              </Badge>
                            );
                          })()}
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-400">River Mile</span>
                          <span className="text-white font-mono">
                            {locks.find(l => l.id === selectedLock)?.river_mile}
                          </span>
                        </div>
                        <button
                          className="w-full mt-1 py-1 text-[10px] text-cyan-400 hover:text-cyan-300 flex items-center justify-center gap-1 bg-cyan-500/10 rounded"
                          onClick={() => setSelectedLockDetail(selectedLock)}
                        >
                          <Info className="w-3 h-3" />
                          View Full Details
                        </button>
                      </div>
                    )}
                  </TabsContent>
                  <TabsContent value="debug" className="mt-0 flex-1 min-h-0">
                    <ScrollArea className="h-full">
                      <div className="p-2 text-[10px] font-mono text-slate-400">
                        <div>Vessels: {vessels.length}</div>
                        <div>Connected: {isConnected ? 'Yes' : 'No'}</div>
                        <div>User MMSI: {userMmsi || 'N/A'}</div>
                        <div>Selected Lock: {selectedLock}</div>
                        {raceAnalysis?.analysis && (
                          <>
                            <div className="mt-2 text-cyan-400">Race Analysis:</div>
                            <div>User ETA: {raceAnalysis.analysis.user_eta_minutes?.toFixed(1)}m</div>
                            <div>Threat ETA: {raceAnalysis.analysis.threat_eta_minutes?.toFixed(1) || 'N/A'}m</div>
                            <div>Required Speed: {raceAnalysis.analysis.required_speed_mph?.toFixed(1) || 'N/A'} mph</div>
                          </>
                        )}
                      </div>
                    </ScrollArea>
                  </TabsContent>
                </Tabs>
              </Card>
            </div>
          </div>
        </div>

        {/* Mobile Content Panels */}
        <div className="md:hidden">
          {/* Race Panel - Mobile */}
          {mobilePanel === "race" && (
            <div className="space-y-4">
              <RaceAnalysisPanel 
                raceAnalysis={raceAnalysis}
                userVessel={userVessel}
                isDangerous={isDangerous}
                compact={true}
                showVesselNames={userSettings.show_vessel_names !== false}
              />
              
              {userVessel && (
                <Card className="glass-panel border-cyan-500/30">
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-semibold text-cyan-400">Your Vessel</span>
                      <div className="flex items-center gap-2">
                        <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/50 text-xs">
                          {getVesselDisplayName(userVessel, userSettings.show_vessel_names !== false)}
                        </Badge>
                        {/* Quick Position Edit - Mobile (using Sheet for better mobile UX) */}
                        <Sheet>
                          <SheetTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={openPositionEditor}
                              className="h-6 w-6 p-0 text-slate-400 hover:text-cyan-400 hover:bg-cyan-500/10"
                              data-testid="quick-position-edit-btn-mobile"
                            >
                              <Edit3 className="w-3 h-3" />
                            </Button>
                          </SheetTrigger>
                          <SheetContent side="bottom" className="bg-slate-900 border-slate-700 rounded-t-xl">
                            <div className="space-y-4 pb-6">
                              <div className="flex items-center justify-between">
                                <h4 className="text-lg font-medium text-white">Edit Position</h4>
                                <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/50 text-xs">
                                  Testing
                                </Badge>
                              </div>
                              <div className="space-y-3">
                                <div>
                                  <Label className="text-sm text-slate-400">River Mile</Label>
                                  <Input
                                    type="number"
                                    placeholder="830"
                                    value={editRM}
                                    onChange={(e) => setEditRM(e.target.value)}
                                    className="bg-slate-950 border-slate-700 text-white font-mono h-10 text-lg"
                                  />
                                </div>
                                <div className="grid grid-cols-2 gap-3">
                                  <div>
                                    <Label className="text-sm text-slate-400">Speed (MPH)</Label>
                                    <Input
                                      type="number"
                                      placeholder="15"
                                      value={editSpeed}
                                      onChange={(e) => setEditSpeed(e.target.value)}
                                      className="bg-slate-950 border-slate-700 text-white font-mono h-10"
                                    />
                                  </div>
                                  <div>
                                    <Label className="text-sm text-slate-400">Course (°)</Label>
                                    <Input
                                      type="number"
                                      placeholder="180"
                                      value={editCourse}
                                      onChange={(e) => setEditCourse(e.target.value)}
                                      className="bg-slate-950 border-slate-700 text-white font-mono h-10"
                                    />
                                  </div>
                                </div>
                              </div>
                              <Button
                                onClick={updateQuickPosition}
                                className="w-full bg-cyan-600 hover:bg-cyan-700 text-white h-12 text-base"
                              >
                                <Check className="w-4 h-4 mr-2" />
                                Update Position
                              </Button>
                              <p className="text-xs text-slate-500 text-center">
                                0°=North, 180°=South (downriver)
                              </p>
                            </div>
                          </SheetContent>
                        </Sheet>
                      </div>
                    </div>
                    <div className="grid grid-cols-4 gap-2 text-center">
                      <div>
                        <div className="text-[10px] text-slate-500 uppercase">RM</div>
                        <div className="text-base font-mono text-white">{userVessel.river_mile?.toFixed(1)}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500 uppercase">Speed</div>
                        <div className="text-base font-mono text-white">{(userVessel.speed * 1.15078).toFixed(1)}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500 uppercase">Course</div>
                        <div className="text-base font-mono text-white">{userVessel.course?.toFixed(0)}°</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500 uppercase">Dir</div>
                        <div className="text-base font-mono text-white capitalize">{userVessel.heading?.slice(0,1) || '-'}</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Map Panel - Mobile */}
          {mobilePanel === "map" && (
            <Card className="glass-panel hud-border" data-testid="river-map-card-mobile">
              {/* Mobile Map Header with controls */}
              <div className="border-b border-white/10 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Navigation className="w-4 h-4 text-cyan-400" />
                    <span className="text-sm font-medium text-white">River Map</span>
                    {autoNextLock && (
                      <Badge className="bg-green-500/20 text-green-400 border-green-500/50 text-[10px]">
                        Auto
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {/* Auto Next Lock - Mobile */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setAutoNextLock(!autoNextLock);
                        if (!autoNextLock && nextLock) {
                          onSelectLock(nextLock.id);
                          toast.success(`Auto: ${nextLock.name}`);
                        }
                      }}
                      className={`h-7 px-2 ${autoNextLock ? 'bg-green-500/20 text-green-400' : 'text-slate-400'}`}
                      data-testid="auto-next-lock-btn-mobile"
                    >
                      <Target className="w-3 h-3" />
                    </Button>
                    {/* Zoom Slider - Mobile */}
                    <div className="flex items-center gap-1">
                      <input
                        type="range"
                        min="10"
                        max="500"
                        step="10"
                        value={zoomLevel}
                        onChange={(e) => setZoomLevel(parseInt(e.target.value))}
                        className="w-16 h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-500"
                        data-testid="zoom-slider-mobile"
                      />
                    </div>
                  </div>
                </div>
              </div>
              <CardContent className="p-0 h-[calc(100vh-260px)] min-h-[350px]">
                <RiverVisualization
                  vessels={vessels}
                  userMmsi={userMmsi}
                  locks={locks}
                  selectedLock={selectedLock}
                  raceAnalysis={raceAnalysis}
                  compact={true}
                  zoomRange={zoomLevel}
                  onVesselClick={handleVesselClick}
                  onLockClick={setSelectedLockDetail}
                  onUserVesselEdit={handleUserVesselEdit}
                  showVesselNames={userSettings.show_vessel_names !== false}
                  focusedVessel={focusedVessel}
                  onFocusClear={() => setFocusedVessel(null)}
                  onVesselDetails={(vessel) => setSelectedVessel(vessel)}
                />
              </CardContent>
            </Card>
          )}

          {/* Vessels Panel - Mobile */}
          {mobilePanel === "vessels" && (
            <Card className="glass-panel hud-border">
              <CardContent className="p-0">
                <Tabs defaultValue="all" className="w-full">
                  <TabsList className="w-full bg-slate-900/50 border-b border-white/10 rounded-none">
                    <TabsTrigger 
                      value="all" 
                      className="flex-1 data-[state=active]:bg-cyan-500/10 data-[state=active]:text-cyan-400 text-sm"
                    >
                      All ({vessels.length})
                    </TabsTrigger>
                    <TabsTrigger 
                      value="commercial"
                      className="flex-1 data-[state=active]:bg-cyan-500/10 data-[state=active]:text-cyan-400 text-sm"
                    >
                      Commercial ({commercialVessels.length})
                    </TabsTrigger>
                  </TabsList>
                  
                  <TabsContent value="all" className="mt-0">
                    <ScrollArea className="h-[calc(100vh-250px)]">
                      <VesselList 
                        vessels={vessels} 
                        userMmsi={userMmsi}
                        selectedLock={locks.find(l => l.id === selectedLock)}
                        compact={true}
                        onVesselClick={handleVesselClickFromList}
                        showVesselNames={userSettings.show_vessel_names !== false}
                      />
                    </ScrollArea>
                  </TabsContent>
                  
                  <TabsContent value="commercial" className="mt-0">
                    <ScrollArea className="h-[calc(100vh-250px)]">
                      <VesselList 
                        vessels={commercialVessels}
                        userMmsi={userMmsi}
                        selectedLock={locks.find(l => l.id === selectedLock)}
                        compact={true}
                        onVesselClick={handleVesselClickFromList}
                        showVesselNames={userSettings.show_vessel_names !== false}
                      />
                    </ScrollArea>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          )}

          {/* Locks Panel - Mobile */}
          {mobilePanel === "locks" && (
            <LockStatusPanel
              locks={locks}
              lockStatus={lockStatus}
              lockageTimes={lockageTimes}
              selectedLock={selectedLock}
              onSelectLock={onSelectLock}
              onLockDetails={setSelectedLockDetail}
              compact={true}
            />
          )}

          {/* Debug/Raw Data Panel - Mobile */}
          {mobilePanel === "debug" && (
            <div className="h-[calc(100vh-200px)] min-h-[400px]">
              <RawDataPanel isConnected={isConnected} />
            </div>
          )}
        </div>
      </main>

      {/* Alert Overlay for Traffic Delay */}
      {isDangerous && currentThreatMmsi !== dismissedThreatMmsi && (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-50 animate-bounce">
          <div className="glass-panel border-2 border-red-500 alert-pulse px-6 py-4 rounded-lg flex items-center gap-3">
            <AlertTriangle className="w-6 h-6 text-red-400" />
            <div>
              <div className="text-red-400 font-bold">Traffic Delay Expected</div>
              <div className="text-sm text-slate-300">
                Required speed ({raceAnalysis?.analysis?.required_speed_mph?.toFixed(1)} MPH) exceeds your max (25 MPH)
              </div>
            </div>
            <button
              onClick={() => setDismissedThreatMmsi(currentThreatMmsi)}
              className="ml-2 p-1 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors"
              aria-label="Dismiss alert"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>
      )}

      {/* Vessel Detail Modal */}
      <VesselDetailModal
        vessel={selectedVessel}
        isOpen={!!selectedVessel}
        onClose={() => setSelectedVessel(null)}
        selectedLock={selectedLockObj}
      />

      {/* Lock Detail Modal */}
      <LockDetailModal
        lockId={selectedLockDetail}
        isOpen={!!selectedLockDetail}
        onClose={() => setSelectedLockDetail(null)}
        onSelectOnMap={(lockId) => {
          onSelectLock(lockId);
          setDesktopPanel("timing");
        }}
      />
    </div>
  );
}
