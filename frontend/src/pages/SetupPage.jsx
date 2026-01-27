import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Anchor, Ship, ArrowRight, Settings, ChevronDown, ChevronUp, LogOut, User } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Default connection settings - can be edited in advanced settings
const DEFAULT_IP = "136.116.165.255";
const DEFAULT_PORT = "7000";

export default function SetupPage({ onConnect }) {
  const [userMmsi, setUserMmsi] = useState("");
  const [boatName, setBoatName] = useState("");
  const [loading, setLoading] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [ipAddress, setIpAddress] = useState(DEFAULT_IP);
  const [port, setPort] = useState(DEFAULT_PORT);
  const [existingSession, setExistingSession] = useState(null); // Existing MMSI session

  // Check for existing session on mount
  useEffect(() => {
    const checkExistingSession = async () => {
      try {
        // Check localStorage for existing MMSI session
        const storedMmsi = localStorage.getItem('riverwatch_mmsi');
        
        if (storedMmsi) {
          // Load this user's settings from backend
          const response = await fetch(`${API}/user/${storedMmsi}/settings`);
          if (response.ok) {
            const data = await response.json();
            const settings = data.settings || {};
            
            setExistingSession({
              mmsi: storedMmsi,
              boatName: settings.boat_name || '',
              lastUsed: data.updated_at
            });
            
            // Pre-fill form with existing settings
            setUserMmsi(storedMmsi);
            setBoatName(settings.boat_name || '');
            
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
  }, []);

  const handleConnect = async () => {
    if (!userMmsi) {
      toast.error("Please enter your vessel's MMSI");
      return;
    }
    
    // Validate MMSI format (should be 9 digits)
    if (!/^\d{9}$/.test(userMmsi)) {
      toast.warning("MMSI should be a 9-digit number");
    }
    
    // Save MMSI to localStorage for session persistence
    localStorage.setItem('riverwatch_mmsi', userMmsi);
    
    // Save user settings to backend
    try {
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
      console.log(`Session saved for MMSI: ${userMmsi}`);
    } catch (error) {
      console.error("Failed to save session:", error);
    }
    
    // Connect with the config
    onConnect({
      ip_address: ipAddress,
      port: parseInt(port),
      user_mmsi: userMmsi,
      boat_name: boatName
    });
  };

  const handleClearSession = () => {
    localStorage.removeItem('riverwatch_mmsi');
    setExistingSession(null);
    setUserMmsi("");
    setBoatName("");
    setIpAddress(DEFAULT_IP);
    setPort(DEFAULT_PORT);
    toast.info("Session cleared. Enter a new MMSI to continue.");
  };

  const handleQuickConnect = () => {
    // Use existing session settings
    if (existingSession) {
      handleConnect();
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center">
        <div className="text-cyan-400 text-lg">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center p-4">
      <Card className="w-full max-w-md glass-panel border-cyan-500/20">
        <CardHeader className="text-center pb-2">
          <div className="mx-auto w-16 h-16 rounded-full bg-cyan-500/10 flex items-center justify-center mb-4">
            <Anchor className="w-8 h-8 text-cyan-400" />
          </div>
          <CardTitle className="text-2xl text-white">River Watch</CardTitle>
          <CardDescription className="text-slate-400">
            {existingSession 
              ? "Welcome back! Continue with your vessel or change MMSI below."
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
                    <span className="text-slate-400">({existingSession.boatName})</span>
                  )}
                </div>
              </div>
              
              <Button
                onClick={handleQuickConnect}
                className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-semibold"
                data-testid="quick-connect-btn"
              >
                Continue as {existingSession.boatName || `MMSI ${existingSession.mmsi}`}
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </div>
          )}

          {/* Divider if existing session */}
          {existingSession && (
            <div className="flex items-center gap-4">
              <div className="flex-1 h-px bg-slate-700" />
              <span className="text-xs text-slate-500">or enter different MMSI</span>
              <div className="flex-1 h-px bg-slate-700" />
            </div>
          )}

          {/* MMSI Input */}
          <div className="space-y-2">
            <Label htmlFor="mmsi" className="text-slate-300 flex items-center gap-2">
              <Ship className="w-4 h-4 text-cyan-400" />
              {existingSession ? "Different MMSI" : "Your Vessel MMSI *"}
            </Label>
            <Input
              id="mmsi"
              type="text"
              placeholder="e.g., 367123456"
              value={userMmsi}
              onChange={(e) => {
                setUserMmsi(e.target.value);
                // Clear existing session indicator if user types different MMSI
                if (existingSession && e.target.value !== existingSession.mmsi) {
                  setExistingSession(null);
                }
              }}
              className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 font-mono"
              data-testid="mmsi-input"
            />
            <p className="text-xs text-slate-500">
              9-digit Maritime Mobile Service Identity number
            </p>
          </div>

          {/* Boat Name (Optional) */}
          <div className="space-y-2">
            <Label htmlFor="boatName" className="text-slate-300">
              Boat Name (optional)
            </Label>
            <Input
              id="boatName"
              type="text"
              placeholder="e.g., Sea Breeze"
              value={boatName}
              onChange={(e) => setBoatName(e.target.value)}
              className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500"
              data-testid="boat-name-input"
            />
          </div>

          {/* Advanced Settings Toggle */}
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-cyan-400 transition-colors"
          >
            <Settings className="w-4 h-4" />
            Advanced Connection Settings
            {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          {/* Advanced Settings - Collapsible */}
          {showAdvanced && (
            <div className="space-y-4 p-4 rounded-lg bg-slate-800/50 border border-slate-700">
              <div className="space-y-2">
                <Label htmlFor="ip" className="text-slate-300">
                  AIS Server IP Address
                </Label>
                <Input
                  id="ip"
                  type="text"
                  placeholder="192.168.1.100"
                  value={ipAddress}
                  onChange={(e) => setIpAddress(e.target.value)}
                  className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 font-mono"
                  data-testid="ip-input"
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="port" className="text-slate-300">
                  Port
                </Label>
                <Input
                  id="port"
                  type="text"
                  placeholder="5353"
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                  className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 font-mono w-32"
                  data-testid="port-input"
                />
              </div>
              
              <p className="text-xs text-slate-500">
                Connection to Boat Beacon TCP relay. Only change if you know your server details.
              </p>
            </div>
          )}

          {/* Connect Button - Only show if no existing session or MMSI changed */}
          {(!existingSession || userMmsi !== existingSession.mmsi) && (
            <Button
              onClick={handleConnect}
              disabled={!userMmsi}
              className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-semibold py-6 text-lg"
              data-testid="connect-btn"
            >
              {existingSession ? "Connect with New MMSI" : "Connect"}
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
          )}
          
          <p className="text-xs text-center text-slate-500">
            Connecting to {ipAddress}:{port}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
