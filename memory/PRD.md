# River Watch - Product Requirements Document

## Original Problem Statement
Build a local application named "River Watch" to track vessels on the upper Mississippi River. The application should connect to an AIS (Automatic Identification System) TCP feed, calculate "Lock Timing" to help the user's vessel beat commercial traffic to locks, and display this information on a simplified river map.

## Core Requirements
1. **AIS/GPS Data Integration:** Connect to a TCP feed to receive and parse AIS and NMEA GPS data.
2. **Vessel Tracking:** Display the user's vessel and other commercial vessels on a simplified river map.
3. **"Lock Timing" Calculation:** Calculate the required speed for the user's vessel to reach a target lock before a competing commercial vessel.
4. **Alert System:** Trigger a visual alert if the required speed exceeds the user's boat's maximum speed.
5. **Local Deployment:** Provide a `docker-compose` setup.
6. **Persistent Configuration:** A Settings page for persisting vessel MMSI, name, max speed, and other UI preferences.
7. **USACE Data Integration:** Fetch and display lock status and real-time lockage data.
8. **Tow/Barge Estimation:** Identify commercial tows and display their barge count from USACE data.
9. **Data Visibility:** Show all available AIS data for any vessel in a detail view.
10. **MMSI/Vessel Name Search:** Implement a search bar to filter the vessel list.
11. **Click-to-Map Info:** Clicking a vessel on the map or in the list should display a compact information card on the map.
12. **Lock Wait Time Predictions:** When a lock is clicked, show predicted wait times, USACE delays, and other detailed information.
13. **User Accounts:** Implement user registration and login (Email/Password and Google Social Login) to support multiple users with their own settings and lists of MMSIs.
14. **Persistent Vessel Position:** A user's vessel position should be stored in their account and restored when they log in.
15. **Demo Vessels:** The application should include simulated vessels for testing purposes, with a setting to toggle them on/off.
16. **NOAA/USGS Integration:** Integrate real-time environmental data like water levels, current speed, and water temperature from gauges near the locks.
17. **Traffic Watch Mode:** Allow users without vessels to monitor river traffic (for lock operators, marina operators, shipping companies, etc.)

## User Personas

### 1. Vessel Owner (Primary)
- Recreational boater on the upper Mississippi
- Wants to time arrivals at locks to avoid commercial traffic
- Needs real-time position tracking and race analysis

### 2. Traffic Watcher (New)
- Lock operators, marina operators, shipping companies, river enthusiasts
- Monitors traffic flow without owning a vessel
- Needs traffic summaries, vessel counts by direction, and recent lockage history

## Architecture

### Tech Stack
- **Frontend**: React, Shadcn UI, TailwindCSS
- **Backend**: FastAPI, Python 3.11
- **Database**: MongoDB
- **Real-time**: WebSockets
- **Authentication**: JWT (email/password) + OAuth2 (Google)
- **External APIs**: USACE (lock data), USGS Water Services (river conditions)

### Key Files
```
/app/
├── backend/
│   ├── config.py          # App config, LOCKS data, USGS_GAUGE_MAP
│   ├── database.py        # MongoDB connection setup
│   ├── models/            # Pydantic models
│   ├── routes/            # Route modules
│   ├── services/          # Service logic
│   ├── server.py          # Core app logic (NEEDS REFACTOR)
│   └── ...
└── frontend/
    ├── src/
    │   ├── App.js         # Core component, handles routing
    │   ├── pages/
    │   │   ├── Dashboard.jsx      # Main dashboard with map
    │   │   ├── SettingsPage.jsx   # User settings, demo toggle, raw data
    │   │   └── SetupPage.jsx      # Account type selection, vessel/watch point setup
    │   ├── components/
    │   │   ├── RiverVisualization.jsx
    │   │   ├── LockDetailModal.jsx
    │   │   └── VesselDetailModal.jsx
    │   └── context/
    │       └── AuthContext.jsx
    └── ...
```

### Database Schema
- **users**: `{ user_id, email, name, account_type, vessels[], watch_point, favorite_locks[], vessel_watch_list[], settings }`
- **vessel_sightings**: `{ mmsi, timestamp, lat, lon, usace_source, ... }`
- **lockage_history**: `{ lock_id, vessel_name, mmsi, direction, timestamps... }`

## Implemented Features

### Phase 1: Core MVP ✅
- [x] AIS TCP connection and NMEA parsing
- [x] River map visualization with vessel markers
- [x] Lock timing calculation and race analysis
- [x] User authentication (email/password + Google OAuth)
- [x] Persistent vessel settings per user
- [x] USACE lock status integration
- [x] Demo vessel simulation

### Phase 2: Enhanced UX ✅
- [x] Session isolation fix (data cleared on logout)
- [x] Auto-connect for returning users with saved vessels
- [x] Redesigned vessel info panel (single-click, all data visible)
- [x] Demo vessels with direction and ETA
- [x] Clickable lock header to open details

### Phase 3: Environmental Data ✅
- [x] USGS Water Services API integration
- [x] Water level, temperature, current speed in lock details
- [x] Flood stage indicators with thresholds

### Phase 4: Traffic Watch Mode ✅ (January 27, 2026)
- [x] Account type selection (vessel_owner / traffic_watch)
- [x] Watch point presets for all locks
- [x] Traffic Summary dashboard for observers
- [x] Directional vessel counts (Northbound/Southbound)
- [x] "Near Lock" vessel list
- [x] Recent lockages history
- [x] Backend APIs for account type, watch point, favorite locks, vessel watch

### UI/UX Improvements ✅
- [x] Nearby Vessels sorted by River Mile (descending)
- [x] Race analysis only shows threats BETWEEN user and lock
- [x] Removed Locks/Raw tabs, moved Raw Data to Settings
- [x] Extended Nearby Vessels card to fill sidebar height
- [x] Swapped Traffic Ahead and Queue positions

## Pending Features

### P0 - High Priority
- [ ] Expand NOAA/USGS integration with forecast data
- [ ] Vessel Alert notifications (when watched vessels pass a point)

### P1 - Medium Priority
- [ ] Sound/Vibration alerts for "Can't Beat" warnings
- [ ] MarineTraffic API integration for vessel name lookups
- [ ] Favorite Locks quick-switch UI

### P2 - Lower Priority
- [ ] Quick Position Presets
- [ ] Switch Mode button (vessel owner ↔ traffic watch)

### Future/Backlog
- [ ] Lock Wait Time Predictions (ML-powered)
- [ ] Mobile App (PWA Conversion)
- [ ] Offline Mode with Smart Sync
- [ ] Trip Planner
- [ ] Community/Social Features
- [ ] Premium Data Integrations
- [ ] Vessel Watchlist with alerts
- [ ] Speed Advisor

## Technical Debt
1. **Backend Refactoring**: Extract AIS service, USACE service, and WebSocket logic from server.py into separate modules
2. **Frontend Refactoring**: Extract state management and data fetching into custom hooks in App.js

## Test Accounts
- **Vessel Owner**: `chaddillerud@gmail.com` / `test123`
- **Vessel Owner 2**: `test@example.com` / `password123`
- **Traffic Watch**: `trafficwatch@test.com` / `test123`
- **Google Auth**: `cdillerud@gmail.com` (OAuth flow)

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login with email/password
- `POST /api/auth/logout` - Logout and clear session
- `GET /api/auth/me` - Get current user info

### User Settings
- `GET/PUT /api/user/settings` - User settings
- `POST/GET /api/user/account-type` - Account type (NEW)
- `POST/GET /api/user/watch-point` - Watch point (NEW)
- `POST/GET /api/user/favorite-locks` - Favorite locks (NEW)
- `POST/GET/DELETE /api/user/vessel-watch` - Vessel watch list (NEW)

### Data
- `GET /api/vessels` - Get all vessels
- `GET /api/locks` - Get all locks with status
- `GET /api/traffic-summary/{lock_id}` - Traffic summary (NEW)
- `GET /api/locks/{lock_id}/water-conditions` - USGS water data
- `GET /api/session/{mmsi}/race-analysis/{lock_id}` - Race analysis

## Refresh Intervals
- Vessels: 30 seconds (WebSocket provides real-time updates)
- Race Analysis: 20 seconds
- Lock Status: 5 minutes
- Lockage Times: 10 minutes
- Traffic Summary: 30 seconds
- Auto Soft-Refresh: 15 minutes
