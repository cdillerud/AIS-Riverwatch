import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";
import { getConnectivity, onConnectivityChange, offlineText } from "@/lib/connectivity";

// One quiet line under the header while the phone has no (or weak) signal and
// the page is showing saved data (lib/connectivity.js, public/sw.js).
export default function OfflineHint() {
  const [conn, setConn] = useState(getConnectivity);
  useEffect(() => onConnectivityChange(setConn), []);
  const text = offlineText(conn);
  if (!text) return null;
  return (
    <div className="border-b border-slate-800 bg-slate-900/80 text-slate-300" role="status" data-testid="offline-hint">
      <div className="container mx-auto px-4 py-1.5 flex items-center gap-2 text-xs">
        <WifiOff className="w-3.5 h-3.5 shrink-0 text-amber-400" />
        <span>{text}</span>
      </div>
    </div>
  );
}
