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
13. **User Authentication (NEW - Jan 2026)** ✅
    - Email/password registration and login
    - Google OAuth via Emergent-managed auth
    - Session-based authentication with httpOnly cookies
    - Protected routes (redirect to login if not authenticated)
    - Logout functionality (desktop and mobile)
14. **Multi-Vessel Fleet Management (NEW - Jan 2026)** ✅
    - Associate multiple MMSIs with a single user account
    - Set primary vessel for lock timing calculations
    - Add/remove vessels from fleet in Settings page
    - MMSI uniqueness enforced (one user per MMSI)

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
- `/app/backend/server.py` - Monolithic FastAPI server (3000+ lines, needs refactoring)
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
- Backend server.py is monolithic (3000+ lines) - needs refactoring

## Refactoring Needed
- Break down `backend/server.py` into smaller modules (routes, services, models)
- Extract frontend logic into custom hooks (useWebSocket, useAuth, useApiData)

## Test Reports
- `/app/test_reports/iteration_3.json` - Latest test results (100% pass rate)
- `/app/backend/tests/test_auth.py` - Authentication test suite
