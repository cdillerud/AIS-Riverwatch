import { useState, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
  Anchor, Ship, Gauge, Clock, MapPin, AlertTriangle, 
  Wifi, WifiOff, ChevronDown, Navigation, Lock, Settings,
  Play, Zap, Target
} from "lucide-react";
import RiverVisualization from "@/components/RiverVisualization";
import RaceAnalysisPanel from "@/components/RaceAnalysisPanel";
import VesselList from "@/components/VesselList";
import ConnectionStatus from "@/components/ConnectionStatus";

export default function Dashboard({ 
  isConnected, 
  vessels, 
  userMmsi, 
  locks, 
  raceAnalysis,
  selectedLock,
  onSelectLock,
  onDisconnect,
  onResetConnection,
  onReconnect,
  onAddDemoVessels,
  connectionConfig
}) {
  const [showSettings, setShowSettings] = useState(false);

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

  return (
    <div className="min-h-screen bg-[#020617]" data-testid="dashboard">
      {/* Header */}
      <header className="glass-panel border-b border-white/10 sticky top-0 z-50">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Anchor className="w-6 h-6 text-cyan-400" />
                <h1 className="text-xl font-bold text-white tracking-wide">RIVER WATCH</h1>
              </div>
              <ConnectionStatus 
                isConnected={isConnected} 
                config={connectionConfig}
              />
            </div>
            
            <div className="flex items-center gap-3">
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
                variant="ghost"
                size="sm"
                onClick={() => setShowSettings(!showSettings)}
                className="text-slate-300 hover:text-white"
                data-testid="settings-btn"
              >
                <Settings className="w-5 h-5" />
              </Button>
              
              <Button
                variant="destructive"
                size="sm"
                onClick={onDisconnect}
                className="bg-red-900/50 border border-red-500/50 text-red-100 hover:bg-red-900"
                data-testid="disconnect-btn"
              >
                <WifiOff className="w-4 h-4 mr-1" />
                Disconnect
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* Left Panel - River Visualization */}
          <div className="lg:col-span-8 xl:col-span-9">
            <Card className="glass-panel hud-border h-full min-h-[600px]" data-testid="river-map-card">
              <CardHeader className="border-b border-white/10 pb-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg text-white flex items-center gap-2">
                    <Navigation className="w-5 h-5 text-cyan-400" />
                    Pool 2-3 Overview
                  </CardTitle>
                  
                  {/* Lock Selector */}
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-slate-400">Target Lock:</span>
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

            {/* User Vessel Quick Stats */}
            {userVessel && (
              <Card className="glass-panel border-cyan-500/30" data-testid="user-vessel-card">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-3 h-3 rounded-full bg-cyan-400 user-vessel-pulse" />
                    <span className="text-sm font-semibold text-white">Your Vessel</span>
                    <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/50">
                      {userVessel.name || 'MMSI: ' + userVessel.mmsi}
                    </Badge>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div className="data-highlight">
                      <div className="text-xs text-slate-500 uppercase">River Mile</div>
                      <div className="text-xl font-mono text-white">
                        {userVessel.river_mile?.toFixed(1) || '--'}
                      </div>
                    </div>
                    <div className="data-highlight">
                      <div className="text-xs text-slate-500 uppercase">Speed</div>
                      <div className="text-xl font-mono text-white">
                        {(userVessel.speed * 1.15078).toFixed(1)} <span className="text-sm text-slate-400">MPH</span>
                      </div>
                    </div>
                    <div className="data-highlight">
                      <div className="text-xs text-slate-500 uppercase">Course</div>
                      <div className="text-lg font-mono text-white">
                        {userVessel.course?.toFixed(0)}°
                      </div>
                    </div>
                    <div className="data-highlight">
                      <div className="text-xs text-slate-500 uppercase">Direction</div>
                      <div className="text-lg font-semibold text-white capitalize">
                        {userVessel.heading || '--'}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
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
