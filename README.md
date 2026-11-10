# River Watch

Live AIS vessel tracking and lock-arrival planning for the Upper Mississippi
River (Locks 1–27, RM 185–848), for commercial river operators and
recreational boaters.

> **Not for navigation.** Positions, ETAs and lock times are estimates. Always
> follow lockmaster instructions and the Inland Navigation Rules.

## Features

- **Live AIS picture.** Ingests NMEA/AIS from a Boat Beacon phone, a hardware
  receiver, or a push relay. Multi-sentence messages (type 5 names and
  dimensions) are reassembled.
- **Official river miles.** Every position is snapped to the USACE National
  Waterway Network sailing line (`backend/services/river_geometry.py`), which
  gives the river mile, the up/downbound direction from the river's local
  bearing, and which channel a vessel is on. Tributary traffic (St. Croix,
  Minnesota, Black, Illinois, Missouri, ...) is excluded automatically.
- **Lock arrival planner.** Shows commercial traffic heading to your target
  lock, its ETA, and the speed you would need (capped at your configured max)
  to arrive ahead of it with a buffer.
- **Trip planning.** Multi-lock trip plans, lock queues, meeting predictions
  and bottleneck forecasts.
- **Lock status and river conditions.** USACE lock status (UNKNOWN when it
  can't be read; never assumed open) and the official water-level station
  for each lock.
- **Lockage history.** Lock passages observed via AIS are recorded and replace
  the baseline estimates as data accumulates.

## Quick start (Docker)

```bash
docker compose up -d --build        # local dev stack (Linux host networking)
open http://localhost:3000
```

| File | Use |
|---|---|
| `docker-compose.yml` | Local / single host development |
| `docker-compose.prod.yml` | Production: nginx + TLS, same-origin API |
| `docker-compose.clean.yml` | Single VM with the AIS push relay (`PUBLIC_HOST=...`) |
| `docker-compose.pi.yml` | Raspberry Pi kiosk on the boat LAN |

See [DEPLOYMENT.md](DEPLOYMENT.md) for details.

## Configuration

Every backend setting is documented in
[`backend/.env.example`](backend/.env.example). For any internet-facing
deployment, set at least these:

- `AIS_INGEST_TOKEN`: a shared secret that relays send as `X-Ingest-Token`.
  Without it, anyone can post vessel positions.
- `AIS_ALLOW_PRIVATE_TARGETS=false` on a hosted server, so users can't make
  it connect to internal addresses.
- `GOOGLE_CLIENT_ID`: enables "Sign in with Google". Create a *Web
  application* OAuth client in Google Cloud Console and add the site's origin
  (e.g. `https://riverwatch.example.com`) under *Authorized JavaScript
  origins*. The backend verifies Google's signed ID token itself; no third-party
  auth broker is involved. Leave empty for email/password only.
- `SUPER_ADMIN_EMAIL`: the account that always gets super-admin rights.
- `CORS_ORIGINS`: explicit origins only. Leave it empty when nginx serves the
  app and the API on the same origin.

Sign-in is required for anything that changes shared state: feed
connection, settings, vessel naming, block list, debug and admin endpoints.

## Development

```bash
# Backend
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                               # adjust MONGO_URL etc.
uvicorn server:app --reload --port 8001
python -m pytest -q tests                          # offline unit tests

# Integration tests against a running backend
REACT_APP_BACKEND_URL=http://localhost:8001 python -m pytest -q tests

# Frontend
cd frontend
yarn install --frozen-lockfile
REACT_APP_BACKEND_URL=http://localhost:8001 yarn start
```

CI (`.github/workflows/ci.yml`) runs the backend tests and the frontend
build on every push.

### Rebuilding the river centerline

```bash
python scripts/build_river_centerline.py   # downloads from the USDOT/BTS NTAD service
```

The output is `backend/data/umr_centerline.json`. The source data is the
USACE National Waterway Network (public domain).

## Feeding AIS data

1. **Direct TCP.** In Boat Beacon, enable *Settings → AIS Output → TCP
   Server*, then enter the phone's IP in River Watch. This only works when the
   backend is on the same network.
2. **Push relay.** Run `scripts/ais_relay_http.py`, `scripts/ais_relay.ps1`
   or the Windows bridge on a machine on the boat network. It posts NMEA to
   `/api/ais/ingest` over HTTPS. Set `AIS_INGEST_TOKEN` on both ends.
3. **Relay service** (`ais_push_relay/`). Discovers Boat Beacon on the LAN and
   fans the feed out to the backend.

## License

MIT
