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
  Anchor, Ship, Gauge, Clock, MapPin, AlertTriangle, 
  Wifi, WifiOff, ChevronDown, Navigation, Lock, Settings,
  Play, Zap, Target, Menu, X, ChevronUp, ZoomIn, ZoomOut, Terminal,
  Edit3, Check
} from "lucide-react";
import { toast } from "sonner";
import RiverVisualization from "@/components/RiverVisualization";
import RaceAnalysisPanel from "@/components/RaceAnalysisPanel";
import VesselList from "@/components/VesselList";
import ConnectionStatus from "@/components/ConnectionStatus";
import LockStatusPanel from "@/components/LockStatusPanel";
import VesselDetailModal from "@/components/VesselDetailModal";
import RawDataPanel from "@/components/RawDataPanel";
import { getVesselDisplayName } from "@/utils/vesselDisplay";

const API = process.env.REACT_APP_BACKEND_URL + '/api';

export default function Dashboard({ 
  isConnected, 
  vessels, 
  userMmsi, 
  locks, 
  lockStatus,
  raceAnalysis,
  selectedLock,
  onSelectLock,
  onDisconnect,
  onResetConnection,
  onReconnect,
  onAddDemoVessels,
  onOpenSettings,
  connectionConfig,
  userSettings = {},
  demoMode = false
}) {
  const [mobilePanel, setMobilePanel] = useState("race"); // "race" | "vessels" | "map" | "locks" | "debug"
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [mapZoomed, setMapZoomed] = useState(true); // Default to zoomed view
  const [selectedVessel, setSelectedVessel] = useState(null); // For vessel detail modal
  
  // Quick position editor state
  const [showPositionEditor, setShowPositionEditor] = useState(false);
  const [editRM, setEditRM] = useState("");
  const [editSpeed, setEditSpeed] = useState("");
  const [editCourse, setEditCourse] = useState("");
  
  // Auto next lock tracking
  const [autoNextLock, setAutoNextLock] = useState(false);
  
  // Alert dismissal - tracks which threat was dismissed
  const [dismissedThreatMmsi, setDismissedThreatMmsi] = useState(null);

  // Find user vessel
  const userVessel = useMemo(() => {
    return vessels.find(v => v.mmsi === userMmsi || v.is_user_vessel);
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

  // Commercial vessels (non-user)
  const commercialVessels = useMemo(() => {
    return vessels.filter(v => v.mmsi !== userMmsi && !v.is_user_vessel);
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

  // Handle vessel click (from map or list)
  const handleVesselClick = (vessel) => {
    setSelectedVessel(vessel);
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
    <div className="min-h-screen bg-[#020617]" data-testid="dashboard">
      {/* Header - Mobile Optimized */}
      <header className="glass-panel border-b border-white/10 sticky top-0 z-50">
        <div className="container mx-auto px-3 md:px-4 py-2 md:py-3">
          <div className="flex items-center justify-between">
            {/* Logo & Status */}
            <div className="flex items-center gap-2 md:gap-4">
              <div className="flex items-center gap-2">
                <Anchor className="w-5 h-5 md:w-6 md:h-6 text-cyan-400" />
                <h1 className="text-lg md:text-xl font-bold text-white tracking-wide">
                  RIVER WATCH
                  <span className="text-xs md:text-sm font-normal text-slate-500 ml-2">v1.0</span>
                </h1>
              </div>
              <ConnectionStatus 
                isConnected={isConnected} 
                config={connectionConfig}
                compact={true}
                demoMode={demoMode}
              />
            </div>
            
            {/* Desktop Actions */}
            <div className="hidden md:flex items-center gap-3">
              {!isConnected && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onReconnect}
                  className="border-cyan-500/50 text-cyan-400 hover:bg-cyan-500/10"
                  data-testid="reconnect-btn"
                >
                  <Wifi className="w-4 h-4 mr-1" />
                  Retry Connection
                </Button>
              )}
              
              <Button
                variant="outline"
                size="sm"
                onClick={onAddDemoVessels}
                className="border-slate-600 text-slate-300 hover:bg-slate-800"
                data-testid="demo-vessels-btn"
              >
                <Play className="w-4 h-4 mr-1" />
                Demo Mode
              </Button>
              
              <Button
                variant="outline"
                size="sm"
                onClick={onOpenSettings}
                className="border-slate-600 text-slate-300 hover:bg-slate-800"
                data-testid="settings-btn"
              >
                <Settings className="w-4 h-4 mr-1" />
                Settings
              </Button>
              
              <Button
                variant="outline"
                size="sm"
                onClick={onResetConnection}
                className="border-slate-600 text-slate-300 hover:bg-slate-800"
                data-testid="change-connection-btn"
              >
                <Wifi className="w-4 h-4 mr-1" />
                Connection
              </Button>
            </div>

            {/* Mobile Menu Button */}
            <Sheet open={showMobileMenu} onOpenChange={setShowMobileMenu}>
              <SheetTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="md:hidden text-slate-300"
                  data-testid="mobile-menu-btn"
                >
                  <Menu className="w-5 h-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="bg-slate-900 border-slate-700 w-72">
                <div className="flex flex-col gap-3 mt-6">
                  {!isConnected && (
                    <Button
                      variant="outline"
                      onClick={() => { onReconnect(); setShowMobileMenu(false); }}
                      className="border-cyan-500/50 text-cyan-400 justify-start"
                    >
                      <Wifi className="w-4 h-4 mr-2" />
                      Retry Connection
                    </Button>
                  )}
                  
                  <Button
                    variant="outline"
                    onClick={() => { onAddDemoVessels(); setShowMobileMenu(false); }}
                    className="border-slate-600 text-slate-300 justify-start"
                  >
                    <Play className="w-4 h-4 mr-2" />
                    Demo Mode
                  </Button>
                  
                  <Button
                    variant="outline"
                    onClick={() => { onOpenSettings(); setShowMobileMenu(false); }}
                    className="border-slate-600 text-slate-300 justify-start"
                  >
                    <Settings className="w-4 h-4 mr-2" />
                    Settings
                  </Button>
                  
                  <Button
                    variant="outline"
                    onClick={() => { onResetConnection(); setShowMobileMenu(false); }}
                    className="border-slate-600 text-slate-300 justify-start"
                  >
                    <Wifi className="w-4 h-4 mr-2" />
                    Change Connection
                  </Button>
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </div>

        {/* Mobile Quick Stats Bar */}
        <div className="md:hidden border-t border-white/5 px-3 py-2 flex items-center justify-between bg-slate-900/50">
          <div className="flex items-center gap-3">
            {/* Your Position */}
            {userVessel ? (
              <div className="text-center">
                <div className="text-[10px] text-slate-500 uppercase">Your RM</div>
                <div className="text-lg font-mono text-cyan-400">
                  {userVessel.river_mile?.toFixed(1) || '--'}
                </div>
              </div>
            ) : userMmsi ? (
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-auto py-1 px-2 text-cyan-400 border border-cyan-500/30"
                    data-testid="set-position-btn-mobile"
                  >
                    <MapPin className="w-3 h-3 mr-1" />
                    <span className="text-xs">Set Pos</span>
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-64 bg-slate-900 border-slate-700" align="start">
                  <div className="space-y-3">
                    <h4 className="text-sm font-medium text-white">Set Your Position</h4>
                    <div className="space-y-2">
                      <div>
                        <Label className="text-xs text-slate-400">River Mile</Label>
                        <Input
                          type="number"
                          placeholder="830"
                          value={editRM}
                          onChange={(e) => setEditRM(e.target.value)}
                          className="bg-slate-950 border-slate-700 text-white font-mono h-8"
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
                            className="bg-slate-950 border-slate-700 text-white font-mono h-8"
                          />
                        </div>
                        <div>
                          <Label className="text-xs text-slate-400">Course (°)</Label>
                          <Input
                            type="number"
                            placeholder="180"
                            value={editCourse}
                            onChange={(e) => setEditCourse(e.target.value)}
                            className="bg-slate-950 border-slate-700 text-white font-mono h-8"
                          />
                        </div>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      onClick={updateQuickPosition}
                      className="w-full bg-cyan-600 hover:bg-cyan-700 text-white h-8"
                    >
                      <Check className="w-3 h-3 mr-1" />
                      Set Position
                    </Button>
                  </div>
                </PopoverContent>
              </Popover>
            ) : null}
            
            <div className="text-center">
              <div className="text-[10px] text-slate-500 uppercase">Speed Req</div>
              <div className={`text-lg font-mono font-bold ${isDangerous ? 'text-red-400' : requiredSpeed ? 'text-green-400' : 'text-slate-500'}`}>
                {requiredSpeed?.toFixed(0) || '--'}
                <span className="text-xs ml-0.5">mph</span>
              </div>
            </div>
            <div className="text-center">
              <div className="text-[10px] text-slate-500 uppercase">Your ETA</div>
              <div className="text-lg font-mono text-white">
                {userEta?.toFixed(0) || '--'}
                <span className="text-xs ml-0.5">min</span>
              </div>
            </div>
          </div>
          
          {isDangerous && (
            <div className="flex items-center gap-1 text-red-400 text-xs font-semibold animate-pulse">
              <AlertTriangle className="w-4 h-4" />
              DELAY
            </div>
          )}
          
          {/* Lock Selector - Mobile */}
          <select
            value={selectedLock}
            onChange={(e) => {
              setAutoNextLock(false);
              onSelectLock(e.target.value);
            }}
            className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-white text-xs font-mono"
            data-testid="lock-selector-mobile"
          >
            {locks.map(lock => (
              <option key={lock.id} value={lock.id}>
                L{lock.id.replace('lock_', '')}
              </option>
            ))}
          </select>
        </div>
      </header>

      {/* Your Vessel Status Bar - Desktop */}
      <div className="hidden md:block border-b border-white/10 bg-slate-900/50">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full ${userVessel ? 'bg-cyan-400 user-vessel-pulse' : 'bg-slate-600'}`} />
                <span className="text-sm font-semibold text-white">Your Vessel</span>
                {userVessel ? (
                  <>
                    <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/50">
                      {getVesselDisplayName(userVessel, userSettings.show_vessel_names !== false)}
                    </Badge>
                    {userVessel.source && (
                      <Badge className={`text-xs ${userVessel.source === 'GPS' ? 'bg-green-900/30 text-green-400 border-green-500/30' : 'bg-blue-900/30 text-blue-400 border-blue-500/30'}`}>
                        {userVessel.source}
                      </Badge>
                    )}
                  </>
                ) : userMmsi ? (
                  <Badge className="bg-slate-700 text-slate-400 border-slate-600">
                    MMSI: {userMmsi} <span className="text-xs ml-1">(awaiting position data)</span>
                  </Badge>
                ) : (
                  <Badge className="bg-amber-900/30 text-amber-400 border-amber-500/30">
                    No MMSI configured
                  </Badge>
                )}
              </div>
            </div>
            
            {userVessel ? (
              <div className="flex items-center gap-4 md:gap-6">
                <div className="text-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider">River Mile</div>
                  <div className="text-lg font-mono text-white">
                    {userVessel.river_mile?.toFixed(1) || '--'}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider">Speed</div>
                  <div className="text-lg font-mono text-white">
                    {(userVessel.speed * 1.15078).toFixed(1)} <span className="text-xs text-slate-400">MPH</span>
                  </div>
                </div>
                <div className="text-center hidden sm:block">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider">Course</div>
                  <div className="text-lg font-mono text-white">
                    {userVessel.course?.toFixed(0)}°
                  </div>
                </div>
                <div className="text-center hidden md:block">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider">Direction</div>
                  <div className="text-lg font-semibold text-white capitalize">
                    {userVessel.heading || '--'}
                  </div>
                </div>
                
                {/* Quick Position Edit Button */}
                <Popover open={showPositionEditor} onOpenChange={setShowPositionEditor}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={openPositionEditor}
                      className="text-slate-400 hover:text-cyan-400 hover:bg-cyan-500/10"
                      data-testid="quick-position-edit-btn"
                    >
                      <Edit3 className="w-4 h-4" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-72 bg-slate-900 border-slate-700" align="end">
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-sm font-medium text-white">Quick Position Edit</h4>
                        <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/50 text-xs">
                          Testing
                        </Badge>
                      </div>
                      
                      <div className="space-y-2">
                        <div>
                          <Label className="text-xs text-slate-400">River Mile</Label>
                          <Input
                            type="number"
                            placeholder="830"
                            value={editRM}
                            onChange={(e) => setEditRM(e.target.value)}
                            className="bg-slate-950 border-slate-700 text-white font-mono h-9"
                            data-testid="quick-edit-rm"
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
                              data-testid="quick-edit-speed"
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
                              data-testid="quick-edit-course"
                            />
                          </div>
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
                          data-testid="quick-edit-save-btn"
                        >
                          <Check className="w-4 h-4 mr-1" />
                          Update
                        </Button>
                      </div>
                      
                      <p className="text-[10px] text-slate-500">
                        0°=North, 180°=South (downriver)
                      </p>
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <div className="text-sm text-slate-500">
                  {isConnected ? 'Waiting for your vessel position from AIS feed...' : 'Not connected to AIS'}
                </div>
                {/* Allow setting position even without existing vessel data */}
                {userMmsi && (
                  <Popover open={showPositionEditor} onOpenChange={setShowPositionEditor}>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEditRM("");
                          setEditSpeed("15");
                          setEditCourse("180");
                          setShowPositionEditor(true);
                        }}
                        className="text-cyan-400 border-cyan-500/50 hover:bg-cyan-500/10"
                        data-testid="set-position-btn"
                      >
                        <MapPin className="w-4 h-4 mr-1" />
                        Set Position
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-72 bg-slate-900 border-slate-700" align="end">
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <h4 className="text-sm font-medium text-white">Set Your Position</h4>
                          <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/50 text-xs">
                            Testing
                          </Badge>
                        </div>
                        
                        <div className="space-y-2">
                          <div>
                            <Label className="text-xs text-slate-400">River Mile</Label>
                            <Input
                              type="number"
                              placeholder="830"
                              value={editRM}
                              onChange={(e) => setEditRM(e.target.value)}
                              className="bg-slate-950 border-slate-700 text-white font-mono h-9"
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
                              />
                            </div>
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
                          >
                            <Check className="w-4 h-4 mr-1" />
                            Set
                          </Button>
                        </div>
                        
                        <p className="text-[10px] text-slate-500">
                          0°=North, 180°=South (downriver)
                        </p>
                      </div>
                    </PopoverContent>
                  </Popover>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

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

        {/* Desktop Grid Layout */}
        <div className="hidden md:grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* Left Panel - River Visualization */}
          <div className="lg:col-span-8 xl:col-span-9">
            <Card className="glass-panel hud-border h-full min-h-[600px]" data-testid="river-map-card">
              <CardHeader className="border-b border-white/10 pb-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg text-white flex items-center gap-2">
                    <Navigation className="w-5 h-5 text-cyan-400" />
                    {mapZoomed ? `Around Lock ${selectedLock.replace('lock_', '').toUpperCase()}` : 'Locks 2-10 Overview'}
                    {autoNextLock && nextLock && (
                      <Badge className="bg-green-500/20 text-green-400 border-green-500/50 text-xs ml-2">
                        Auto
                      </Badge>
                    )}
                  </CardTitle>
                  
                  {/* Lock Selector + Zoom Toggle */}
                  <div className="flex items-center gap-2">
                    {/* Auto Next Lock Toggle */}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setAutoNextLock(!autoNextLock);
                        if (!autoNextLock && nextLock) {
                          onSelectLock(nextLock.id);
                          toast.success(`Auto-tracking: ${nextLock.name}`);
                        }
                      }}
                      className={`border-slate-600 ${autoNextLock ? 'bg-green-500/20 text-green-400 border-green-500/50' : 'text-slate-400'}`}
                      data-testid="auto-next-lock-btn"
                      title={nextLock ? `Next lock: ${nextLock.name} (RM ${nextLock.river_mile})` : 'No vessel heading detected'}
                    >
                      <Target className="w-4 h-4 mr-1" />
                      {autoNextLock ? 'Auto' : 'Next'}
                    </Button>
                    
                    {/* Zoom Toggle */}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setMapZoomed(!mapZoomed)}
                      className={`border-slate-600 ${mapZoomed ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/50' : 'text-slate-300'}`}
                      data-testid="zoom-toggle"
                    >
                      <MapPin className="w-4 h-4 mr-1" />
                      {mapZoomed ? 'Zoomed' : 'Full'}
                    </Button>
                    
                    {/* Manual Lock Selector */}
                    <select
                      value={selectedLock}
                      onChange={(e) => {
                        setAutoNextLock(false); // Disable auto when manually selecting
                        onSelectLock(e.target.value);
                      }}
                      disabled={autoNextLock}
                      className={`bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-white text-sm font-mono focus:border-cyan-500 focus:outline-none ${autoNextLock ? 'opacity-50 cursor-not-allowed' : ''}`}
                      data-testid="lock-selector"
                    >
                      {locks.map(lock => (
                        <option key={lock.id} value={lock.id}>
                          Lock {lock.id.replace('lock_', '')} (RM {lock.river_mile})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </CardHeader>
              
              <CardContent className="p-0 h-full">
                <RiverVisualization
                  vessels={vessels}
                  userMmsi={userMmsi}
                  locks={locks}
                  selectedLock={selectedLock}
                  raceAnalysis={raceAnalysis}
                  zoomed={mapZoomed}
                  zoomRange={userSettings.map_zoom_miles || 25}
                  onVesselClick={handleVesselClick}
                  showVesselNames={userSettings.show_vessel_names !== false}
                />
              </CardContent>
            </Card>
          </div>

          {/* Right Panel - Analysis & Vessels */}
          <div className="lg:col-span-4 xl:col-span-3 space-y-6">
            
            {/* Race Analysis Panel */}
            <RaceAnalysisPanel 
              raceAnalysis={raceAnalysis}
              userVessel={userVessel}
              isDangerous={isDangerous}
              showVesselNames={userSettings.show_vessel_names !== false}
            />

            {/* Vessel List */}
            <Card className="glass-panel hud-border" data-testid="vessel-list-card">
              <CardHeader className="border-b border-white/10 pb-3">
                <CardTitle className="text-lg text-white flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Ship className="w-5 h-5 text-cyan-400" />
                    Tracked Vessels
                  </span>
                  <Badge variant="outline" className="border-cyan-500/50 text-cyan-400">
                    {vessels.length}
                  </Badge>
                </CardTitle>
              </CardHeader>
              
              <CardContent className="p-0">
                <Tabs defaultValue="all" className="w-full">
                  <TabsList className="w-full bg-slate-900/50 border-b border-white/10 rounded-none">
                    <TabsTrigger 
                      value="all" 
                      className="flex-1 data-[state=active]:bg-cyan-500/10 data-[state=active]:text-cyan-400"
                    >
                      All ({vessels.length})
                    </TabsTrigger>
                    <TabsTrigger 
                      value="commercial"
                      className="flex-1 data-[state=active]:bg-cyan-500/10 data-[state=active]:text-cyan-400"
                    >
                      Commercial ({commercialVessels.length})
                    </TabsTrigger>
                  </TabsList>
                  
                  <TabsContent value="all" className="mt-0">
                    <ScrollArea className="h-[300px]">
                      <VesselList 
                        vessels={vessels} 
                        userMmsi={userMmsi}
                        selectedLock={locks.find(l => l.id === selectedLock)}
                        onVesselClick={handleVesselClick}
                        showVesselNames={userSettings.show_vessel_names !== false}
                      />
                    </ScrollArea>
                  </TabsContent>
                  
                  <TabsContent value="commercial" className="mt-0">
                    <ScrollArea className="h-[300px]">
                      <VesselList 
                        vessels={commercialVessels}
                        userMmsi={userMmsi}
                        selectedLock={locks.find(l => l.id === selectedLock)}
                        onVesselClick={handleVesselClick}
                        showVesselNames={userSettings.show_vessel_names !== false}
                      />
                    </ScrollArea>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>

            {/* Raw Data Panel - Debug */}
            <RawDataPanel isConnected={isConnected} />
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
                    <span className="text-sm font-medium text-white">
                      {mapZoomed ? `Lock ${selectedLock.replace('lock_', '')}` : 'Overview'}
                    </span>
                    {autoNextLock && (
                      <Badge className="bg-green-500/20 text-green-400 border-green-500/50 text-[10px]">
                        Auto
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
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
                    {/* Zoom Toggle - Mobile */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setMapZoomed(!mapZoomed)}
                      className={`h-7 px-2 ${mapZoomed ? 'bg-cyan-500/20 text-cyan-400' : 'text-slate-400'}`}
                      data-testid="zoom-toggle-mobile"
                    >
                      {mapZoomed ? <ZoomIn className="w-3 h-3" /> : <ZoomOut className="w-3 h-3" />}
                    </Button>
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
                  zoomed={mapZoomed}
                  zoomRange={userSettings.map_zoom_miles || 25}
                  onVesselClick={handleVesselClick}
                  showVesselNames={userSettings.show_vessel_names !== false}
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
                        onVesselClick={handleVesselClick}
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
                        onVesselClick={handleVesselClick}
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
              selectedLock={selectedLock}
              onSelectLock={onSelectLock}
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
    </div>
  );
}
