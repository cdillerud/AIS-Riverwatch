#!/usr/bin/env bash
# ============================================================================
# River Watch - Raspberry Pi one-shot deploy script
# ============================================================================
# Mirror of the Cloud VM's ./scripts/deploy-static-frontend.sh, but for the
# Pi native install (systemd + native Nginx + venv).
#
# Idempotent. Safe to run from ANY directory under the repo.
#
# Usage on the Pi:
#   ./scripts/pi-deploy.sh             # pull + build frontend + copy + restart backend
#   ./scripts/pi-deploy.sh --no-pull   # skip git pull (already pulled)
#   ./scripts/pi-deploy.sh --frontend  # rebuild & deploy frontend only
#   ./scripts/pi-deploy.sh --backend   # restart backend only
# ============================================================================
set -euo pipefail

# Resolve repo root regardless of where this is invoked from.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

BLUE="\033[1;34m"; GREEN="\033[1;32m"; YELLOW="\033[1;33m"; RED="\033[1;31m"; NC="\033[0m"
log()  { echo -e "${BLUE}==>${NC} $*"; }
ok()   { echo -e "${GREEN}OK ${NC} $*"; }
warn() { echo -e "${YELLOW}!!${NC} $*"; }
err()  { echo -e "${RED}xx${NC} $*" >&2; }

DO_PULL=1
DO_FRONTEND=1
DO_BACKEND=1

for arg in "$@"; do
    case "$arg" in
        --no-pull)  DO_PULL=0 ;;
        --frontend) DO_BACKEND=0 ;;
        --backend)  DO_FRONTEND=0 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) warn "Unknown arg: $arg" ;;
    esac
done

if [[ $DO_PULL -eq 1 ]]; then
    log "git pull (origin)"
    git pull --ff-only || warn "git pull had conflicts/local changes - continuing with current tree"
fi

if [[ $DO_FRONTEND -eq 1 ]]; then
    log "Building frontend..."
    cd "$REPO_DIR/frontend"
    DISABLE_ESLINT_PLUGIN=true yarn build
    ok  "Frontend built"

    log "Copying build/ -> /var/www/riverwatch/"
    sudo rm -rf /var/www/riverwatch/static
    sudo cp -r build/* /var/www/riverwatch/
    ok  "Frontend deployed"
    cd "$REPO_DIR"
fi

if [[ $DO_BACKEND -eq 1 ]]; then
    log "Restarting riverwatch backend (systemd)..."
    sudo systemctl restart riverwatch.service
    sleep 2
    if systemctl is-active --quiet riverwatch.service; then
        ok "Backend running"
    else
        err "Backend failed to start - check: journalctl -u riverwatch -n 50"
        exit 1
    fi
fi

log "Reloading nginx (cache-bust)..."
sudo systemctl reload nginx || warn "nginx reload failed - check: sudo nginx -t"

cat <<EOF

==============================================
  River Watch - Pi deploy complete
==============================================
  Open or refresh:  http://localhost
  Hard refresh:     Ctrl+Shift+R in Chromium
  Backend logs:     journalctl -u riverwatch -f
==============================================
EOF
