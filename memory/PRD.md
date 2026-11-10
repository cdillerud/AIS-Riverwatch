# River Watch - Product Requirements Document

## Original Problem Statement
Build a local application named "River Watch" to track vessels on the upper Mississippi River. The application should connect to an AIS (Automatic Identification System) TCP feed, calculate "Lock Timing" to help the user's vessel beat commercial traffic to locks, and display this information on a simplified river map.

## Core Requirements
1. AIS/GPS Data Integration via TCP from Boat Beacon
2. Vessel tracking and lock-timing race analysis
3. Visual alert if required speed exceeds boat max speed
4. Persistent settings (MMSI, boat name, max speed, IP, port, lock filters)
5. USACE lock data + USGS/NWPS water conditions
6. User accounts: Vessel Owner / Traffic Watch + Google social login
7. Demo vessels + user-vessel simulation + Quick Test preset
8. Dual deployment: Cloud VM (Docker + Nginx + Let's Encrypt) and Raspberry Pi 4 native install
9. Touchscreen-friendly kiosk mode on LysMarine OS

See CHANGELOG below for implementation history.

## Architecture
- Frontend: React (CRA), Tailwind, shadcn/ui, Sonner for toasts
- Backend: FastAPI + AsyncIOMotorClient, all routes under `/api`
- Database: MongoDB (cloud: latest; Pi: 4.4.18 for ARMv8.0 compat)
- Realtime: WebSockets (`/ws/ais`, `/api/ws/ais`, `/api/ws/raw`)
- Pi: native Python venv + systemd, native Nginx, MongoDB in single Docker container
- Cloud VM: full docker-compose + Nginx + Let's Encrypt

## Key DB Schema
- `users`, `user_accounts`, `user_sessions`
- `settings` — `{key, value, updated_at}` (now incl. `last_connection_config`)
- `user_settings` — `{mmsi, settings, updated_at}`
- `vessel_names` (cached names) / `vessel_sightings` (history)
- `trips` — `{user_id, name, start_rm, end_rm, heading, departure_time, notes, locks, created_at, updated_at}`

## Key Endpoints
- `GET  /api/connection/status` — live AIS state (polled by Settings UI every 3s)
- `POST /api/connection/start` — set IP/port/MMSI/boat_name + persist to Mongo
- `POST /api/connection/reconnect` — re-dial current config
- `POST /api/connection/stop` — disconnect manually (Settings → Disconnect)
- `POST /api/ais/ingest` — push-based NMEA relay
- `GET  /api/water-conditions/{lock_id}` — NWS NWPS per-lock gauge
- `WS   /ws/ais`, `WS /api/ws/ais` — vessel stream
- `WS   /ws/raw`, `WS /api/ws/raw` — raw NMEA debug stream

## Active P0 (Pi)
- ✅ Pi nginx WebSocket upgrade (now proxies `/ws/` and `/api/ws/`)
- ✅ AIS connection IP/port editable from the app + persisted across reboots
- ✅ NMEA drift warning (Sonner toast if feed stalls > 30 s, recovery toast on restore)

## Cross-deployment rule (locked in 2026-02-18)
ALL feature changes must apply to BOTH the Raspberry Pi native install and
the Cloud VM Docker deployment from the same `/app` codebase. No Pi-only or
VM-only code paths. New features live in `/app/frontend` + `/app/backend`
and use endpoints that exist on both deployments.

## Roadmap
- **P1** — On-screen keyboard (`onboard`) reliable trigger in Chromium kiosk on Pi
- **P1** — Phase 4 Traffic Watch vessel alerts
- **P1** — Audio/haptic "Can't Beat" feedback
- **P1** — Finish `server.py` repository-pattern migration
- **P2** — Phase 2 Pi: SQLite migration (drop final Docker dependency)
- **P2** — 48-hr stage forecast sparkline per Lock card
- **P2** — Split `Dashboard.jsx` / `SettingsPage.jsx` into hooks/components
- **Future** — External AIS API enrichment, ML wait-time predictions, offline mode

## Changelog (recent)

- **2026-02-17** — Lock Detail Modal "River Conditions" no longer disappears on slow USGS feed; defensive rendering with LOADING / NO GAUGE badges.

- **2026-02-17** — Per-lock NWS hydrograph gauges via `config.LOCK_GAUGES` + `fetch_nws_gauge_data()`. Supports mixed datums (stage vs elev. MSL).

- **2026-02-18** — Pi WebSocket "OFFLINE" fix. Two root causes: App.js used `/ws/ais` on non-Emergent hosts but Pi nginx only proxied `/api/ws/`; and bare `/api/ws` triggered nginx auto-301 stripping WS upgrade headers. Fix: added `location /ws/` proxy block + `308` redirects for bare paths. Files: `scripts/pi-native-install.sh`, NEW `scripts/pi-fix-nginx-ws.sh` (idempotent patch for existing Pi installs).

### Bug Fix: Mode Toggle Not Switching Views ✅ (January 27, 2026)
- [x] Fixed: Dashboard was reading `accountType` from stale `connectionConfig` instead of `user.account_type`
- [x] Fixed: App.js now properly handles localStorage config restoration for both modes
- [x] Fixed: Traffic Watch config is now stored to localStorage for session persistence
- [x] Fixed: Mode toggle correctly routes to SetupPage for watch point configuration when needed
- [x] Fixed: AIS WebSocket connection maintained across mode switches

### User Vessel Simulation Feature ✅ (February 12, 2026)
- [x] Implemented vessel simulation for testing when no live AIS feed is available
- [x] Settings page UI controls: toggle switch, river mile, speed (knots), heading (northbound/southbound)
- [x] Backend API: GET/POST /api/user-vessel/simulation/{mmsi}
- [x] Simulated vessel appears on Dashboard map at correct position
- [x] Bug Fixed: Frontend `userMmsi` undefined variable changed to `settings.user_mmsi`
- [x] Feature isolated to vessel_owner account type (hidden in traffic_watch mode)
- [x] Test file created: `/app/backend/tests/test_user_vessel_simulation.py`
- [x] **Quick Test button** added - one-click preset (RM 820, 8 kts, southbound) for instant testing

### UI/UX Improvements ✅
- [x] Nearby Vessels sorted by River Mile (descending)
- [x] Removed Locks/Raw tabs, moved Raw Data to Settings
- [x] Extended Nearby Vessels card to fill sidebar height
- [x] Swapped Traffic Ahead and Queue positions
- [x] Filter vessels within 100 miles of user

### Race Logic Fix ✅ (February 4, 2026)
- [x] **Bi-directional competitor detection**: Fixed race analysis to consider vessels heading toward the lock from EITHER side (not just vessels between user and lock)
- [x] Before: Only detected vessels that were physically between user position and lock
- [x] After: Detects ANY vessel heading toward the target lock, regardless of which side they're on
- [x] Example: User at RM 850, Lock at RM 815 - now correctly detects both:
  - Vessel at RM 830 heading southbound (between user and lock)
  - Vessel at RM 800 heading northbound (opposite side of lock, but heading toward it)
- [x] UI updated to show vessel heading direction (↑N/↓S) and distance to lock

### Phase 6: River Traffic Planning ✅ (February 12, 2026)
Synced workspace to baseline commit `e3ff8e0` on branch `riverwatch-runtime-stable` and developed on `feature/river-traffic-planning`.

- [x] **Trip Planner**: `POST /api/planning/trip` — origin/destination RM + ETD → multi-leg plan with per-lock wait + lockage minutes and full ETA. Auto-prefills speed from AIS (when `mmsi` provided), else user override, else 8 kn default
- [x] **Lock Queue View**: `GET /api/planning/lock-queue/{lock_id}?lookahead_hours=N` — ordered approaching vessels with slot numbers, ETA, direction, distance, barge counts
- [x] **Meeting Predictor**: `GET /api/planning/meetings?lookahead_hours=N` — head-on and overtake encounters between AIS vessels with meeting RM and passing advice
- [x] **Bottleneck Forecast**: `GET /api/planning/bottlenecks?hours=N` — utilization heatmap for all 27 Upper Mississippi locks (low/moderate/high severity) using USACE queue + lockage history
- [x] Helper endpoint `GET /api/planning/locks` for the UI
- [x] Frontend `pages/TrafficPlanner.jsx` at `/planning` with 4 tabs, quick-pick presets, severity badges, per-leg table
- [x] Dashboard header `Compass` button (`data-testid=planning-nav-btn`) routes to `/planning`
- [x] Available to all account types (Vessel Owner, Traffic Watch, Super Admin)
- [x] 10/10 pytest cases pass at `/app/backend/tests/test_planning.py`
- [x] testing_agent_v3_fork iteration_7 — 100% backend + frontend pass

### Phase 7: Lock Detail Data Accuracy Audit ✅ (February 12, 2026)
Audit + corrections requested in user prompt of 2026-02-12 ("audit and correct Lock Detail modal data accuracy").

- [x] **Per-lock water-station catalog** (`backend/lock_stations.py`) with `official_station` + `reference_stations`, each carrying `station_id`, `source`, `river_mile`, `datum`, `thresholds`, `threshold_source`.
- [x] **Lock 2 mapped to HSTM5** (NWS/USACE Hastings L&D 2) with thresholds `{action:13, flood:15, moderate:17, major:18}` and datum `"USACE Gage Zero 600.00 ft 1912 MSL (NGVD29)"`. Prescott (USGS 05344500) demoted to a labelled **reference station** with `thresholds=null` — never cross-applied.
- [x] **No cross-station threshold application**: locks without a verified station/threshold pairing (L&D 5/5A/6/7/9/10/12-18/20-25) return `thresholds=null` and the UI displays *"Flood category not defined for this gauge."*
- [x] New service `services/water_station_service.py` fetches USGS JSON or NWS AHPS XML, builds the structured record with `value`, `units`, `observed_at`, `status`, `status_explanation`, `data_url`, `source_url`, etc.
- [x] `GET /api/water-conditions/{lock_id}` returns the new `{official, references, selection_reason, fetched_at}` shape (legacy fields preserved).
- [x] New `GET /api/locks/{lock_id}/water-condition-debug` returns selection reasoning + alternates + raw values + source URLs.
- [x] `LockDetailModal.jsx` renders station_id/source/datum/threshold_source, supports `not_defined` and `unknown` status states, and exposes a **"Station details / debug"** expandable section showing reference stations and source URLs.
- [x] **AIS-inferred lockage tracker**: dwell session opens when a vessel is within ±0.2 RM at ≤0.3 kt; closes on exit or speed-up; persists `lockage_history` record with `source="ais_inferred"`, `confidence="medium"`, `mmsi`, `direction`, `start/end_time`, `duration_minutes`. State-machine recordings now tagged `source="ais_state_machine"`.
- [x] UI: "No lockage history recorded" → **"No recorded lockages yet."**; baseline lockage averages now show a clear *"Baseline estimates — used until real lockages are observed"* explanation block.
- [x] Tests: 14 new pytest cases (10 water-stations + 4 lockage-events) — all green.

## Pending Features

### P0 - High Priority
- [ ] Expand NOAA/USGS integration with forecast data
- [ ] Vessel Alert notifications (when watched vessels pass a point)
- [ ] Password reset email flow
- [ ] Improve Trip Planner lock-wait estimates: feed direction-aware USACE queue count and average lockage time per lock direction

### P1 - Medium Priority
- [ ] Sound/Vibration alerts for "Can't Beat" warnings
- [ ] MarineTraffic API integration for vessel name lookups
- [ ] Favorite Locks quick-switch UI
- [ ] Exit Impersonation banner/button

### P2 - Lower Priority
- [ ] Quick Position Presets
- [ ] System announcements/banner messages

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

### Backend Refactoring (PHASE 2 IN PROGRESS)
**Status**: Services extracted, route modules created, performance improvements added

Completed (Phase 1):
- [x] `services/usace_service.py` - USACE lock queue/status data (~230 lines)
- [x] `services/usgs_service.py` - USGS water conditions (~180 lines)
- [x] `services/ais_parser.py` - NMEA/AIS parsing (~350 lines)
- [x] `routes/admin.py` - Admin endpoints module (~280 lines)
- [x] `routes/locks.py` - Lock info endpoints module
- [x] `routes/traffic.py` - Traffic watch endpoints module  
- [x] `routes/water.py` - Water conditions endpoints module
- [x] Updated server.py imports to use new services
- [x] Updated README.md with new architecture

Completed (Phase 2 - Performance):
- [x] `services/vessel_service.py` - Centralized vessel data management with TTL cache (~200 lines)
- [x] `services/cache_service.py` - TTL-based caching for expensive API calls (~150 lines)
- [x] `services/http_client.py` - Shared HTTP client pool for connection reuse (~80 lines)
- [x] `services/websocket_manager.py` - WebSocket connection manager (~200 lines)
- [x] `routes/vessels.py` - Vessel and session endpoints module (~250 lines)
- [x] `/api/debug/performance` endpoint for monitoring cache stats and connections

Remaining (Phase 3 - Code Consolidation):
- [x] Extract AISConnectionManager class to `services/ais_connection.py` (~380 lines) - CREATED
- [x] Create WebSocket handlers module `services/websocket_handlers.py` (~170 lines) - CREATED  
- [x] Create Repository layer `repositories/__init__.py` (~540 lines) - CREATED & EXPANDED
- [x] Replace vessel_names db calls with repos.vessels (3 calls)
- [x] Replace blocked_mmsi db calls with repos.blocked_mmsi (4 calls)
- [x] Replace majority of db.users calls (31 of 48 replaced)
- [x] Replace majority of db.user_sessions calls (8 of 9 replaced)
- [ ] Replace remaining db.users calls (17 remaining)
- [ ] Replace db.lockage_history calls (12 remaining)
- [ ] Replace db.vessel_sightings calls (6 remaining)
- [ ] Replace db.vessel_history calls (4 remaining)
- [ ] Replace db.user_settings calls (6 remaining)
- [ ] Migrate inline routes to use route modules
- [ ] Wire up new AIS connection manager to replace inline class
- [ ] Target: Reduce server.py from ~5,850 lines to <2,000 lines (currently 50 db calls remain, down from 96)

**Progress Summary (March 23, 2026):**
- Started with 96 direct db.* calls in server.py
- Replaced 46 calls with repository pattern
- 50 db calls remaining
- repos.* calls: 46

**Repository Classes Created:**
- VesselRepository - vessel names cache
- UserRepository - user accounts (expanded with get_user_by_email, update_by_email, find_by_vessel_mmsi)
- SessionRepository - user sessions (expanded with get_by_token, delete_by_token, count_active)
- TrafficWatchRepository - watch points
- LockPassageRepository - lock passage history
- SettingsRepository - global app settings
- UserSettingsRepository - per-user settings
- BlockedMMSIRepository - blocked vessel list

**New Modules Created (March 23, 2026):**
- `services/ais_connection.py` - AIS TCP connection manager with watchdog
- `services/websocket_handlers.py` - WebSocket endpoint handlers for /ws/ais and /ws/raw
- `repositories/__init__.py` - Database repository layer with 8 repositories

**Note**: Phase 3 requires careful testing as it removes code rather than adding modules.

### Frontend Refactoring (NOT STARTED)
- [ ] Extract state management from Dashboard.jsx into custom hooks
- [ ] Extract mode-specific UI into separate components
- [ ] Break down SettingsPage.jsx into smaller components

## Admin Accounts
- **Super Admin**: `cdillerud@gmail.com` (Google OAuth) - Full access
- **Admin**: `chaddillerud@gmail.com` / `test123` - Standard admin

## Test Accounts
- **Vessel Owner**: `chaddillerud@gmail.com` / `test123`
- **Vessel Owner 2**: `test@example.com` / `password123`
- **Traffic Watch**: `trafficwatch@test.com` / `test123`
- **Google Auth**: `cdillerud@gmail.com` (OAuth flow)

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user (handles existing users gracefully)
- `POST /api/auth/login` - Login with email/password
- `POST /api/auth/logout` - Logout and clear session
- `GET /api/auth/me` - Get current user info

### User Settings
- `GET/PUT /api/user/settings` - User settings
- `POST/GET /api/user/account-type` - Account type (mode toggle)
- `POST/GET /api/user/watch-point` - Watch point
- `POST/GET /api/user/favorite-locks` - Favorite locks
- `POST/GET/DELETE /api/user/vessel-watch` - Vessel watch list

### Admin (requires admin role)
- `GET /api/admin/stats` - System statistics
- `GET /api/admin/users` - List users (with search)
- `POST /api/admin/users` - Create user
- `PUT /api/admin/users/{id}` - Update user
- `DELETE /api/admin/users/{id}` - Delete user
- `POST /api/admin/users/{id}/promote` - Promote to admin
- `POST /api/admin/users/{id}/demote` - Demote from admin
- `POST /api/admin/users/{id}/reset-password` - Reset password
- `POST /api/admin/impersonate/{id}` - Impersonate user
- `GET /api/admin/vessels` - List all tracked vessels

### Data
- `GET /api/vessels` - Get all vessels
- `GET /api/locks` - Get all locks with status
- `GET /api/traffic-summary/{lock_id}` - Traffic summary
- `GET /api/locks/{lock_id}/water-conditions` - USGS water data
- `GET /api/session/{mmsi}/race-analysis/{lock_id}` - Race analysis

### User Vessel Simulation
- `GET /api/user-vessel/simulation/{mmsi}` - Get simulation status and parameters
- `POST /api/user-vessel/simulation/{mmsi}` - Enable/configure simulation
- `POST /api/user-vessel/simulation/{mmsi}/stop` - Stop simulation

## Refresh Intervals
- Vessels: 30 seconds (WebSocket provides real-time updates)
- Race Analysis: 20 seconds
- Lock Status: 5 minutes
- Lockage Times: 10 minutes
- Traffic Summary: 30 seconds
- Auto Soft-Refresh: 15 minutes
- **2026-02-18** — Editable AIS Connection from the app + reboot persistence.
  - Backend: `POST /api/connection/start` now persists `{ip, port, mmsi, boat_name}` to `settings.last_connection_config`; added `POST /api/connection/stop`; `ConnectionConfig` Pydantic model now accepts `boat_name`; startup event auto-restores last known good config (skips stale `ais-relay` / `push://relay`).
  - Frontend (`SettingsPage.jsx`): replaced cosmetic IP/port fields with a live, touch-friendly AIS Connection card. Polls `/api/connection/status` every 3s, shows LIVE/OFFLINE pill + In Use / MMSI / Subscribers / Last NMEA strip. Four editable fields (Phone IP, Port, Your MMSI, Boat name) with 12 px-tall inputs for the Pi touchscreen. Three buttons: Apply & Reconnect (POST `/api/connection/start`), Reconnect (POST `/api/connection/reconnect`), Disconnect (POST `/api/connection/stop`). Toasts on every action.
  - Verified backend e2e: POST /start → status reflects new config → MongoDB `settings` collection persists → backend restart → auto-restore log entry → status still correct.
  - Test IDs added: `ais-connection-card`, `ais-conn-pill-live`, `ais-conn-pill-offline`, `ais-conn-status-strip`, `ais-conn-current-target`, `ais-conn-last-data`, `conn-ip-input`, `conn-port-input`, `conn-mmsi-input`, `conn-boat-input`, `conn-apply-btn`, `conn-reconnect-btn`, `conn-stop-btn`, `conn-dirty-hint`.
