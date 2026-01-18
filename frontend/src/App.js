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
  const [raceAnalysis, setRaceAnalysis] = useState(null);
  const [selectedLock, setSelectedLock] = useState("lock_2");
  const [showSettings, setShowSettings] = useState(false);
  const [userSettings, setUserSettings] = useState({
    max_speed_mph: 25,
    map_zoom_miles: 25,
    show_all_locks: true,
    alert_sound_enabled: true,
    alert_speed_threshold: 25,
  });
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

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
          }));
          if (settings.connection_config) {
            setConnectionConfig(JSON.parse(settings.connection_config));
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

  // Fetch race analysis periodically
  useEffect(() => {
    const fetchRaceAnalysis = async () => {
      if (!selectedLock) return;
      try {
        const response = await fetch(`${API}/race-analysis/${selectedLock}`);
        if (response.ok) {
          const data = await response.json();
          setRaceAnalysis(data);
        }
      } catch (error) {
        console.error("Failed to fetch race analysis:", error);
      }
    };

    fetchRaceAnalysis();
    const interval = setInterval(fetchRaceAnalysis, 5000);
    return () => clearInterval(interval);
  }, [selectedLock, vessels]);

  // WebSocket connection
  const connectWebSocket = useCallback((config) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const ws = new WebSocket(`${WS_URL}/ws/ais`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket connected");
      // Send connection config
      ws.send(JSON.stringify({
        action: "connect",
        ip_address: config.ip_address,
        port: config.port,
        user_mmsi: config.user_mmsi
      }));
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === "connected") {
        setIsConnected(true);
        toast.success(data.message);
      } else if (data.type === "disconnected") {
        setIsConnected(false);
        toast.info(data.message);
      } else if (data.type === "error") {
        toast.error(data.message);
      } else if (data.type === "vessel_update") {
        setVessels(prev => {
          const existing = prev.findIndex(v => v.mmsi === data.vessel.mmsi);
          if (existing >= 0) {
            const updated = [...prev];
            updated[existing] = data.vessel;
            return updated;
          }
          return [...prev, data.vessel];
        });
      } else if (data.type === "vessels") {
        setVessels(data.vessels);
      }
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      toast.error("Connection error");
    };

    ws.onclose = () => {
      setIsConnected(false);
      // Attempt reconnect after 5 seconds if we have config
      if (connectionConfig) {
        reconnectTimeoutRef.current = setTimeout(() => {
          connectWebSocket(connectionConfig);
        }, 5000);
      }
    };
  }, [connectionConfig]);

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

  // Add demo vessels for testing
  const addDemoVessels = async () => {
    // Clear existing demo vessels first
    await fetch(`${API}/demo/clear-vessels`, { method: "DELETE" });
    
    // Add user vessel
    await fetch(`${API}/demo/add-vessel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mmsi: "123456789",
        name: "MY BOAT",
        lat: 44.82,
        lon: -92.90,
        speed: 8,
        course: 180,
        is_user_vessel: true,
        vessel_type: "recreational"
      })
    });

    // Add commercial tow with 12 barges (single lock)
    await fetch(`${API}/demo/add-tow`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mmsi: "987654321",
        name: "M/V MISS KATHY",
        lat: 44.70,
        lon: -92.80,
        speed: 4,
        course: 0,
        barge_count: 12,
        tow_config: "3x4"
      })
    });

    // Add commercial tow with 18 barges (double lock required!)
    await fetch(`${API}/demo/add-tow`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mmsi: "555555555",
        name: "M/V BIG RIVER",
        lat: 44.65,
        lon: -92.70,
        speed: 3.5,
        course: 0,
        barge_count: 18,
        tow_config: "3x6"
      })
    });

    // Add smaller tow with 6 barges
    await fetch(`${API}/demo/add-tow`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mmsi: "777777777",
        name: "M/V QUICK TRIP",
        lat: 44.55,
        lon: -92.60,
        speed: 5,
        course: 0,
        barge_count: 6,
        tow_config: "2x3"
      })
    });

    // Set user MMSI
    await fetch(`${API}/set-user-mmsi`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mmsi: "123456789" })
    });
    
    // Refresh vessels
    try {
      const response = await fetch(`${API}/vessels`);
      if (response.ok) {
        const data = await response.json();
        setVessels(data);
      }
    } catch (error) {
      console.error("Failed to refresh vessels:", error);
    }
    
    toast.success("Demo vessels added");
  };

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
                  vessels={vessels}
                  userMmsi={userMmsi}
                  locks={locks}
                  lockStatus={lockStatus}
                  raceAnalysis={raceAnalysis}
                  selectedLock={selectedLock}
                  onSelectLock={setSelectedLock}
                  onDisconnect={handleDisconnect}
                  onResetConnection={handleResetConnection}
                  onReconnect={() => connectWebSocket(connectionConfig)}
                  onAddDemoVessels={addDemoVessels}
                  connectionConfig={connectionConfig}
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
