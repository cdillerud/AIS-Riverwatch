#!/usr/bin/env bash
set -u

BASE="http://34.172.47.153"

echo "=== Riverwatch nginx/static healthcheck ==="
echo "Base: $BASE"
echo

echo "=== Containers ==="
sudo docker compose -p riverwatchclean -f docker-compose.clean.yml ps

echo
echo "=== Listening ports ==="
sudo ss -ltnp | egrep ':80 |:443 |:3000|:8001|:8088' || true

echo
echo "=== /login ==="
curl -sS -D - -o /tmp/riverwatch-login-check.html "$BASE/login" | head -25
echo
head -c 120 /tmp/riverwatch-login-check.html
echo

echo
echo "=== /docs ==="
curl -sS -D - -o /dev/null "$BASE/docs" | head -25

echo
echo "=== /api/locks ==="
curl -sS "$BASE/api/locks" | head -c 500
echo

echo
echo "=== /api/auth/login ==="
curl -sS -i -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"cdillerud@gmail.com","password":"TestPassword123!"}' | head -80
