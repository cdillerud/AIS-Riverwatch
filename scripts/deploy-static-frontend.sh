#!/usr/bin/env bash
set -euo pipefail

PROJECT="riverwatchclean"
COMPOSE_FILE="docker-compose.clean.yml"
WEBROOT="/var/www/riverwatch"

cd "$(dirname "$0")/.."

echo "=== Build frontend image ==="
sudo docker compose -p "$PROJECT" -f "$COMPOSE_FILE" build frontend

echo
echo "=== Stop frontend dev server container ==="
sudo docker compose -p "$PROJECT" -f "$COMPOSE_FILE" stop frontend 2>/dev/null || true

echo
echo "=== Build static React assets ==="
sudo docker rm -f riverwatch-static-build 2>/dev/null || true

sudo docker create \
  --name riverwatch-static-build \
  -e REACT_APP_BACKEND_URL="" \
  -e WDS_SOCKET_PORT=0 \
  -e FAST_REFRESH=false \
  -e DISABLE_ESLINT_PLUGIN=true \
  -e CI=false \
  -e GENERATE_SOURCEMAP=false \
  riverwatchclean-frontend:latest \
  sh -lc '
    set -e
    cd /app
    rm -rf build

    if ! FAST_REFRESH=false DISABLE_ESLINT_PLUGIN=true CI=false GENERATE_SOURCEMAP=false yarn build; then
      echo "First build failed. Patching temporary react-refresh guard and retrying."
      if [ -f /app/node_modules/react-refresh/babel.js ]; then
        sed -i "s/env !== '\''development'\'' && !opts.skipEnvCheck/false \&\& env !== '\''development'\'' \&\& !opts.skipEnvCheck/g" /app/node_modules/react-refresh/babel.js
      fi
      rm -rf build
      FAST_REFRESH=false DISABLE_ESLINT_PLUGIN=true CI=false GENERATE_SOURCEMAP=false yarn build
    fi

    tar -czf /tmp/riverwatch-build.tgz -C build .
  ' >/dev/null

sudo docker start -a riverwatch-static-build

echo
echo "=== Install static frontend to nginx webroot ==="
sudo rm -rf "$WEBROOT"
sudo mkdir -p "$WEBROOT"
sudo docker cp riverwatch-static-build:/tmp/riverwatch-build.tgz /tmp/riverwatch-build.tgz
sudo tar -xzf /tmp/riverwatch-build.tgz -C "$WEBROOT"
sudo chown -R www-data:www-data "$WEBROOT"
sudo rm -f /tmp/riverwatch-build.tgz
sudo docker rm -f riverwatch-static-build >/dev/null 2>&1 || true

echo
echo "=== Restart nginx ==="
sudo nginx -t
sudo systemctl restart nginx

echo
echo "=== Run healthcheck ==="
./scripts/healthcheck-nginx.sh
