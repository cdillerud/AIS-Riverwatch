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
13. **User Authentication (Jan 2026)** ✅
    - Email/password registration and login
    - Google OAuth via Emergent-managed auth
    - Session-based authentication with httpOnly cookies (7-day expiry)
    - Protected routes (redirect to login if not authenticated)
    - Logout functionality (desktop and mobile)
    - **Session persistence across browser restarts** ✅ (Jan 27, 2026)
14. **Multi-Vessel Fleet Management (Jan 2026)** ✅
    - Associate multiple MMSIs with a single user account
    - Set primary vessel for lock timing calculations
    - Add/remove vessels from fleet in Settings page
    - MMSI uniqueness enforced (one user per MMSI)
15. **Position Editor (Jan 26, 2026)** ✅
    - Edit position directly from HUD bar (click "Set Position" or RM display)
    - Set River Mile, Speed (MPH), and Course (°) manually
    - Accessible even when no AIS data is available
16. **Keyboard Shortcuts (Jan 26, 2026)** ✅
    - `P` - Open position editor
    - `M` - Switch to Map tab
    - `L` - Switch to Locks tab
    - `V` - Switch to Vessels tab
    - `R` - Refresh data
    - `Esc` - Close modal/editor
    - `?` - Show keyboard shortcuts help
17. **Demo Vessels with Direction & ETA (Jan 27, 2026)** ✅
    - Two simulated towboats for testing (M/V DELTA QUEEN, M/V RIVER RUNNER)
    - **Direction of travel** displayed (upriver/downriver, ↑N/↓S)
    - **ETA to next lock** calculated based on direction and speed
    - ETA shown in vessel list (e.g., "→ 2h 50m") and detail modal
    - **Settings toggle** to enable/disable demo vessels
    - **Race analysis working** - demo vessels appear as competitors
18. **Session Isolation Fix (Jan 27, 2026)** ✅
    - Fixed session bleed when switching user accounts
    - localStorage properly cleared on logout
    - User data correctly isolated between sessions

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
- **Authentication**: Session tokens (httpOnly cookies), Google OAuth

### Key Files
#### Backend (Refactored Structure)
- `/app/backend/server.py` - Main FastAPI server (still monolithic, but imports from modules)
- `/app/backend/config.py` - Configuration (LOCKS, CORS, constants)
- `/app/backend/database.py` - MongoDB connection
- `/app/backend/models/` - Pydantic models (auth.py, vessel.py, lock.py)
- `/app/backend/services/` - Business logic (auth_service.py, navigation_service.py)
- `/app/backend/routes/` - Route templates for future migration
- `/app/backend/README.md` - Architecture documentation

#### Frontend
- `/app/frontend/src/pages/Dashboard.jsx` - Main dashboard with tab navigation
- `/app/frontend/src/components/RiverVisualization.jsx` - River map component
- `/app/frontend/src/components/LockDetailModal.jsx` - Lock details with wait predictions
- `/app/frontend/src/components/VesselList.jsx` - Vessel list with search
- `/app/frontend/src/components/VesselManagement.jsx` - Fleet management component (NEW)
- `/app/frontend/src/context/AuthContext.jsx` - Authentication context and hooks
- `/app/frontend/src/pages/LoginPage.jsx` - Login page
- `/app/frontend/src/pages/RegisterPage.jsx` - Registration page

### Key API Endpoints

#### Authentication
- `POST /api/auth/register` - Register new user with email/password
- `POST /api/auth/login` - Login with email/password
- `POST /api/auth/google/session` - Exchange Google OAuth session for user session
- `GET /api/auth/me` - Get current authenticated user
- `POST /api/auth/logout` - Logout and clear session

#### Vessel Data (with persistence)
- `GET /api/vessels` - Get active vessels (in-memory)
- `GET /api/vessels/sightings` - Get persisted vessel sightings from database
- `GET /api/vessels/history/{mmsi}` - Get historical sightings for a specific vessel
- `GET /api/vessels/stats` - Get vessel tracking statistics

#### User/Fleet Management
- `GET /api/user/vessels` - Get all vessels for current user
- `POST /api/user/vessels` - Add a vessel to user's fleet
- `DELETE /api/user/vessels/{mmsi}` - Remove a vessel from fleet
- `PUT /api/user/vessels/{mmsi}/primary` - Set vessel as primary
- `PUT /api/user/profile` - Update user profile
- `PUT /api/user/settings` - Update user settings

#### Session Data (legacy, still functional)
- `GET /api/session/{mmsi}/vessels` - Get vessels with correct is_user_vessel flag
- `POST /api/session/{mmsi}/position` - Update position for this session's vessel
- `GET /api/session/{mmsi}/race-analysis/{lock_id}` - Race analysis for this session

#### Other
- `POST /api/connection/start` - Start AIS connection
- `GET /api/vessels` - Get active vessels in river mile range
- `GET /api/usace/lock-queue` - Get USACE vessel cache
- `GET /api/locks/{lock_id}/details` - Get comprehensive lock details with wait prediction
- `GET /api/connection/status` - Get AIS connection status

## Database Schema

### users Collection
```javascript
{
  user_id: "user_xxx",
  email: "user@example.com",
  name: "User Name",
  password_hash: "salt$hash", // For email/password auth
  google_id: "google_id", // For Google OAuth
  picture: "url",
  fleet_name: "optional",
  vessels: [
    { mmsi: "123456789", boat_name: "My Boat", is_primary: true, added_at: "ISO" }
  ],
  settings: {},
  created_at: "ISO",
  auth_provider: "email" | "google"
}
```

### user_sessions Collection
```javascript
{
  user_id: "user_xxx",
  session_token: "session_xxx",
  expires_at: "ISO",
  created_at: "ISO"
}
```

## Recent Changes (Jan 2026)

### Backend Refactoring (Jan 26, 2026) ✅
- Created modular backend structure:
  - `/backend/config.py` - Configuration constants (LOCKS, CORS origins)
  - `/backend/database.py` - MongoDB connection
  - `/backend/models/` - Pydantic models (auth, vessel, lock)
  - `/backend/services/` - Business logic (auth_service, navigation_service)
  - `/backend/routes/` - API route templates for future migration
  - `/backend/README.md` - Architecture documentation
- Fixed CORS configuration for credentials mode (changed from wildcard to explicit origins)
- server.py now imports from modular config and services
- All routes remain functional with zero downtime

### User Authentication Implementation
- Added email/password registration and login
- Integrated Google OAuth via Emergent-managed auth
- Session-based authentication with secure cookies
- Protected routes that redirect to login
- Logout buttons on desktop and mobile

### Multi-Vessel Fleet Management
- Users can now have multiple vessels in their "fleet"
- One vessel designated as primary for lock timing
- VesselManagement component in Settings page
- MMSI uniqueness enforced across all users

## Known Issues
- WebSocket dev server errors in console (harmless - hot reload trying to connect)

## Recent Bug Fixes (Jan 27, 2026) ✅

### Session Isolation Fix - CRITICAL
**Issue:** When switching between user accounts (logout User A, login User B), the previous user's data persisted in the frontend. This caused session bleed between users.

**Root Cause:** 
1. localStorage was not being cleared on logout (stored `riverwatch_mmsi` and `riverwatch_connection`)
2. Frontend `App.js` was reading stale MMSI from localStorage before the user data from the account was loaded

**Fix Applied:**
1. `AuthContext.jsx` logout function now clears `localStorage.riverwatch_mmsi` and `localStorage.riverwatch_connection`
2. `App.js` useEffect for logout cleanup also clears localStorage
3. `App.js` settings load now depends on `userMmsi` state (set from user account) instead of localStorage
4. `SetupPage.jsx` now has a proper logout button in the top-right corner that calls the AuthContext logout

**Files Modified:**
- `/app/frontend/src/context/AuthContext.jsx` - Added localStorage cleanup to logout()
- `/app/frontend/src/App.js` - Fixed useEffect dependencies and localStorage handling
- `/app/frontend/src/pages/SetupPage.jsx` - Added logout button with proper auth context integration

**Verification:** 
- Backend correctly clears user vessels from active_vessels on logout ✅
- Frontend correctly clears localStorage on logout ✅
- Session switch from User1 to User2 shows correct MMSI data ✅

## Refactoring Status
### Completed ✅
- Configuration extraction to `/backend/config.py`
- Pydantic models extraction to `/backend/models/`
- Navigation service extraction to `/backend/services/navigation_service.py`
- Auth service extraction to `/backend/services/auth_service.py`

### In Progress 🔄
- Route migration (templates in `/backend/routes/`)

### Planned ⏳
- AIS service extraction
- USACE service extraction
- WebSocket handlers extraction
- Frontend hook extraction (useWebSocket, useApiData)

## Test Reports
- `/app/test_reports/iteration_5.json` - Demo vessel direction, ETA, toggle, session persistence (100% pass)
- `/app/test_reports/iteration_4.json` - Session isolation testing (90% pass - missing logout button was the only issue, now fixed)
- `/app/test_reports/iteration_3.json` - Previous test results (100% pass rate)
- `/app/backend/tests/test_auth.py` - Authentication test suite
- `/app/backend/tests/test_new_features.py` - New features test suite
