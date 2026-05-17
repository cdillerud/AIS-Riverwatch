#!/usr/bin/env bash
# ============================================================================
# River Watch - Pi-local touchscreen kiosk launcher
# ============================================================================
# Boots Chromium full-screen pointed at the locally-running River Watch stack.
# Designed for a Pi 4 with the official 7" touchscreen.
#
# Usage (manual):
#   ./scripts/pi-kiosk-launch.sh
#
# To autostart at boot, copy the systemd unit installed by this script:
#   ./scripts/pi-kiosk-launch.sh --install-autostart
#   sudo reboot
# ============================================================================
set -euo pipefail

KIOSK_URL="${KIOSK_URL:-http://localhost}"

install_autostart() {
    # Pick the best available LXDE autostart path; create one if it doesn't exist.
    LXDE_AUTOSTART="$HOME/.config/lxsession/LXDE-pi/autostart"
    mkdir -p "$(dirname "$LXDE_AUTOSTART")"
    touch "$LXDE_AUTOSTART"
    # Disable screen blanking + start kiosk launcher
    grep -q '^@xset s off'         "$LXDE_AUTOSTART" || echo '@xset s off'         >> "$LXDE_AUTOSTART"
    grep -q '^@xset -dpms'         "$LXDE_AUTOSTART" || echo '@xset -dpms'         >> "$LXDE_AUTOSTART"
    grep -q '^@xset s noblank'     "$LXDE_AUTOSTART" || echo '@xset s noblank'     >> "$LXDE_AUTOSTART"
    grep -q 'pi-kiosk-launch.sh'   "$LXDE_AUTOSTART" || echo "@$PWD/$(basename "$0")" >> "$LXDE_AUTOSTART"
    echo "Autostart entry written to $LXDE_AUTOSTART"
    echo "Reboot to start the kiosk automatically: sudo reboot"
    exit 0
}

if [[ "${1:-}" == "--install-autostart" ]]; then
    install_autostart
fi

# Wait for desktop + display
sleep 5

# Disable screen blanking
xset s off          || true
xset s noblank      || true
xset -dpms          || true

# Hide mouse cursor after 3s idle (only if unclutter is installed)
command -v unclutter >/dev/null && unclutter -idle 3 -root &

# Pick a Chromium binary
CHROMIUM="$(command -v chromium-browser || command -v chromium || true)"
if [[ -z "$CHROMIUM" ]]; then
    echo "Chromium not found. Install with: sudo apt-get install -y chromium-browser unclutter"
    exit 1
fi

# Make sure the local stack is up before launching
for i in {1..30}; do
    if curl -fsS "$KIOSK_URL" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

# Launch
exec "$CHROMIUM" \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-restore-session-state \
    --no-first-run \
    --start-fullscreen \
    --autoplay-policy=no-user-gesture-required \
    --check-for-update-interval=31536000 \
    --disable-features=TranslateUI \
    --overscroll-history-navigation=0 \
    --disable-pinch \
    --touch-events=enabled \
    --enable-touch-drag-drop \
    "$KIOSK_URL"
