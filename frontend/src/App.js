import { useState, useEffect, useCallback, useRef } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";
import Dashboard from "@/pages/Dashboard";
import SetupPage from "@/pages/SetupPage";
import SettingsPage from "@/pages/SettingsPage";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import LandingPage from "@/pages/LandingPage";
import AuthCallback from "@/pages/AuthCallback";
import { AuthProvider, useAuth } from "@/context/AuthContext";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const WS_URL = BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://');

// Protected Route wrapper
function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
          <span className="font-heading text-sm uppercase tracking-wider text-slate-400">Loading...</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

// App Router - Check for auth callback first
function AppRouter() {
  const location = useLocation();
  const { isAuthenticated } = useAuth();
  
  // Check URL hash for session_id (Google OAuth callback)
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }
  
  return (
    <Routes>
      {/* Landing page - redirect to dashboard if already logged in */}
      <Route path="/" element={
        isAuthenticated ? <Navigate to="/dashboard" replace /> : <LandingPage />
      } />
      <Route path="/login" element={
        isAuthenticated ? <Navigate to="/dashboard" replace /> : <LoginPage />
      } />
      <Route path="/register" element={
        isAuthenticated ? <Navigate to="/dashboard" replace /> : <RegisterPage />
      } />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/dashboard" element={
        <ProtectedRoute>
          <MainApp />
        </ProtectedRoute>
      } />
      {/* Catch-all redirect to landing or dashboard */}
      <Route path="*" element={
        isAuthenticated ? <Navigate to="/dashboard" replace /> : <Navigate to="/" replace />
      } />
    </Routes>
  );
}

function MainApp() {
  const { user } = useAuth();
  const [isConnected, setIsConnected] = useState(false);
  const [connectionConfig, setConnectionConfig] = useState(null);
  const [vessels, setVessels] = useState([]);
  const [userMmsi, setUserMmsi] = useState("");
  const [locks, setLocks] = useState([]);
  const [lockStatus, setLockStatus] = useState({});
  const [lockageTimes, setLockageTimes] = useState({});
  const [raceAnalysis, setRaceAnalysis] = useState(null);
  const [selectedLock, setSelectedLock] = useState("lock_2");
  const [showSettings, setShowSettings] = useState(false);
  const [userSettings, setUserSettings] = useState({
    max_speed_mph: 25,
    map_zoom_miles: 25,
    show_all_locks: true,
    alert_sound_enabled: true,
    alert_speed_threshold: 25,
    show_buoys: false,
    lock_buffer_minutes: 20,
    use_device_gps: false,
    show_vessel_names: true,
  });
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const geoWatchRef = useRef(null);
  const autoRefreshRef = useRef(null);
  const [lastRefresh, setLastRefresh] = useState(Date.now());

  // Load primary vessel from user account
  useEffect(() => {
    if (user?.vessels?.length > 0) {
      const primaryVessel = user.vessels.find(v => v.is_primary) || user.vessels[0];
      if (primaryVessel) {
        setUserMmsi(primaryVessel.mmsi);
        // Auto-configure connection if we have a vessel
        const storedConfig = localStorage.getItem('riverwatch_connection');
        if (storedConfig) {
          const config = JSON.parse(storedConfig);
          config.user_mmsi = primaryVessel.mmsi;
          config.boat_name = primaryVessel.boat_name;
          setConnectionConfig(config);
        }
      }
    }
  }, [user]);

  // Clear all session data when user logs out
  useEffect(() => {
    if (!user) {
      // User logged out - clear all vessel and session data
      setVessels([]);
      setRaceAnalysis(null);
      setUserMmsi("");
      setConnectionConfig(null);
      setIsConnected(false);
      // Close WebSocket if connected
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      console.log("User logged out - cleared all session data");
    }
  }, [user]);

  // Full app refresh - clears stale data and reconnects
  const performFullRefresh = useCallback(() => {
    console.log("Performing full refresh...");
    
    // Clear vessels to prevent stale data accumulation
    setVessels([]);
    setRaceAnalysis(null);
    
    // Close and reconnect WebSocket
    if (wsRef.current) {
      wsRef.current.close();
    }
    
    // Update refresh timestamp
    setLastRefresh(Date.now());
    
    // Refetch all data
    window.location.reload();
  }, []);

  // Soft refresh - just refetch data without page reload
  const performSoftRefresh = useCallback(async () => {
    console.log("Performing soft refresh...");
    
    setLastRefresh(Date.now());
    
    // Force refetch vessels, lock status, and lockage times
    try {
      const [vesselsRes, lockStatusRes, lockageRes] = await Promise.all([
        fetch(`${API}/vessels`),
        fetch(`${API}/locks/status`),
        fetch(`${API}/locks/lockage-times`)
      ]);
      
      // Update vessels
      if (vesselsRes.ok) {
        const vesselsData = await vesselsRes.json();
        setVessels(vesselsData);
      }
      
      if (lockStatusRes.ok) {
        const statusData = await lockStatusRes.json();
        const statusMap = {};
        statusData.forEach(lock => {
          statusMap[lock.lock_id] = lock;
        });
        setLockStatus(statusMap);
      }
      
      if (lockageRes.ok) {
        const lockageData = await lockageRes.json();
        const timesMap = {};
        lockageData.forEach(lock => {
          timesMap[lock.lock_id] = {
            avg_tow_lockage_minutes: lock.avg_tow_lockage_minutes,
            avg_recreational_lockage_minutes: lock.avg_recreational_lockage_minutes,
            avg_tow_wait_minutes: lock.avg_tow_wait_minutes,
            avg_recreational_wait_minutes: lock.avg_recreational_wait_minutes,
            sample_count: lock.sample_count,
            is_baseline: lock.is_baseline,
          };
        });
        setLockageTimes(timesMap);
      }
    } catch (error) {
      console.error("Soft refresh failed:", error);
    }
  }, []);

  // Auto-refresh every 15 minutes to prevent memory buildup
  useEffect(() => {
    autoRefreshRef.current = setInterval(() => {
      console.log("Auto soft-refresh triggered");
      performSoftRefresh();
    }, 15 * 60 * 1000); // 15 minutes
    
    return () => {
      if (autoRefreshRef.current) {
        clearInterval(autoRefreshRef.current);
      }
    };
  }, [performSoftRefresh]);

  // Load saved settings on mount - check localStorage for MMSI first
  useEffect(() => {
    const loadSettings = async () => {
      try {
        // Check localStorage for stored MMSI (persists across sessions)
        const storedMmsi = localStorage.getItem('riverwatch_mmsi');
        
        if (storedMmsi) {
          // Load user-specific settings
          setUserMmsi(storedMmsi);
          const response = await fetch(`${API}/user/${storedMmsi}/settings`);
          if (response.ok) {
            const data = await response.json();
            const settings = data.settings || {};
            
            if (settings.default_lock) {
              setSelectedLock(settings.default_lock);
            }
            setUserSettings(prev => ({
              ...prev,
              max_speed_mph: parseInt(settings.max_speed_mph) || 25,
              map_zoom_miles: parseInt(settings.map_zoom_miles) || 25,
              show_all_locks: settings.show_all_locks !== false,
              alert_sound_enabled: settings.alert_sound_enabled !== false,
              alert_speed_threshold: parseInt(settings.alert_speed_threshold) || 25,
              boat_name: settings.boat_name || "",
              show_buoys: settings.show_buoys === true,
              lock_buffer_minutes: parseInt(settings.lock_buffer_minutes) || 20,
              use_device_gps: settings.use_device_gps === true,
              show_vessel_names: settings.show_vessel_names !== false,
            }));
            if (settings.connection_config) {
              const config = typeof settings.connection_config === 'string' 
                ? JSON.parse(settings.connection_config) 
                : settings.connection_config;
              setConnectionConfig(config);
            }
            console.log(`Loaded settings for MMSI: ${storedMmsi}`);
          }
        } else {
          // No stored MMSI - try legacy global settings
          const response = await fetch(`${API}/settings`);
          if (response.ok) {
            const settings = await response.json();
            if (settings.user_mmsi) {
              setUserMmsi(settings.user_mmsi);
              // Store in localStorage for future sessions
              localStorage.setItem('riverwatch_mmsi', settings.user_mmsi);
            }
            if (settings.default_lock) {
              setSelectedLock(settings.default_lock);
            }
            setUserSettings(prev => ({
              ...prev,
              max_speed_mph: parseInt(settings.max_speed_mph) || 25,
              map_zoom_miles: parseInt(settings.map_zoom_miles) || 25,
              show_all_locks: settings.show_all_locks !== "false",
              alert_sound_enabled: settings.alert_sound_enabled !== "false",
              alert_speed_threshold: parseInt(settings.alert_speed_threshold) || 25,
              boat_name: settings.boat_name || "",
              show_buoys: settings.show_buoys === "true",
              lock_buffer_minutes: parseInt(settings.lock_buffer_minutes) || 20,
              use_device_gps: settings.use_device_gps === "true",
              show_vessel_names: settings.show_vessel_names !== "false",
            }));
            if (settings.connection_config) {
              const config = JSON.parse(settings.connection_config);
              setConnectionConfig(config);
            }
          }
        }
      } catch (error) {
        console.error("Failed to load settings:", error);
      }
    };

    const loadLocks = async () => {
      try {
        const response = await fetch(`${API}/locks`);
        if (response.ok) {
          const data = await response.json();
          setLocks(data);
        }
      } catch (error) {
        console.error("Failed to load locks:", error);
      }
    };

    loadSettings();
    loadLocks();
  }, []);

  // Fetch lock status from USACE
  useEffect(() => {
    const fetchLockStatus = async () => {
      try {
        const response = await fetch(`${API}/locks/status`);
        if (response.ok) {
          const data = await response.json();
          // Convert to map by lock_id
          const statusMap = {};
          data.forEach(lock => {
            statusMap[lock.lock_id] = lock;
          });
          setLockStatus(statusMap);
        }
      } catch (error) {
        console.error("Failed to fetch lock status:", error);
      }
    };

    fetchLockStatus();
    // Refresh every 5 minutes
    const interval = setInterval(fetchLockStatus, 300000);
    return () => clearInterval(interval);
  }, []);

  // Fetch lockage time averages from LPMS
  useEffect(() => {
    const fetchLockageTimes = async () => {
      try {
        const response = await fetch(`${API}/locks/lockage-times`);
        if (response.ok) {
          const data = await response.json();
          // Convert to map by lock_id
          const timesMap = {};
          data.forEach(lock => {
            timesMap[lock.lock_id] = {
              avg_tow_lockage_minutes: lock.avg_tow_lockage_minutes,
              avg_recreational_lockage_minutes: lock.avg_recreational_lockage_minutes,
              avg_tow_wait_minutes: lock.avg_tow_wait_minutes,
              avg_recreational_wait_minutes: lock.avg_recreational_wait_minutes,
              sample_count: lock.sample_count,
              is_baseline: lock.is_baseline,
              upbound: lock.upbound,
              downbound: lock.downbound
            };
          });
          setLockageTimes(timesMap);
        }
      } catch (error) {
        console.error("Failed to fetch lockage times:", error);
      }
    };

    fetchLockageTimes();
    // Refresh every 10 minutes
    const interval = setInterval(fetchLockageTimes, 600000);
    return () => clearInterval(interval);
  }, []);

  // Periodic vessel fetch (backup for when WebSocket isn't providing updates)
  // OPTIMIZED: Increased interval from 15s to 30s - WebSocket handles real-time
  useEffect(() => {
    const fetchVessels = async () => {
      try {
        const response = await fetch(`${API}/vessels`);
        if (response.ok) {
          const data = await response.json();
          // Only update if data actually changed (compare length and first/last MMSI)
          setVessels(prev => {
            if (prev.length === data.length && 
                prev[0]?.mmsi === data[0]?.mmsi &&
                prev[prev.length-1]?.mmsi === data[data.length-1]?.mmsi) {
              return prev; // No change
            }
            return data;
          });
        }
      } catch (error) {
        console.error("Failed to fetch vessels:", error);
      }
    };

    // Fetch immediately on mount
    fetchVessels();
    
    // OPTIMIZED: Reduced polling to every 30 seconds (WebSocket handles real-time updates)
    const interval = setInterval(fetchVessels, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fetch race analysis periodically - EXPLICITLY scoped to session MMSI
  // OPTIMIZED: Increased interval from 10s to 20s
  useEffect(() => {
    const fetchRaceAnalysis = async () => {
      if (!selectedLock || !userMmsi) return;
      try {
        const bufferMinutes = userSettings.lock_buffer_minutes || 20;
        // Use session-scoped endpoint
        const response = await fetch(`${API}/session/${userMmsi}/race-analysis/${selectedLock}?buffer_minutes=${bufferMinutes}`);
        if (response.ok) {
          const data = await response.json();
          // Only update if analysis actually changed
          setRaceAnalysis(prev => {
            if (prev && JSON.stringify(prev) === JSON.stringify(data)) {
              return prev;
            }
            return data;
          });
        }
      } catch (error) {
        console.error("Failed to fetch race analysis:", error);
      }
    };

    fetchRaceAnalysis();
    // OPTIMIZED: Reduced frequency from 10s to 20s
    const interval = setInterval(fetchRaceAnalysis, 20000);
    return () => clearInterval(interval);
  }, [selectedLock, userMmsi, userSettings.lock_buffer_minutes]);

  // Continuous GPS tracking (bypasses AIS self-suppression) - EXPLICITLY scoped to session MMSI
  useEffect(() => {
    // Send position update to backend
    const sendPositionUpdate = async (position) => {
      if (!userMmsi) return; // Must have session MMSI
      
      const { latitude, longitude, speed, heading } = position.coords;
      try {
        // Use session-scoped endpoint
        const response = await fetch(`${API}/session/${userMmsi}/position`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            lat: latitude,
            lon: longitude,
            speed: speed ? speed * 1.94384 : 0, // m/s to knots
            course: heading || 0,
            source: "geolocation"
          })
        });
        
        if (response.ok) {
          const data = await response.json();
          // Update local vessels list with the user vessel
          if (data.vessel) {
            setVessels(prev => {
              const mmsi = data.vessel.mmsi;
              const existing = prev.findIndex(v => v.mmsi === mmsi);
              if (existing >= 0) {
                const updated = [...prev];
                updated[existing] = data.vessel;
                return updated;
              }
              return [...prev, data.vessel];
            });
          }
        }
      } catch (error) {
        console.error("Failed to send GPS position:", error);
      }
    };

    // Start/stop geolocation watch based on settings
    if (userSettings.use_device_gps && navigator.geolocation) {
      // Clear any existing watch
      if (geoWatchRef.current) {
        navigator.geolocation.clearWatch(geoWatchRef.current);
      }
      
      // Start watching position
      geoWatchRef.current = navigator.geolocation.watchPosition(
        sendPositionUpdate,
        (error) => {
          console.error("Geolocation error:", error.message);
        },
        { 
          enableHighAccuracy: true, 
          timeout: 15000, 
          maximumAge: 5000 // Allow cached position up to 5 seconds old
        }
      );
      
      console.log("Started GPS tracking");
    } else if (geoWatchRef.current) {
      // Stop watching if disabled
      navigator.geolocation.clearWatch(geoWatchRef.current);
      geoWatchRef.current = null;
      console.log("Stopped GPS tracking");
    }

    return () => {
      if (geoWatchRef.current) {
        navigator.geolocation.clearWatch(geoWatchRef.current);
      }
    };
  }, [userSettings.use_device_gps]);

  // WebSocket connection
  const connectWebSocket = useCallback((config) => {
    if (!config) return;
    
    // Clear any pending reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    // Close existing connection if any
    if (wsRef.current) {
      const oldWs = wsRef.current;
      wsRef.current = null;
      oldWs.onclose = null; // Prevent triggering reconnect from old socket
      oldWs.close();
    }

    console.log("Connecting to WebSocket with config:", config.ip_address, config.port);
    const ws = new WebSocket(`${WS_URL}/ws/ais`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket connected, sending connection request...");
      setIsConnected(true);
      // Send connection config including boat name for proper identification
      ws.send(JSON.stringify({
        action: "connect",
        ip_address: config.ip_address,
        port: config.port,
        user_mmsi: config.user_mmsi,
        boat_name: userSettings.boat_name || config.boat_name || ""
      }));
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === "connected") {
        // Silently log - don't toast to avoid spam across sessions
        console.log("AIS feed status:", data.message);
      } else if (data.type === "disconnected") {
        // Only log, don't toast - this fires for all subscribers
        console.log("AIS feed status:", data.message);
      } else if (data.type === "error") {
        // Only show errors to the user
        toast.error(data.message);
      } else if (data.type === "vessel_update") {
        // OPTIMIZED: Throttle vessel updates - batch them every 2 seconds
        // This prevents excessive re-renders from rapid AIS messages
        setVessels(prev => {
          const mmsi = data.vessel.mmsi;
          const existingIdx = prev.findIndex(v => v.mmsi === mmsi);
          
          if (existingIdx >= 0) {
            // Check if vessel data actually changed meaningfully
            const existing = prev[existingIdx];
            // Only update if position changed by more than 0.0001 degrees (~10m)
            // or speed changed by more than 0.5 knots
            const latDiff = Math.abs((existing.lat || 0) - (data.vessel.lat || 0));
            const lonDiff = Math.abs((existing.lon || 0) - (data.vessel.lon || 0));
            const speedDiff = Math.abs((existing.speed || 0) - (data.vessel.speed || 0));
            
            if (latDiff < 0.0001 && lonDiff < 0.0001 && speedDiff < 0.5) {
              return prev; // No significant change, skip update
            }
            const updated = [...prev];
            updated[existingIdx] = data.vessel;
            return updated;
          }
          // Limit total vessels to prevent unbounded growth
          if (prev.length >= 75) { // Reduced from 100
            // Remove oldest vessel (by timestamp) before adding new one
            const sorted = [...prev].sort((a, b) => 
              new Date(a.timestamp) - new Date(b.timestamp)
            );
            return [...sorted.slice(1), data.vessel];
          }
          return [...prev, data.vessel];
        });
      } else if (data.type === "vessels") {
        // Full vessel list update - limit size
        const limited = data.vessels.slice(0, 75); // Reduced from 100
        setVessels(limited);
      }
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };

    ws.onclose = () => {
      // Only handle if this is still our active socket
      if (wsRef.current === ws) {
        wsRef.current = null;
        setIsConnected(false);
        // Attempt reconnect after 5 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          if (config) {
            connectWebSocket(config);
          }
        }, 5000);
      }
    };
  }, [userSettings.boat_name]);

  // Auto-connect when we have config but aren't connected
  useEffect(() => {
    // Only auto-connect if we have config, aren't connected, AND no socket exists
    // The reconnect logic in onclose handles reconnection, so we only trigger initial connect
    if (connectionConfig && !isConnected && !wsRef.current && !reconnectTimeoutRef.current) {
      console.log("Auto-connecting to AIS server:", connectionConfig.ip_address, connectionConfig.port);
      connectWebSocket(connectionConfig);
    }
  }, [connectionConfig]); // Removed isConnected to prevent reconnect loops

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  const handleConnect = async (config) => {
    setConnectionConfig(config);
    setUserMmsi(config.user_mmsi);
    
    // Store MMSI in localStorage for session persistence
    localStorage.setItem('riverwatch_mmsi', config.user_mmsi);
    
    // Save user-specific settings
    try {
      await fetch(`${API}/user/${config.user_mmsi}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          connection_config: config,
          boat_name: config.boat_name || userSettings.boat_name || ""
        })
      });
      console.log(`Saved settings for MMSI: ${config.user_mmsi}`);
    } catch (error) {
      console.error("Failed to save user settings:", error);
    }
    
    connectWebSocket(config);
  };

  const handleDisconnect = () => {
    if (wsRef.current) {
      // Only try to send if the socket is open (readyState === 1)
      if (wsRef.current.readyState === WebSocket.OPEN) {
        try {
          wsRef.current.send(JSON.stringify({ action: "disconnect" }));
        } catch (e) {
          console.warn("Failed to send disconnect message:", e);
        }
      }
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  };

  const handleResetConnection = () => {
    handleDisconnect();
    setConnectionConfig(null);
    setVessels([]);
    // Clear stored MMSI so user can enter a different one
    localStorage.removeItem('riverwatch_mmsi');
    setUserMmsi("");
  };

  const handleSettingsUpdate = async (newSettings) => {
    setUserSettings(prev => ({ ...prev, ...newSettings }));
    if (newSettings.user_mmsi) {
      setUserMmsi(newSettings.user_mmsi);
      localStorage.setItem('riverwatch_mmsi', newSettings.user_mmsi);
    }
    if (newSettings.default_lock) {
      setSelectedLock(newSettings.default_lock);
    }
    setShowSettings(false);
    
    // Save user-specific settings if we have an MMSI
    const mmsiToSave = newSettings.user_mmsi || userMmsi || localStorage.getItem('riverwatch_mmsi');
    if (mmsiToSave) {
      try {
        await fetch(`${API}/user/${mmsiToSave}/settings`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...newSettings,
            connection_config: connectionConfig
          })
        });
        console.log(`Settings saved for MMSI: ${mmsiToSave}`);
      } catch (error) {
        console.error("Failed to save user settings:", error);
      }
    }
    
    // Refresh vessels after settings update (in case position was set manually)
    try {
      const response = await fetch(`${API}/vessels`);
      if (response.ok) {
        const data = await response.json();
        setVessels(data);
      }
    } catch (error) {
      console.error("Failed to refresh vessels after settings:", error);
    }
  };

  // If showing settings page
  if (showSettings) {
    return (
      <div className="app-container bg-[#020617] min-h-screen">
        <SettingsPage 
          onBack={handleSettingsUpdate}
          initialSettings={userSettings}
        />
        <Toaster position="top-right" theme="dark" />
      </div>
    );
  }

  // Main dashboard or setup page based on connection state
  return (
    <div className="app-container bg-[#020617] min-h-screen">
      {connectionConfig ? (
        <Dashboard 
          isConnected={isConnected}
          vessels={vessels
            .filter(v => v.mmsi !== "2339005") // Filter Boat Beacon UK test signal
            .filter(v => userSettings.show_buoys || !v.mmsi?.toString().startsWith("99"))
          }
          userMmsi={userMmsi}
          locks={locks}
          lockStatus={lockStatus}
          lockageTimes={lockageTimes}
          raceAnalysis={raceAnalysis}
          selectedLock={selectedLock}
          onSelectLock={setSelectedLock}
          onDisconnect={handleDisconnect}
          onResetConnection={handleResetConnection}
          onReconnect={() => connectWebSocket(connectionConfig)}
          onOpenSettings={() => setShowSettings(true)}
          connectionConfig={connectionConfig}
          userSettings={userSettings}
          onRefresh={performSoftRefresh}
          onFullRefresh={performFullRefresh}
          lastRefresh={lastRefresh}
        />
      ) : (
        <SetupPage onConnect={handleConnect} />
      )}
      <Toaster position="top-right" theme="dark" />
    </div>
  );
}

// Root App component - wraps everything with BrowserRouter and AuthProvider
function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRouter />
      </AuthProvider>
      <Toaster position="top-right" theme="dark" />
    </BrowserRouter>
  );
}

export default App;
