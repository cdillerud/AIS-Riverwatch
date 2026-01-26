import { useState, useEffect } from "react";
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle,
  DialogDescription 
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { 
  Ship, Navigation, Gauge, Compass, Anchor, 
  MapPin, Clock, Phone, Radio, Hash, Ruler,
  ArrowUp, ArrowDown, Minus, Box, Timer, AlertTriangle,
  Edit3, Check, X, Lock, History
} from "lucide-react";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL + '/api';

// Lock positions for "At Lock" detection
const LOCK_POSITIONS = {
  lock_1: 847.6, lock_2: 815.2, lock_3: 796.9, lock_4: 752.8,
  lock_5: 738.1, lock_5a: 728.3, lock_6: 714.2, lock_7: 702.4,
  lock_8: 679.1, lock_9: 647.8, lock_10: 615.1, lock_11: 583.0,
  lock_12: 556.6, lock_13: 522.4, lock_14: 493.2, lock_15: 482.9,
  lock_16: 457.2, lock_17: 437.1, lock_18: 410.5, lock_19: 364.2,
  lock_20: 343.2, lock_21: 324.9, lock_22: 301.2, lock_24: 273.4,
  lock_25: 241.4, lock_26: 202.9, lock_27: 185.0
};

// Check if a vessel is "at" any lock (within 0.5 miles)
const getVesselLockStatus = (vessel) => {
  if (!vessel?.river_mile) return null;
  
  const AT_LOCK_DISTANCE = 0.5; // miles
  
  for (const [lockId, lockRM] of Object.entries(LOCK_POSITIONS)) {
    const distance = Math.abs(vessel.river_mile - lockRM);
    if (distance <= AT_LOCK_DISTANCE) {
      const lockNum = lockId.replace('lock_', '').toUpperCase();
      return {
        lockId,
        lockNum,
        lockRM,
        distance: distance.toFixed(2)
      };
    }
  }
  return null;
};

// Ship type descriptions
const SHIP_TYPES = {
  0: "Not available",
  20: "Wing in ground",
  30: "Fishing",
  31: "Towing",
  32: "Towing (large)",
  33: "Dredging",
  34: "Diving ops",
  35: "Military ops",
  36: "Sailing",
  37: "Pleasure craft",
  40: "High speed craft",
  50: "Pilot vessel",
  51: "Search & rescue",
  52: "Tug",
  53: "Port tender",
  54: "Anti-pollution",
  55: "Law enforcement",
  60: "Passenger",
  70: "Cargo",
  80: "Tanker",
  90: "Other",
};

const getShipTypeDescription = (code) => {
  if (!code) return "Unknown";
  // Check exact match first
  if (SHIP_TYPES[code]) return SHIP_TYPES[code];
  // Check range (e.g., 70-79 are all cargo)
  const base = Math.floor(code / 10) * 10;
  return SHIP_TYPES[base] || `Type ${code}`;
};

const getDirectionIcon = (heading) => {
  if (heading === "northbound") return <ArrowUp className="w-4 h-4 text-green-400" />;
  if (heading === "southbound") return <ArrowDown className="w-4 h-4 text-red-400" />;
  return <Minus className="w-4 h-4 text-slate-400" />;
};

export default function VesselDetailModal({ vessel, isOpen, onClose, selectedLock }) {
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState("");
  const [isEditingType, setIsEditingType] = useState(false);
  const [editedType, setEditedType] = useState("");
  const [lockageHistory, setLockageHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [vesselData, setVesselData] = useState(null);  // Persisted vessel data from DB

  // Fetch lockage history and persisted vessel data when modal opens
  useEffect(() => {
    if (isOpen && vessel) {
      fetchLockageHistory();
      fetchVesselData();
    }
  }, [isOpen, vessel?.mmsi, vessel?.name]);

  const fetchVesselData = async () => {
    if (!vessel?.mmsi) return;
    
    try {
      const response = await fetch(`${API}/vessels/history/${vessel.mmsi}`);
      if (response.ok) {
        const data = await response.json();
        setVesselData(data);
      }
    } catch (error) {
      console.error("Error fetching vessel data:", error);
    }
  };

  const fetchLockageHistory = async () => {
    if (!vessel?.name) return;
    
    setLoadingHistory(true);
    try {
      const response = await fetch(`${API}/lockage/history?days=30`);
      if (response.ok) {
        const data = await response.json();
        // Filter to only this vessel's records
        const vesselHistory = data.records.filter(
          r => r.vessel_name?.toLowerCase() === vessel.name?.toLowerCase()
        );
        setLockageHistory(vesselHistory);
      }
    } catch (error) {
      console.error("Error fetching lockage history:", error);
    } finally {
      setLoadingHistory(false);
    }
  };

  if (!vessel) return null;

  const speedMph = (vessel.speed * 1.15078).toFixed(1);
  // ONLY match by MMSI - need to get userMmsi from localStorage as fallback
  const storedMmsi = typeof window !== 'undefined' ? localStorage.getItem('riverwatch_mmsi') : null;
  const isUser = storedMmsi && vessel.mmsi === storedMmsi;
  const isTow = vessel.is_tow || vessel.barge_count > 0 || 
    (vessel.name && (vessel.name.includes('M/V') || vessel.name.includes('CAPT')));
  const lockStatus = getVesselLockStatus(vessel);

  // Calculate distance to selected lock
  const distanceToLock = selectedLock && vessel.river_mile 
    ? Math.abs(vessel.river_mile - selectedLock.river_mile).toFixed(1)
    : null;

  // Start editing name
  const startEditingName = () => {
    setEditedName(vessel.name || "");
    setIsEditingName(true);
  };

  // Save vessel name
  const saveVesselName = async () => {
    if (!editedName.trim()) {
      toast.error("Please enter a vessel name");
      return;
    }

    try {
      const response = await fetch(`${API}/vessel-cache/${vessel.mmsi}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editedName.trim() })
      });

      if (response.ok) {
        toast.success(`Saved name "${editedName.trim()}" for MMSI ${vessel.mmsi}`);
        setIsEditingName(false);
        // Update the vessel object locally (will be refreshed on next poll)
        vessel.name = editedName.trim();
      } else {
        toast.error("Failed to save vessel name");
      }
    } catch (error) {
      console.error("Error saving vessel name:", error);
      toast.error("Failed to save vessel name");
    }
  };

  // Cancel editing
  const cancelEditingName = () => {
    setIsEditingName(false);
    setEditedName("");
  };

  // Start editing type
  const startEditingType = () => {
    setEditedType(vessel.ship_type?.toString() || "0");
    setIsEditingType(true);
  };

  // Save vessel type
  const saveVesselType = async () => {
    const typeCode = parseInt(editedType);
    if (isNaN(typeCode) || typeCode < 0 || typeCode > 99) {
      toast.error("Please enter a valid type code (0-99)");
      return;
    }

    try {
      const response = await fetch(`${API}/vessel-cache/${vessel.mmsi}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          name: vessel.name || null,
          ship_type: typeCode 
        })
      });

      if (response.ok) {
        toast.success(`Saved vessel type for MMSI ${vessel.mmsi}`);
        setIsEditingType(false);
        vessel.ship_type = typeCode;
      } else {
        toast.error("Failed to save vessel type");
      }
    } catch (error) {
      console.error("Error saving vessel type:", error);
      toast.error("Failed to save vessel type");
    }
  };

  // Cancel editing type
  const cancelEditingType = () => {
    setIsEditingType(false);
    setEditedType("");
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="bg-slate-900 border-slate-700 text-white max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3 flex-wrap">
            {isUser ? (
              <div className="w-4 h-4 rounded-full bg-cyan-400 animate-pulse" />
            ) : isTow ? (
              <Box className="w-5 h-5 text-amber-400" />
            ) : (
              <Ship className="w-5 h-5 text-amber-400" />
            )}
            <span className={isUser ? "text-cyan-400" : "text-white"}>
              {vessel.name || `MMSI: ${vessel.mmsi}`}
            </span>
            {isUser && (
              <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/50">
                YOUR VESSEL
              </Badge>
            )}
            {isTow && !isUser && (
              <Badge className="bg-amber-900/30 text-amber-400 border-amber-500/30">
                TOW
              </Badge>
            )}
            {lockStatus && (
              <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/50">
                <Lock className="w-3 h-3 mr-1" />
                AT LOCK {lockStatus.lockNum}
              </Badge>
            )}
          </DialogTitle>
          <DialogDescription className="text-slate-400">
            {lockStatus 
              ? `Currently at Lock ${lockStatus.lockNum} (RM ${lockStatus.lockRM}) - ${lockStatus.distance}mi from lock center`
              : "Complete AIS data for this vessel"
            }
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-4">
          {/* At Lock Alert */}
          {lockStatus && (
            <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3">
              <div className="flex items-center gap-2">
                <Lock className="w-5 h-5 text-purple-400" />
                <div>
                  <div className="text-purple-400 font-semibold">At Lock {lockStatus.lockNum}</div>
                  <div className="text-xs text-slate-400">
                    {lockStatus.distance} miles from lock center at RM {lockStatus.lockRM}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Identification Section */}
          <div className="glass-panel p-4 rounded-lg border border-slate-700">
            <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <Hash className="w-4 h-4" />
              Identification
            </h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-slate-500">MMSI</span>
                <div className="font-mono text-white">{vessel.mmsi}</div>
              </div>
              
              {/* Editable Name Field */}
              <div className="col-span-2">
                <span className="text-slate-500">Name</span>
                {isEditingName ? (
                  <div className="flex items-center gap-2 mt-1">
                    <Input
                      value={editedName}
                      onChange={(e) => setEditedName(e.target.value)}
                      placeholder="Enter vessel name"
                      className="bg-slate-950 border-slate-600 text-white h-8 flex-1"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveVesselName();
                        if (e.key === 'Escape') cancelEditingName();
                      }}
                    />
                    <Button
                      size="sm"
                      onClick={saveVesselName}
                      className="bg-green-600 hover:bg-green-700 h-8 px-2"
                    >
                      <Check className="w-4 h-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={cancelEditingName}
                      className="border-slate-600 h-8 px-2"
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className={vessel.name ? "text-white" : "text-slate-500 italic"}>
                      {vessel.name || "Unknown - click to add"}
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={startEditingName}
                      className="h-6 px-2 text-slate-400 hover:text-cyan-400"
                      title="Edit vessel name"
                    >
                      <Edit3 className="w-3 h-3" />
                    </Button>
                  </div>
                )}
              </div>
              
              {vessel.callsign && (
                <div>
                  <span className="text-slate-500">Call Sign</span>
                  <div className="font-mono text-white">{vessel.callsign}</div>
                </div>
              )}
              {vessel.imo && (
                <div>
                  <span className="text-slate-500">IMO</span>
                  <div className="font-mono text-white">{vessel.imo}</div>
                </div>
              )}
              {/* Editable Ship Type Field */}
              <div className="col-span-2">
                <span className="text-slate-500">Ship Type</span>
                {isEditingType ? (
                  <div className="flex items-center gap-2 mt-1">
                    <select
                      value={editedType}
                      onChange={(e) => setEditedType(e.target.value)}
                      className="bg-slate-950 border border-slate-600 text-white h-8 px-2 rounded flex-1"
                      autoFocus
                    >
                      <option value="0">Not available (0)</option>
                      <option value="30">Fishing (30)</option>
                      <option value="31">Towing (31)</option>
                      <option value="32">Towing - Large (32)</option>
                      <option value="33">Dredging (33)</option>
                      <option value="36">Sailing (36)</option>
                      <option value="37">Pleasure Craft (37)</option>
                      <option value="52">Tug (52)</option>
                      <option value="60">Passenger (60)</option>
                      <option value="70">Cargo (70)</option>
                      <option value="80">Tanker (80)</option>
                      <option value="90">Other (90)</option>
                    </select>
                    <Button
                      size="sm"
                      onClick={saveVesselType}
                      className="bg-green-600 hover:bg-green-700 h-8 px-2"
                    >
                      <Check className="w-4 h-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={cancelEditingType}
                      className="border-slate-600 h-8 px-2"
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="text-white">
                      {getShipTypeDescription(vessel.ship_type)}
                      {vessel.ship_type > 0 && (
                        <span className="text-slate-500 ml-1">({vessel.ship_type})</span>
                      )}
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={startEditingType}
                      className="h-6 px-2 text-slate-400 hover:text-cyan-400"
                      title="Edit vessel type"
                    >
                      <Edit3 className="w-3 h-3" />
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Position Section */}
          <div className="glass-panel p-4 rounded-lg border border-slate-700">
            <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <MapPin className="w-4 h-4" />
              Position
            </h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-slate-500">Latitude</span>
                <div className="font-mono text-white">{vessel.lat?.toFixed(6)}°</div>
              </div>
              <div>
                <span className="text-slate-500">Longitude</span>
                <div className="font-mono text-white">{vessel.lon?.toFixed(6)}°</div>
              </div>
              <div>
                <span className="text-slate-500">River Mile</span>
                <div className="font-mono text-cyan-400 text-lg">
                  {vessel.river_mile?.toFixed(1) || '--'}
                </div>
              </div>
              {distanceToLock && (
                <div>
                  <span className="text-slate-500">Distance to Lock</span>
                  <div className="font-mono text-amber-400 text-lg">{distanceToLock} mi</div>
                </div>
              )}
            </div>
          </div>

          {/* Navigation Section */}
          <div className="glass-panel p-4 rounded-lg border border-slate-700">
            <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <Compass className="w-4 h-4" />
              Navigation
            </h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-slate-500">Speed</span>
                <div className="text-white">
                  <span className="font-mono text-lg">{speedMph}</span>
                  <span className="text-slate-400 ml-1">mph</span>
                  <span className="text-slate-500 ml-2">({vessel.speed?.toFixed(1)} kn)</span>
                </div>
              </div>
              <div>
                <span className="text-slate-500">Course (COG)</span>
                <div className="font-mono text-white">{vessel.course?.toFixed(1)}°</div>
              </div>
              {vessel.heading_true !== null && vessel.heading_true !== undefined && (
                <div>
                  <span className="text-slate-500">True Heading</span>
                  <div className="font-mono text-white">{vessel.heading_true}°</div>
                </div>
              )}
              <div>
                <span className="text-slate-500">Direction</span>
                <div className="flex items-center gap-2 text-white capitalize">
                  {getDirectionIcon(vessel.heading)}
                  {vessel.heading || 'Stationary'}
                </div>
              </div>
              {vessel.turn_rate !== null && vessel.turn_rate !== undefined && (
                <div>
                  <span className="text-slate-500">Turn Rate</span>
                  <div className="font-mono text-white">{vessel.turn_rate}°/min</div>
                </div>
              )}
              {vessel.nav_status_text && (
                <div className="col-span-2">
                  <span className="text-slate-500">Navigation Status</span>
                  <div className="text-white">
                    <Badge className={`
                      ${vessel.nav_status === 0 ? 'bg-green-900/30 text-green-400 border-green-500/30' : ''}
                      ${vessel.nav_status === 1 ? 'bg-blue-900/30 text-blue-400 border-blue-500/30' : ''}
                      ${vessel.nav_status === 5 ? 'bg-purple-900/30 text-purple-400 border-purple-500/30' : ''}
                      ${![0,1,5].includes(vessel.nav_status) ? 'bg-slate-700 text-slate-300' : ''}
                    `}>
                      {vessel.nav_status_text}
                    </Badge>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Voyage Section */}
          {(vessel.destination || vessel.eta) && (
            <div className="glass-panel p-4 rounded-lg border border-slate-700">
              <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                <Navigation className="w-4 h-4" />
                Voyage
              </h3>
              <div className="grid grid-cols-2 gap-3 text-sm">
                {vessel.destination && (
                  <div className="col-span-2">
                    <span className="text-slate-500">Destination</span>
                    <div className="text-white">{vessel.destination}</div>
                  </div>
                )}
                {vessel.eta && (
                  <div>
                    <span className="text-slate-500">ETA</span>
                    <div className="font-mono text-white">{vessel.eta}</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Dimensions Section */}
          {(vessel.length || vessel.width || vessel.draught) && (
            <div className="glass-panel p-4 rounded-lg border border-slate-700">
              <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                <Ruler className="w-4 h-4" />
                Dimensions
              </h3>
              <div className="grid grid-cols-3 gap-3 text-sm">
                {vessel.length && (
                  <div>
                    <span className="text-slate-500">Length</span>
                    <div className="font-mono text-white">{vessel.length}m</div>
                    <div className="text-slate-500 text-xs">{(vessel.length * 3.28084).toFixed(0)}ft</div>
                  </div>
                )}
                {vessel.width && (
                  <div>
                    <span className="text-slate-500">Beam</span>
                    <div className="font-mono text-white">{vessel.width}m</div>
                    <div className="text-slate-500 text-xs">{(vessel.width * 3.28084).toFixed(0)}ft</div>
                  </div>
                )}
                {vessel.draught && (
                  <div>
                    <span className="text-slate-500">Draught</span>
                    <div className="font-mono text-white">{vessel.draught}m</div>
                    <div className="text-slate-500 text-xs">{(vessel.draught * 3.28084).toFixed(1)}ft</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Tow/Barge Section - Always show */}
          <div className="glass-panel p-4 rounded-lg border border-amber-500/30 bg-amber-900/10">
            <h3 className="text-sm font-semibold text-amber-400 mb-3 flex items-center gap-2">
              <Box className="w-4 h-4" />
              Tow Information
              {(vessel.usace_source || vesselData?.current?.usace_source) && (
                <Badge className="bg-green-900/30 text-green-400 border-green-500/30 text-xs ml-2">
                  USACE Verified
                </Badge>
              )}
            </h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {/* Barge Count */}
              <div>
                <span className="text-slate-500">Barge Count</span>
                {(vessel.barge_count !== null && vessel.barge_count !== undefined) || 
                 (vesselData?.current?.barge_count !== null && vesselData?.current?.barge_count !== undefined) ? (
                  <div className="text-amber-400 font-semibold text-lg">
                    {vessel.barge_count ?? vesselData?.current?.barge_count}
                  </div>
                ) : (
                  <div className="text-slate-400 italic">No data</div>
                )}
              </div>
              {/* Configuration */}
              <div>
                <span className="text-slate-500">Configuration</span>
                {(vessel.tow_config || vesselData?.current?.tow_config) ? (
                  <div className="font-mono text-white">{vessel.tow_config || vesselData?.current?.tow_config}</div>
                ) : (
                  <div className="text-slate-400 italic">No data</div>
                )}
              </div>
              {/* Estimated Lockage Time */}
              <div>
                <span className="text-slate-500">Est. Lockage Time</span>
                {(vessel.estimated_lockage_time || vesselData?.current?.estimated_lockage_time) ? (
                  <div className="flex items-center gap-2">
                    <Timer className="w-4 h-4 text-amber-400" />
                    <span className="text-white">{vessel.estimated_lockage_time || vesselData?.current?.estimated_lockage_time} min</span>
                  </div>
                ) : (
                  <div className="text-slate-400 italic">No data</div>
                )}
              </div>
              {/* Current Lock */}
              <div>
                <span className="text-slate-500">USACE Lock</span>
                {(vessel.usace_lock || vesselData?.current?.usace_lock) ? (
                  <div className="text-white">Lock {(vessel.usace_lock || vesselData?.current?.usace_lock).replace('lock_', '')}</div>
                ) : (
                  <div className="text-slate-400 italic">No data</div>
                )}
              </div>
              {/* Double Lockage Warning */}
              {((vessel.barge_count ?? vesselData?.current?.barge_count) > 9) && (
                  <div className="col-span-2">
                    <Badge className="bg-red-900/30 text-red-400 border-red-500/30">
                      <AlertTriangle className="w-3 h-3 mr-1" />
                      DOUBLE LOCKAGE REQUIRED
                    </Badge>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Lockage History Section */}
          <div className="glass-panel p-4 rounded-lg border border-slate-700">
            <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <History className="w-4 h-4" />
              Lockage History
              {lockageHistory.length > 0 && (
                <Badge className="bg-cyan-900/30 text-cyan-400 border-cyan-500/30 text-xs">
                  {lockageHistory.length} passages
                </Badge>
              )}
            </h3>
            
            {loadingHistory ? (
              <div className="text-slate-500 text-sm text-center py-4">
                Loading history...
              </div>
            ) : lockageHistory.length === 0 ? (
              <div className="text-slate-500 text-sm text-center py-4">
                No recorded lockages for this vessel
              </div>
            ) : (
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {lockageHistory.map((record, idx) => (
                  <div 
                    key={idx} 
                    className="bg-slate-800/50 rounded p-2 text-sm"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <Lock className="w-3 h-3 text-cyan-400" />
                        <span className="font-medium text-white">
                          {record.lock_id?.replace('lock_', 'Lock ')}
                        </span>
                        <Badge className={`text-[10px] ${
                          record.direction === 'downbound' 
                            ? 'bg-red-900/30 text-red-400' 
                            : 'bg-green-900/30 text-green-400'
                        }`}>
                          {record.direction === 'downbound' ? (
                            <><ArrowDown className="w-2 h-2 mr-0.5" />DOWN</>
                          ) : (
                            <><ArrowUp className="w-2 h-2 mr-0.5" />UP</>
                          )}
                        </Badge>
                      </div>
                      <span className="text-slate-500 text-xs">
                        {record.recorded_at ? new Date(record.recorded_at).toLocaleDateString() : ''}
                      </span>
                    </div>
                    <div className="flex gap-4 text-xs">
                      <div>
                        <span className="text-slate-500">Wait: </span>
                        <span className="text-amber-400 font-mono">
                          {record.wait_time_minutes?.toFixed(1) || '0'}m
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500">Lockage: </span>
                        <span className="text-cyan-400 font-mono">
                          {record.lockage_duration_minutes?.toFixed(1) || '0'}m
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500">Total: </span>
                        <span className="text-white font-mono">
                          {record.total_time_minutes?.toFixed(1) || '0'}m
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Historical USACE Sightings - Always show */}
          <div className="glass-panel p-4 rounded-lg border border-green-500/30">
            <h3 className="text-sm font-semibold text-green-400 mb-3 flex items-center gap-2">
              <History className="w-4 h-4" />
              USACE Sighting History
              {vesselData?.history?.length > 0 && (
                <Badge className="bg-green-900/30 text-green-400 text-xs">
                  {vesselData.history.length} records
                </Badge>
              )}
            </h3>
            {vesselData?.history && vesselData.history.length > 0 ? (
              <div className="space-y-2 max-h-[150px] overflow-y-auto">
                {vesselData.history.slice(0, 10).map((record, idx) => (
                  <div 
                    key={idx} 
                    className="bg-slate-800/50 rounded p-2 text-sm"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        {record.usace_lock && (
                          <>
                            <Lock className="w-3 h-3 text-cyan-400" />
                            <span className="font-medium text-white">
                              {record.usace_lock.replace('lock_', 'Lock ')}
                            </span>
                          </>
                        )}
                        {record.barge_count !== null && record.barge_count !== undefined && (
                          <Badge className="bg-amber-900/30 text-amber-400 text-xs">
                            {record.barge_count} barges
                          </Badge>
                        )}
                      </div>
                      <span className="text-slate-500 text-xs">
                        {record.recorded_at ? new Date(record.recorded_at).toLocaleString() : ''}
                      </span>
                    </div>
                    <div className="flex gap-4 text-xs text-slate-400">
                      {record.river_mile && (
                        <span>RM {record.river_mile.toFixed(1)}</span>
                      )}
                      {record.tow_config && (
                        <span className="font-mono">{record.tow_config}</span>
                      )}
                      {record.usace_status && (
                        <span className="text-cyan-400">{record.usace_status}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-slate-500 text-sm text-center py-4">
                No USACE sighting records
              </div>
            )}
          </div>

          {/* First Seen Info */}
          <div className="text-xs text-slate-500 text-center">
            {vesselData?.current?.first_seen ? (
              <>First seen: {new Date(vesselData.current.first_seen).toLocaleString()}</>
            ) : (
              <>No tracking history</>
            )}
          </div>

          {/* Data Source */}
          <div className="text-xs text-slate-500 text-center pt-2 border-t border-slate-700">
            {vessel.source && (
              <span>Data source: {vessel.source} • </span>
            )}
            Last updated: {vessel.timestamp ? new Date(vessel.timestamp).toLocaleTimeString() : 'Unknown'}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
