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
  Ship, Compass, 
  MapPin, Hash,
  ArrowUp, ArrowDown, Minus, Box, 
  Edit3, Check, X, Lock, History, Navigation, Clock
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

const getVesselLockStatus = (vessel) => {
  if (!vessel?.river_mile) return null;
  const AT_LOCK_DISTANCE = 0.5;
  for (const [lockId, lockRM] of Object.entries(LOCK_POSITIONS)) {
    const distance = Math.abs(vessel.river_mile - lockRM);
    if (distance <= AT_LOCK_DISTANCE) {
      return {
        lockId,
        lockNum: lockId.replace('lock_', '').toUpperCase(),
        lockRM,
        distance: distance.toFixed(2)
      };
    }
  }
  return null;
};

const SHIP_TYPES = {
  0: "Unknown", 30: "Fishing", 31: "Towing", 32: "Towing (large)",
  36: "Sailing", 37: "Pleasure craft", 52: "Tug", 60: "Passenger",
  70: "Cargo", 80: "Tanker", 90: "Other",
};

const getShipTypeDescription = (code) => {
  if (!code) return "Unknown";
  if (SHIP_TYPES[code]) return SHIP_TYPES[code];
  const base = Math.floor(code / 10) * 10;
  return SHIP_TYPES[base] || `Type ${code}`;
};

const getLastCheckInValue = (vessel) => (
  vessel?.last_ais_checkin || vessel?.timestamp || vessel?.last_update || null
);

const parseCheckInTime = (value) => {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
};

const formatLastCheckIn = (vessel, nowMs) => {
  const parsed = parseCheckInTime(getLastCheckInValue(vessel));
  if (!parsed) return "--";

  const ageSeconds = Math.max(0, Math.floor((nowMs - parsed.getTime()) / 1000));

  if (ageSeconds < 10) return "just now";
  if (ageSeconds < 60) return `${ageSeconds}s ago`;

  const ageMinutes = Math.floor(ageSeconds / 60);
  if (ageMinutes < 60) return `${ageMinutes}m ago`;

  const ageHours = Math.floor(ageMinutes / 60);
  if (ageHours < 24) return `${ageHours}h ago`;

  const ageDays = Math.floor(ageHours / 24);
  return `${ageDays}d ago`;
};

export default function VesselDetailModal({ vessel, isOpen, onClose }) {
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState("");
  const [lockageHistory, setLockageHistory] = useState([]);
  const [vesselData, setVesselData] = useState(null);
  const [nowTick, setNowTick] = useState(() => Date.now());

  // Keep displayed check-in age current while the modal is open.
  useEffect(() => {
    if (!isOpen) return undefined;
    const intervalId = window.setInterval(() => setNowTick(Date.now()), 30000);
    return () => window.clearInterval(intervalId);
  }, [isOpen]);

  // Fetch additional vessel data on open
  useEffect(() => {
    if (isOpen && vessel?.mmsi) {
      // Fetch vessel history
      fetch(`${API}/vessels/history/${vessel.mmsi}`)
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          if (data) {
            setLockageHistory(data.lockage_history || []);
            setVesselData(data);
          }
        })
        .catch(() => {});
    }
  }, [isOpen, vessel?.mmsi]);

  if (!vessel) return null;

  const isUser = vessel.is_user_vessel;
  const isTow = vessel.is_tow || vessel.ship_type === 31 || vessel.ship_type === 32 || vessel.barge_count > 0;
  const lockStatus = getVesselLockStatus(vessel);
  const speedMph = (vessel.speed * 1.15078).toFixed(1);
  const direction = vessel.direction || vessel.heading_direction || vessel.heading;
  const lastCheckInDisplay = formatLastCheckIn(vessel, nowTick);

  const saveVesselName = async () => {
    if (!editedName.trim()) {
      toast.error("Please enter a name");
      return;
    }
    try {
      const response = await fetch(`${API}/vessel-cache/${vessel.mmsi}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editedName.trim() })
      });
      if (response.ok) {
        toast.success(`Saved name "${editedName.trim()}"`);
        setIsEditingName(false);
        // Note: vessel name will update on next data refresh
      }
    } catch (error) {
      toast.error("Failed to save name");
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="bg-slate-900 border-slate-700 text-white max-w-md" data-testid="vessel-detail-modal">
        {/* Compact Header */}
        <DialogHeader className="pb-2">
          <DialogTitle className="flex items-center gap-2">
            {isUser ? (
              <div className="w-3 h-3 rounded-full bg-cyan-400 animate-pulse" />
            ) : isTow ? (
              <Box className="w-4 h-4 text-amber-400" />
            ) : (
              <Ship className="w-4 h-4 text-slate-400" />
            )}
            
            {isEditingName ? (
              <div className="flex items-center gap-1 flex-1">
                <Input
                  value={editedName}
                  onChange={(e) => setEditedName(e.target.value)}
                  placeholder="Vessel name"
                  className="bg-slate-950 border-slate-600 text-white h-7 text-sm"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') saveVesselName();
                    if (e.key === 'Escape') setIsEditingName(false);
                  }}
                />
                <Button size="sm" onClick={saveVesselName} className="h-7 w-7 p-0 bg-green-600">
                  <Check className="w-3 h-3" />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setIsEditingName(false)} className="h-7 w-7 p-0">
                  <X className="w-3 h-3" />
                </Button>
              </div>
            ) : (
              <span 
                className={`${isUser ? "text-cyan-400" : "text-white"} cursor-pointer hover:underline`}
                onClick={() => { setEditedName(vessel.name || ""); setIsEditingName(true); }}
              >
                {vessel.name || <span className="text-slate-500 italic">Click to name</span>}
              </span>
            )}
            
            {isUser && <Badge className="bg-cyan-500/20 text-cyan-400 text-[10px] px-1.5">YOU</Badge>}
            {isTow && !isUser && <Badge className="bg-amber-900/30 text-amber-400 text-[10px] px-1.5">TOW</Badge>}
            {lockStatus && <Badge className="bg-purple-500/20 text-purple-400 text-[10px] px-1.5">AT LOCK {lockStatus.lockNum}</Badge>}
          </DialogTitle>
          <DialogDescription className="text-xs text-slate-500">
            MMSI: {vessel.mmsi} • {getShipTypeDescription(vessel.ship_type)}
          </DialogDescription>
        </DialogHeader>

        {/* All Info in Compact Grid */}
        <div className="grid grid-cols-3 gap-3 text-sm">
          {/* Position */}
          <div className="col-span-2 bg-slate-800/50 rounded p-2">
            <div className="flex items-center gap-1 text-slate-400 text-xs mb-1">
              <MapPin className="w-3 h-3" /> Position
            </div>
            <div className="font-mono text-lg text-white">RM {vessel.river_mile?.toFixed(1)}</div>
            <div className="text-[10px] text-slate-500">
              {vessel.lat?.toFixed(4)}°N, {vessel.lon?.toFixed(4)}°W
            </div>
          </div>

          {/* Speed & Direction */}
          <div className="bg-slate-800/50 rounded p-2">
            <div className="flex items-center gap-1 text-slate-400 text-xs mb-1">
              <Compass className="w-3 h-3" /> Speed
            </div>
            <div className="font-mono text-lg text-white">{speedMph}</div>
            <div className="text-[10px] text-slate-500">mph {vessel.course?.toFixed(0)}°</div>
          </div>

          {/* Last AIS Check-In */}
          <div className="bg-slate-800/50 rounded p-2">
            <div className="flex items-center gap-1 text-slate-400 text-xs mb-1">
              <Clock className="w-3 h-3" /> Check-In
            </div>
            <div className="font-mono text-sm text-white">{lastCheckInDisplay}</div>
            <div className="text-[10px] text-slate-500">last AIS</div>
          </div>

          {/* Direction */}
          <div className="bg-slate-800/50 rounded p-2">
            <div className="text-slate-400 text-xs mb-1">Direction</div>
            <div className="flex items-center gap-1">
              {direction === 'northbound' || direction === 'upriver' ? (
                <ArrowUp className="w-4 h-4 text-green-400" />
              ) : direction === 'southbound' || direction === 'downriver' ? (
                <ArrowDown className="w-4 h-4 text-red-400" />
              ) : (
                <Minus className="w-4 h-4 text-slate-400" />
              )}
              <span className={`text-sm capitalize ${
                direction === 'northbound' || direction === 'upriver' ? 'text-green-400' :
                direction === 'southbound' || direction === 'downriver' ? 'text-red-400' : 'text-slate-400'
              }`}>
                {direction || 'Stationary'}
              </span>
            </div>
          </div>

          {/* Barge Count (if tow) */}
          {isTow && (
            <div className="bg-amber-900/20 rounded p-2 border border-amber-500/30">
              <div className="text-amber-400 text-xs mb-1">Barges</div>
              <div className="font-mono text-lg text-amber-400">
                {vessel.barge_count || '?'}
              </div>
              {vessel.tow_config && <div className="text-[10px] text-amber-400/70">{vessel.tow_config}</div>}
            </div>
          )}

          {/* Next Lock ETA */}
          {vessel.next_lock && (
            <div className={`${isTow ? 'col-span-1' : 'col-span-2'} bg-cyan-900/20 rounded p-2 border border-cyan-500/30`}>
              <div className="flex items-center gap-1 text-cyan-400 text-xs mb-1">
                <Navigation className="w-3 h-3" /> Next Lock
              </div>
              <div className="text-white font-medium text-sm">{vessel.next_lock.next_lock_name}</div>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-slate-400">{vessel.next_lock.distance_miles} mi</span>
                <span className="text-cyan-400 font-mono">{vessel.next_lock.eta_display}</span>
              </div>
            </div>
          )}
        </div>

        {/* USACE Data (if available) */}
        {(vessel.usace_source || vessel.usace_status) && (
          <div className="mt-3 bg-slate-800/30 rounded p-2 text-xs">
            <div className="text-slate-400 mb-1 flex items-center gap-1">
              <Hash className="w-3 h-3" /> USACE Data
            </div>
            <div className="grid grid-cols-2 gap-x-4 text-slate-300">
              {vessel.usace_source && <div>Source: <span className="text-white">{vessel.usace_source}</span></div>}
              {vessel.usace_status && <div>Status: <span className="text-white">{vessel.usace_status}</span></div>}
              {vessel.usace_lock && <div>Lock: <span className="text-white">{vessel.usace_lock}</span></div>}
              {vessel.estimated_lockage_time && <div>Lock time: <span className="text-white">{vessel.estimated_lockage_time}min</span></div>}
            </div>
          </div>
        )}

        {/* Lockage History (compact) */}
        {lockageHistory.length > 0 && (
          <div className="mt-3 bg-slate-800/30 rounded p-2 text-xs">
            <div className="text-slate-400 mb-1 flex items-center gap-1">
              <History className="w-3 h-3" /> Recent Lockages ({lockageHistory.length})
            </div>
            <div className="space-y-1 max-h-24 overflow-y-auto">
              {lockageHistory.slice(0, 3).map((l, i) => (
                <div key={i} className="flex justify-between text-slate-300">
                  <span>{l.lock_name || l.lock_id}</span>
                  <span className="text-slate-500">{l.direction} • {l.wait_time_minutes || '?'}min wait</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Quick Actions */}
        <div className="mt-3 flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="flex-1 text-xs h-8 border-slate-600"
            onClick={() => { setEditedName(vessel.name || ""); setIsEditingName(true); }}
          >
            <Edit3 className="w-3 h-3 mr-1" />
            Edit Name
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="flex-1 text-xs h-8 border-slate-600"
            onClick={onClose}
          >
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
