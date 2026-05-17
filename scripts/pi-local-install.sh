#!/usr/bin/env bash
# ============================================================================
# River Watch - Raspberry Pi local install
# ============================================================================
# Self-contained installer for the Pi. Installs Docker (if missing), pulls the
# repo, builds the four-service stack (Mongo + backend + ais-relay + frontend),
# and prints the LAN endpoints to use from Boat Beacon and from any other
# device on the boat WiFi.
#
# Run on the Pi:
#   curl -fsSL https://raw.githubusercontent.com/cdillerud/AIS-Riverwatch/main-v2/scripts/pi-local-install.sh | bash
# or
#   ./scripts/pi-local-install.sh   (from a cloned repo)
# ============================================================================

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/cdillerud/AIS-Riverwatch.git}"
REPO_BRANCH="${REPO_BRANCH:-main-v2}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/AIS-Riverwatch}"

BLUE="\033[1;34m"; GREEN="\033[1;32m"; YELLOW="\033[1;33m"; RED="\033[1;31m"; NC="\033[0m"
log()  { echo -e "${BLUE}==>${NC} $*"; }
ok()   { echo -e "${GREEN}OK ${NC} $*"; }
warn() { echo -e "${YELLOW}!!${NC} $*"; }
err()  { echo -e "${RED}xx${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# 0. Sanity
# ---------------------------------------------------------------------------
if [[ "$(id -u)" -eq 0 ]]; then
    err "Run this as your normal user (the script will sudo as needed)."
    exit 1
fi

ARCH="$(uname -m)"
log "Detected architecture: $ARCH"
case "$ARCH" in
    aarch64|arm64) ok "ARM64 — supported." ;;
    armv7l)        warn "32-bit ARM. Mongo 7 requires 64-bit; consider a 64-bit Raspberry Pi OS install." ;;
    x86_64)        ok "x86_64 — supported." ;;
    *)             warn "Unknown architecture: $ARCH (continuing anyway)" ;;
esac

# ---------------------------------------------------------------------------
# 1. Docker + Compose
# ---------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    DOCKER_NEEDS_RELOGIN=1
    ok "Docker installed."
else
    ok "Docker already installed: $(docker --version)"
fi

if ! docker compose version >/dev/null 2>&1; then
    log "Installing Docker Compose plugin..."
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
fi
ok "Compose: $(docker compose version)"

# ---------------------------------------------------------------------------
# 2. Clone or update repo
# ---------------------------------------------------------------------------
if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    log "Cloning $REPO_URL ($REPO_BRANCH) -> $INSTALL_DIR"
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
else
    log "Updating existing repo at $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" checkout "$REPO_BRANCH"
    git -C "$INSTALL_DIR" pull --ff-only origin "$REPO_BRANCH" || warn "Pull skipped (uncommitted changes?)"
fi
cd "$INSTALL_DIR"

# ---------------------------------------------------------------------------
# 3. Generate backend/.env.pi if missing
# ---------------------------------------------------------------------------
if [[ ! -f backend/.env.pi ]]; then
    log "Generating backend/.env.pi"
    cp backend/.env.pi.example backend/.env.pi
    SECRET="$(openssl rand -hex 32)"
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" backend/.env.pi
    ok "Wrote backend/.env.pi (SECRET_KEY auto-generated)."
else
    ok "backend/.env.pi already present — leaving alone."
fi

# ---------------------------------------------------------------------------
# 4. Build + start the stack
# ---------------------------------------------------------------------------
COMPOSE="docker compose -f docker-compose.pi.yml"

# If user is not yet in the docker group, fall back to sudo for this run
if ! docker info >/dev/null 2>&1; then
    warn "Docker group not active yet for this shell — using sudo for compose."
    COMPOSE="sudo $COMPOSE"
fi

log "Building images (first run takes ~10-15 min on a Pi 4)..."
$COMPOSE build

log "Starting River Watch stack..."
$COMPOSE up -d

log "Waiting for backend healthcheck..."
for i in {1..30}; do
    if curl -fsS http://localhost/api/locks >/dev/null 2>&1; then
        ok "Backend reachable through nginx."
        break
    fi
    sleep 2
    [[ $i -eq 30 ]] && warn "Backend did not respond within 60s — check 'docker compose logs backend'."
done

# ---------------------------------------------------------------------------
# 5. Print LAN endpoints
# ---------------------------------------------------------------------------
LAN_IP="$(hostname -I | awk '{print $1}')"
HOSTNAME_LOCAL="$(hostname).local"

cat <<EOF

==============================================
  River Watch is installed locally on this Pi
==============================================

Open the dashboard from any device on the same WiFi:
  http://${LAN_IP}
  http://${HOSTNAME_LOCAL}

On THIS Pi (kiosk display):
  http://localhost

Boat Beacon AIS push target (set in the Boat Beacon app):
  http://${LAN_IP}/api/ais/ingest

Stack management:
  cd ${INSTALL_DIR}
  docker compose -f docker-compose.pi.yml ps
  docker compose -f docker-compose.pi.yml logs -f
  docker compose -f docker-compose.pi.yml down

To launch the touchscreen kiosk on this Pi, run:
  ${INSTALL_DIR}/scripts/pi-kiosk-launch.sh

EOF

if [[ "${DOCKER_NEEDS_RELOGIN:-0}" -eq 1 ]]; then
    warn "Docker was just installed. Log out and back in (or reboot) so this user can run 'docker' without sudo."
fi
