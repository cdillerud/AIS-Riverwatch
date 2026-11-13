import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { API } from "@/lib/api";
import { feedBanner } from "@/lib/feedStatus";
import { whenVisible, onVisible } from "@/lib/visibility";

// Strip under the header while the live AIS feed is down.
export default function FeedBanner() {
  const [health, setHealth] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await fetch(`${API}/health`);
        const body = await r.json();
        if (alive) setHealth(body);
      } catch (e) {
        /* offline: keep the last answer */
      }
    };
    load();
    const id = setInterval(whenVisible(load), 60000);
    const off = onVisible(load);
    return () => { alive = false; clearInterval(id); off(); };
  }, []);
  const banner = feedBanner(health);
  if (!banner) return null;
  return (
    <div className="bg-amber-500/10 border-b border-amber-500/30 text-amber-200" role="status" data-testid="feed-banner">
      <div className="container mx-auto px-4 py-2 flex items-start gap-2 text-sm">
        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-amber-400" />
        <div>
          <span className="font-semibold">{banner.title}.</span>{" "}
          <span className="text-amber-200/80">{banner.detail}</span>
        </div>
      </div>
    </div>
  );
}
