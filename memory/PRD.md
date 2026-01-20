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
- **Backend**: FastAPI (Python), asyncio, WebSockets, BeautifulSoup4, pyais, pymongo
- **Frontend**: React, TailwindCSS, lucide-react, shadcn/ui
- **Database**: MongoDB
- **Deployment**: Docker, docker-compose

## What's Been Implemented

### December 2025 - Latest Session
- ✅ **Demo Mode Removed (P0)** - Completely removed all Demo Mode functionality per user request
  - Removed `/api/demo/add-vessel`, `/api/demo/add-tow`, `/api/demo/clear-vessels` backend endpoints
  - Removed Demo Mode button and Exit Demo button from desktop header
  - Removed Demo Mode button from mobile menu
  - Removed demoMode state and handlers from App.js
  - Removed demo status display from ConnectionStatus component
  - App now requires a live AIS TCP connection to function (no mock data option)

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
