import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Anchor, Ship, ArrowRight, Settings, ChevronDown, ChevronUp, LogOut, User, Eye, MapPin, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Default connection settings - can be edited in advanced settings.
// The relay (ais-relay:5353 inside the docker network) is the canonical
// upstream. Operators discover the real Boat Beacon feed via the AIS
// Feed Scanner panel on the Settings page; the relay then forwards.
const DEFAULT_IP = "ais-relay";
const DEFAULT_PORT = "5353";

// Preset watch points for common river locations
const WATCH_POINT_PRESETS = [
  { name: "Lock 2 (Hastings)", rm: 815.2 },
  { name: "Lock 3 (Red Wing)", rm: 796.9 },
  { name: "Lock 4 (Alma)", rm: 752.8 },
  { name: "Lock 5 (Whitman)", rm: 738.1 },
  { name: "Lock 5A (Fountain City)", rm: 728.5 },
  { name: "Lock 6 (Trempealeau)", rm: 714.3 },
  { name: "Lock 7 (Dresbach)", rm: 702.5 },
  { name: "Lock 8 (Genoa)", rm: 679.2 },
  { name: "Lock 9 (Lynxville)", rm: 647.9 },
  { name: "Lock 10 (Guttenberg)", rm: 615.1 },
];

export default function SetupPage({ onConnect }) {
  const { user, logout } = useAuth();
  
  // Account type selection
  const [accountType, setAccountType] = useState(null); // null = choosing, "vessel_owner", "traffic_watch"
  const [step, setStep] = useState("choose"); // "choose", "vessel_setup", "traffic_setup"
  
  // Vessel owner state
  const [userMmsi, setUserMmsi] = useState("");
  const [boatName, setBoatName] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [ipAddress, setIpAddress] = useState(DEFAULT_IP);
  const [port, setPort] = useState(DEFAULT_PORT);
  const [existingSession, setExistingSession] = useState(null);
  
  // Traffic watch state
  const [watchPointRM, setWatchPointRM] = useState("");
  const [watchPointName, setWatchPointName] = useState("");
  const [selectedPreset, setSelectedPreset] = useState(null);
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Handle logout
  const handleLogout = async () => {
    await logout();
    toast.info("Logged out successfully");
  };

  // Check for existing session on mount
  useEffect(() => {
    const checkExistingSession = async () => {
      try {
        // Check user's account type
        const savedAccountType = user?.account_type;
        
        if (savedAccountType === "traffic_watch") {
          // Traffic watch user - check for watch point
          const watchPoint = user?.watch_point;
          if (watchPoint) {
            setAccountType("traffic_watch");
            setWatchPointRM(watchPoint.river_mile?.toString() || "");
            setWatchPointName(watchPoint.name || "");
            setStep("traffic_setup");
            
            // Auto-connect for traffic watch users with saved watch point
            setLoading(false);
            setTimeout(() => {
              onConnect({
                ip_address: ipAddress,
                port: parseInt(port),
                user_mmsi: "",
                boat_name: "",
                account_type: "traffic_watch",
                watch_point: watchPoint
              });
            }, 500);
            return;
          }
          setAccountType("traffic_watch");
          setStep("traffic_setup");
          setLoading(false);
          return;
        }
        
        // Vessel owner flow
        if (user?.vessels?.length > 0) {
          const primaryVessel = user.vessels.find(v => v.is_primary) || user.vessels[0];
          if (primaryVessel) {
            setAccountType("vessel_owner");
            setExistingSession({
              mmsi: primaryVessel.mmsi,
              boatName: primaryVessel.boat_name || '',
              fromAccount: true
            });
            
            setUserMmsi(primaryVessel.mmsi);
            setBoatName(primaryVessel.boat_name || '');
            
            localStorage.setItem('riverwatch_mmsi', primaryVessel.mmsi);
            
            try {
              const response = await fetch(`${API}/user/${primaryVessel.mmsi}/settings`);
              if (response.ok) {
                const data = await response.json();
                const settings = data.settings || {};
                if (settings.connection_config) {
                  const config = typeof settings.connection_config === 'string' 
                    ? JSON.parse(settings.connection_config) 
                    : settings.connection_config;
                  setIpAddress(config.ip_address || DEFAULT_IP);
                  setPort(config.port?.toString() || DEFAULT_PORT);
                }
              }
            } catch (e) {
              console.log("[SETUP] No additional settings found for MMSI");
            }
            
            setStep("vessel_setup");
            setLoading(false);
            return;
          }
        }
        
        // Check localStorage for existing MMSI
        const storedMmsi = localStorage.getItem('riverwatch_mmsi');
        if (storedMmsi) {
          const response = await fetch(`${API}/user/${storedMmsi}/settings`);
          if (response.ok) {
            const data = await response.json();
            const settings = data.settings || {};
            
            setAccountType("vessel_owner");
            setExistingSession({
              mmsi: storedMmsi,
              boatName: settings.boat_name || '',
              lastUsed: data.updated_at
            });
            
            setUserMmsi(storedMmsi);
            setBoatName(settings.boat_name || '');
            setStep("vessel_setup");
            
            if (settings.connection_config) {
              const config = typeof settings.connection_config === 'string' 
                ? JSON.parse(settings.connection_config) 
                : settings.connection_config;
              setIpAddress(config.ip_address || DEFAULT_IP);
              setPort(config.port?.toString() || DEFAULT_PORT);
            }
          }
        }
      } catch (error) {
        console.error("Failed to check existing session:", error);
      } finally {
        setLoading(false);
      }
    };
    
    checkExistingSession();
  }, [user, onConnect, ipAddress, port]);

  // Handle account type selection
  const handleSelectAccountType = async (type) => {
    setAccountType(type);
    
    // Save account type to backend
    try {
      await fetch(`${API}/user/account-type`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ account_type: type })
      });
    } catch (e) {
      console.error("Failed to save account type:", e);
    }
    
    setStep(type === "vessel_owner" ? "vessel_setup" : "traffic_setup");
  };

  // Handle vessel owner connect
  const handleVesselConnect = async () => {
    if (!userMmsi) {
      toast.error("Please enter your vessel's MMSI");
      return;
    }
    
    if (!/^\d{9}$/.test(userMmsi)) {
      toast.warning("MMSI should be a 9-digit number");
    }
    
    localStorage.setItem('riverwatch_mmsi', userMmsi);
    
    try {
      const vesselExists = user?.vessels?.some(v => v.mmsi === userMmsi);
      if (!vesselExists) {
        const addResponse = await fetch(`${API}/user/vessels`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            mmsi: userMmsi,
            boat_name: boatName,
            is_primary: true
          })
        });
        
        if (addResponse.ok) {
          console.log(`[SETUP] Vessel ${userMmsi} added to user account`);
        }
      }
      
      await fetch(`${API}/user/${userMmsi}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          boat_name: boatName,
          connection_config: {
            ip_address: ipAddress,
            port: parseInt(port),
            user_mmsi: userMmsi
          }
        })
      });
    } catch (error) {
      console.error("Failed to save session:", error);
    }
    
    onConnect({
      ip_address: ipAddress,
      port: parseInt(port),
      user_mmsi: userMmsi,
      boat_name: boatName,
      account_type: "vessel_owner"
    });
  };

  // Handle traffic watch connect
  const handleTrafficWatchConnect = async () => {
    if (!watchPointRM) {
      toast.error("Please select or enter a watch point");
      return;
    }
    
    const rm = parseFloat(watchPointRM);
    if (isNaN(rm) || rm < 0 || rm > 1000) {
      toast.error("Please enter a valid river mile (0-1000)");
      return;
    }
    
    setSaving(true);
    
    const watchPoint = {
      river_mile: rm,
      name: watchPointName || `RM ${rm}`
    };
    
    try {
      await fetch(`${API}/user/watch-point`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(watchPoint)
      });
    } catch (error) {
      console.error("Failed to save watch point:", error);
    }
    
    setSaving(false);
    
    onConnect({
      ip_address: ipAddress,
      port: parseInt(port),
      user_mmsi: "",
      boat_name: "",
      account_type: "traffic_watch",
      watch_point: watchPoint
    });
  };

  const handleClearSession = () => {
    localStorage.removeItem('riverwatch_mmsi');
    setExistingSession(null);
    setUserMmsi("");
    setBoatName("");
    setAccountType(null);
    setStep("choose");
    toast.info("Session cleared. Choose how you'd like to use River Watch.");
  };

  const handlePresetSelect = (preset) => {
    setSelectedPreset(preset);
    setWatchPointRM(preset.rm.toString());
    setWatchPointName(preset.name);
  };

  // Auto-connect for vessel owners with saved session
  useEffect(() => {
    if (!loading && existingSession?.fromAccount && userMmsi && boatName && accountType === "vessel_owner") {
      const timer = setTimeout(() => {
        onConnect({
          ip_address: ipAddress,
          port: parseInt(port),
          user_mmsi: userMmsi,
          boat_name: boatName,
          account_type: "vessel_owner"
        });
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [loading, existingSession, userMmsi, boatName, accountType, ipAddress, port, onConnect]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center">
        <div className="text-cyan-400 text-lg flex items-center gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          Loading...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center p-4 relative">
      {/* Logout button */}
      {user && (
        <div className="absolute top-4 right-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleLogout}
            className="text-slate-400 hover:text-red-400 hover:bg-red-500/10"
            data-testid="logout-btn"
          >
            <LogOut className="w-4 h-4 mr-2" />
            Sign Out ({user.email?.split('@')[0]})
          </Button>
        </div>
      )}
      
      {/* Step 1: Choose Account Type */}
      {step === "choose" && (
        <Card className="w-full max-w-lg glass-panel border-cyan-500/20">
          <CardHeader className="text-center pb-2">
            <div className="mx-auto w-16 h-16 rounded-full bg-cyan-500/10 flex items-center justify-center mb-4">
              <Anchor className="w-8 h-8 text-cyan-400" />
            </div>
            <CardTitle className="text-2xl text-white">River Watch</CardTitle>
            <CardDescription className="text-slate-400">
              How would you like to use River Watch?
            </CardDescription>
          </CardHeader>
          
          <CardContent className="space-y-4">
            {/* Vessel Owner Option */}
            <button
              onClick={() => handleSelectAccountType("vessel_owner")}
              className="w-full p-4 rounded-lg border border-slate-700 hover:border-cyan-500/50 hover:bg-cyan-500/5 transition-all text-left group"
              data-testid="vessel-owner-btn"
            >
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-full bg-cyan-500/10 flex items-center justify-center flex-shrink-0 group-hover:bg-cyan-500/20 transition-colors">
                  <Ship className="w-6 h-6 text-cyan-400" />
                </div>
                <div>
                  <h3 className="text-white font-semibold text-lg">I Have a Vessel</h3>
                  <p className="text-slate-400 text-sm mt-1">
                    Track your position, get lock timing calculations, and see when to speed up or slow down to beat commercial traffic.
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <span className="text-[10px] bg-cyan-500/10 text-cyan-400 px-2 py-0.5 rounded">Lock Timing</span>
                    <span className="text-[10px] bg-cyan-500/10 text-cyan-400 px-2 py-0.5 rounded">Race Analysis</span>
                    <span className="text-[10px] bg-cyan-500/10 text-cyan-400 px-2 py-0.5 rounded">Position Tracking</span>
                  </div>
                </div>
              </div>
            </button>
            
            {/* Traffic Watch Option */}
            <button
              onClick={() => handleSelectAccountType("traffic_watch")}
              className="w-full p-4 rounded-lg border border-slate-700 hover:border-purple-500/50 hover:bg-purple-500/5 transition-all text-left group"
              data-testid="traffic-watch-btn"
            >
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-full bg-purple-500/10 flex items-center justify-center flex-shrink-0 group-hover:bg-purple-500/20 transition-colors">
                  <Eye className="w-6 h-6 text-purple-400" />
                </div>
                <div>
                  <h3 className="text-white font-semibold text-lg">Traffic Watch</h3>
                  <p className="text-slate-400 text-sm mt-1">
                    Monitor river traffic without a vessel. Perfect for lock operators, marina operators, shipping companies, or river enthusiasts.
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <span className="text-[10px] bg-purple-500/10 text-purple-400 px-2 py-0.5 rounded">Traffic Summary</span>
                    <span className="text-[10px] bg-purple-500/10 text-purple-400 px-2 py-0.5 rounded">Vessel Alerts</span>
                    <span className="text-[10px] bg-purple-500/10 text-purple-400 px-2 py-0.5 rounded">No MMSI Required</span>
                  </div>
                </div>
              </div>
            </button>
          </CardContent>
        </Card>
      )}
      
      {/* Step 2A: Vessel Owner Setup */}
      {step === "vessel_setup" && (
        <Card className="w-full max-w-md glass-panel border-cyan-500/20">
          <CardHeader className="text-center pb-2">
            <div className="mx-auto w-16 h-16 rounded-full bg-cyan-500/10 flex items-center justify-center mb-4">
              <Ship className="w-8 h-8 text-cyan-400" />
            </div>
            <CardTitle className="text-2xl text-white">Vessel Setup</CardTitle>
            <CardDescription className="text-slate-400">
              {existingSession 
                ? "Welcome back! Continue with your vessel or change below."
                : "Enter your vessel's MMSI to get started"
              }
            </CardDescription>
          </CardHeader>
          
          <CardContent className="space-y-6">
            {/* Existing Session Card */}
            {existingSession && (
              <div className="p-4 rounded-lg bg-cyan-500/10 border border-cyan-500/30">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <User className="w-5 h-5 text-cyan-400" />
                    <span className="text-white font-medium">Active Session</span>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleClearSession}
                    className="text-slate-400 hover:text-red-400 hover:bg-red-500/10 h-8 px-2"
                  >
                    <LogOut className="w-4 h-4 mr-1" />
                    Change
                  </Button>
                </div>
                
                <div className="space-y-1 mb-4">
                  <div className="flex items-center gap-2">
                    <Ship className="w-4 h-4 text-cyan-400" />
                    <span className="text-white font-mono">{existingSession.mmsi}</span>
                    {existingSession.boatName && (
                      <span className="text-slate-400">• {existingSession.boatName}</span>
                    )}
                  </div>
                </div>
                
                <Button 
                  onClick={handleVesselConnect}
                  className="w-full bg-cyan-600 hover:bg-cyan-700"
                >
                  <ArrowRight className="w-4 h-4 mr-2" />
                  Continue as {existingSession.boatName || existingSession.mmsi}
                </Button>
              </div>
            )}
            
            {/* New/Edit Vessel Form */}
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="mmsi" className="text-slate-300">Vessel MMSI</Label>
                <Input
                  id="mmsi"
                  type="text"
                  placeholder="123456789"
                  value={userMmsi}
                  onChange={(e) => setUserMmsi(e.target.value.replace(/\D/g, '').slice(0, 9))}
                  className="bg-slate-800/50 border-slate-600 text-white font-mono"
                  data-testid="mmsi-input"
                />
                <p className="text-xs text-slate-500">
                  9-digit Maritime Mobile Service Identity number
                </p>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="boatName" className="text-slate-300">Boat Name (Optional)</Label>
                <Input
                  id="boatName"
                  type="text"
                  placeholder="My Boat"
                  value={boatName}
                  onChange={(e) => setBoatName(e.target.value)}
                  className="bg-slate-800/50 border-slate-600 text-white"
                  data-testid="boat-name-input"
                />
              </div>
              
              {/* Advanced Settings */}
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-300"
              >
                <Settings className="w-4 h-4" />
                Advanced Settings
                {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
              
              {showAdvanced && (
                <div className="space-y-4 p-4 bg-slate-800/30 rounded-lg border border-slate-700">
                  <div className="space-y-2">
                    <Label htmlFor="ip" className="text-slate-300">AIS Server IP</Label>
                    <Input
                      id="ip"
                      type="text"
                      value={ipAddress}
                      onChange={(e) => setIpAddress(e.target.value)}
                      className="bg-slate-800/50 border-slate-600 text-white font-mono"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="port" className="text-slate-300">Port</Label>
                    <Input
                      id="port"
                      type="text"
                      value={port}
                      onChange={(e) => setPort(e.target.value.replace(/\D/g, ''))}
                      className="bg-slate-800/50 border-slate-600 text-white font-mono"
                    />
                  </div>
                </div>
              )}
              
              <Button 
                onClick={handleVesselConnect}
                className="w-full bg-cyan-600 hover:bg-cyan-700"
                data-testid="connect-btn"
              >
                <ArrowRight className="w-4 h-4 mr-2" />
                Connect to River Watch
              </Button>
              
              <Button 
                variant="ghost"
                onClick={handleClearSession}
                className="w-full text-slate-400 hover:text-white"
              >
                ← Back to options
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
      
      {/* Step 2B: Traffic Watch Setup */}
      {step === "traffic_setup" && (
        <Card className="w-full max-w-md glass-panel border-purple-500/20">
          <CardHeader className="text-center pb-2">
            <div className="mx-auto w-16 h-16 rounded-full bg-purple-500/10 flex items-center justify-center mb-4">
              <Eye className="w-8 h-8 text-purple-400" />
            </div>
            <CardTitle className="text-2xl text-white">Traffic Watch Setup</CardTitle>
            <CardDescription className="text-slate-400">
              Choose a location to center your traffic view
            </CardDescription>
          </CardHeader>
          
          <CardContent className="space-y-6">
            {/* Preset Watch Points */}
            <div className="space-y-2">
              <Label className="text-slate-300">Quick Select - Lock Locations</Label>
              <div className="grid grid-cols-2 gap-2 max-h-[200px] overflow-y-auto pr-1">
                {WATCH_POINT_PRESETS.map((preset) => (
                  <button
                    key={preset.rm}
                    onClick={() => handlePresetSelect(preset)}
                    className={`p-2 rounded text-left text-xs transition-all ${
                      selectedPreset?.rm === preset.rm
                        ? 'bg-purple-500/20 border border-purple-500/50 text-purple-300'
                        : 'bg-slate-800/50 border border-slate-700 text-slate-300 hover:border-purple-500/30'
                    }`}
                  >
                    <div className="font-medium truncate">{preset.name}</div>
                    <div className="text-slate-500 text-[10px]">RM {preset.rm}</div>
                  </button>
                ))}
              </div>
            </div>
            
            <div className="flex items-center gap-4">
              <div className="h-px flex-1 bg-slate-700" />
              <span className="text-xs text-slate-500">OR</span>
              <div className="h-px flex-1 bg-slate-700" />
            </div>
            
            {/* Custom Watch Point */}
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="watchRM" className="text-slate-300">Custom River Mile</Label>
                <div className="flex gap-2">
                  <Input
                    id="watchRM"
                    type="text"
                    placeholder="815.2"
                    value={watchPointRM}
                    onChange={(e) => {
                      setWatchPointRM(e.target.value);
                      setSelectedPreset(null);
                    }}
                    className="bg-slate-800/50 border-slate-600 text-white font-mono flex-1"
                    data-testid="watch-rm-input"
                  />
                  <Input
                    type="text"
                    placeholder="Location name"
                    value={watchPointName}
                    onChange={(e) => setWatchPointName(e.target.value)}
                    className="bg-slate-800/50 border-slate-600 text-white flex-1"
                    data-testid="watch-name-input"
                  />
                </div>
                <p className="text-xs text-slate-500">
                  Enter a river mile to center your traffic view
                </p>
              </div>
            </div>
            
            <Button 
              onClick={handleTrafficWatchConnect}
              disabled={!watchPointRM || saving}
              className="w-full bg-purple-600 hover:bg-purple-700 disabled:opacity-50"
              data-testid="traffic-connect-btn"
            >
              {saving ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <MapPin className="w-4 h-4 mr-2" />
              )}
              Start Watching Traffic
            </Button>
            
            <Button 
              variant="ghost"
              onClick={handleClearSession}
              className="w-full text-slate-400 hover:text-white"
            >
              ← Back to options
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
