import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Anchor, Ship, ArrowRight, Settings, ChevronDown, ChevronUp } from "lucide-react";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Default connection settings - can be edited in advanced settings
const DEFAULT_IP = "192.168.1.100";
const DEFAULT_PORT = "5353";

export default function SetupPage({ onConnect }) {
  const [userMmsi, setUserMmsi] = useState("");
  const [loading, setLoading] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [ipAddress, setIpAddress] = useState(DEFAULT_IP);
  const [port, setPort] = useState(DEFAULT_PORT);

  // Load saved settings on mount
  useEffect(() => {
    const loadSavedSettings = async () => {
      try {
        const response = await fetch(`${API}/settings`);
        if (response.ok) {
          const settings = await response.json();
          if (settings.user_mmsi) {
            setUserMmsi(settings.user_mmsi);
          }
          // Load saved IP/port if they exist, otherwise keep defaults
          if (settings.last_ip) {
            setIpAddress(settings.last_ip);
          }
          if (settings.last_port) {
            setPort(settings.last_port);
          }
        }
      } catch (error) {
        console.error("Failed to load saved settings:", error);
      } finally {
        setLoading(false);
      }
    };
    loadSavedSettings();
  }, []);

  const handleConnect = async () => {
    if (!userMmsi) {
      toast.error("Please enter your vessel's MMSI");
      return;
    }
    
    // Save settings
    try {
      await fetch(`${API}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_mmsi: userMmsi,
          last_ip: ipAddress,
          last_port: port
        })
      });
    } catch (error) {
      console.error("Failed to save settings:", error);
    }
    
    // Connect with the config
    onConnect({
      ip_address: ipAddress,
      port: parseInt(port),
      user_mmsi: userMmsi
    });
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
            Enter your vessel's MMSI to get started
          </CardDescription>
        </CardHeader>
        
        <CardContent className="space-y-6">
          {/* MMSI Input - Primary */}
          <div className="space-y-2">
            <Label htmlFor="mmsi" className="text-slate-300 flex items-center gap-2">
              <Ship className="w-4 h-4 text-cyan-400" />
              Your Vessel MMSI *
            </Label>
            <Input
              id="mmsi"
              type="text"
              placeholder="e.g., 367123456"
              value={userMmsi}
              onChange={(e) => setUserMmsi(e.target.value)}
              className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500"
              data-testid="mmsi-input"
            />
            <p className="text-xs text-slate-500">
              9-digit Maritime Mobile Service Identity number
            </p>
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

          {/* Connect Button */}
          <Button
            onClick={handleConnect}
            disabled={!userMmsi}
            className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-semibold py-6 text-lg"
            data-testid="connect-btn"
          >
            Connect
            <ArrowRight className="w-5 h-5 ml-2" />
          </Button>
          
          <p className="text-xs text-center text-slate-500">
            Connecting to {ipAddress}:{port}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
