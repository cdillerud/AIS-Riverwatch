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
  Wifi, Bell, MapPin, AlertTriangle, Plus, Trash2, Users
} from "lucide-react";
import { toast } from "sonner";

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
    ...initialSettings
  });
  
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  
  // Vessel name cache management
  const [vesselCache, setVesselCache] = useState({});
  const [newVesselMmsi, setNewVesselMmsi] = useState("");
  const [newVesselName, setNewVesselName] = useState("");

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
          }));
        }
      } catch (error) {
        console.error("Failed to load settings:", error);
      } finally {
        setLoading(false);
      }
    };
    loadSettings();
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
