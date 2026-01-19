import { useState } from "react";
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
  Edit3, Check, X
} from "lucide-react";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL + '/api';

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

  if (!vessel) return null;

  const speedMph = (vessel.speed * 1.15078).toFixed(1);
  const isUser = vessel.is_user_vessel;
  const isTow = vessel.is_tow || vessel.barge_count > 0 || 
    (vessel.name && (vessel.name.includes('M/V') || vessel.name.includes('CAPT')));

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
          <DialogTitle className="flex items-center gap-3">
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
          </DialogTitle>
          <DialogDescription className="text-slate-400">
            Complete AIS data for this vessel
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-4">
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

          {/* Tow/Barge Section */}
          {isTow && (
            <div className="glass-panel p-4 rounded-lg border border-amber-500/30 bg-amber-900/10">
              <h3 className="text-sm font-semibold text-amber-400 mb-3 flex items-center gap-2">
                <Box className="w-4 h-4" />
                Tow Information
              </h3>
              <div className="grid grid-cols-2 gap-3 text-sm">
                {vessel.barge_count && (
                  <div>
                    <span className="text-slate-500">Barge Count</span>
                    <div className="text-amber-400 font-semibold text-lg">{vessel.barge_count}</div>
                  </div>
                )}
                {vessel.tow_config && (
                  <div>
                    <span className="text-slate-500">Configuration</span>
                    <div className="font-mono text-white">{vessel.tow_config}</div>
                  </div>
                )}
                {vessel.estimated_lockage_time && (
                  <div>
                    <span className="text-slate-500">Est. Lockage Time</span>
                    <div className="flex items-center gap-2">
                      <Timer className="w-4 h-4 text-amber-400" />
                      <span className="text-white">{vessel.estimated_lockage_time} min</span>
                    </div>
                  </div>
                )}
                {vessel.barge_count > 9 && (
                  <div className="col-span-2">
                    <Badge className="bg-red-900/30 text-red-400 border-red-500/30">
                      <AlertTriangle className="w-3 h-3 mr-1" />
                      DOUBLE LOCKAGE REQUIRED
                    </Badge>
                  </div>
                )}
              </div>
            </div>
          )}

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
