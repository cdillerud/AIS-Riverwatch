# River Watch - AIS Vessel Tracker & Lock Timer

## Original Problem Statement
Build an app that uses an AIS feed via TCP to track vessels on the upper Mississippi, use their speed and position to gauge timing to the next lock. Specifically interested in pools 2 and 3. User wants to calculate if they can beat commercial vessels to the lock - if downbound from river mile 830 and a commercial vessel is northbound at river mile 792, calculate how fast they need to go to beat that commercial vessel to lock 2.

## User Requirements
- AIS feed connection via TCP on port 5353
- App prompts for current IP address
- Vessel identification by MMSI number
- Speed display in MPH
- Alert if required speed > 25 MPH (user's max speed)
- Focus on Lock 2 (RM 815.2) and Lock 3 (RM 796.9)

## User Personas
1. **Recreational Boater** - Primary user who owns a boat with AIS transponder via Boat Beacon app, needs to time lock approaches to avoid waiting behind commercial traffic

## Core Requirements (Static)
- Connect to AIS TCP feed from Boat Beacon mobile app
- Parse NMEA/AIS messages for vessel position, speed, course
- Track user's vessel by MMSI
- Identify commercial vessels heading to same lock
- Calculate ETA to lock for all vessels
- Calculate required speed to beat threatening vessels
- Alert when required speed exceeds 25 MPH

## What's Been Implemented (January 18, 2026)

### Backend (FastAPI)
- AIS TCP connection via WebSocket bridge
- NMEA/AIS message parsing with pyais library
- Vessel tracking with river mile estimation
- Lock positions (Locks 2-10, RM 615-835)
- Race analysis API with ETA calculations
- Required speed calculator
- Demo mode for testing without live AIS feed
- Settings persistence API (GET/POST /api/settings)
- USACE lock status scraping for open/closed status
- Tow/barge detection with lockage time estimation
- Docker support for local deployment

### Frontend (React)
- Setup page for IP/Port/MMSI configuration
- **Settings Page** (accessible via Settings button):
  - Vessel info: MMSI, boat name, max speed
  - AIS Connection: default IP/port
  - Map Display: zoom range, show all locks, default lock
  - Alerts: sound toggle, speed threshold
  - All settings persist across sessions
- Dashboard with:
  - River visualization (Locks 2-10)
  - **Map Zoom feature**: Zooms to ±25mi around selected lock (configurable)
  - Lock positions with tooltips
  - Vessel markers (user in cyan, commercial in amber)
  - Direction indicators (north/southbound)
  - "Zoomed" / "Full Map" toggle button
  - Out-of-view vessels indicator
- Race to Lock panel:
  - Target lock selection
  - User distance and ETA
  - Threatening vessel info
  - Required speed calculation
  - Speed gauge with color coding
  - "Can Beat" / "Cannot Beat" indicators
- Alert banner when speed > 25 MPH required
- Vessel list with tow/barge info (e.g., "+45min lock", "DOUBLE LOCK")
- Lock status panel (USACE open/closed status)
- Mobile-responsive design with tab navigation
- Dark nautical "Tactical Sonar" theme
- Demo Mode for testing in cloud environment

### API Endpoints
- `GET /api/` - Health check
- `GET /api/locks` - Get lock positions (Locks 2-10)
- `GET /api/locks/status` - Get USACE lock status (open/closed)
- `POST /api/connection/test` - Test AIS connection
- `GET /api/vessels` - Get tracked vessels
- `GET /api/race-analysis/{lock_id}` - Race analysis
- `POST /api/set-user-mmsi` - Set user MMSI
- `GET/POST /api/settings` - Settings management (persistent)
- `POST /api/demo/add-vessel` - Add demo vessel
- `POST /api/demo/add-tow` - Add demo tow with barges
- `DELETE /api/demo/clear-vessels` - Clear demo vessels
- `WS /ws/ais` - WebSocket for real-time AIS

## Prioritized Backlog

### P0 (Critical) - ✅ COMPLETED
- [x] AIS connection and parsing
- [x] Vessel tracking
- [x] ETA calculations
- [x] Speed requirement analysis
- [x] 25 MPH alert
- [x] Extended lock coverage (Locks 2-10)
- [x] Mobile responsive UI
- [x] Docker local deployment
- [x] USACE lock status integration
- [x] Barge/tow tracking with lockage estimates
- [x] Settings page with persistence
- [x] Map zoom to target lock

### P1 (High Priority) - Upcoming
- [ ] Sound/vibration alerts for "Cannot Beat" scenarios
- [ ] Actual AIS TCP connection testing with live Boat Beacon
- [ ] Persist vessel history in MongoDB
- [ ] Push notifications

### P2 (Medium Priority) - Future
- [ ] USACE lock wait time API (if available)
- [ ] Offline mode with service workers
- [ ] Multiple target locks display
- [ ] Historical lock wait times

### P3 (Low Priority) - Backlog
- [ ] Map layer with actual river geography
- [ ] Weather overlay
- [ ] River current speed from USGS
- [ ] Multiple user vessel support

## Next Tasks
1. Implement sound/vibration alerts for critical warnings
2. Test with actual Boat Beacon AIS feed on local network
3. Add offline mode for graceful degradation
4. Implement vessel history tracking
