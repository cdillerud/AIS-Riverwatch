# River Watch - Product Requirements Document

## Overview
River Watch is a vessel tracking application for the Upper Mississippi River that connects to AIS (Automatic Identification System) data feeds to track commercial and recreational vessels, calculate lock timing, and provide navigation assistance.

## Core Features

### Implemented ✅
1. **AIS/GPS Data Integration** - Connect to TCP feed from Boat Beacon app to receive and parse AIS/NMEA data
2. **Vessel Tracking** - Display user's vessel and commercial vessels on a simplified river map
3. **Lock Timing Calculation** - Calculate required speed to reach target lock before competing vessels
4. **Alert System** - Visual alert when required speed exceeds boat's max speed
5. **Connection Management** - Configure and manage AIS connection settings
6. **Persistent Settings** - Settings page for vessel MMSI, name, max speed, UI preferences
7. **USACE Data Integration** - Fetch lock status and real-time lockage data with barge counts
8. **Tow/Barge Estimation** - Identify commercial tows and display barge counts from USACE
9. **Data Visibility** - Show all AIS data for any vessel in detail view
10. **Vessel Search** - Search bar in Vessels tab to filter by MMSI or name
11. **Click-to-Map with Centering** - Click vessel in list → switches to Map tab → centers map on vessel → shows info overlay
12. **Lock Detail Modal** - Click any lock (map or list) to see:
    - Wait time predictions based on current queue
    - Vessels currently locking and waiting
    - Average lockage times (commercial vs recreational)
    - USACE status and closure info
    - Lock master phone number (click to call)
    - Prediction confidence indicators

### Upcoming (P1)
- Sound/Vibration Alerts for "Traffic Delay" warnings
- MarineTraffic API Integration for faster vessel name lookups

### Future (P2/P3)
- Offline Mode with data caching
- Multiple Target Locks (show ETAs to next 2-3 locks)
- Trip Planner (optimal departure times, multi-lock optimization)
- Mobile App (iOS/Android PWA)
- Community features (user-reported wait times, hazards)

## Technical Architecture

### Stack
- **Backend**: FastAPI, WebSockets, Motor (async MongoDB)
- **Frontend**: React, Tailwind CSS, Shadcn/UI
- **Database**: MongoDB
- **Deployment**: Docker, docker-compose

### Key Files
- `/app/backend/server.py` - Monolithic FastAPI server (3000+ lines, needs refactoring)
- `/app/frontend/src/pages/Dashboard.jsx` - Main dashboard with tab navigation
- `/app/frontend/src/components/RiverVisualization.jsx` - River map component
- `/app/frontend/src/components/LockDetailModal.jsx` - Lock details with wait predictions
- `/app/frontend/src/components/VesselList.jsx` - Vessel list with search

### Key API Endpoints
- `POST /api/connection/start` - Start AIS connection
- `GET /api/vessels` - Get active vessels in river mile range
- `GET /api/usace/lock-queue` - Get USACE vessel cache
- `GET /api/locks/{lock_id}/details` - Get comprehensive lock details with wait prediction
- `GET /api/connection/status` - Get AIS connection status

## Recent Changes

### Lock Detail Modal Feature (Jan 2025)
**New Feature**: Click any lock on the map or in the locks list to see comprehensive details including:
- Wait time predictions based on queue analysis
- Current vessels locking and waiting (with barge counts)
- Average lockage times for commercial tows vs recreational boats
- USACE closure/restriction alerts
- One-tap calling to Lock Master
- Prediction confidence indicators (baseline vs observed data)

**Files Added/Modified**:
- NEW: `/app/frontend/src/components/LockDetailModal.jsx`
- NEW: `/app/backend/server.py` - Added `GET /api/locks/{lock_id}/details` endpoint
- MODIFIED: `RiverVisualization.jsx` - Lock markers are now clickable
- MODIFIED: `LockStatusPanel.jsx` - Added "View Details" buttons
- MODIFIED: `Dashboard.jsx` - Integrated LockDetailModal

### Critical Fix: Docker + WebSocket Connection (Jan 2025)
**Problem**: Frontend couldn't connect to backend on production VM - mixed content errors and WebSocket reconnection loops.

**Solution**:
1. Fixed `docker-compose.yml` to use `build.args` (React needs env vars at build time)
2. Set `REACT_APP_BACKEND_URL=https://riverwatchais.com` for HTTPS compatibility
3. Rewrote WebSocket connection logic to prevent reconnect loops

### Multi-User Support (Jan 2025)
**Feature**: Multiple users can use the app simultaneously with their own MMSI and settings.

**How it works:**
- MMSI stored in browser localStorage (persists across sessions)
- Settings stored per-MMSI in MongoDB (`user_settings` collection)
- One shared AIS feed connection (saves resources)
- Each WebSocket tracks its user's MMSI for personalized vessel highlighting

**New API Endpoints:**
- `GET /api/user/{mmsi}/settings` - Get user-specific settings
- `POST /api/user/{mmsi}/settings` - Save user-specific settings

### Lock Panel Redesign (Jan 2025)

## Known Issues
- WebSocket dev server errors in console (harmless - hot reload trying to connect)

## Refactoring Needed
- Break down `backend/server.py` into smaller modules
