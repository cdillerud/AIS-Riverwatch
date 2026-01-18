import { useState, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { 
  Anchor, Ship, Gauge, Clock, MapPin, AlertTriangle, 
  Wifi, WifiOff, ChevronDown, Navigation, Lock, Settings,
  Play, Zap, Target, Menu, X, ChevronUp, ZoomIn, ZoomOut
} from "lucide-react";
import RiverVisualization from "@/components/RiverVisualization";
import RaceAnalysisPanel from "@/components/RaceAnalysisPanel";
import VesselList from "@/components/VesselList";
import ConnectionStatus from "@/components/ConnectionStatus";
import LockStatusPanel from "@/components/LockStatusPanel";
import VesselDetailModal from "@/components/VesselDetailModal";

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
  userSettings = {}
}) {
  const [mobilePanel, setMobilePanel] = useState("race"); // "race" | "vessels" | "map" | "locks"
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [mapZoomed, setMapZoomed] = useState(true); // Default to zoomed view
  const [selectedVessel, setSelectedVessel] = useState(null); // For vessel detail modal

  // Find user vessel
  const userVessel = useMemo(() => {
    return vessels.find(v => v.mmsi === userMmsi || v.is_user_vessel);
  }, [vessels, userMmsi]);

  // Commercial vessels (non-user)
  const commercialVessels = useMemo(() => {
    return vessels.filter(v => v.mmsi !== userMmsi && !v.is_user_vessel);
  }, [vessels, userMmsi]);

  // Check if speed requirement is dangerous
  const isDangerous = raceAnalysis?.analysis?.required_speed_mph && 
                      raceAnalysis.analysis.required_speed_mph > 25;

  // Get the selected lock object for the modal
  const selectedLockObj = useMemo(() => {
    return locks.find(l => l.id === selectedLock);
  }, [locks, selectedLock]);

  // Handle vessel click (from map or list)
  const handleVesselClick = (vessel) => {
    setSelectedVessel(vessel);
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
                <h1 className="text-lg md:text-xl font-bold text-white tracking-wide hidden sm:block">RIVER WATCH</h1>
              </div>
              <ConnectionStatus 
                isConnected={isConnected} 
                config={connectionConfig}
                compact={true}
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
          <div className="flex items-center gap-4">
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
              CAN'T BEAT
            </div>
          )}
          
          {/* Lock Selector - Mobile */}
          <select
            value={selectedLock}
            onChange={(e) => onSelectLock(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-white text-xs font-mono"
            data-testid="lock-selector-mobile"
          >
            {locks.map(lock => (
              <option key={lock.id} value={lock.id}>
                Lock {lock.id.replace('lock_', '')}
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
                      {userVessel.name || userSettings.boat_name || 'MMSI: ' + userVessel.mmsi}
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
              <div className="flex items-center gap-6">
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
                <div className="text-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider">Course</div>
                  <div className="text-lg font-mono text-white">
                    {userVessel.course?.toFixed(0)}°
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider">Direction</div>
                  <div className="text-lg font-semibold text-white capitalize">
                    {userVessel.heading || '--'}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-sm text-slate-500">
                {isConnected ? 'Waiting for your vessel position from AIS feed...' : 'Not connected to AIS'}
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
              Race
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
                  </CardTitle>
                  
                  {/* Lock Selector + Zoom Toggle */}
                  <div className="flex items-center gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setMapZoomed(!mapZoomed)}
                      className={`border-slate-600 ${mapZoomed ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/50' : 'text-slate-300'}`}
                      data-testid="zoom-toggle"
                    >
                      <MapPin className="w-4 h-4 mr-1" />
                      {mapZoomed ? 'Zoomed' : 'Full Map'}
                    </Button>
                    
                    <span className="text-sm text-slate-400">Target:</span>
                    <select
                      value={selectedLock}
                      onChange={(e) => onSelectLock(e.target.value)}
                      className="bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-white text-sm font-mono focus:border-cyan-500 focus:outline-none"
                      data-testid="lock-selector"
                    >
                      {locks.map(lock => (
                        <option key={lock.id} value={lock.id}>
                          {lock.name} (RM {lock.river_mile})
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
                      />
                    </ScrollArea>
                  </TabsContent>
                  
                  <TabsContent value="commercial" className="mt-0">
                    <ScrollArea className="h-[300px]">
                      <VesselList 
                        vessels={commercialVessels}
                        userMmsi={userMmsi}
                        selectedLock={locks.find(l => l.id === selectedLock)}
                      />
                    </ScrollArea>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
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
              />
              
              {userVessel && (
                <Card className="glass-panel border-cyan-500/30">
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-semibold text-cyan-400">Your Vessel</span>
                      <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/50 text-xs">
                        {userVessel.name || userVessel.mmsi}
                      </Badge>
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
              <CardContent className="p-0 h-[calc(100vh-200px)] min-h-[400px]">
                <RiverVisualization
                  vessels={vessels}
                  userMmsi={userMmsi}
                  locks={locks}
                  selectedLock={selectedLock}
                  raceAnalysis={raceAnalysis}
                  compact={true}
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
        </div>
      </main>

      {/* Alert Overlay for Dangerous Speed */}
      {isDangerous && (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-50 animate-bounce">
          <div className="glass-panel border-2 border-red-500 alert-pulse px-6 py-4 rounded-lg flex items-center gap-3">
            <AlertTriangle className="w-6 h-6 text-red-400" />
            <div>
              <div className="text-red-400 font-bold">Cannot Beat to Lock!</div>
              <div className="text-sm text-slate-300">
                Required speed ({raceAnalysis?.analysis?.required_speed_mph?.toFixed(1)} MPH) exceeds your max (25 MPH)
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
