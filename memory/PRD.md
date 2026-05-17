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

- **2026-02-18** — Editable AIS Connection from the app + reboot persistence.
  - Backend: `POST /api/connection/start` now persists `{ip, port, mmsi, boat_name}` to `settings.last_connection_config`; added `POST /api/connection/stop`; `ConnectionConfig` Pydantic model now accepts `boat_name`; startup event auto-restores last known good config (skips stale `ais-relay` / `push://relay`).
  - Frontend (`SettingsPage.jsx`): replaced cosmetic IP/port fields with a live, touch-friendly AIS Connection card. Polls `/api/connection/status` every 3s, shows LIVE/OFFLINE pill + In Use / MMSI / Subscribers / Last NMEA strip. Four editable fields (Phone IP, Port, Your MMSI, Boat name) with 12 px-tall inputs for the Pi touchscreen. Three buttons: Apply & Reconnect (POST `/api/connection/start`), Reconnect (POST `/api/connection/reconnect`), Disconnect (POST `/api/connection/stop`). Toasts on every action.
  - Verified backend e2e: POST /start → status reflects new config → MongoDB `settings` collection persists → backend restart → auto-restore log entry → status still correct.
  - Test IDs added: `ais-connection-card`, `ais-conn-pill-live`, `ais-conn-pill-offline`, `ais-conn-status-strip`, `ais-conn-current-target`, `ais-conn-last-data`, `conn-ip-input`, `conn-port-input`, `conn-mmsi-input`, `conn-boat-input`, `conn-apply-btn`, `conn-reconnect-btn`, `conn-stop-btn`, `conn-dirty-hint`.
