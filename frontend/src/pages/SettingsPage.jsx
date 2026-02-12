import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { 
  Settings, Ship, Gauge, Anchor, Save, ArrowLeft, 
  Wifi, Bell, MapPin, AlertTriangle, Plus, Trash2, Users,
  Navigation, Crosshair, Loader2, Ban, Terminal, Shield,
  UserPlus, UserMinus, Eye, EyeOff, RefreshCw, BarChart3,
  Key, Search, ChevronRight
} from "lucide-react";
import { toast } from "sonner";
import VesselManagement from "@/components/VesselManagement";
import RawDataPanel from "@/components/RawDataPanel";
import { useAuth } from "@/context/AuthContext";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function SettingsPage({ onBack, initialSettings = {} }) {
  const { user } = useAuth();
  
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
  
  // Illinois River filter toggle
  const [illinoisFilterEnabled, setIllinoisFilterEnabled] = useState(true);
  const [filterStats, setFilterStats] = useState({ passed: 0, filtered: 0 });
  
  // User vessel simulation
  const [userSimEnabled, setUserSimEnabled] = useState(false);
  const [userSimRiverMile, setUserSimRiverMile] = useState("815.0");
  const [userSimSpeed, setUserSimSpeed] = useState("5.0");
  const [userSimHeading, setUserSimHeading] = useState("southbound");
  
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

  // Admin state
  const [adminStats, setAdminStats] = useState(null);
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminVessels, setAdminVessels] = useState([]);
  const [adminLoading, setAdminLoading] = useState(false);
  const [userSearchQuery, setUserSearchQuery] = useState("");
  const [showCreateUserDialog, setShowCreateUserDialog] = useState(false);
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserName, setNewUserName] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserIsAdmin, setNewUserIsAdmin] = useState(false);
  const [selectedUserForAction, setSelectedUserForAction] = useState(null);
  const [showResetPasswordDialog, setShowResetPasswordDialog] = useState(false);
  const [resetPasswordValue, setResetPasswordValue] = useState("");
  
  // Account type (mode toggle)
  const [accountType, setAccountType] = useState(user?.account_type || "vessel_owner");
  const [modeToggleLoading, setModeToggleLoading] = useState(false);

  // Demo vessel editor
  const [demoVessels, setDemoVessels] = useState([]);
  const [editingDemoVessel, setEditingDemoVessel] = useState(null);
  const [demoVesselEdit, setDemoVesselEdit] = useState({
    river_mile: "",
    speed: "",
    heading: "southbound",
    barge_count: ""
  });

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

  // Toggle account type (vessel owner <-> traffic watch)
  const toggleAccountType = async () => {
    setModeToggleLoading(true);
    const newType = accountType === "vessel_owner" ? "traffic_watch" : "vessel_owner";
    
    try {
      const response = await fetch(`${API}/user/account-type`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ account_type: newType })
      });
      
      if (response.ok) {
        setAccountType(newType);
        toast.success(`Switched to ${newType === "vessel_owner" ? "Vessel Owner" : "Traffic Watch"} mode`);
        // Reload page to apply changes
        setTimeout(() => window.location.reload(), 1000);
      } else {
        toast.error("Failed to switch mode");
      }
    } catch (error) {
      console.error("Failed to toggle account type:", error);
      toast.error("Failed to switch mode");
    } finally {
      setModeToggleLoading(false);
    }
  };

  // Admin functions
  const loadAdminStats = async () => {
    try {
      const response = await fetch(`${API}/admin/stats`, { credentials: "include" });
      if (response.ok) {
        const data = await response.json();
        setAdminStats(data);
      }
    } catch (error) {
      console.error("Failed to load admin stats:", error);
    }
  };

  const loadAdminUsers = async (search = "") => {
    setAdminLoading(true);
    try {
      const url = search ? `${API}/admin/users?search=${encodeURIComponent(search)}` : `${API}/admin/users`;
      const response = await fetch(url, { credentials: "include" });
      if (response.ok) {
        const data = await response.json();
        setAdminUsers(data.users);
      }
    } catch (error) {
      console.error("Failed to load admin users:", error);
    } finally {
      setAdminLoading(false);
    }
  };

  const loadAdminVessels = async () => {
    try {
      const response = await fetch(`${API}/admin/vessels`, { credentials: "include" });
      if (response.ok) {
        const data = await response.json();
        setAdminVessels(data.vessels);
      }
    } catch (error) {
      console.error("Failed to load admin vessels:", error);
    }
  };

  const createUser = async () => {
    if (!newUserEmail) {
      toast.error("Email is required");
      return;
    }
    
    try {
      const response = await fetch(`${API}/admin/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: newUserEmail,
          name: newUserName,
          password: newUserPassword,
          is_admin: newUserIsAdmin
        })
      });
      
      if (response.ok) {
        toast.success("User created successfully");
        setShowCreateUserDialog(false);
        setNewUserEmail("");
        setNewUserName("");
        setNewUserPassword("");
        setNewUserIsAdmin(false);
        loadAdminUsers();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Failed to create user");
      }
    } catch (error) {
      console.error("Failed to create user:", error);
      toast.error("Failed to create user");
    }
  };

  const deleteUser = async (userId) => {
    if (!window.confirm("Are you sure you want to delete this user?")) return;
    
    try {
      const response = await fetch(`${API}/admin/users/${userId}`, {
        method: "DELETE",
        credentials: "include"
      });
      
      if (response.ok) {
        toast.success("User deleted");
        loadAdminUsers();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Failed to delete user");
      }
    } catch (error) {
      console.error("Failed to delete user:", error);
      toast.error("Failed to delete user");
    }
  };

  const toggleUserAdmin = async (userId, currentIsAdmin) => {
    const endpoint = currentIsAdmin ? "demote" : "promote";
    
    try {
      const response = await fetch(`${API}/admin/users/${userId}/${endpoint}`, {
        method: "POST",
        credentials: "include"
      });
      
      if (response.ok) {
        toast.success(currentIsAdmin ? "User demoted from admin" : "User promoted to admin");
        loadAdminUsers();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Failed to update user");
      }
    } catch (error) {
      console.error("Failed to toggle admin:", error);
      toast.error("Failed to update user");
    }
  };

  const resetUserPassword = async () => {
    if (!selectedUserForAction || !resetPasswordValue) {
      toast.error("Password is required");
      return;
    }
    
    try {
      const response = await fetch(`${API}/admin/users/${selectedUserForAction.user_id}/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ password: resetPasswordValue })
      });
      
      if (response.ok) {
        toast.success("Password reset successfully");
        setShowResetPasswordDialog(false);
        setResetPasswordValue("");
        setSelectedUserForAction(null);
      } else {
        const error = await response.json();
        toast.error(error.detail || "Failed to reset password");
      }
    } catch (error) {
      console.error("Failed to reset password:", error);
      toast.error("Failed to reset password");
    }
  };

  const impersonateUser = async (userId) => {
    if (!window.confirm("You will be logged in as this user. Continue?")) return;
    
    try {
      const response = await fetch(`${API}/admin/impersonate/${userId}`, {
        method: "POST",
        credentials: "include"
      });
      
      if (response.ok) {
        toast.success("Impersonating user - reloading...");
        setTimeout(() => window.location.reload(), 1000);
      } else {
        const error = await response.json();
        toast.error(error.detail || "Failed to impersonate user");
      }
    } catch (error) {
      console.error("Failed to impersonate:", error);
      toast.error("Failed to impersonate user");
    }
  };

  // Load admin data when admin tab is visible
  useEffect(() => {
    if (user?.is_admin || user?.is_super_admin) {
      loadAdminStats();
      loadAdminUsers();
      loadAdminVessels();
    }
  }, [user]);

  // Load account type on mount
  useEffect(() => {
    const loadAccountType = async () => {
      try {
        const response = await fetch(`${API}/user/account-type`, { credentials: "include" });
        if (response.ok) {
          const data = await response.json();
          setAccountType(data.account_type);
        }
      } catch (error) {
        console.error("Failed to load account type:", error);
      }
    };
    loadAccountType();
  }, []);

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

  // Load Illinois River filter status
  const loadFilterStatus = async () => {
    try {
      const response = await fetch(`${API}/filter/stats`);
      if (response.ok) {
        const data = await response.json();
        setIllinoisFilterEnabled(data.enabled);
        setFilterStats({ passed: data.passed, filtered: data.filtered });
      }
    } catch (error) {
      console.error("Failed to load filter status:", error);
    }
  };

  // Toggle Illinois River filter
  const toggleIllinoisFilter = async (enabled) => {
    try {
      const response = await fetch(`${API}/filter/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled })
      });
      if (response.ok) {
        const data = await response.json();
        setIllinoisFilterEnabled(data.enabled);
        toast.success(`Illinois River filter ${data.enabled ? 'enabled' : 'disabled'}`);
      }
    } catch (error) {
      toast.error("Failed to toggle filter");
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

  // Load user vessel simulation status
  const loadUserSimulation = async () => {
    if (!userMmsi) return;
    try {
      const response = await fetch(`${API}/user-vessel/simulation/${userMmsi}`);
      if (response.ok) {
        const data = await response.json();
        setUserSimEnabled(data.simulation_enabled || false);
        setUserSimRiverMile(data.river_mile?.toString() || "815.0");
        setUserSimSpeed(data.speed_knots?.toString() || "5.0");
        setUserSimHeading(data.heading || "southbound");
      }
    } catch (error) {
      console.error("Failed to load user simulation:", error);
    }
  };

  // Update user vessel simulation
  const updateUserSimulation = async (enabled) => {
    if (!userMmsi) {
      toast.error("No vessel MMSI configured");
      return;
    }
    try {
      const response = await fetch(`${API}/user-vessel/simulation/${userMmsi}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: enabled,
          river_mile: parseFloat(userSimRiverMile) || 815.0,
          speed_knots: parseFloat(userSimSpeed) || 5.0,
          heading: userSimHeading
        })
      });
      if (response.ok) {
        setUserSimEnabled(enabled);
        toast.success(enabled ? "Vessel simulation started" : "Vessel simulation stopped");
      }
    } catch (error) {
      toast.error("Failed to update simulation");
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

  // Load demo vessels for editing
  const loadDemoVessels = async () => {
    try {
      const response = await fetch(`${API}/demo-vessels`);
      if (response.ok) {
        const data = await response.json();
        setDemoVessels(data.demo_vessels || []);
      }
    } catch (error) {
      console.error("Failed to load demo vessels:", error);
    }
  };

  // Update demo vessel position
  const updateDemoVesselPosition = async (mmsi) => {
    try {
      const updates = {};
      if (demoVesselEdit.river_mile) updates.river_mile = parseFloat(demoVesselEdit.river_mile);
      if (demoVesselEdit.speed) updates.speed = parseFloat(demoVesselEdit.speed);
      if (demoVesselEdit.heading) updates.heading = demoVesselEdit.heading;
      if (demoVesselEdit.barge_count) updates.barge_count = parseInt(demoVesselEdit.barge_count);

      const response = await fetch(`${API}/demo-vessels/${mmsi}/position`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates)
      });

      if (response.ok) {
        toast.success("Demo vessel position updated");
        setEditingDemoVessel(null);
        loadDemoVessels();
      } else {
        toast.error("Failed to update position");
      }
    } catch (error) {
      toast.error("Failed to update demo vessel");
    }
  };

  // Start editing a demo vessel
  const startEditDemoVessel = (vessel) => {
    setEditingDemoVessel(vessel.mmsi);
    setDemoVesselEdit({
      river_mile: vessel.river_mile?.toString() || "",
      speed: vessel.speed?.toString() || "",
      heading: vessel.heading || "southbound",
      barge_count: vessel.barge_count?.toString() || ""
    });
  };

  // Resume auto-movement for a demo vessel
  const resumeDemoVessel = async (mmsi) => {
    try {
      const response = await fetch(`${API}/demo-vessels/${mmsi}/resume`, {
        method: "POST"
      });
      if (response.ok) {
        toast.success("Resumed auto-movement");
        loadDemoVessels();
      }
    } catch (error) {
      toast.error("Failed to resume");
    }
  };

  // Resume all demo vessels
  const resumeAllDemoVessels = async () => {
    try {
      const response = await fetch(`${API}/demo-vessels/resume-all`, {
        method: "POST"
      });
      if (response.ok) {
        toast.success("Resumed all demo vessels");
        loadDemoVessels();
      }
    } catch (error) {
      toast.error("Failed to resume");
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
    loadDemoVessels();
    loadFilterStatus();
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
          {/* Vessel Information - Only show for Vessel Owners */}
          {accountType !== "traffic_watch" && (
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
          )}

          {/* Fleet Management - Only show for Vessel Owners */}
          {accountType !== "traffic_watch" && <VesselManagement />}

          {/* Self Position - Only show for Vessel Owners */}
          {accountType !== "traffic_watch" && (
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
          )}

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

              {/* Demo Vessel Position Editor */}
              {demoVesselsEnabled && demoVessels.length > 0 && (
                <div className="space-y-3 p-3 bg-slate-800/50 rounded-lg border border-slate-700">
                  <div className="flex items-center justify-between">
                    <Label className="text-cyan-400 text-sm font-semibold">Edit Demo Vessel Positions</Label>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={loadDemoVessels}
                      className="h-6 px-2 text-slate-400 hover:text-white"
                    >
                      <RefreshCw className="w-3 h-3 mr-1" />
                      Refresh
                    </Button>
                  </div>
                  
                  {demoVessels.map((vessel) => (
                    <div key={vessel.mmsi} className="p-2 bg-slate-900 rounded border border-slate-700">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-white font-medium text-sm">{vessel.name}</span>
                        <Badge className="bg-amber-500/20 text-amber-400 text-[10px]">
                          RM {vessel.river_mile?.toFixed(1)}
                        </Badge>
                      </div>
                      
                      {editingDemoVessel === vessel.mmsi ? (
                        <div className="space-y-2">
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <Label className="text-[10px] text-slate-500">River Mile</Label>
                              <Input
                                type="number"
                                value={demoVesselEdit.river_mile}
                                onChange={(e) => setDemoVesselEdit({...demoVesselEdit, river_mile: e.target.value})}
                                className="h-7 text-xs bg-slate-950 border-slate-600"
                                placeholder="e.g., 815.0"
                              />
                            </div>
                            <div>
                              <Label className="text-[10px] text-slate-500">Speed (knots)</Label>
                              <Input
                                type="number"
                                value={demoVesselEdit.speed}
                                onChange={(e) => setDemoVesselEdit({...demoVesselEdit, speed: e.target.value})}
                                className="h-7 text-xs bg-slate-950 border-slate-600"
                                placeholder="e.g., 5.0"
                              />
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <Label className="text-[10px] text-slate-500">Heading</Label>
                              <select
                                value={demoVesselEdit.heading}
                                onChange={(e) => setDemoVesselEdit({...demoVesselEdit, heading: e.target.value})}
                                className="w-full h-7 text-xs bg-slate-950 border border-slate-600 rounded px-2 text-white"
                              >
                                <option value="northbound">Northbound (Upriver)</option>
                                <option value="southbound">Southbound (Downriver)</option>
                              </select>
                            </div>
                            <div>
                              <Label className="text-[10px] text-slate-500">Barge Count</Label>
                              <Input
                                type="number"
                                value={demoVesselEdit.barge_count}
                                onChange={(e) => setDemoVesselEdit({...demoVesselEdit, barge_count: e.target.value})}
                                className="h-7 text-xs bg-slate-950 border-slate-600"
                                placeholder="e.g., 6"
                              />
                            </div>
                          </div>
                          <div className="flex gap-2 pt-1">
                            <Button
                              size="sm"
                              onClick={() => updateDemoVesselPosition(vessel.mmsi)}
                              className="h-6 px-2 text-xs bg-cyan-600 hover:bg-cyan-500"
                            >
                              Save (Pauses Auto)
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setEditingDemoVessel(null)}
                              className="h-6 px-2 text-xs text-slate-400"
                            >
                              Cancel
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between">
                          <div className="text-[10px] text-slate-400 space-x-3">
                            <span>{vessel.heading === 'northbound' ? '↑ Upriver' : '↓ Downriver'}</span>
                            <span>{vessel.speed?.toFixed(1)} kts</span>
                            <span>{vessel.barge_count}B</span>
                            {vessel.paused && (
                              <span className="text-amber-400 font-semibold">⏸ PAUSED</span>
                            )}
                          </div>
                          <div className="flex gap-1">
                            {vessel.paused && (
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => resumeDemoVessel(vessel.mmsi)}
                                className="h-6 px-2 text-xs text-green-400 hover:text-white"
                              >
                                Resume
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => startEditDemoVessel(vessel)}
                              className="h-6 px-2 text-xs text-cyan-400 hover:text-white"
                            >
                              Edit
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                  
                  {/* Resume All button if any are paused */}
                  {demoVessels.some(v => v.paused) && (
                    <Button
                      size="sm"
                      onClick={resumeAllDemoVessels}
                      className="w-full h-7 text-xs bg-green-600 hover:bg-green-500"
                    >
                      Resume All Auto-Movement
                    </Button>
                  )}
                </div>
              )}

              {/* Illinois River Filter Toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-slate-300">Filter Illinois River</Label>
                  <p className="text-xs text-slate-500">
                    Only show vessels on Upper Mississippi (hide Illinois River traffic)
                  </p>
                  {filterStats.filtered > 0 && (
                    <p className="text-[10px] text-amber-400 mt-1">
                      {filterStats.passed} passed, {filterStats.filtered} filtered
                    </p>
                  )}
                </div>
                <Switch
                  checked={illinoisFilterEnabled}
                  onCheckedChange={(checked) => toggleIllinoisFilter(checked)}
                  data-testid="settings-illinois-filter"
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

          {/* Alert Settings - Only show for Vessel Owners */}
          {accountType !== "traffic_watch" && (
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
          )}

          {/* Mode Toggle - Switch between Vessel Owner and Traffic Watch */}
          <Card className="glass-panel border-white/10">
            <CardHeader>
              <CardTitle className="text-lg text-white flex items-center gap-2">
                <Eye className="w-5 h-5 text-purple-400" />
                Account Mode
              </CardTitle>
              <CardDescription className="text-slate-400">
                Switch between Vessel Owner and Traffic Watch modes
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between p-4 rounded-lg bg-slate-800/50 border border-slate-700">
                <div className="flex items-center gap-3">
                  {accountType === "vessel_owner" ? (
                    <Ship className="w-6 h-6 text-cyan-400" />
                  ) : (
                    <Eye className="w-6 h-6 text-purple-400" />
                  )}
                  <div>
                    <div className="text-white font-medium">
                      {accountType === "vessel_owner" ? "Vessel Owner" : "Traffic Watch"}
                    </div>
                    <div className="text-xs text-slate-400">
                      {accountType === "vessel_owner" 
                        ? "Track your vessel, get lock timing and race analysis" 
                        : "Monitor traffic without a vessel"}
                    </div>
                  </div>
                </div>
                <Button
                  onClick={toggleAccountType}
                  disabled={modeToggleLoading}
                  variant="outline"
                  className="border-slate-600 text-slate-300 hover:bg-slate-700"
                >
                  {modeToggleLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  ) : null}
                  Switch to {accountType === "vessel_owner" ? "Traffic Watch" : "Vessel Owner"}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Admin Panel - Only visible to admins */}
          {(user?.is_admin || user?.is_super_admin) && (
            <Card className="glass-panel border-amber-500/30">
              <CardHeader>
                <CardTitle className="text-lg text-white flex items-center gap-2">
                  <Shield className="w-5 h-5 text-amber-400" />
                  Admin Panel
                  {user?.is_super_admin && (
                    <Badge className="ml-2 bg-amber-500/20 text-amber-400 border-amber-500/50">
                      Super Admin
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription className="text-slate-400">
                  Manage users, vessels, and system settings
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Tabs defaultValue="stats" className="w-full">
                  <TabsList className="w-full bg-slate-800/50 mb-4">
                    <TabsTrigger value="stats" className="flex-1">
                      <BarChart3 className="w-4 h-4 mr-2" />
                      Stats
                    </TabsTrigger>
                    <TabsTrigger value="users" className="flex-1">
                      <Users className="w-4 h-4 mr-2" />
                      Users
                    </TabsTrigger>
                    <TabsTrigger value="vessels" className="flex-1">
                      <Ship className="w-4 h-4 mr-2" />
                      Vessels
                    </TabsTrigger>
                  </TabsList>
                  
                  {/* Stats Tab */}
                  <TabsContent value="stats" className="space-y-4">
                    <div className="flex justify-end">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          loadAdminStats();
                          loadAdminUsers();
                          loadAdminVessels();
                        }}
                        className="border-slate-600"
                      >
                        <RefreshCw className="w-4 h-4 mr-2" />
                        Refresh
                      </Button>
                    </div>
                    
                    {adminStats ? (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="p-4 bg-slate-800/50 rounded-lg text-center">
                          <div className="text-2xl font-bold text-cyan-400">{adminStats.users?.total || 0}</div>
                          <div className="text-xs text-slate-400">Total Users</div>
                        </div>
                        <div className="p-4 bg-slate-800/50 rounded-lg text-center">
                          <div className="text-2xl font-bold text-amber-400">{adminStats.users?.admins || 0}</div>
                          <div className="text-xs text-slate-400">Admins</div>
                        </div>
                        <div className="p-4 bg-slate-800/50 rounded-lg text-center">
                          <div className="text-2xl font-bold text-green-400">{adminStats.sessions?.active || 0}</div>
                          <div className="text-xs text-slate-400">Active Sessions</div>
                        </div>
                        <div className="p-4 bg-slate-800/50 rounded-lg text-center">
                          <div className="text-2xl font-bold text-purple-400">{adminStats.vessels?.currently_tracked || 0}</div>
                          <div className="text-xs text-slate-400">Vessels Tracked</div>
                        </div>
                        <div className="p-4 bg-slate-800/50 rounded-lg text-center">
                          <div className="text-2xl font-bold text-cyan-400">{adminStats.users?.vessel_owners || 0}</div>
                          <div className="text-xs text-slate-400">Vessel Owners</div>
                        </div>
                        <div className="p-4 bg-slate-800/50 rounded-lg text-center">
                          <div className="text-2xl font-bold text-purple-400">{adminStats.users?.traffic_watchers || 0}</div>
                          <div className="text-xs text-slate-400">Traffic Watchers</div>
                        </div>
                        <div className="p-4 bg-slate-800/50 rounded-lg text-center">
                          <div className="text-2xl font-bold text-green-400">{adminStats.users?.recent_signups || 0}</div>
                          <div className="text-xs text-slate-400">New (7 days)</div>
                        </div>
                        <div className="p-4 bg-slate-800/50 rounded-lg text-center">
                          <div className="text-2xl font-bold text-slate-400">{adminStats.lockages?.total_recorded || 0}</div>
                          <div className="text-xs text-slate-400">Lockages Recorded</div>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-8 text-slate-500">
                        <Loader2 className="w-8 h-8 animate-spin mx-auto mb-2" />
                        Loading stats...
                      </div>
                    )}
                  </TabsContent>
                  
                  {/* Users Tab */}
                  <TabsContent value="users" className="space-y-4">
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <Input
                          placeholder="Search users by email or name..."
                          value={userSearchQuery}
                          onChange={(e) => {
                            setUserSearchQuery(e.target.value);
                            loadAdminUsers(e.target.value);
                          }}
                          className="bg-slate-800/50 border-slate-700 text-white pl-10"
                        />
                      </div>
                      <Button
                        onClick={() => setShowCreateUserDialog(true)}
                        className="bg-cyan-600 hover:bg-cyan-500"
                      >
                        <UserPlus className="w-4 h-4 mr-2" />
                        Add User
                      </Button>
                    </div>
                    
                    <ScrollArea className="h-[300px]">
                      {adminLoading ? (
                        <div className="text-center py-8 text-slate-500">
                          <Loader2 className="w-8 h-8 animate-spin mx-auto mb-2" />
                          Loading users...
                        </div>
                      ) : adminUsers.length > 0 ? (
                        <div className="space-y-2">
                          {adminUsers.map((u) => (
                            <div
                              key={u.user_id}
                              className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700"
                            >
                              <div className="flex items-center gap-3">
                                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                                  u.is_super_admin ? 'bg-amber-500/20' : u.is_admin ? 'bg-cyan-500/20' : 'bg-slate-700'
                                }`}>
                                  {u.is_super_admin ? (
                                    <Shield className="w-4 h-4 text-amber-400" />
                                  ) : u.is_admin ? (
                                    <Shield className="w-4 h-4 text-cyan-400" />
                                  ) : (
                                    <Users className="w-4 h-4 text-slate-400" />
                                  )}
                                </div>
                                <div>
                                  <div className="text-white text-sm font-medium">{u.name || "No name"}</div>
                                  <div className="text-xs text-slate-400">{u.email}</div>
                                  <div className="flex items-center gap-2 mt-1">
                                    <Badge className={`text-[10px] ${
                                      u.account_type === "traffic_watch" 
                                        ? "bg-purple-500/20 text-purple-400" 
                                        : "bg-cyan-500/20 text-cyan-400"
                                    }`}>
                                      {u.account_type === "traffic_watch" ? "Traffic Watch" : "Vessel Owner"}
                                    </Badge>
                                    {u.is_super_admin && (
                                      <Badge className="text-[10px] bg-amber-500/20 text-amber-400">Super Admin</Badge>
                                    )}
                                    {u.is_admin && !u.is_super_admin && (
                                      <Badge className="text-[10px] bg-cyan-500/20 text-cyan-400">Admin</Badge>
                                    )}
                                  </div>
                                </div>
                              </div>
                              <div className="flex items-center gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => impersonateUser(u.user_id)}
                                  className="text-slate-400 hover:text-white"
                                  title="View as this user"
                                >
                                  <Eye className="w-4 h-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    setSelectedUserForAction(u);
                                    setShowResetPasswordDialog(true);
                                  }}
                                  className="text-slate-400 hover:text-white"
                                  title="Reset password"
                                >
                                  <Key className="w-4 h-4" />
                                </Button>
                                {user?.is_super_admin && !u.is_super_admin && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => toggleUserAdmin(u.user_id, u.is_admin)}
                                    className={u.is_admin ? "text-amber-400 hover:text-amber-300" : "text-slate-400 hover:text-cyan-400"}
                                    title={u.is_admin ? "Demote from admin" : "Promote to admin"}
                                  >
                                    {u.is_admin ? <UserMinus className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
                                  </Button>
                                )}
                                {!u.is_super_admin && u.user_id !== user?.user_id && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => deleteUser(u.user_id)}
                                    className="text-slate-400 hover:text-red-400"
                                    title="Delete user"
                                  >
                                    <Trash2 className="w-4 h-4" />
                                  </Button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-center py-8 text-slate-500">No users found</div>
                      )}
                    </ScrollArea>
                  </TabsContent>
                  
                  {/* Vessels Tab */}
                  <TabsContent value="vessels" className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="text-sm text-slate-400">
                        {adminVessels.length} vessels currently being tracked
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={loadAdminVessels}
                        className="border-slate-600"
                      >
                        <RefreshCw className="w-4 h-4 mr-2" />
                        Refresh
                      </Button>
                    </div>
                    
                    <ScrollArea className="h-[300px]">
                      {adminVessels.length > 0 ? (
                        <div className="space-y-2">
                          {adminVessels.map((v) => (
                            <div
                              key={v.mmsi}
                              className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700"
                            >
                              <div className="flex items-center gap-3">
                                <Ship className={`w-5 h-5 ${v.is_tow ? 'text-amber-400' : 'text-cyan-400'}`} />
                                <div>
                                  <div className="text-white text-sm font-medium">
                                    {v.name || `Vessel ${v.mmsi}`}
                                  </div>
                                  <div className="text-xs text-slate-400">
                                    MMSI: {v.mmsi} • RM {v.river_mile?.toFixed(1) || '--'}
                                  </div>
                                  <div className="flex items-center gap-2 mt-1">
                                    <span className={`text-[10px] ${
                                      v.heading === 'northbound' ? 'text-green-400' : 
                                      v.heading === 'southbound' ? 'text-red-400' : 'text-slate-500'
                                    }`}>
                                      {v.heading === 'northbound' ? '↑ North' : v.heading === 'southbound' ? '↓ South' : 'Stationary'}
                                    </span>
                                    {v.is_tow && (
                                      <Badge className="text-[10px] bg-amber-500/20 text-amber-400">
                                        Tow {v.barge_count > 0 ? `(${v.barge_count}B)` : ''}
                                      </Badge>
                                    )}
                                  </div>
                                </div>
                              </div>
                              <div className="text-right">
                                <div className="text-sm text-white">{(v.speed * 1.15078).toFixed(1)} mph</div>
                                <div className="text-xs text-slate-500">{v.speed?.toFixed(1)} kn</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-center py-8 text-slate-500">No vessels currently tracked</div>
                      )}
                    </ScrollArea>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          )}

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
      
      {/* Create User Dialog */}
      <Dialog open={showCreateUserDialog} onOpenChange={setShowCreateUserDialog}>
        <DialogContent className="bg-slate-900 border-slate-700">
          <DialogHeader>
            <DialogTitle className="text-white">Create New User</DialogTitle>
            <DialogDescription className="text-slate-400">
              Add a new user to the system
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-slate-300">Email *</Label>
              <Input
                type="email"
                value={newUserEmail}
                onChange={(e) => setNewUserEmail(e.target.value)}
                className="bg-slate-800 border-slate-700 text-white"
                placeholder="user@example.com"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">Name</Label>
              <Input
                value={newUserName}
                onChange={(e) => setNewUserName(e.target.value)}
                className="bg-slate-800 border-slate-700 text-white"
                placeholder="John Doe"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">Password</Label>
              <Input
                type="password"
                value={newUserPassword}
                onChange={(e) => setNewUserPassword(e.target.value)}
                className="bg-slate-800 border-slate-700 text-white"
                placeholder="Leave blank for no password (Google only)"
              />
            </div>
            {user?.is_super_admin && (
              <div className="flex items-center justify-between">
                <Label className="text-slate-300">Make Admin</Label>
                <Switch
                  checked={newUserIsAdmin}
                  onCheckedChange={setNewUserIsAdmin}
                />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateUserDialog(false)} className="border-slate-600">
              Cancel
            </Button>
            <Button onClick={createUser} className="bg-cyan-600 hover:bg-cyan-500">
              Create User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      
      {/* Reset Password Dialog */}
      <Dialog open={showResetPasswordDialog} onOpenChange={setShowResetPasswordDialog}>
        <DialogContent className="bg-slate-900 border-slate-700">
          <DialogHeader>
            <DialogTitle className="text-white">Reset Password</DialogTitle>
            <DialogDescription className="text-slate-400">
              Set a new password for {selectedUserForAction?.email}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-slate-300">New Password</Label>
              <Input
                type="password"
                value={resetPasswordValue}
                onChange={(e) => setResetPasswordValue(e.target.value)}
                className="bg-slate-800 border-slate-700 text-white"
                placeholder="Enter new password"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowResetPasswordDialog(false)} className="border-slate-600">
              Cancel
            </Button>
            <Button onClick={resetUserPassword} className="bg-cyan-600 hover:bg-cyan-500">
              Reset Password
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
