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
- GPS sentence parsing ($GPGGA, $GPRMC, $GPGLL)
- Vessel tracking with river mile estimation
- Lock positions (All 27 Upper Mississippi locks)
- Race analysis API with ETA calculations and configurable buffer time
- Required speed calculator
- Demo mode for testing without live AIS feed
- Settings persistence API (GET/POST /api/settings)
- USACE lock status scraping for open/closed status
- Tow/barge detection with lockage time estimation
- Vessel static data cache for names (from AIS Type 5/24 messages)
- Docker support for local deployment
- **Raw NMEA WebSocket** (`/ws/raw`) for debugging live data stream

### Frontend (React)
- Setup page for IP/Port/MMSI configuration
- **Settings Page** (accessible via Settings button):
  - Vessel info: MMSI, boat name, max speed
  - AIS Connection: default IP/port
  - Map Display: zoom range, show all locks, default lock
  - Lock priority buffer (minutes before tow arrival)
  - Show/hide buoys toggle
  - Known vessel names management
  - Alerts: sound toggle, speed threshold
  - All settings persist across sessions
- Dashboard with:
  - River visualization (All 27 locks)
  - **Map Zoom feature**: Zooms to ±N mi around selected lock (configurable)
  - Lock positions with tooltips and phone numbers
  - Vessel markers (user in cyan, commercial in amber)
  - Direction indicators (north/southbound)
  - "Zoomed" / "Full Map" toggle button
  - Off-screen user vessel indicator
- Race to Lock panel:
  - Target lock selection (all 27 locks)
  - User distance and ETA
  - Threatening vessel info with barge count
  - Required speed calculation with configurable buffer
  - Speed gauge with color coding
  - "Can Beat" / "Cannot Beat" indicators
- Alert banner when speed > max speed required
- Vessel list with tow/barge info (e.g., "+45min lock", "DOUBLE LOCK" for >9 barges)
- **Vessel Detail Modal**: Click any vessel to see all AIS data (destination, ETA, callsign, etc.)
- Lock status panel (USACE open/closed status)
- **Raw Data Debug Panel**: View live NMEA sentences from AIS feed
  - Filter by type: GPS, AIS, Own (AIVDO)
  - Pause/resume, clear, download log
  - Available on both desktop (right panel) and mobile ("Raw" tab)
- Mobile-responsive design with tab navigation (Race, Locks, Map, Boats, Raw)
- Dark nautical "Tactical Sonar" theme
- Demo Mode for testing in cloud environment

### API Endpoints
- `GET /api/` - Health check
- `GET /api/locks` - Get lock positions (all 27 locks)
- `GET /api/locks/status` - Get USACE lock status (open/closed)
- `GET /api/locks/{lock_id}/status` - Get specific lock status
- `POST /api/connection/test` - Test AIS connection
- `GET /api/vessels` - Get tracked vessels
- `GET /api/vessel-cache` - Get cached vessel static data
- `POST /api/vessel-cache/{mmsi}` - Manually set vessel name
- `GET /api/race-analysis/{lock_id}?buffer_minutes=20` - Race analysis with buffer
- `POST /api/set-user-mmsi` - Set user MMSI
- `GET/POST /api/settings` - Settings management (persistent)
- `GET /api/debug/state` - Debug endpoint for backend state
- `POST /api/demo/add-vessel` - Add demo vessel
- `POST /api/demo/add-tow` - Add demo tow with barges
- `DELETE /api/demo/clear-vessels` - Clear demo vessels
- `WS /ws/ais` - WebSocket for real-time AIS data (processed)
- `WS /ws/raw` - WebSocket for raw NMEA data stream (debug)

## Prioritized Backlog

### P0 (Critical) - ✅ COMPLETED
- [x] AIS connection and parsing
- [x] GPS sentence parsing (GPGGA, GPRMC, GPGLL)
- [x] Vessel tracking
- [x] ETA calculations with configurable buffer
- [x] Speed requirement analysis
- [x] Max speed alert
- [x] All 27 Upper Mississippi locks
- [x] Mobile responsive UI
- [x] Docker local deployment
- [x] USACE lock status integration
- [x] Barge/tow tracking with lockage estimates
- [x] Double lockage warning (>9 barges)
- [x] Settings page with persistence
- [x] Map zoom to target lock
- [x] Vessel detail modal with full AIS data
- [x] Raw NMEA data debug panel
- [x] Vessel static data caching (names from Type 5/24)
- [x] Off-screen user vessel indicator

### P1 (High Priority) - Upcoming
- [ ] **Debug user MMSI issue with live Boat Beacon feed** (use Raw Data panel)
- [ ] Sound/vibration alerts for "Cannot Beat" scenarios
- [ ] MarineTraffic/AISHub API integration for vessel names
- [ ] Push notifications

### P2 (Medium Priority) - Future
- [ ] USACE lock wait time API (if available)
- [ ] Offline mode with service workers
- [ ] Multiple target locks display
- [ ] Historical lock wait times
- [ ] Persist vessel history in MongoDB

### P3 (Low Priority) - Backlog
- [ ] Map layer with actual river geography
- [ ] Weather overlay
- [ ] River current speed from USGS
- [ ] Multiple user vessel support

## Known Issues
- **User vessel (MMSI 338414076) not appearing with live Boat Beacon feed**: User reports their vessel doesn't show up. Use the Raw Data panel to diagnose if GPS/AIVDO sentences are being received.

## Next Tasks
1. **Use Raw Data panel to debug live feed** - Have user connect and check if GPS sentences ($GPGGA/$GPRMC) or AIVDO messages appear
2. Implement sound/vibration alerts for critical warnings
3. Add MarineTraffic API integration for vessel name lookup
4. Add offline mode for graceful degradation
