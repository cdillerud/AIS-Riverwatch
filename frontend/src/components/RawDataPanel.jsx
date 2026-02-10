import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  Terminal, Trash2, Pause, Play, Download, 
  Radio, Satellite, Ship, MapPin
} from "lucide-react";

const MAX_LINES = 200;

// Categorize NMEA sentence types
const getSentenceInfo = (line) => {
  // Demo vessel simulated data
  if (line.startsWith('[DEMO]')) {
    if (line.includes('GPRMC') || line.includes('GPGGA')) {
      return { type: 'DEMO', icon: Satellite, color: 'text-purple-400', bg: 'bg-purple-900/20' };
    }
    if (line.includes('AIVDM')) {
      return { type: 'DEMO', icon: Ship, color: 'text-purple-400', bg: 'bg-purple-900/20' };
    }
    return { type: 'DEMO', icon: Radio, color: 'text-purple-400', bg: 'bg-purple-900/20' };
  }
  if (line.startsWith('$GPGGA') || line.startsWith('$GNGGA')) {
    return { type: 'GPS', icon: Satellite, color: 'text-green-400', bg: 'bg-green-900/20' };
  }
  if (line.startsWith('$GPRMC') || line.startsWith('$GNRMC')) {
    return { type: 'GPS', icon: Satellite, color: 'text-green-400', bg: 'bg-green-900/20' };
  }
  if (line.startsWith('$GPGLL') || line.startsWith('$GNGLL')) {
    return { type: 'GPS', icon: Satellite, color: 'text-green-400', bg: 'bg-green-900/20' };
  }
  if (line.startsWith('!AIVDM')) {
    return { type: 'AIS', icon: Ship, color: 'text-amber-400', bg: 'bg-amber-900/20' };
  }
  if (line.startsWith('!AIVDO')) {
    return { type: 'OWN', icon: MapPin, color: 'text-cyan-400', bg: 'bg-cyan-900/20' };
  }
  return { type: 'OTHER', icon: Radio, color: 'text-slate-400', bg: 'bg-slate-900/20' };
};

export default function RawDataPanel({ isConnected, compact = false }) {
  const [lines, setLines] = useState([]);
  const [isPaused, setIsPaused] = useState(false);
  const [filter, setFilter] = useState('all'); // 'all', 'gps', 'ais', 'own', 'demo'
  const [stats, setStats] = useState({ gps: 0, ais: 0, own: 0, other: 0, demo: 0 });
  const scrollRef = useRef(null);
  const wsRef = useRef(null);

  // Connect to raw data WebSocket
  useEffect(() => {
    if (!isConnected) return;

    const WS_URL = process.env.REACT_APP_BACKEND_URL?.replace('https://', 'wss://').replace('http://', 'ws://');
    const ws = new WebSocket(`${WS_URL}/api/ws/raw`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      if (isPaused) return;
      
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'raw') {
          const line = data.line;
          const info = getSentenceInfo(line);
          const timestamp = new Date().toLocaleTimeString();
          
          setLines(prev => {
            const newLines = [...prev, { line, info, timestamp, id: Date.now() }];
            return newLines.slice(-MAX_LINES);
          });
          
          setStats(prev => ({
            ...prev,
            [info.type.toLowerCase()]: prev[info.type.toLowerCase()] + 1
          }));
        }
      } catch (e) {
        // Not JSON, treat as raw line
      }
    };

    return () => {
      if (ws) ws.close();
    };
  }, [isConnected, isPaused]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current && !isPaused) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines, isPaused]);

  const clearLines = () => {
    setLines([]);
    setStats({ gps: 0, ais: 0, own: 0, other: 0, demo: 0 });
  };

  const downloadLog = () => {
    const content = lines.map(l => `${l.timestamp} [${l.info.type}] ${l.line}`).join('\n');
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ais_log_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.txt`;
    a.click();
  };

  const filteredLines = filter === 'all' 
    ? lines 
    : lines.filter(l => l.info.type.toLowerCase() === filter);

  // Compact mode removes header/card wrapper
  if (compact) {
    return (
      <div className="h-full flex flex-col">
        {/* Compact header with filter badges and controls */}
        <div className="flex items-center justify-between p-2 border-b border-white/10 flex-shrink-0">
          <div className="flex items-center gap-1 flex-wrap">
            <Badge 
              className={`cursor-pointer text-[9px] px-1.5 py-0 ${filter === 'all' ? 'bg-white/20 text-white' : 'bg-slate-800/50 text-slate-500'}`}
              onClick={() => setFilter('all')}
            >
              All
            </Badge>
            <Badge 
              className={`cursor-pointer text-[9px] px-1.5 py-0 ${filter === 'gps' ? 'bg-green-500/30 text-green-400' : 'bg-slate-800/50 text-slate-500'}`}
              onClick={() => setFilter('gps')}
            >
              GPS
            </Badge>
            <Badge 
              className={`cursor-pointer text-[9px] px-1.5 py-0 ${filter === 'ais' ? 'bg-amber-500/30 text-amber-400' : 'bg-slate-800/50 text-slate-500'}`}
              onClick={() => setFilter('ais')}
            >
              AIS
            </Badge>
            <Badge 
              className={`cursor-pointer text-[9px] px-1.5 py-0 ${filter === 'demo' ? 'bg-purple-500/30 text-purple-400' : 'bg-slate-800/50 text-slate-500'}`}
              onClick={() => setFilter('demo')}
            >
              DEMO
            </Badge>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsPaused(!isPaused)}
              className={`h-6 w-6 p-0 ${isPaused ? 'text-amber-400' : 'text-slate-500'}`}
            >
              {isPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={clearLines}
              className="h-6 w-6 p-0 text-slate-500"
            >
              <Trash2 className="w-3 h-3" />
            </Button>
          </div>
        </div>
        
        {/* Scrollable content */}
        <ScrollArea className="flex-1" ref={scrollRef}>
          <div className="font-mono text-[9px] p-1.5 space-y-0.5">
            {!isConnected ? (
              <div className="text-center py-4 text-slate-500">
                <Radio className="w-6 h-6 mx-auto mb-1 opacity-30" />
                <p className="text-[10px]">Connect to see raw data</p>
              </div>
            ) : filteredLines.length === 0 ? (
              <div className="text-center py-6 text-slate-500">
                <Terminal className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-[11px] font-medium mb-1">No NMEA Data</p>
                <p className="text-[9px] text-slate-600 max-w-[200px] mx-auto">
                  Raw data will appear here when:
                </p>
                <ul className="text-[9px] text-slate-600 mt-1 text-left max-w-[180px] mx-auto space-y-0.5">
                  <li>• AIS TCP feed is connected</li>
                  <li>• Demo vessels are enabled (simulated NMEA)</li>
                </ul>
                <p className="text-[9px] text-cyan-400/60 mt-2">
                  Check Settings → Connection
                </p>
              </div>
            ) : (
              filteredLines.slice(-50).map((item) => {
                const Icon = item.info.icon;
                return (
                  <div 
                    key={item.id} 
                    className={`flex items-start gap-1 p-1 rounded ${item.info.bg} border border-white/5`}
                  >
                    <Icon className={`w-2.5 h-2.5 mt-0.5 flex-shrink-0 ${item.info.color}`} />
                    <span className={`${item.info.color} break-all leading-tight`}>{item.line}</span>
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>
        
        {isPaused && (
          <div className="text-center py-1 border-t border-white/10">
            <Badge className="bg-amber-500/30 text-amber-400 border-amber-500/50 text-[9px]">
              PAUSED
            </Badge>
          </div>
        )}
      </div>
    );
  }

  return (
    <Card className="glass-panel hud-border h-full">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base text-white flex items-center gap-2">
            <Terminal className="w-4 h-4 text-cyan-400" />
            Raw NMEA Data
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsPaused(!isPaused)}
              className={isPaused ? 'text-amber-400' : 'text-slate-400'}
            >
              {isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={clearLines}
              className="text-slate-400"
            >
              <Trash2 className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={downloadLog}
              className="text-slate-400"
            >
              <Download className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <Badge 
            className={`cursor-pointer ${filter === 'all' ? 'bg-white/20 text-white' : 'bg-slate-800 text-slate-400'}`}
            onClick={() => setFilter('all')}
          >
            All ({lines.length})
          </Badge>
          <Badge 
            className={`cursor-pointer ${filter === 'gps' ? 'bg-green-500/30 text-green-400' : 'bg-slate-800 text-slate-400'}`}
            onClick={() => setFilter('gps')}
          >
            <Satellite className="w-3 h-3 mr-1" />
            GPS ({stats.gps})
          </Badge>
          <Badge 
            className={`cursor-pointer ${filter === 'ais' ? 'bg-amber-500/30 text-amber-400' : 'bg-slate-800 text-slate-400'}`}
            onClick={() => setFilter('ais')}
          >
            <Ship className="w-3 h-3 mr-1" />
            AIS ({stats.ais})
          </Badge>
          <Badge 
            className={`cursor-pointer ${filter === 'own' ? 'bg-cyan-500/30 text-cyan-400' : 'bg-slate-800 text-slate-400'}`}
            onClick={() => setFilter('own')}
          >
            <MapPin className="w-3 h-3 mr-1" />
            Own ({stats.own})
          </Badge>
          <Badge 
            className={`cursor-pointer ${filter === 'demo' ? 'bg-purple-500/30 text-purple-400' : 'bg-slate-800 text-slate-400'}`}
            onClick={() => setFilter('demo')}
          >
            <Radio className="w-3 h-3 mr-1" />
            Demo ({stats.demo})
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        <ScrollArea className="h-[300px]" ref={scrollRef}>
          <div className="font-mono text-xs p-2 space-y-1">
            {!isConnected ? (
              <div className="text-center py-8 text-slate-500">
                <Radio className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p>Connect to AIS feed to see raw data</p>
              </div>
            ) : filteredLines.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                <Terminal className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p className="text-sm font-medium mb-2">No NMEA Data Received</p>
                <p className="text-xs text-slate-600 max-w-[280px] mx-auto mb-3">
                  Raw NMEA sentences will appear here when data is flowing from your AIS receiver or when demo vessels are active.
                </p>
                <div className="text-xs text-slate-600 text-left max-w-[240px] mx-auto space-y-1">
                  <p className="font-medium text-slate-400">To see data:</p>
                  <p>• Connect to an AIS TCP feed in Settings</p>
                  <p>• Or enable Demo Vessels (simulated NMEA)</p>
                </div>
                <p className="text-xs text-cyan-400/60 mt-4">
                  Demo vessels generate [DEMO] prefixed sentences
                </p>
              </div>
            ) : (
              filteredLines.map((item) => {
                const Icon = item.info.icon;
                return (
                  <div 
                    key={item.id} 
                    className={`flex items-start gap-2 p-1.5 rounded ${item.info.bg} border border-white/5`}
                  >
                    <span className="text-slate-600 whitespace-nowrap">{item.timestamp}</span>
                    <Icon className={`w-3 h-3 mt-0.5 flex-shrink-0 ${item.info.color}`} />
                    <span className={`${item.info.color} break-all`}>{item.line}</span>
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>
        
        {isPaused && (
          <div className="absolute bottom-2 left-1/2 -translate-x-1/2">
            <Badge className="bg-amber-500/30 text-amber-400 border-amber-500/50">
              PAUSED
            </Badge>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
