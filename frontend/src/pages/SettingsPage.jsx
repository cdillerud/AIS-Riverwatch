import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { 
  Settings, Ship, Gauge, Anchor, Save, ArrowLeft, 
  Wifi, Bell, MapPin, AlertTriangle, Plus, Trash2, Users,
  Navigation, Crosshair, Loader2, Ban, Terminal
} from "lucide-react";
import { toast } from "sonner";
import VesselManagement from "@/components/VesselManagement";
import RawDataPanel from "@/components/RawDataPanel";
import { useAuth } from "@/context/AuthContext";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function SettingsPage({ onBack, initialSettings = {} }) {
  const [settings, setSettings] = useState({
    user_mmsi: "",
    boat_name: "",
    max_speed_mph: 25,
    last_ip: "",
    last_port: "5353",
    default_lock: "lock_2",
    alert_sound_enabled: true,
    alert_speed_threshold: 25,
    show_all_locks: true,
    map_zoom_miles: 25,
    show_buoys: false,
    lock_buffer_minutes: 20,
    use_device_gps: false,
    show_vessel_names: true,
    ...initialSettings
  });
  
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  
  // Demo vessel toggle
  const [demoVesselsEnabled, setDemoVesselsEnabled] = useState(true);
  const [demoToggleLoading, setDemoToggleLoading] = useState(false);
  
  // Vessel name cache management
  const [vesselCache, setVesselCache] = useState({});
  const [newVesselMmsi, setNewVesselMmsi] = useState("");
  const [newVesselName, setNewVesselName] = useState("");
  
  // Blocked MMSI management
  const [blockedMmsi, setBlockedMmsi] = useState([]);
  const [newBlockedMmsi, setNewBlockedMmsi] = useState("");
  const [newBlockedReason, setNewBlockedReason] = useState("");
  
  // Self-position management
  const [manualLat, setManualLat] = useState("");
  const [manualLon, setManualLon] = useState("");
  const [manualSpeed, setManualSpeed] = useState("");
  const [manualCourse, setManualCourse] = useState("");
  const [manualRiverMile, setManualRiverMile] = useState("");
  const [geoStatus, setGeoStatus] = useState("idle"); // "idle", "getting", "active", "error"
  const [lastGeoUpdate, setLastGeoUpdate] = useState(null);
  const [lastPositionResult, setLastPositionResult] = useState(null);

  // Load demo vessel status on mount
  const loadDemoVesselsStatus = async () => {
    try {
      const response = await fetch(`${API}/demo-vessels/status`);
      if (response.ok) {
        const data = await response.json();
        setDemoVesselsEnabled(data.enabled);
      }
    } catch (error) {
      console.error("Failed to load demo vessels status:", error);
    }
  };

  // Toggle demo vessels
  const toggleDemoVessels = async (enabled) => {
    setDemoToggleLoading(true);
    try {
      const response = await fetch(`${API}/demo-vessels/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ enabled })
      });
      
      if (response.ok) {
        const data = await response.json();
        setDemoVesselsEnabled(data.enabled);
        toast.success(data.enabled ? "Demo vessels enabled" : "Demo vessels disabled");
      } else {
        toast.error("Failed to toggle demo vessels");
      }
    } catch (error) {
      console.error("Failed to toggle demo vessels:", error);
      toast.error("Failed to toggle demo vessels");
    } finally {
      setDemoToggleLoading(false);
    }
  };

  // Convert River Mile to lat/lon
  const convertRiverMileToCoords = async (rm) => {
    try {
      const response = await fetch(`${API}/river-mile-to-coords/${rm}`);
      if (response.ok) {
        const data = await response.json();
        setManualLat(data.lat.toString());
        setManualLon(data.lon.toString());
        return data;
      }
    } catch (error) {
      console.error("Failed to convert river mile:", error);
      toast.error("Failed to convert river mile");
    }
  };

  // Handle River Mile input change
  const handleRiverMileChange = async (value) => {
    setManualRiverMile(value);
    const rm = parseFloat(value);
    // Upper Mississippi: Lock 27 at RM 185 to Lock 1 at RM 848
    if (!isNaN(rm) && rm >= 100 && rm <= 900) {
      await convertRiverMileToCoords(rm);
    }
  };

  // Load blocked MMSIs
  const loadBlockedMmsi = async () => {
    try {
      const response = await fetch(`${API}/blocked-mmsi`);
      if (response.ok) {
        const data = await response.json();
        setBlockedMmsi(data.blocked || []);
      }
    } catch (error) {
      console.error("Failed to load blocked MMSIs:", error);
    }
  };

  // Add MMSI to block list
  const addBlockedMmsi = async () => {
    if (!newBlockedMmsi.trim()) {
      toast.error("Please enter an MMSI to block");
      return;
    }
    
    try {
      const response = await fetch(`${API}/blocked-mmsi`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          mmsi: newBlockedMmsi.trim(),
          reason: newBlockedReason.trim() || "User blocked"
        })
      });
      
      if (response.ok) {
        toast.success(`Blocked MMSI ${newBlockedMmsi}`);
        setNewBlockedMmsi("");
        setNewBlockedReason("");
        loadBlockedMmsi();
      }
    } catch (error) {
      toast.error("Failed to block MMSI");
    }
  };

  // Remove MMSI from block list
  const removeBlockedMmsi = async (mmsi) => {
    try {
      const response = await fetch(`${API}/blocked-mmsi/${mmsi}`, {
        method: "DELETE"
      });
      
      if (response.ok) {
        toast.success(`Unblocked MMSI ${mmsi}`);
        loadBlockedMmsi();
      }
    } catch (error) {
      toast.error("Failed to unblock MMSI");
    }
  };

  // Load vessel cache
  const loadVesselCache = async () => {
    try {
      const response = await fetch(`${API}/vessel-cache`);
      if (response.ok) {
        const data = await response.json();
        setVesselCache(data.cache || {});
      }
    } catch (error) {
      console.error("Failed to load vessel cache:", error);
    }
  };

  // Add vessel name to cache
  const addVesselName = async () => {
    if (!newVesselMmsi.trim() || !newVesselName.trim()) {
      toast.error("Please enter both MMSI and vessel name");
      return;
    }
    
    try {
      const response = await fetch(`${API}/vessel-cache/${newVesselMmsi.trim()}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newVesselName.trim() })
      });
      
      if (response.ok) {
        toast.success(`Added name for MMSI ${newVesselMmsi}`);
        setNewVesselMmsi("");
        setNewVesselName("");
        loadVesselCache();
      }
    } catch (error) {
      toast.error("Failed to add vessel name");
    }
  };

  // Send position update to backend
  const sendPositionUpdate = async (lat, lon, speed = 0, course = 0, source = "manual") => {
    // Require MMSI to be set
    if (!settings.user_mmsi) {
      toast.error("Please set your MMSI in the 'Your Vessel' section first");
      return null;
    }
    
    try {
      const response = await fetch(`${API}/user-position`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          lat, 
          lon, 
          speed, 
          course, 
          source,
          mmsi: settings.user_mmsi,
          name: settings.boat_name || "Your Vessel"
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        setLastGeoUpdate(new Date());
        return data;
      } else {
        toast.error("Failed to set position");
        return null;
      }
    } catch (error) {
      console.error("Failed to update position:", error);
      toast.error("Failed to set position");
      throw error;
    }
  };

  // Get current position using browser Geolocation API
  const getCurrentPosition = () => {
    if (!navigator.geolocation) {
      toast.error("Geolocation is not supported by your browser");
      return;
    }

    setGeoStatus("getting");
    
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude, speed, heading } = position.coords;
        setManualLat(latitude.toFixed(6));
        setManualLon(longitude.toFixed(6));
        
        try {
          await sendPositionUpdate(
            latitude, 
            longitude, 
            speed ? speed * 1.94384 : 0, // m/s to knots
            heading || 0,
            "geolocation"
          );
          setGeoStatus("active");
          toast.success("Position updated from GPS!");
        } catch (error) {
          setGeoStatus("error");
          toast.error("Failed to send position to server");
        }
      },
      (error) => {
        setGeoStatus("error");
        switch (error.code) {
          case error.PERMISSION_DENIED:
            toast.error("Location permission denied. Please enable in browser settings.");
            break;
          case error.POSITION_UNAVAILABLE:
            toast.error("Location information unavailable.");
            break;
          case error.TIMEOUT:
            toast.error("Location request timed out.");
            break;
          default:
            toast.error("Failed to get location.");
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  // Submit manual position
  const submitManualPosition = async () => {
    const lat = parseFloat(manualLat);
    const lon = parseFloat(manualLon);
    const speed = parseFloat(manualSpeed) || 0;
    const course = parseFloat(manualCourse) || 0;
    
    if (isNaN(lat) || isNaN(lon)) {
      toast.error("Please enter valid latitude and longitude values");
      return;
    }
    
    if (lat < -90 || lat > 90) {
      toast.error("Latitude must be between -90 and 90");
      return;
    }
    
    if (lon < -180 || lon > 180) {
      toast.error("Longitude must be between -180 and 180");
      return;
    }
    
    // Convert speed from MPH to knots for the API
    const speedKnots = speed * 0.868976;
    
    try {
      // Disable continuous GPS tracking when setting manual position
      if (settings.use_device_gps) {
        updateSetting("use_device_gps", false);
        toast.info("Disabled GPS tracking for manual testing");
      }
      
      const result = await sendPositionUpdate(lat, lon, speedKnots, course, "manual");
      if (!result) {
        // sendPositionUpdate already showed an error toast
        return;
      }
      
      if (result?.vessel) {
        setLastPositionResult(result.vessel);
        toast.success(`Position set! River Mile: ${result.vessel.river_mile?.toFixed(1) || 'N/A'}, MMSI: ${result.vessel.mmsi}`);
        setGeoStatus("active");
      }
    } catch (error) {
      toast.error("Failed to set position");
    }
  };

  // Load settings on mount
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const response = await fetch(`${API}/settings`);
        if (response.ok) {
          const data = await response.json();
          setSettings(prev => ({
            ...prev,
            user_mmsi: data.user_mmsi || "",
            boat_name: data.boat_name || "",
            max_speed_mph: parseInt(data.max_speed_mph) || 25,
            last_ip: data.last_ip || "",
            last_port: data.last_port || "5353",
            default_lock: data.default_lock || "lock_2",
            alert_sound_enabled: data.alert_sound_enabled !== "false",
            alert_speed_threshold: parseInt(data.alert_speed_threshold) || 25,
            show_all_locks: data.show_all_locks !== "false",
            map_zoom_miles: parseInt(data.map_zoom_miles) || 25,
            show_buoys: data.show_buoys === "true",
            lock_buffer_minutes: parseInt(data.lock_buffer_minutes) || 20,
            use_device_gps: data.use_device_gps === "true",
            show_vessel_names: data.show_vessel_names !== "false",
          }));
        }
      } catch (error) {
        console.error("Failed to load settings:", error);
      } finally {
        setLoading(false);
      }
    };
    loadSettings();
    loadVesselCache();
    loadBlockedMmsi();
    loadDemoVesselsStatus();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      // Save all settings
      const settingsToSave = {
        user_mmsi: settings.user_mmsi,
        boat_name: settings.boat_name,
        max_speed_mph: settings.max_speed_mph.toString(),
        last_ip: settings.last_ip,
        last_port: settings.last_port,
        default_lock: settings.default_lock,
        alert_sound_enabled: settings.alert_sound_enabled.toString(),
        alert_speed_threshold: settings.alert_speed_threshold.toString(),
        show_all_locks: settings.show_all_locks.toString(),
        map_zoom_miles: settings.map_zoom_miles.toString(),
        show_buoys: settings.show_buoys.toString(),
        lock_buffer_minutes: settings.lock_buffer_minutes.toString(),
        use_device_gps: settings.use_device_gps.toString(),
        show_vessel_names: settings.show_vessel_names.toString(),
      };

      const response = await fetch(`${API}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settingsToSave)
      });

      if (response.ok) {
        // Also update user MMSI
        if (settings.user_mmsi) {
          await fetch(`${API}/set-user-mmsi`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mmsi: settings.user_mmsi })
          });
        }
        
        toast.success("Settings saved successfully!");
        onBack(settings);
      } else {
        toast.error("Failed to save settings");
      }
    } catch (error) {
      console.error("Save error:", error);
      toast.error("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const updateSetting = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#020617] flex items-center justify-center">
        <div className="text-slate-400">Loading settings...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#020617] p-4 md:p-6">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onBack(settings)}
            className="text-slate-400 hover:text-white"
            data-testid="back-btn"
          >
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back
          </Button>
          <div className="flex items-center gap-2">
            <Settings className="w-6 h-6 text-cyan-400" />
            <h1 className="text-2xl font-bold text-white">Settings</h1>
          </div>
        </div>

        <div className="space-y-6">
          {/* Vessel Information */}
          <Card className="glass-panel border-white/10">
            <CardHeader>
              <CardTitle className="text-lg text-white flex items-center gap-2">
                <Ship className="w-5 h-5 text-cyan-400" />
                Your Vessel
              </CardTitle>
              <CardDescription className="text-slate-400">
                Information about your boat for tracking and identification
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="mmsi" className="text-slate-300">
                    MMSI Number <span className="text-red-400">*</span>
                  </Label>
                  <Input
                    id="mmsi"
                    data-testid="settings-mmsi"
                    placeholder="123456789"
                    value={settings.user_mmsi}
                    onChange={(e) => updateSetting("user_mmsi", e.target.value)}
                    className="bg-slate-950 border-slate-700 text-white font-mono"
                  />
                  <p className="text-xs text-slate-500">9-digit Maritime Mobile Service Identity</p>
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="boatname" className="text-slate-300">Boat Name</Label>
                  <Input
                    id="boatname"
                    data-testid="settings-boatname"
                    placeholder="My Boat"
                    value={settings.boat_name}
                    onChange={(e) => updateSetting("boat_name", e.target.value)}
                    className="bg-slate-950 border-slate-700 text-white"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300">
                  Maximum Speed: <span className="text-cyan-400 font-mono">{settings.max_speed_mph} MPH</span>
                </Label>
                <Slider
                  value={[settings.max_speed_mph]}
                  onValueChange={([value]) => updateSetting("max_speed_mph", value)}
                  min={5}
                  max={50}
                  step={1}
                  className="w-full"
                  data-testid="settings-maxspeed"
                />
                <p className="text-xs text-slate-500">
                  Used to calculate if you can beat commercial vessels to the lock
                </p>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300">
                  Lock Priority Buffer: <span className="text-cyan-400 font-mono">{settings.lock_buffer_minutes} min</span>
                </Label>
                <Slider
                  value={[settings.lock_buffer_minutes]}
                  onValueChange={([value]) => updateSetting("lock_buffer_minutes", value)}
                  min={10}
                  max={45}
                  step={5}
                  className="w-full"
                  data-testid="settings-lockbuffer"
                />
                <p className="text-xs text-slate-500">
                  Minutes you need to arrive BEFORE a commercial tow to get through first. 
                  Tows always have priority - you need time to complete your lockage before they arrive.
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Fleet Management - Multiple Vessels */}
          <VesselManagement />

          {/* Self Position - Bypasses AIS self-suppression */}
          <Card className="glass-panel border-white/10 border-l-4 border-l-green-500">
            <CardHeader>
              <CardTitle className="text-lg text-white flex items-center gap-2">
                <Crosshair className="w-5 h-5 text-green-400" />
                Self Position
                {geoStatus === "active" && (
                  <Badge className="bg-green-500/20 text-green-400 border-green-500/50 text-xs ml-2">
                    Active
                  </Badge>
                )}
              </CardTitle>
              <CardDescription className="text-slate-400">
                <span className="text-amber-400 font-medium">AIS Self-Suppression Bypass:</span>{" "}
                Boat Beacon and most AIS apps intentionally filter out your own MMSI from the feed. 
                Use this to inject your position directly.
              </CardDescription>
              
              {/* Mode indicator */}
              {(settings.use_device_gps || lastPositionResult) && (
                <div className={`mt-2 p-2 rounded text-xs ${
                  settings.use_device_gps 
                    ? "bg-cyan-950/30 border border-cyan-500/30 text-cyan-400"
                    : "bg-amber-950/30 border border-amber-500/30 text-amber-400"
                }`}>
                  <span className="font-medium">Active Mode:</span>{" "}
                  {settings.use_device_gps ? "📍 Continuous GPS Tracking" : "🎯 Manual Position (testing)"}
                </div>
              )}
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Browser Geolocation */}
              <div className="p-4 rounded-lg bg-slate-900/50 border border-slate-700/50">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Navigation className="w-5 h-5 text-cyan-400" />
                    <Label className="text-white font-medium">Use Device GPS</Label>
                  </div>
                  <Button
                    onClick={getCurrentPosition}
                    disabled={geoStatus === "getting"}
                    variant="outline"
                    size="sm"
                    className="border-cyan-500/50 text-cyan-400 hover:bg-cyan-500/20"
                    data-testid="get-location-btn"
                  >
                    {geoStatus === "getting" ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                        Getting...
                      </>
                    ) : (
                      <>
                        <Crosshair className="w-4 h-4 mr-1" />
                        Get My Location
                      </>
                    )}
                  </Button>
                </div>
                <p className="text-xs text-slate-500 mb-3">
                  Uses your phone/tablet's GPS to set your position. Works if River Watch is running on your boat.
                </p>
                
                {/* Continuous tracking toggle */}
                <div className="flex items-center justify-between p-3 rounded bg-slate-800/50 border border-slate-600/50">
                  <div>
                    <Label className="text-slate-300 text-sm">Continuous GPS Tracking</Label>
                    <p className="text-xs text-slate-500">Auto-update your position as you move</p>
                  </div>
                  <Switch
                    checked={settings.use_device_gps}
                    onCheckedChange={(checked) => updateSetting("use_device_gps", checked)}
                    data-testid="settings-use-device-gps"
                  />
                </div>
                
                {lastGeoUpdate && (
                  <p className="text-xs text-green-400 mt-2">
                    Last updated: {lastGeoUpdate.toLocaleTimeString()}
                  </p>
                )}
              </div>

              {/* Manual Position Entry */}
              <div className="p-4 rounded-lg bg-slate-900/50 border border-slate-700/50">
                <div className="flex items-center gap-2 mb-3">
                  <MapPin className="w-5 h-5 text-amber-400" />
                  <Label className="text-white font-medium">Manual Position Entry</Label>
                  <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/50 text-xs">
                    Testing
                  </Badge>
                </div>
                
                {/* River Mile - Primary input for testing */}
                <div className="mb-4 p-3 rounded bg-amber-950/30 border border-amber-500/30">
                  <div className="space-y-1">
                    <Label htmlFor="rm" className="text-amber-400 text-xs font-medium">River Mile (auto-fills lat/lon)</Label>
                    <div className="flex gap-2">
                      <Input
                        id="rm"
                        type="number"
                        placeholder="830"
                        value={manualRiverMile}
                        onChange={(e) => handleRiverMileChange(e.target.value)}
                        className="bg-slate-950 border-amber-500/50 text-white font-mono text-lg"
                        data-testid="manual-river-mile"
                      />
                      <span className="flex items-center text-amber-400 text-sm whitespace-nowrap">RM</span>
                    </div>
                    <p className="text-xs text-slate-500">Enter a river mile (e.g., 830) to auto-calculate coordinates</p>
                  </div>
                </div>
                
                {/* Lat/Lon Row */}
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div className="space-y-1">
                    <Label htmlFor="lat" className="text-slate-400 text-xs">Latitude</Label>
                    <Input
                      id="lat"
                      placeholder="44.7433"
                      value={manualLat}
                      onChange={(e) => setManualLat(e.target.value)}
                      className="bg-slate-950 border-slate-700 text-white font-mono text-sm"
                      data-testid="manual-lat"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="lon" className="text-slate-400 text-xs">Longitude</Label>
                    <Input
                      id="lon"
                      placeholder="-92.8506"
                      value={manualLon}
                      onChange={(e) => setManualLon(e.target.value)}
                      className="bg-slate-950 border-slate-700 text-white font-mono text-sm"
                      data-testid="manual-lon"
                    />
                  </div>
                </div>
                
                {/* Speed/Course Row */}
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div className="space-y-1">
                    <Label htmlFor="speed" className="text-slate-400 text-xs">Speed (MPH)</Label>
                    <Input
                      id="speed"
                      type="number"
                      placeholder="12"
                      value={manualSpeed}
                      onChange={(e) => setManualSpeed(e.target.value)}
                      className="bg-slate-950 border-slate-700 text-white font-mono text-sm"
                      data-testid="manual-speed"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="course" className="text-slate-400 text-xs">Course (0-360°)</Label>
                    <Input
                      id="course"
                      type="number"
                      placeholder="180"
                      value={manualCourse}
                      onChange={(e) => setManualCourse(e.target.value)}
                      className="bg-slate-950 border-slate-700 text-white font-mono text-sm"
                      data-testid="manual-course"
                    />
                  </div>
                </div>
                
                <Button
                  onClick={submitManualPosition}
                  disabled={!manualLat || !manualLon}
                  variant="outline"
                  size="sm"
                  className="w-full border-amber-500/50 text-amber-400 hover:bg-amber-500/20"
                  data-testid="set-manual-position-btn"
                >
                  <MapPin className="w-4 h-4 mr-1" />
                  Set Position
                </Button>
                
                {/* Result display */}
                {lastPositionResult && (
                  <div className="mt-3 p-2 rounded bg-green-950/30 border border-green-500/30 text-sm">
                    <div className="flex items-center gap-2 text-green-400 font-medium mb-1">
                      <Navigation className="w-4 h-4" />
                      Position Set
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="text-slate-400">
                        River Mile: <span className="text-white font-mono">{lastPositionResult.river_mile?.toFixed(1) || 'N/A'}</span>
                      </div>
                      <div className="text-slate-400">
                        Speed: <span className="text-white font-mono">{((lastPositionResult.speed || 0) * 1.15078).toFixed(1)} MPH</span>
                      </div>
                      <div className="text-slate-400">
                        Heading: <span className="text-white font-mono">{lastPositionResult.heading || 'N/A'}</span>
                      </div>
                      <div className="text-slate-400">
                        Course: <span className="text-white font-mono">{lastPositionResult.course?.toFixed(0) || 0}°</span>
                      </div>
                    </div>
                  </div>
                )}
                
                <p className="text-xs text-slate-500 mt-2">
                  <span className="text-amber-400/70">Quick ref:</span> Lock 2 = RM 815, Lock 3 = RM 797, Lock 4 = RM 752
                  <br />
                  Course: 0°=North, 180°=South (downriver)
                </p>
              </div>

              {/* Help text */}
              <div className="text-xs text-slate-500 p-3 bg-slate-800/50 rounded-lg">
                <p className="font-medium text-slate-400 mb-1">Why is this needed?</p>
                <p>
                  Most AIS apps (including Boat Beacon) intentionally suppress your own MMSI 
                  from the data feed to prevent feedback loops. This is normal behavior - 
                  other vessels can see you, but you won't see yourself in your own feed.
                  Use one of the options above to manually inject your position.
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Connection Settings */}
          <Card className="glass-panel border-white/10">
            <CardHeader>
              <CardTitle className="text-lg text-white flex items-center gap-2">
                <Wifi className="w-5 h-5 text-cyan-400" />
                AIS Connection
              </CardTitle>
              <CardDescription className="text-slate-400">
                Boat Beacon TCP connection settings
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="ip" className="text-slate-300">Default IP Address</Label>
                  <Input
                    id="ip"
                    data-testid="settings-ip"
                    placeholder="192.168.1.100"
                    value={settings.last_ip}
                    onChange={(e) => updateSetting("last_ip", e.target.value)}
                    className="bg-slate-950 border-slate-700 text-white font-mono"
                  />
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="port" className="text-slate-300">Port</Label>
                  <Input
                    id="port"
                    data-testid="settings-port"
                    placeholder="5353"
                    value={settings.last_port}
                    onChange={(e) => updateSetting("last_port", e.target.value)}
                    className="bg-slate-950 border-slate-700 text-white font-mono"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Map Settings */}
          <Card className="glass-panel border-white/10">
            <CardHeader>
              <CardTitle className="text-lg text-white flex items-center gap-2">
                <MapPin className="w-5 h-5 text-cyan-400" />
                Map Display
              </CardTitle>
              <CardDescription className="text-slate-400">
                Customize the river map view
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-slate-300">Show All Locks</Label>
                  <p className="text-xs text-slate-500">Display all locks 2-10 on the map</p>
                </div>
                <Switch
                  checked={settings.show_all_locks}
                  onCheckedChange={(checked) => updateSetting("show_all_locks", checked)}
                  data-testid="settings-showalllocks"
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-slate-300">Show River Buoys</Label>
                  <p className="text-xs text-slate-500">Display buoys and navigation aids (MMSI 99xxxxxx)</p>
                </div>
                <Switch
                  checked={settings.show_buoys}
                  onCheckedChange={(checked) => updateSetting("show_buoys", checked)}
                  data-testid="settings-showbuoys"
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-slate-300">Show Vessel Names</Label>
                  <p className="text-xs text-slate-500">Display vessel names when available (otherwise show MMSI)</p>
                </div>
                <Switch
                  checked={settings.show_vessel_names}
                  onCheckedChange={(checked) => updateSetting("show_vessel_names", checked)}
                  data-testid="settings-showvesselnames"
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-slate-300">Show Demo Vessels</Label>
                  <p className="text-xs text-slate-500">Display simulated towboats for testing (M/V DELTA QUEEN, M/V RIVER RUNNER)</p>
                </div>
                <Switch
                  checked={demoVesselsEnabled}
                  onCheckedChange={(checked) => toggleDemoVessels(checked)}
                  disabled={demoToggleLoading}
                  data-testid="settings-demovessels"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300">
                  Zoom Range: <span className="text-cyan-400 font-mono">±{settings.map_zoom_miles} miles</span>
                </Label>
                <Slider
                  value={[settings.map_zoom_miles]}
                  onValueChange={([value]) => updateSetting("map_zoom_miles", value)}
                  min={10}
                  max={100}
                  step={5}
                  className="w-full"
                  data-testid="settings-zoomrange"
                />
                <p className="text-xs text-slate-500">
                  River miles to show around the target lock when zoomed in
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="defaultlock" className="text-slate-300">Default Target Lock</Label>
                <select
                  id="defaultlock"
                  value={settings.default_lock}
                  onChange={(e) => updateSetting("default_lock", e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-md px-3 py-2 text-white text-sm"
                  data-testid="settings-defaultlock"
                >
                  <optgroup label="Upper River (MN/WI)">
                    <option value="lock_1">Lock 1 - Minneapolis (RM 848)</option>
                    <option value="lock_2">Lock 2 - Hastings (RM 815)</option>
                    <option value="lock_3">Lock 3 - Red Wing (RM 797)</option>
                    <option value="lock_4">Lock 4 - Alma (RM 753)</option>
                    <option value="lock_5">Lock 5 - Minnesota City (RM 738)</option>
                    <option value="lock_5a">Lock 5A - Fountain City (RM 729)</option>
                    <option value="lock_6">Lock 6 - Trempealeau (RM 714)</option>
                    <option value="lock_7">Lock 7 - Dresbach (RM 703)</option>
                    <option value="lock_8">Lock 8 - Genoa (RM 679)</option>
                    <option value="lock_9">Lock 9 - Lynxville (RM 648)</option>
                    <option value="lock_10">Lock 10 - Guttenberg (RM 615)</option>
                  </optgroup>
                  <optgroup label="Middle River (IA/IL)">
                    <option value="lock_11">Lock 11 - Dubuque (RM 583)</option>
                    <option value="lock_12">Lock 12 - Bellevue (RM 557)</option>
                    <option value="lock_13">Lock 13 - Fulton (RM 523)</option>
                    <option value="lock_14">Lock 14 - Le Claire (RM 493)</option>
                    <option value="lock_15">Lock 15 - Rock Island (RM 483)</option>
                    <option value="lock_16">Lock 16 - Muscatine (RM 457)</option>
                    <option value="lock_17">Lock 17 - New Boston (RM 437)</option>
                    <option value="lock_18">Lock 18 - Gladstone (RM 411)</option>
                  </optgroup>
                  <optgroup label="Lower River (MO/IL)">
                    <option value="lock_19">Lock 19 - Keokuk (RM 364)</option>
                    <option value="lock_20">Lock 20 - Canton (RM 343)</option>
                    <option value="lock_21">Lock 21 - Quincy (RM 325)</option>
                    <option value="lock_22">Lock 22 - Saverton (RM 301)</option>
                    <option value="lock_24">Lock 24 - Clarksville (RM 273)</option>
                    <option value="lock_25">Lock 25 - Cap au Gris (RM 241)</option>
                    <option value="melvin_price">Melvin Price - Alton (RM 201)</option>
                    <option value="chain_of_rocks">Chain of Rocks (RM 185)</option>
                  </optgroup>
                </select>
              </div>
            </CardContent>
          </Card>

          {/* Known Vessel Names */}
          <Card className="glass-panel border-white/10">
            <CardHeader>
              <CardTitle className="text-lg text-white flex items-center gap-2">
                <Users className="w-5 h-5 text-cyan-400" />
                Known Vessel Names
              </CardTitle>
              <CardDescription className="text-slate-400">
                Add names for vessels you recognize. AIS sends names infrequently, so this helps identify boats faster.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Add new vessel */}
              <div className="flex gap-2">
                <div className="flex-1">
                  <Input
                    placeholder="MMSI (e.g., 367000001)"
                    value={newVesselMmsi}
                    onChange={(e) => setNewVesselMmsi(e.target.value)}
                    className="bg-slate-950 border-slate-700 text-white"
                    data-testid="new-vessel-mmsi"
                  />
                </div>
                <div className="flex-1">
                  <Input
                    placeholder="Vessel Name"
                    value={newVesselName}
                    onChange={(e) => setNewVesselName(e.target.value)}
                    className="bg-slate-950 border-slate-700 text-white"
                    data-testid="new-vessel-name"
                  />
                </div>
                <Button
                  onClick={addVesselName}
                  variant="outline"
                  className="border-cyan-500/50 text-cyan-400 hover:bg-cyan-500/20"
                  data-testid="add-vessel-btn"
                >
                  <Plus className="w-4 h-4" />
                </Button>
              </div>

              {/* List of cached vessels */}
              {Object.keys(vesselCache).length > 0 ? (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {Object.entries(vesselCache).map(([mmsi, data]) => (
                    <div 
                      key={mmsi}
                      className="flex items-center justify-between p-2 rounded bg-slate-900/50 border border-slate-700/50"
                    >
                      <div className="flex items-center gap-3">
                        <Ship className="w-4 h-4 text-amber-400" />
                        <div>
                          <div className="text-white text-sm font-medium">
                            {data.name || 'Unknown'}
                          </div>
                          <div className="text-slate-500 text-xs font-mono">
                            MMSI: {mmsi}
                          </div>
                        </div>
                      </div>
                      {data.ship_type && (
                        <Badge className="bg-slate-800 text-slate-400 text-xs">
                          Type {data.ship_type}
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-4 text-slate-500 text-sm">
                  No vessel names cached yet. Names are learned automatically from AIS Type 5 messages, or you can add them manually above.
                </div>
              )}
            </CardContent>
          </Card>

          {/* Blocked Vessels */}
          <Card className="glass-panel border-white/10 border-l-4 border-l-red-500">
            <CardHeader>
              <CardTitle className="text-lg text-white flex items-center gap-2">
                <Ban className="w-5 h-5 text-red-400" />
                Blocked Vessels
                {blockedMmsi.length > 0 && (
                  <Badge className="bg-red-500/20 text-red-400 border-red-500/50 text-xs ml-2">
                    {blockedMmsi.length}
                  </Badge>
                )}
              </CardTitle>
              <CardDescription className="text-slate-400">
                Block invalid or noisy vessels from appearing in your feed. Blocked vessels will be filtered from all views.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Add new blocked MMSI */}
              <div className="space-y-2">
                <div className="flex gap-2">
                  <div className="flex-1">
                    <Input
                      placeholder="MMSI to block (e.g., 3669167)"
                      value={newBlockedMmsi}
                      onChange={(e) => setNewBlockedMmsi(e.target.value)}
                      className="bg-slate-950 border-slate-700 text-white font-mono"
                      data-testid="block-mmsi-input"
                    />
                  </div>
                  <Button
                    onClick={addBlockedMmsi}
                    disabled={!newBlockedMmsi.trim()}
                    variant="outline"
                    className="border-red-500/50 text-red-400 hover:bg-red-500/20"
                    data-testid="block-mmsi-btn"
                  >
                    <Ban className="w-4 h-4 mr-1" />
                    Block
                  </Button>
                </div>
                <Input
                  placeholder="Reason (optional, e.g., 'Invalid position data')"
                  value={newBlockedReason}
                  onChange={(e) => setNewBlockedReason(e.target.value)}
                  className="bg-slate-950 border-slate-700 text-white text-sm"
                  data-testid="block-reason-input"
                />
              </div>

              {/* List of blocked vessels */}
              {blockedMmsi.length > 0 ? (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {blockedMmsi.map((item) => (
                    <div 
                      key={item.mmsi}
                      className="flex items-center justify-between p-2 rounded bg-red-950/30 border border-red-500/20"
                    >
                      <div className="flex items-center gap-3">
                        <Ban className="w-4 h-4 text-red-400" />
                        <div>
                          <div className="text-white text-sm font-mono">
                            MMSI: {item.mmsi}
                          </div>
                          {item.reason && (
                            <div className="text-slate-500 text-xs">
                              {item.reason}
                            </div>
                          )}
                        </div>
                      </div>
                      <Button
                        onClick={() => removeBlockedMmsi(item.mmsi)}
                        variant="ghost"
                        size="sm"
                        className="text-slate-400 hover:text-white hover:bg-slate-700"
                        data-testid={`unblock-${item.mmsi}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-4 text-slate-500 text-sm">
                  No vessels blocked. Add an MMSI above to filter out invalid or noisy vessels.
                </div>
              )}

              {/* Info about system-filtered */}
              <div className="text-xs text-slate-500 p-3 bg-slate-800/50 rounded-lg">
                <p className="font-medium text-slate-400 mb-1">System-filtered MMSIs:</p>
                <p>
                  The following are automatically filtered: test beacons (2339005), buoys (MMSI starting with 99*).
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Alert Settings */}
          <Card className="glass-panel border-white/10">
            <CardHeader>
              <CardTitle className="text-lg text-white flex items-center gap-2">
                <Bell className="w-5 h-5 text-cyan-400" />
                Alerts
              </CardTitle>
              <CardDescription className="text-slate-400">
                Configure warning notifications
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-slate-300">Sound Alerts</Label>
                  <p className="text-xs text-slate-500">Play audio when "Can't Beat" warning triggers</p>
                </div>
                <Switch
                  checked={settings.alert_sound_enabled}
                  onCheckedChange={(checked) => updateSetting("alert_sound_enabled", checked)}
                  data-testid="settings-soundalerts"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300">
                  Speed Alert Threshold: <span className="text-cyan-400 font-mono">{settings.alert_speed_threshold} MPH</span>
                </Label>
                <Slider
                  value={[settings.alert_speed_threshold]}
                  onValueChange={([value]) => updateSetting("alert_speed_threshold", value)}
                  min={10}
                  max={50}
                  step={1}
                  className="w-full"
                  data-testid="settings-alertthreshold"
                />
                <p className="text-xs text-slate-500">
                  Alert when required speed exceeds this value (usually your max speed)
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Raw AIS Data - Debug/Developer Section */}
          <Card className="glass-panel border-white/10">
            <CardHeader>
              <CardTitle className="text-lg text-white flex items-center gap-2">
                <Terminal className="w-5 h-5 text-cyan-400" />
                Raw AIS Data
              </CardTitle>
              <CardDescription className="text-slate-400">
                View raw NMEA sentences and parsed AIS messages for debugging
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-[300px] overflow-hidden rounded-lg border border-slate-700">
                <RawDataPanel isConnected={true} compact={false} />
              </div>
            </CardContent>
          </Card>

          {/* Save Button */}
          <div className="flex gap-4">
            <Button
              onClick={handleSave}
              disabled={saving || !settings.user_mmsi}
              className="flex-1 bg-cyan-500 hover:bg-cyan-400 text-black font-bold"
              data-testid="save-settings-btn"
            >
              {saving ? (
                <span className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
                  Saving...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <Save className="w-4 h-4" />
                  Save Settings
                </span>
              )}
            </Button>
          </div>

          {/* Warning if MMSI not set */}
          {!settings.user_mmsi && (
            <div className="p-4 rounded-lg bg-amber-900/20 border border-amber-500/30 flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <div className="text-amber-400 font-semibold">MMSI Required</div>
                <div className="text-sm text-slate-400">
                  Enter your vessel's MMSI number to enable tracking and race calculations.
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
