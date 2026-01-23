import { memo, useMemo } from "react";
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle,
  DialogDescription 
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { MapPin, Lock, ChevronUp, ChevronDown, Minus, Ship, Navigation, Gauge } from "lucide-react";
import { getVesselDisplayName } from "@/utils/vesselDisplay";

// Lock positions
const LOCK_POSITIONS = {
  lock_1: { rm: 847.6, name: "Lock 1" }, lock_2: { rm: 815.2, name: "Lock 2" },
  lock_3: { rm: 796.9, name: "Lock 3" }, lock_4: { rm: 752.8, name: "Lock 4" },
  lock_5: { rm: 738.1, name: "Lock 5" }, lock_5a: { rm: 728.3, name: "Lock 5A" },
  lock_6: { rm: 714.2, name: "Lock 6" }, lock_7: { rm: 702.4, name: "Lock 7" },
  lock_8: { rm: 679.1, name: "Lock 8" }, lock_9: { rm: 647.8, name: "Lock 9" },
  lock_10: { rm: 615.1, name: "Lock 10" }, lock_11: { rm: 583.0, name: "Lock 11" },
  lock_12: { rm: 556.6, name: "Lock 12" }, lock_13: { rm: 522.4, name: "Lock 13" },
  lock_14: { rm: 493.2, name: "Lock 14" }, lock_15: { rm: 482.9, name: "Lock 15" },
  lock_16: { rm: 457.2, name: "Lock 16" }, lock_17: { rm: 437.1, name: "Lock 17" },
  lock_18: { rm: 410.5, name: "Lock 18" }, lock_19: { rm: 364.2, name: "Lock 19" },
  lock_20: { rm: 343.2, name: "Lock 20" }, lock_21: { rm: 324.9, name: "Lock 21" },
  lock_22: { rm: 301.2, name: "Lock 22" }, lock_24: { rm: 273.4, name: "Lock 24" },
  lock_25: { rm: 241.4, name: "Lock 25" }, lock_26: { rm: 202.9, name: "Melvin Price" },
  lock_27: { rm: 185.0, name: "Chain of Rocks" }
};

const VesselMiniMapComponent = ({ vessel, isOpen, onClose }) => {
  const vesselRM = vessel?.river_mile;
  const zoomRange = 15; // ±15 miles around vessel

  // Calculate visible range centered on vessel
  const { minRM, maxRM } = useMemo(() => {
    if (!vesselRM) return { minRM: 180, maxRM: 850 };
    return {
      minRM: Math.max(180, vesselRM - zoomRange),
      maxRM: Math.min(850, vesselRM + zoomRange)
    };
  }, [vesselRM]);

  // Get locks in view
  const visibleLocks = useMemo(() => {
    return Object.entries(LOCK_POSITIONS)
      .filter(([_, lock]) => lock.rm >= minRM && lock.rm <= maxRM)
      .map(([id, lock]) => ({ id, ...lock }));
  }, [minRM, maxRM]);

  if (!vessel) return null;

  // Get position percentage (inverted - north at top)
  const getPosition = (rm) => {
    const pct = ((rm - minRM) / (maxRM - minRM)) * 100;
    return Math.max(2, Math.min(98, 100 - pct));
  };

  const getDirectionIcon = (heading) => {
    if (heading === "northbound") return <ChevronUp className="w-4 h-4 text-green-400" />;
    if (heading === "southbound") return <ChevronDown className="w-4 h-4 text-amber-400" />;
    return <Minus className="w-4 h-4 text-slate-500" />;
  };

  const speedMph = (vessel.speed * 1.15078).toFixed(1);
  const isTow = vessel.is_tow || vessel.barge_count > 0;
  const isUser = vessel.is_user_vessel;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md bg-slate-900 border-slate-700">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-white">
            <MapPin className="w-5 h-5 text-cyan-400" />
            Vessel Location
          </DialogTitle>
          <DialogDescription className="text-slate-400">
            {getVesselDisplayName(vessel, true)} • MMSI: {vessel.mmsi}
          </DialogDescription>
        </DialogHeader>

        {/* Mini Map */}
        <div className="relative h-64 bg-slate-800/50 rounded-lg border border-slate-700 overflow-hidden">
          {/* River channel */}
          <div className="absolute left-1/2 top-0 bottom-0 w-16 -translate-x-1/2 bg-blue-900/30 border-x border-blue-500/20" />

          {/* Locks */}
          {visibleLocks.map(lock => (
            <div
              key={lock.id}
              className="absolute left-1/2 -translate-x-1/2 flex items-center gap-2"
              style={{ top: `${getPosition(lock.rm)}%` }}
            >
              <div className="absolute right-full mr-2 text-xs text-slate-500 whitespace-nowrap">
                {lock.name}
              </div>
              <Lock className="w-4 h-4 text-slate-500" />
              <div className="absolute left-full ml-2 text-xs text-slate-600 font-mono">
                RM {lock.rm.toFixed(1)}
              </div>
            </div>
          ))}

          {/* Vessel marker */}
          {vesselRM && (
            <div
              className="absolute left-1/2 -translate-x-1/2 z-10 flex flex-col items-center"
              style={{ top: `${getPosition(vesselRM)}%` }}
            >
              {/* Direction indicator */}
              <div className="mb-1">
                {getDirectionIcon(vessel.heading)}
              </div>
              
              {/* Vessel icon */}
              {isUser ? (
                <div className="w-4 h-4 rounded-full bg-cyan-500 animate-pulse ring-4 ring-cyan-500/30" />
              ) : isTow ? (
                <div className="w-4 h-4 bg-amber-500 rotate-45 ring-4 ring-amber-500/30" />
              ) : (
                <div className="w-3 h-3 bg-amber-400 rotate-45 ring-4 ring-amber-400/30" />
              )}

              {/* Label */}
              <div className="mt-2 bg-slate-900/90 px-2 py-1 rounded text-xs font-mono text-white whitespace-nowrap">
                RM {vesselRM.toFixed(1)}
              </div>
            </div>
          )}

          {/* Range indicator */}
          <div className="absolute top-2 left-2 text-xs text-slate-600 font-mono">
            N ↑ RM {maxRM.toFixed(0)}
          </div>
          <div className="absolute bottom-2 left-2 text-xs text-slate-600 font-mono">
            S ↓ RM {minRM.toFixed(0)}
          </div>
        </div>

        {/* Vessel Info */}
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div className="bg-slate-800/50 rounded p-2 text-center">
            <Navigation className="w-4 h-4 mx-auto mb-1 text-slate-400" />
            <div className="text-white font-mono">RM {vesselRM?.toFixed(1) || '--'}</div>
            <div className="text-xs text-slate-500">Position</div>
          </div>
          <div className="bg-slate-800/50 rounded p-2 text-center">
            <Gauge className="w-4 h-4 mx-auto mb-1 text-slate-400" />
            <div className="text-white font-mono">{speedMph} mph</div>
            <div className="text-xs text-slate-500">Speed</div>
          </div>
          <div className="bg-slate-800/50 rounded p-2 text-center">
            {getDirectionIcon(vessel.heading)}
            <div className="text-white capitalize">{vessel.heading || 'Stationary'}</div>
            <div className="text-xs text-slate-500">Heading</div>
          </div>
        </div>

        {/* Badges */}
        <div className="flex flex-wrap gap-2">
          {isUser && (
            <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/50">YOUR VESSEL</Badge>
          )}
          {isTow && (
            <Badge className="bg-amber-900/30 text-amber-400 border-amber-500/30">
              TOW {vessel.barge_count ? `• ${vessel.barge_count} barges` : ''}
            </Badge>
          )}
          {vessel.usace_source && (
            <Badge className="bg-green-900/30 text-green-400 border-green-500/30">USACE Verified</Badge>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export const VesselMiniMap = memo(VesselMiniMapComponent);
export default VesselMiniMap;
