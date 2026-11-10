#!/usr/bin/env bash
# ============================================================================
# River Watch - Pi WebSocket nginx patch (idempotent)
# ============================================================================
# Symptom this fixes:
#   - App reads "OFFLINE" on the Pi
#   - curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
#       http://localhost/api/ws    returns "HTTP/1.1 301 Moved Permanently"
#   - Browser DevTools shows ws://<host>/ws/ais closing as 404 / served index.html
#
# Root cause:
#   The production frontend build (App.js) connects to ws://<host>/ws/ais
#   on non-Emergent hosts, but the Pi nginx config only proxied /api/ws/.
#   Plus bare /api/ws (no trailing slash) caused nginx to issue a 301 that
#   strips the WebSocket Upgrade headers.
#
# What this script does (safe to re-run):
#   1. Rewrites /etc/nginx/sites-available/riverwatch with the corrected
#      WebSocket location blocks for /ws/ AND /api/ws/.
#   2. Adds 308 redirects for bare /ws and /api/ws so curl tests work too.
#   3. Validates and reloads nginx.
#   4. Prints a verification curl you can run to confirm 101 Switching Protocols.
#
# Run on the Pi:
#   sudo ./scripts/pi-fix-nginx-ws.sh
# ============================================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Please run with sudo:  sudo $0"
    exit 1
fi

CONF=/etc/nginx/sites-available/riverwatch

if [[ ! -f "$CONF" ]]; then
    echo "!! $CONF not found - run scripts/pi-native-install.sh first."
    exit 1
fi

echo "==> Backing up current nginx config to $CONF.bak.$(date +%s)"
cp "$CONF" "$CONF.bak.$(date +%s)"

cat > "$CONF" <<'NGINX'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    root /var/www/riverwatch;
    index index.html;
    client_max_body_size 25m;

    # WebSocket upgrade for AIS data (App.js production builds use /ws/ais).
    # Backend exposes both /ws/* and /api/ws/* for compatibility.
    location /ws/ {
        proxy_pass http://127.0.0.1:8001/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_buffering off;
    }

    # WebSocket upgrade for /api/ws/* (RawDataPanel + Emergent preview path).
    # Must appear before the /api/ block so nginx prefers this longer prefix.
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

    # Bare /api/ws and /ws - return 308 so the WS method is preserved.
    location = /api/ws { return 308 /api/ws/; }
    location = /ws     { return 308 /ws/; }

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

    location /docs         { proxy_pass http://127.0.0.1:8001/docs; }
    location /openapi.json { proxy_pass http://127.0.0.1:8001/openapi.json; }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/riverwatch /etc/nginx/sites-enabled/riverwatch
rm -f /etc/nginx/sites-enabled/default

echo "==> Validating nginx config..."
nginx -t

echo "==> Reloading nginx..."
systemctl reload nginx

cat <<EOF

==============================================
  Nginx WebSocket patch applied.
==============================================
Verify WebSocket upgrade works (expect: HTTP/1.1 101 Switching Protocols):

  curl -i -N --max-time 3 \\
       -H "Connection: Upgrade" -H "Upgrade: websocket" \\
       -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \\
       -H "Sec-WebSocket-Version: 13" \\
       http://localhost/ws/ais

Then refresh the River Watch app in Chromium - the status pill should turn LIVE.
==============================================
EOF
