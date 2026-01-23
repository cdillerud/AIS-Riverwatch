# River Watch v1.0 - Product Requirements Document

## Original Problem Statement
Build a local application named "River Watch" to track vessels on the Upper Mississippi River. The application connects to an AIS (Automatic Identification System) TCP feed from the "Boat Beacon" app to display vessel positions and calculate lock timing.

## Core Features
1. **AIS/GPS Data Integration** - Connect to TCP feed for AIS and NMEA GPS data
2. **Vessel Tracking** - Display user's vessel and commercial vessels on a simplified river map
3. **Lock Timing Calculation** - Calculate required speed to reach target lock before competing vessels
4. **Alert System** - Visual alerts when required speed exceeds maximum
5. **Connection Management** - Configure IP, Port, MMSI settings
6. **Local Deployment** - Docker-compose setup
7. **Persistent Configuration** - Settings page for vessel and UI preferences
8. **Mobile-Friendly UI** - Responsive design

## Tech Stack
- **Backend**: FastAPI (Python), asyncio, WebSockets, BeautifulSoup4, pyais, pymongo, httpx
- **Frontend**: React, TailwindCSS, lucide-react, shadcn/ui
- **Database**: MongoDB
- **Deployment**: Docker, docker-compose
- **External APIs**: USACE LPMS XML API for lock queue data

## What's Been Implemented

### December 2025 - Latest Session
- ✅ **USACE Lock Queue Integration (P0)** - REAL barge counts from authoritative source!
  - Fetches lock queue XML data from `ndc.ops.usace.army.mil/ords/lockqueue_xml`
  - Covers all 26 Upper Mississippi locks (1-27, excluding 23, 26)
  - Provides actual barge counts (no more guessing!)
  - Auto-refreshes every 15 minutes in background
  - New API endpoints: `GET /api/usace/lock-queue`, `POST /api/usace/refresh`, `GET /api/usace/vessel/{mmsi}`
  - Vessels show "USACE Verified" badge when barge count comes from USACE
- ✅ **Lock Timing 100-Mile Filter** - Only warn about threats within 100mi of user
- ✅ **AIS Connection Manager Refactor (P0)** - Fixed connection drops/reconnects issue
  - Implemented singleton `AISConnectionManager` class for ONE long-lived TCP connection
  - All WebSocket clients now share the same AIS connection (no per-client TCP connections)
  - Added automatic reconnection with exponential backoff (1s → 60s max)
  - Added stale connection detection (reconnects if no data for 60s)
  - New API endpoints: `GET /api/connection/status`, `POST /api/connection/reconnect`
  - WebSocket clients now subscribe/unsubscribe instead of creating connections
- ✅ **Demo Mode Removed (P0)** - Completely removed all Demo Mode functionality per user request
- ✅ **GCP Deployment Ready** - Added production Docker Compose and deployment scripts
  - `docker-compose.prod.yml` with nginx reverse proxy
  - `deploy.sh` one-click deployment script
  - `DEPLOYMENT.md` comprehensive deployment guide
  - Production frontend Dockerfile with nginx static serving

### January 2026 - Current Session (Latest Fix)
- ✅ **Fixed Default Barge Counts Bug (P0 - CRITICAL)** - TRUE ROOT CAUSE found and fixed!
  - **Problem**: Tow vessels displayed barge counts ("6 barges (2x3)") even when not at a lock
  - **TRUE Root Cause**: The USACE API returns **historical completed lockages** (days/weeks old). These were being cached and matched to vessels by name, showing old barge data for vessels that had long since left the lock.
  - **Evidence**: Before fix - 171 vessels in cache. After fix - 1 vessel (only the one actually at a lock).
  - **Fix Applied**:
    1. Modified `fetch_usace_lock_queue_data()` to **skip completed lockages** - only cache vessels with status='waiting' or 'locking'
    2. Added `is_valid_active_lockage()` check in `get_usace_vessel_info()` as defense-in-depth
  - Now ONLY vessels **currently at a lock** (waiting or actively locking) show barge counts
  - Previous fix (prepare_vessel_for_output) is still in place for additional protection

- ✅ **Vessel Search with Mini-Map (P1)** - New feature added
  - Search bar in Vessels tab filters by MMSI or vessel name
  - Real-time filtering as you type with match highlighting (yellow border)
  - Shows "Found X of Y vessels" count when filtering
  - Mini-map modal popup shows vessel location on river
    - Centered on vessel position with ±15 mile view
    - Shows nearby locks for context
    - Displays vessel speed, heading, river mile
    - Direction indicator (north/south arrow)
  - Files: `VesselList.jsx` (search + map button), `VesselMiniMap.jsx` (new component)

- ✅ **Click Vessel to Map (P1)** - New feature added
  - Clicking a vessel in Vessels tab:
    - Automatically switches to Map tab
    - Centers map on the selected vessel
    - Shows compact info overlay in top-right corner of map
    - Highlights vessel with yellow pulsing ring animation
  - Clicking vessel marker on Map:
    - Shows compact info overlay with vessel details (position, speed, heading, barge info)
    - Click X or click another vessel to dismiss
  - Info overlay shows: MMSI, river mile, speed, heading, badges (YOUR VESSEL, TOW, USACE), barge config, destination
  - Files: `Dashboard.jsx` (handleVesselClickFromList), `RiverVisualization.jsx` (mapSelectedVessel state, info overlay)

### January 2026 - Previous Session
- ✅ **Running Lockage Averages (P1)** - Implemented average lockage times and wait times for all 27 locks
  - Shows Tow vs Recreational breakdown
  - Displays both lockage duration and wait times
  - Uses USACE baseline data that varies by lock (busier southern locks have higher times)
  - **Real-time vessel passage tracking** - automatically records actual lockage times as vessels transit
  - Data stored in MongoDB and incorporated into running averages
  - Direction breakdown (upbound/downbound) available in API
- ✅ **Touch Gesture Support** - Mobile map now supports drag-to-pan (touch drag up = view south)
- ✅ **Lock Status on Desktop** - Added Lock Status panel to desktop right sidebar (was mobile-only)
- ✅ **Zoom Slider** - Replaced binary zoom toggle with multi-level slider (10mi-500mi range)
- ✅ **Diamond Vessel Markers** - Commercial vessels now render as orange diamonds, user vessel as cyan circle
- ✅ **Scroll-to-Pan Map** - Mouse wheel scrolling pans the river map view up/down
- ✅ **Default Zoom 20mi** - Changed from 25mi to 20mi
- ✅ **Cleaner Map Title** - Simplified from "±20mi around Lock 2" to "River Map"
- ✅ **View Range Indicator** - Shows "RM X – Y" with responsive hint ("Scroll to pan" on desktop, "Drag to pan" on mobile)
- ✅ **Tabbed Desktop Layout** - Performance optimization with conditional rendering
- ✅ **"At Lock" Status** - Vessels inside lock chamber geo-fence show "At Lock" badge
- ✅ **Lockage History in Vessel Detail** - Shows vessel's past transit times through locks

### Previous Sessions
- ✅ Global "Show Vessel Names" toggle
- ✅ Mobile feature parity & UI overhaul
- ✅ UI & terminology refinements ("Lock Timing" instead of "Race")
- ✅ Editable vessel type in detail modal
- ✅ Direction indicators on vessel markers
- ✅ Dynamic lock border colors based on timing status
- ✅ Dismissible "Traffic Delay" alert
- ✅ USACE lock status scraping

## Known Blockers
- **USACE LPMS Integration** - Blocked due to JavaScript-rendered content requiring headless browser

## Database Schema
- `db.vessel_names`: `{ mmsi, name, ship_type, updated_at }`
- `db.blocked_mmsis`: `{ mmsi, reason, blocked_at }`
- `db.lockage_history`: `{ lock_id, vessel_mmsi, is_tow, wait_time_minutes, lockage_duration_minutes, recorded_at }`

## Key Files
- `/app/backend/server.py` - FastAPI server, AIS parsing, scraping
- `/app/frontend/src/pages/Dashboard.jsx` - Main dashboard component
- `/app/frontend/src/components/RiverVisualization.jsx` - River map with vessels
- `/app/frontend/src/components/RaceAnalysisPanel.jsx` - Lock timing analysis
- `/app/frontend/src/App.css` - Custom styles

## Upcoming Tasks (P1)
- Sound/Vibration alerts for "Traffic Delay" warnings
- MarineTraffic API integration for vessel name lookups

## Future Tasks (P2-P3)
- Offline mode with data caching
- Multiple target locks display
- "Recent Lockages" Tab - UI section to display raw lockage history

## Refactoring Needs
- Break down `server.py` (~2500 lines) into modules (routes, services, database)
- Split `Dashboard.jsx` (1300+ lines) into smaller components and custom hooks
- Extract state management from App.js into custom hooks (useVessels, useConnection)
