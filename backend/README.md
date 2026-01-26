# River Watch Backend Architecture

## Overview

The River Watch backend is a FastAPI application that provides real-time vessel tracking, lock timing calculations, and USACE data integration for the Upper Mississippi River.

## Directory Structure

```
/app/backend/
├── server.py           # Main FastAPI app (monolithic, being refactored)
├── config.py           # Configuration constants (LOCKS, CORS, etc.)
├── database.py         # MongoDB connection
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container configuration
│
├── models/             # Pydantic data models
│   ├── __init__.py
│   ├── auth.py         # UserRegistration, UserLogin, User, VesselAdd
│   ├── vessel.py       # VesselPosition, ConnectionConfig
│   └── lock.py         # LockInfo, LockStatus, LockageRecord, RaceAnalysis
│
├── services/           # Business logic (reusable functions)
│   ├── __init__.py
│   ├── auth_service.py       # Password hashing, session management
│   └── navigation_service.py # River mile calculations, ETA, heading
│
├── routes/             # API route handlers (for new features)
│   ├── __init__.py
│   ├── auth.py         # /api/auth/* routes (template for future migration)
│   └── user.py         # /api/user/* routes (template for future migration)
│
├── websocket/          # WebSocket handlers (for new features)
│   └── __init__.py
│
└── tests/              # Test files
    └── test_auth.py
```

## Current State

The application is currently in a **hybrid state**:

1. **`server.py`** contains the main application with all routes and business logic (~3,800 lines)
2. **New modules** (`config.py`, `models/`, `services/`) contain extracted, reusable code
3. Routes in `routes/` are templates for future migration

## Adding New Features

For new features, follow this pattern:

1. **Models**: Add Pydantic models to `models/` directory
2. **Services**: Add business logic to `services/` directory
3. **Routes**: Create a new router in `routes/` and include it in `server.py`

Example:
```python
# In server.py, add:
from routes.my_feature import router as my_feature_router
app.include_router(my_feature_router, prefix="/api")
```

## Key Services

### Navigation Service (`services/navigation_service.py`)
- `estimate_river_mile(lat, lon)` - Convert GPS to river mile
- `river_mile_to_coords(rm)` - Convert river mile to GPS
- `determine_heading(speed, course)` - Determine upstream/downstream
- `calculate_eta_to_lock(vessel_rm, speed, heading, lock_rm)` - Calculate ETA in minutes
- `calculate_required_speed(...)` - Calculate speed needed to beat traffic

### Auth Service (`services/auth_service.py`)
- `hash_password(password)` - Create salted hash
- `verify_password(password, hashed)` - Verify password
- `generate_session_token()` - Create secure session token
- `get_current_user(request, db)` - Get authenticated user from session

## Configuration (`config.py`)

- `LOCKS` - Dictionary of all Upper Mississippi locks with coordinates
- `UPPER_MISS_LOCKS` - List of lock numbers for USACE API
- `RIVER_MILE_POINTS` - Reference points for river mile interpolation
- `get_cors_origins()` - Returns allowed CORS origins

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login with email/password
- `POST /api/auth/google/session` - Google OAuth login
- `GET /api/auth/me` - Get current user
- `POST /api/auth/logout` - Logout

### User/Fleet Management
- `GET /api/user/vessels` - Get user's vessels
- `POST /api/user/vessels` - Add vessel to fleet
- `DELETE /api/user/vessels/{mmsi}` - Remove vessel
- `PUT /api/user/vessels/{mmsi}/primary` - Set primary vessel

### Locks
- `GET /api/locks` - Get all lock info
- `GET /api/locks/status` - Get all lock statuses
- `GET /api/locks/{lock_id}/status` - Get specific lock status
- `GET /api/locks/{lock_id}/details` - Get comprehensive lock details

### Vessels
- `GET /api/vessels` - Get all tracked vessels
- `GET /api/session/{mmsi}/race/{lock_id}` - Get race analysis

### WebSocket
- `WS /ws/ais` - Real-time AIS vessel updates
- `WS /ws/raw` - Raw NMEA data stream

## Refactoring Roadmap

1. ✅ Extract config constants to `config.py`
2. ✅ Extract Pydantic models to `models/`
3. ✅ Extract navigation calculations to `services/`
4. 🔄 Migrate auth routes to `routes/auth.py`
5. 🔄 Migrate user routes to `routes/user.py`
6. ⏳ Extract AIS connection manager to `services/ais_service.py`
7. ⏳ Extract USACE data fetching to `services/usace_service.py`
8. ⏳ Extract WebSocket handlers to `websocket/handlers.py`

## Environment Variables

- `MONGO_URL` - MongoDB connection string
- `DB_NAME` - Database name
- `CORS_ORIGINS` - Comma-separated allowed origins (optional)

## Running Locally

```bash
cd /app/backend
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

## Testing

```bash
cd /app/backend
pytest tests/
```
