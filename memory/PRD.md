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

### January 2026 - Latest Session
- ✅ **Touch Gesture Support** - Mobile map now supports drag-to-pan (touch drag up = view south)
- ✅ **Lock Status on Desktop** - Added Lock Status panel to desktop right sidebar (was mobile-only)
- ✅ **Zoom Slider** - Replaced binary zoom toggle with multi-level slider (10mi-500mi range)
- ✅ **Diamond Vessel Markers** - Commercial vessels now render as orange diamonds, user vessel as cyan circle
- ✅ **Scroll-to-Pan Map** - Mouse wheel scrolling pans the river map view up/down
- ✅ **Default Zoom 20mi** - Changed from 25mi to 20mi
- ✅ **Cleaner Map Title** - Simplified from "±20mi around Lock 2" to "River Map"
- ✅ **View Range Indicator** - Shows "RM X – Y" with responsive hint ("Scroll to pan" on desktop, "Drag to pan" on mobile)

### Previous Sessions
- ✅ Global "Show Vessel Names" toggle
- ✅ Mobile feature parity & UI overhaul
- ✅ UI & terminology refinements ("Lock Timing" instead of "Race")
- ✅ Editable vessel type in detail modal
- ✅ Direction indicators on vessel markers
- ✅ Dynamic lock border colors based on timing status
- ✅ Dismissible "Traffic Delay" alert
- ✅ "Demo Mode" indicator
- ✅ USACE lock status scraping

## Known Blockers
- **USACE LPMS Integration** - Blocked due to JavaScript-rendered content requiring headless browser

## Database Schema
- `db.vessel_names`: `{ mmsi, name, ship_type, updated_at }`
- `db.blocked_mmsis`: `{ mmsi, reason, blocked_at }`
- `db.lpms_lockages`: `{ lock_id, vessel_name, direction, lockage_time_minutes, timestamp }`

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
- Running lockage average calculation
- Offline mode with data caching
- Multiple target locks display

## Refactoring Needs
- Break down `server.py` into modules (routes, services, database)
- Split `Dashboard.jsx` (1200+ lines) into smaller components and custom hooks
