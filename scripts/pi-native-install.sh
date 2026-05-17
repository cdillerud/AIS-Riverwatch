#!/usr/bin/env bash
# ============================================================================
# River Watch - Pi native install (Phase 1)
# ============================================================================
# Runs the backend as a regular Python service (systemd), nginx natively serves
# the frontend, and Mongo stays in a single lightweight Docker container
# (mongo:4.4.18 - ARMv8.0 compatible). No frontend container, no relay container,
# no docker-compose. River Watch shows up in the start menu as one click-to-open
# icon - feels like a normal local app.
#
# After install:
#   sudo systemctl status riverwatch.service       # backend
#   sudo systemctl status riverwatch-mongo.service # mongo
#   journalctl -u riverwatch -f                    # logs
#
# Run on the Pi:
#   ./scripts/pi-native-install.sh
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="${SUDO_USER:-${USER:-$(whoami)}}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"

BLUE="\033[1;34m"; GREEN="\033[1;32m"; YELLOW="\033[1;33m"; NC="\033[0m"
log()  { echo -e "${BLUE}==>${NC} $*"; }
ok()   { echo -e "${GREEN}OK ${NC} $*"; }
warn() { echo -e "${YELLOW}!!${NC} $*"; }

log "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    nginx \
    chromium-browser \
    git curl jq

# ---------------------------------------------------------------------------
# Mongo as a single tiny systemd-managed container (mongo:4.4.18 for ARMv8.0)
# ---------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    warn "Docker not found - installing for mongo container only..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER_NAME"
fi

log "Pulling mongo:4.4.18..."
sudo docker pull mongo:4.4.18 >/dev/null

sudo tee /etc/systemd/system/riverwatch-mongo.service >/dev/null <<EOF
[Unit]
Description=River Watch - MongoDB (single-container)
Requires=docker.service
After=docker.service network-online.target

[Service]
Restart=always
RestartSec=5
ExecStartPre=-/usr/bin/docker rm -f riverwatch-mongo
ExecStart=/usr/bin/docker run --rm --name riverwatch-mongo \\
    -p 127.0.0.1:27017:27017 \\
    -v riverwatch-mongo-data:/data/db \\
    mongo:4.4.18 --bind_ip_all --quiet
ExecStop=/usr/bin/docker stop -t 10 riverwatch-mongo

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now riverwatch-mongo.service
ok "Mongo running on 127.0.0.1:27017"

# ---------------------------------------------------------------------------
# Backend: native Python venv + systemd
# ---------------------------------------------------------------------------
log "Creating Python venv for backend..."
cd "$REPO_DIR/backend"
python3 -m venv .venv
. .venv/bin/activate
pip install --quiet --upgrade pip wheel
pip install --quiet -r requirements.txt
deactivate

# Backend env file (re-uses .env.pi from compose install if present, else fresh)
if [[ ! -f "$REPO_DIR/backend/.env.pi" ]]; then
    SECRET="$(openssl rand -hex 32)"
    cat > "$REPO_DIR/backend/.env.pi" <<EOF
SECRET_KEY=${SECRET}
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
AIS_INGEST_TOKEN=
EOF
fi

# Inject the local Mongo URL + DB name into env (idempotent)
grep -q '^MONGO_URL=' "$REPO_DIR/backend/.env.pi" || \
    echo "MONGO_URL=mongodb://127.0.0.1:27017" >> "$REPO_DIR/backend/.env.pi"
grep -q '^DB_NAME=' "$REPO_DIR/backend/.env.pi" || \
    echo "DB_NAME=riverwatch" >> "$REPO_DIR/backend/.env.pi"
grep -q '^CORS_ALLOWED_ORIGINS=' "$REPO_DIR/backend/.env.pi" || \
    echo 'CORS_ALLOWED_ORIGINS=*' >> "$REPO_DIR/backend/.env.pi"

sudo tee /etc/systemd/system/riverwatch.service >/dev/null <<EOF
[Unit]
Description=River Watch - FastAPI backend
After=network-online.target riverwatch-mongo.service
Requires=riverwatch-mongo.service

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$REPO_DIR/backend
EnvironmentFile=$REPO_DIR/backend/.env.pi
ExecStart=$REPO_DIR/backend/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now riverwatch.service
ok "Backend running on 127.0.0.1:8001"

# ---------------------------------------------------------------------------
# Frontend: yarn build + nginx serve static
# ---------------------------------------------------------------------------
if ! command -v yarn >/dev/null 2>&1; then
    log "Installing yarn..."
    sudo npm install -g yarn@1.22.22 || (curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash - && sudo apt-get install -y nodejs && sudo npm install -g yarn@1.22.22)
fi

log "Building frontend..."
cd "$REPO_DIR/frontend"
REACT_APP_BACKEND_URL="" DISABLE_ESLINT_PLUGIN=true yarn install --production=false
REACT_APP_BACKEND_URL="" DISABLE_ESLINT_PLUGIN=true yarn build
ok "Frontend built at $REPO_DIR/frontend/build"

log "Installing static build to nginx webroot..."
sudo rm -rf /var/www/riverwatch
sudo mkdir -p /var/www/riverwatch
sudo cp -r "$REPO_DIR/frontend/build/"* /var/www/riverwatch/

sudo tee /etc/nginx/sites-available/riverwatch >/dev/null <<'NGINX'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    root /var/www/riverwatch;
    index index.html;
    client_max_body_size 25m;

    # WebSocket upgrade for raw NMEA (must come before /api/)
    location /api/ws/ {
        proxy_pass http://127.0.0.1:8001/api/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_buffering off;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Origin $http_origin;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /docs        { proxy_pass http://127.0.0.1:8001/docs; }
    location /openapi.json { proxy_pass http://127.0.0.1:8001/openapi.json; }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX

# Remove default site, enable ours
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/riverwatch /etc/nginx/sites-enabled/riverwatch

sudo nginx -t && sudo systemctl reload nginx
ok "nginx serving http://localhost"

# ---------------------------------------------------------------------------
# Application menu entry (single-click launcher)
# ---------------------------------------------------------------------------
log "Adding 'River Watch' to applications menu..."
sudo -u "$USER_NAME" mkdir -p "$USER_HOME/.local/share/applications"
sudo -u "$USER_NAME" tee "$USER_HOME/.local/share/applications/riverwatch.desktop" >/dev/null <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=River Watch
GenericName=River Watch
Comment=Mississippi River Lock Timing & Vessel Tracking
Exec=chromium-browser --app=http://localhost --start-maximized --touch-events=enabled --force-renderer-accessibility
Icon=network-workgroup
Terminal=false
Categories=Network;Navigation;Utility;
Keywords=ais;marine;river;locks;mississippi;
EOF

sudo -u "$USER_NAME" update-desktop-database "$USER_HOME/.local/share/applications" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
LAN_IP="$(hostname -I | awk '{print $1}')"
cat <<EOF

==============================================
  River Watch - native install complete
==============================================
  Local URL:        http://localhost
  LAN URL:          http://${LAN_IP}
  Boat Beacon ->    http://${LAN_IP}:8001/api/ais/ingest  (if endpoint is on this branch)

  Backend:          sudo systemctl status riverwatch
  Mongo:            sudo systemctl status riverwatch-mongo
  Logs:             journalctl -u riverwatch -f

  Launch from start menu -> 'River Watch'
  Or run: chromium-browser --app=http://localhost
==============================================
EOF
