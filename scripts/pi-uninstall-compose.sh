#!/usr/bin/env bash
# ============================================================================
# River Watch - uninstall the Docker-Compose Pi stack
# ============================================================================
# Tears down the Phase-0 docker-compose setup (mongodb + backend + frontend
# containers + volumes + network) before installing the native Phase-1 stack.
# Safe to run if nothing is installed - all commands are best-effort.
# ============================================================================
set +e
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

echo "==> Stopping & removing docker-compose stack..."
sudo docker compose -f docker-compose.pi.yml down -v 2>/dev/null

echo "==> Removing built images (free up disk)..."
sudo docker rmi riverwatch-pi-frontend:latest 2>/dev/null
sudo docker rmi riverwatch-pi-backend:latest 2>/dev/null
sudo docker rmi riverwatch-pi-ais-relay:latest 2>/dev/null

echo "==> Removing stale autostart entries..."
rm -f ~/.config/autostart/riverwatch.desktop
rm -f ~/.config/autostart/onboard.desktop

echo "==> Done. You can now run ./scripts/pi-native-install.sh"
