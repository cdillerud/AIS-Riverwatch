# River Watch - AIS Vessel Tracker & Lock Timer

Track vessels on the Upper Mississippi River (Pools 2 & 3) and calculate if you can beat commercial traffic to the locks.

## Features

- **AIS Connection**: Connect to Boat Beacon via TCP (port 5353)
- **Vessel Tracking**: Real-time position, speed, and heading
- **Race to Lock**: Calculate required speed to beat commercial vessels
- **Alerts**: Warning when required speed exceeds your max (25 MPH)
- **Lock Coverage**: Lock 2 (Hastings, RM 815.2) & Lock 3 (Red Wing, RM 796.9)

## Quick Start (Docker)

```bash
# Clone the repo
git clone <your-repo-url>
cd riverwatch

# Start all services
docker-compose up -d

# Open in browser
open http://localhost:3000
```

## Manual Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
MONGO_URL=mongodb://localhost:27017
DB_NAME=riverwatch
CORS_ORIGINS=*
EOF

# Run server
uvicorn server:app --reload --host 0.0.0.0 --port 8001
```

### Frontend

```bash
cd frontend

# Install dependencies
yarn install

# Create .env file
cat > .env << EOF
REACT_APP_BACKEND_URL=http://localhost:8001
EOF

# Run development server
yarn start
```

### MongoDB

Install MongoDB Community Edition:
- **Mac**: `brew install mongodb-community`
- **Ubuntu**: Follow [MongoDB docs](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-ubuntu/)
- **Windows**: Download from [MongoDB](https://www.mongodb.com/try/download/community)

Start MongoDB:
```bash
# Mac/Linux
mongod --dbpath /data/db

# Or use brew services (Mac)
brew services start mongodb-community
```

## Connecting to Boat Beacon

1. Open Boat Beacon on your mobile device
2. Go to **Settings → AIS Output → Enable TCP Server**
3. Note the IP address (e.g., `192.168.1.100`)
4. Enter the IP and your vessel's MMSI in River Watch
5. Click **Connect**

## Configuration

Your MMSI and connection settings are saved automatically and will persist across sessions.

## Demo Mode

If you don't have a live AIS feed, click **Demo Mode** on the dashboard to add simulated vessels for testing.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/` | GET | Health check |
| `/api/locks` | GET | Get lock positions |
| `/api/vessels` | GET | Get tracked vessels |
| `/api/race-analysis/{lock_id}` | GET | Race analysis for a lock |
| `/api/settings` | GET/POST | User settings |
| `/api/demo/add-vessel` | POST | Add demo vessel |
| `/ws/ais` | WebSocket | Real-time AIS data |

## License

MIT
