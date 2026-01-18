import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Anchor, Wifi, Ship, ArrowRight, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function SetupPage({ onConnect }) {
  const [ipAddress, setIpAddress] = useState("");
  const [port, setPort] = useState("5353");
  const [userMmsi, setUserMmsi] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [loading, setLoading] = useState(true);

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

  const handleTestConnection = async () => {
    if (!ipAddress) {
      toast.error("Please enter an IP address");
      return;
    }
    
    setTesting(true);
    setTestResult(null);
    
    try {
      const response = await fetch(`${API}/connection/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ip_address: ipAddress,
          port: parseInt(port),
          user_mmsi: userMmsi
        })
      });
      
      const data = await response.json();
      setTestResult(data);
      
      if (data.success) {
        toast.success("Connection test successful!");
      } else {
        toast.error(data.message || "Connection test failed");
      }
    } catch (error) {
      setTestResult({ success: false, message: error.message });
      toast.error("Connection test failed: " + error.message);
    } finally {
      setTesting(false);
    }
  };

  const handleConnect = async () => {
    if (!ipAddress || !userMmsi) {
      toast.error("Please fill in all required fields");
      return;
    }
    
    // Save settings for next time
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
    
    onConnect({
      ip_address: ipAddress,
      port: parseInt(port),
      user_mmsi: userMmsi
    });
  };

  return (
    <div className="min-h-screen bg-[#020617] flex items-center justify-center p-4">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/5 rounded-full blur-3xl" />
      </div>

      <div className="w-full max-w-lg relative z-10">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-cyan-500/10 border border-cyan-500/30 mb-4">
            <Anchor className="w-8 h-8 text-cyan-400" />
          </div>
          <h1 className="text-3xl font-bold text-white tracking-wide">RIVER WATCH</h1>
          <p className="text-slate-400 mt-2">AIS Vessel Tracker & Lock Timer</p>
        </div>

        {/* Loading State */}
        {loading ? (
          <Card className="glass-panel border-white/10">
            <CardContent className="p-8 flex items-center justify-center">
              <Loader2 className="w-6 h-6 text-cyan-400 animate-spin mr-2" />
              <span className="text-slate-400">Loading saved settings...</span>
            </CardContent>
          </Card>
        ) : (
        <>
        {/* Setup Card */}
        <Card className="glass-panel border-white/10" data-testid="setup-card">
          <CardHeader>
            <CardTitle className="text-xl text-white flex items-center gap-2">
              <Wifi className="w-5 h-5 text-cyan-400" />
              Connection Setup
            </CardTitle>
            <CardDescription className="text-slate-400">
              Enter your Boat Beacon AIS connection details
            </CardDescription>
          </CardHeader>
          
          <CardContent className="space-y-6">
            {/* IP Address */}
            <div className="space-y-2">
              <Label htmlFor="ip" className="text-slate-300">
                Boat Beacon IP Address <span className="text-red-400">*</span>
              </Label>
              <Input
                id="ip"
                data-testid="ip-input"
                placeholder="192.168.1.100"
                value={ipAddress}
                onChange={(e) => setIpAddress(e.target.value)}
                className="bg-slate-950 border-slate-700 text-white font-mono placeholder:text-slate-600 focus:border-cyan-500"
              />
              <p className="text-xs text-slate-500">
                Find this in Boat Beacon app under Settings → AIS Output
              </p>
            </div>

            {/* Port */}
            <div className="space-y-2">
              <Label htmlFor="port" className="text-slate-300">Port</Label>
              <Input
                id="port"
                data-testid="port-input"
                placeholder="5353"
                value={port}
                onChange={(e) => setPort(e.target.value)}
                className="bg-slate-950 border-slate-700 text-white font-mono placeholder:text-slate-600 focus:border-cyan-500"
              />
            </div>

            {/* MMSI */}
            <div className="space-y-2">
              <Label htmlFor="mmsi" className="text-slate-300">
                Your Vessel MMSI <span className="text-red-400">*</span>
              </Label>
              <Input
                id="mmsi"
                data-testid="mmsi-input"
                placeholder="123456789"
                value={userMmsi}
                onChange={(e) => setUserMmsi(e.target.value)}
                className="bg-slate-950 border-slate-700 text-white font-mono placeholder:text-slate-600 focus:border-cyan-500"
              />
              <p className="text-xs text-slate-500">
                Your 9-digit Maritime Mobile Service Identity number
                {userMmsi && <span className="text-cyan-400 ml-1">• Saved for next time</span>}
              </p>
            </div>

            {/* Test Result */}
            {testResult && (
              <div className={`p-4 rounded-lg border ${testResult.success ? 'bg-green-900/20 border-green-500/30' : 'bg-red-900/20 border-red-500/30'}`}>
                <div className="flex items-center gap-2">
                  {testResult.success ? (
                    <CheckCircle2 className="w-5 h-5 text-green-400" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-red-400" />
                  )}
                  <span className={testResult.success ? 'text-green-400' : 'text-red-400'}>
                    {testResult.message}
                  </span>
                </div>
              </div>
            )}

            {/* Buttons */}
            <div className="flex gap-3 pt-4">
              <Button
                variant="outline"
                onClick={handleTestConnection}
                disabled={testing || !ipAddress}
                className="flex-1 border-slate-600 text-slate-300 hover:bg-slate-800 hover:text-white"
                data-testid="test-connection-btn"
              >
                {testing ? (
                  <span className="spinner mr-2" />
                ) : (
                  <Wifi className="w-4 h-4 mr-2" />
                )}
                Test Connection
              </Button>
              
              <Button
                onClick={handleConnect}
                disabled={!ipAddress || !userMmsi}
                className="flex-1 bg-cyan-500 hover:bg-cyan-400 text-black font-bold btn-hover"
                data-testid="connect-btn"
              >
                <Ship className="w-4 h-4 mr-2" />
                Connect
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Info Section */}
        <div className="mt-6 p-4 rounded-lg bg-slate-900/50 border border-slate-800">
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Quick Start</h3>
          <ol className="text-xs text-slate-500 space-y-1 list-decimal list-inside">
            <li>Open Boat Beacon on your mobile device</li>
            <li>Go to Settings → AIS Output → Enable TCP Server</li>
            <li>Note the IP address shown in the app</li>
            <li>Enter the IP address and your vessel's MMSI above</li>
          </ol>
        </div>

        {/* Network Note */}
        <div className="mt-4 p-4 rounded-lg bg-amber-900/20 border border-amber-500/30">
          <h3 className="text-sm font-semibold text-amber-400 mb-2">⚠️ Network Note</h3>
          <p className="text-xs text-slate-400">
            This app runs on a cloud server and <strong>cannot connect to local network IPs</strong> (192.168.x.x). 
            For testing, use <strong>Demo Mode</strong> on the dashboard. For live AIS data, you'll need to 
            either run this app locally or use a public IP/port forwarding.
          </p>
        </div>

        {/* Pool Info */}
        <div className="mt-4 grid grid-cols-3 gap-2">
          <div className="p-2 rounded-lg bg-slate-900/50 border border-slate-800 text-center">
            <div className="text-[10px] text-slate-500 uppercase">Lock 2</div>
            <div className="text-white font-mono text-xs">RM 815</div>
          </div>
          <div className="p-2 rounded-lg bg-slate-900/50 border border-slate-800 text-center">
            <div className="text-[10px] text-slate-500 uppercase">Lock 5</div>
            <div className="text-white font-mono text-xs">RM 738</div>
          </div>
          <div className="p-2 rounded-lg bg-slate-900/50 border border-slate-800 text-center">
            <div className="text-[10px] text-slate-500 uppercase">Lock 10</div>
            <div className="text-white font-mono text-xs">RM 615</div>
          </div>
        </div>
        </>
        )}
      </div>
    </div>
  );
}
