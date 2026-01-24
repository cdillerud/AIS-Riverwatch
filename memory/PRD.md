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

### Upcoming (P1)
- Sound/Vibration Alerts for "Traffic Delay" warnings
- MarineTraffic API Integration for faster vessel name lookups

### Future (P2/P3)
- Offline Mode with data caching
- Multiple Target Locks (show ETAs to next 2-3 locks)
- "Recent Lockages" Tab

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
- `/app/frontend/src/components/VesselList.jsx` - Vessel list with search

### Key API Endpoints
- `POST /api/connection/start` - Start AIS connection
- `GET /api/vessels` - Get active vessels in river mile range
- `GET /api/usace/lock-queue` - Get USACE vessel cache
- `GET /api/connection/status` - Get AIS connection status

## Recent Changes (Dec 2024)

### Critical Fix: Docker + WebSocket Connection (Jan 2025)
**Problem**: Frontend couldn't connect to backend on production VM - mixed content errors and WebSocket reconnection loops.

**Root Causes**:
1. `docker-compose.yml` used `environment:` instead of `build.args` for `REACT_APP_BACKEND_URL`
2. Site served over HTTPS but frontend tried connecting via HTTP/WS (mixed content blocked)
3. WebSocket reconnection logic had race conditions causing connect/disconnect loops

**Solution**:
1. Fixed `docker-compose.yml` to use `build.args` (React needs env vars at build time)
2. Set `REACT_APP_BACKEND_URL=https://riverwatchais.com` for HTTPS compatibility
3. Rewrote WebSocket connection logic in `App.js`:
   - Set `isConnected=true` in `onopen` instead of waiting for server message
   - Clear `wsRef.current` before closing to prevent race conditions
   - Only trigger reconnect from active socket's `onclose`
   - Removed `isConnected` from auto-connect dependencies

### Bug Fix: Map Centering from Vessel List
**Problem**: Clicking a vessel in the list showed info overlay but map didn't pan to vessel location.

**Root Cause**: 
1. Component mounting timing - RiverVisualization unmounts when not on Map tab
2. Setting focusedVessel and switching tabs simultaneously caused race condition
3. Memo comparison function wasn't detecting focusedVessel changes

**Solution**:
1. Added `focusedVessel?.mmsi` check to memo comparison function
2. Added 100ms delay before setting focusedVessel (allows component to mount first)
3. Modified scrollOffset reset logic to not reset when focusing on a vessel
4. Removed orphaned VesselMiniMap.jsx component

### Code Cleanup
- Removed unused VesselMiniMap component and imports from VesselList.jsx
- Cleaned up debug console.log statements after fix verification

## Known Issues
- WebSocket dev server errors in console (harmless - hot reload trying to connect)

## Refactoring Needed
- Break down `backend/server.py` into smaller modules:
  - `ais_parser.py`
  - `usace_api.py`
  - `websocket_manager.py`
  - `api_routes.py`
