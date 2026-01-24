import { useState, useEffect, useCallback, useRef } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";
import Dashboard from "@/pages/Dashboard";
import SetupPage from "@/pages/SetupPage";
import SettingsPage from "@/pages/SettingsPage";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const WS_URL = BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://');

function App() {
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
    show_buoys: false, // Hide buoys (MMSI starting with 99) by default
    lock_buffer_minutes: 20, // Buffer time needed before commercial tow arrives
    use_device_gps: false, // Enable continuous GPS tracking
    show_vessel_names: true, // Show vessel names when available (vs MMSI)
  });
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const geoWatchRef = useRef(null);
  const autoRefreshRef = useRef(null);
  const [lastRefresh, setLastRefresh] = useState(Date.now());

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
    
    // Clear accumulated vessels older than 5 minutes
    setVessels(prev => {
      const fiveMinutesAgo = Date.now() - 5 * 60 * 1000;
      return prev.filter(v => {
        const timestamp = new Date(v.timestamp).getTime();
        return timestamp > fiveMinutesAgo;
      });
    });
    
    setLastRefresh(Date.now());
    
    // Force refetch lock status and lockage times
    try {
      const [lockStatusRes, lockageRes] = await Promise.all([
        fetch(`${API}/locks/status`),
        fetch(`${API}/locks/lockage-times`)
      ]);
      
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

  // Load saved settings on mount
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const response = await fetch(`${API}/settings`);
        if (response.ok) {
          const settings = await response.json();
          if (settings.user_mmsi) {
            setUserMmsi(settings.user_mmsi);
          }
          if (settings.default_lock) {
            setSelectedLock(settings.default_lock);
          }
          // Load user settings
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
  useEffect(() => {
    const fetchVessels = async () => {
      try {
        const response = await fetch(`${API}/vessels`);
        if (response.ok) {
          const data = await response.json();
          setVessels(data);
        }
      } catch (error) {
        console.error("Failed to fetch vessels:", error);
      }
    };

    // Fetch immediately on mount
    fetchVessels();
    
    // Reduce polling to every 15 seconds (WebSocket handles real-time updates)
    const interval = setInterval(fetchVessels, 15000);
    return () => clearInterval(interval);
  }, []);

  // Fetch race analysis periodically
  useEffect(() => {
    const fetchRaceAnalysis = async () => {
      if (!selectedLock) return;
      try {
        const bufferMinutes = userSettings.lock_buffer_minutes || 20;
        const response = await fetch(`${API}/race-analysis/${selectedLock}?buffer_minutes=${bufferMinutes}`);
        if (response.ok) {
          const data = await response.json();
          setRaceAnalysis(data);
        }
      } catch (error) {
        console.error("Failed to fetch race analysis:", error);
      }
    };

    fetchRaceAnalysis();
    // Reduced frequency - race analysis doesn't need to update every 5s
    const interval = setInterval(fetchRaceAnalysis, 10000);
    return () => clearInterval(interval);
  }, [selectedLock, userSettings.lock_buffer_minutes]); // Removed vessels dependency to prevent excessive re-fetches

  // Continuous GPS tracking (bypasses AIS self-suppression)
  useEffect(() => {
    // Send position update to backend
    const sendPositionUpdate = async (position) => {
      const { latitude, longitude, speed, heading } = position.coords;
      try {
        const response = await fetch(`${API}/user-position`, {
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
        toast.success(data.message);
      } else if (data.type === "disconnected") {
        toast.info(data.message);
      } else if (data.type === "error") {
        toast.error(data.message);
      } else if (data.type === "vessel_update") {
        // Optimized: Use functional update with early bailout if no change needed
        setVessels(prev => {
          const mmsi = data.vessel.mmsi;
          const existingIdx = prev.findIndex(v => v.mmsi === mmsi);
          
          if (existingIdx >= 0) {
            // Check if vessel data actually changed to avoid unnecessary re-renders
            const existing = prev[existingIdx];
            if (existing.lat === data.vessel.lat && 
                existing.lon === data.vessel.lon && 
                existing.speed === data.vessel.speed) {
              return prev; // No change, return same reference
            }
            const updated = [...prev];
            updated[existingIdx] = data.vessel;
            return updated;
          }
          // Limit total vessels to prevent unbounded growth
          if (prev.length >= 100) {
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
        const limited = data.vessels.slice(0, 100);
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
    if (connectionConfig && !isConnected && !wsRef.current) {
      console.log("Auto-connecting to AIS server:", connectionConfig.ip_address, connectionConfig.port);
      connectWebSocket(connectionConfig);
    }
  }, [connectionConfig, isConnected, connectWebSocket]);

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
    
    // Save settings
    try {
      await fetch(`${API}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_mmsi: config.user_mmsi,
          connection_config: JSON.stringify(config)
        })
      });
      
      await fetch(`${API}/set-user-mmsi`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mmsi: config.user_mmsi })
      });
    } catch (error) {
      console.error("Failed to save settings:", error);
    }
    
    connectWebSocket(config);
  };

  const handleDisconnect = () => {
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ action: "disconnect" }));
      wsRef.current.close();
    }
    setIsConnected(false);
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
  };

  const handleResetConnection = () => {
    handleDisconnect();
    setConnectionConfig(null);
    setVessels([]);
  };

  const handleSettingsUpdate = async (newSettings) => {
    setUserSettings(prev => ({ ...prev, ...newSettings }));
    if (newSettings.user_mmsi) {
      setUserMmsi(newSettings.user_mmsi);
    }
    if (newSettings.default_lock) {
      setSelectedLock(newSettings.default_lock);
    }
    setShowSettings(false);
    
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

  return (
    <div className="app-container bg-[#020617] min-h-screen">
      <BrowserRouter>
        <Routes>
          <Route 
            path="/" 
            element={
              connectionConfig ? (
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
              )
            } 
          />
          <Route 
            path="/setup" 
            element={<SetupPage onConnect={handleConnect} />} 
          />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" theme="dark" />
    </div>
  );
}

export default App;
