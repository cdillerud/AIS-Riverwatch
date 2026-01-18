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
- Lock positions (Lock 2: RM 815.2, Lock 3: RM 796.9)
- Race analysis API with ETA calculations
- Required speed calculator
- Demo mode for testing without live AIS feed
- Settings persistence in MongoDB

### Frontend (React)
- Setup page for IP/Port/MMSI configuration
- Dashboard with:
  - River visualization (RM 790-835)
  - Lock positions with tooltips
  - Vessel markers (user in cyan, commercial in amber)
  - Direction indicators (north/southbound)
- Race to Lock panel:
  - Target lock selection
  - User distance and ETA
  - Threatening vessel info
  - Required speed calculation
  - Speed gauge with color coding
  - "Can Beat" / "Cannot Beat" indicators
- Alert banner when speed > 25 MPH required
- Vessel list with tabs (All/Commercial)
- Dark nautical "Tactical Sonar" theme

### API Endpoints
- `GET /api/` - Health check
- `GET /api/locks` - Get lock positions
- `POST /api/connection/test` - Test AIS connection
- `GET /api/vessels` - Get tracked vessels
- `GET /api/race-analysis/{lock_id}` - Race analysis
- `POST /api/set-user-mmsi` - Set user MMSI
- `GET/POST /api/settings` - Settings management
- `POST /api/demo/add-vessel` - Add demo vessel
- `DELETE /api/demo/clear-vessels` - Clear demo vessels
- `WS /ws/ais` - WebSocket for real-time AIS

## Prioritized Backlog

### P0 (Critical) - Done
- [x] AIS connection and parsing
- [x] Vessel tracking
- [x] ETA calculations
- [x] Speed requirement analysis
- [x] 25 MPH alert

### P1 (High Priority) - Future
- [ ] Actual AIS TCP connection testing with live Boat Beacon
- [ ] Persist vessel history in MongoDB
- [ ] Sound alerts for "Cannot Beat" scenarios
- [ ] Push notifications

### P2 (Medium Priority) - Future
- [ ] Historical lock wait times
- [ ] Map layer with actual river geography
- [ ] Multiple user vessel support
- [ ] Weather overlay

## Next Tasks
1. Test with actual Boat Beacon AIS feed
2. Add sound alert for critical warnings
3. Implement vessel history tracking
4. Add lock queue estimation based on historical data
