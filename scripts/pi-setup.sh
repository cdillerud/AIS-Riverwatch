#!/bin/bash
# River Watch - Raspberry Pi 4 Setup Script
# Optimized for 7" touchscreen in kiosk mode
# Connects to remote River Watch backend

set -e

echo "=============================================="
echo "  River Watch - Raspberry Pi 4 Setup"
echo "=============================================="

# Configuration - EDIT THESE
BACKEND_URL="${BACKEND_URL:-http://136.116.165.255:8001}"
KIOSK_URL="${KIOSK_URL:-http://136.116.165.255:3000}"

echo ""
echo "Backend URL: $BACKEND_URL"
echo "Kiosk URL: $KIOSK_URL"
echo ""

# Update system
echo "[1/6] Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install dependencies
echo "[2/6] Installing dependencies..."
sudo apt-get install -y \
    chromium-browser \
    unclutter \
    xdotool \
    fonts-liberation \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2

# Create kiosk user if not exists
echo "[3/6] Setting up kiosk environment..."
if ! id "kiosk" &>/dev/null; then
    sudo useradd -m -s /bin/bash kiosk
    echo "Created kiosk user"
fi

# Create autostart directory
mkdir -p /home/kiosk/.config/autostart
mkdir -p /home/kiosk/.config/lxsession/LXDE-pi

# Create kiosk startup script
echo "[4/6] Creating kiosk startup script..."
cat > /home/kiosk/start-riverwatch.sh << 'KIOSK_SCRIPT'
#!/bin/bash
# River Watch Kiosk Startup Script

# Wait for desktop to be ready
sleep 5

# Disable screen blanking
xset s off
xset s noblank
xset -dpms

# Hide mouse cursor after 3 seconds of inactivity
unclutter -idle 3 -root &

# Kill any existing Chromium instances
pkill -f chromium || true
sleep 2

# Start Chromium in kiosk mode
chromium-browser \
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
    --enable-features=TouchpadOverscrollHistoryNavigation \
    "KIOSK_URL_PLACEHOLDER"
KIOSK_SCRIPT

# Replace placeholder with actual URL
sed -i "s|KIOSK_URL_PLACEHOLDER|$KIOSK_URL|g" /home/kiosk/start-riverwatch.sh
chmod +x /home/kiosk/start-riverwatch.sh

# Create autostart entry
echo "[5/6] Configuring autostart..."
cat > /home/kiosk/.config/autostart/riverwatch.desktop << 'DESKTOP_ENTRY'
[Desktop Entry]
Type=Application
Name=River Watch
Exec=/home/kiosk/start-riverwatch.sh
X-GNOME-Autostart-enabled=true
DESKTOP_ENTRY

# Also add to LXDE autostart for Raspberry Pi OS
cat > /home/kiosk/.config/lxsession/LXDE-pi/autostart << 'LXDE_AUTOSTART'
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@xset s off
@xset -dpms
@xset s noblank
@unclutter -idle 3 -root
@/home/kiosk/start-riverwatch.sh
LXDE_AUTOSTART

# Set ownership
sudo chown -R kiosk:kiosk /home/kiosk/

# Create systemd service for auto-login
echo "[6/6] Configuring auto-login..."
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d/
cat | sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf << 'AUTOLOGIN'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin kiosk --noclear %I $TERM
AUTOLOGIN

# Configure lightdm for auto-login (if using desktop)
if [ -f /etc/lightdm/lightdm.conf ]; then
    sudo sed -i 's/^#autologin-user=.*/autologin-user=kiosk/' /etc/lightdm/lightdm.conf
    sudo sed -i 's/^autologin-user=.*/autologin-user=kiosk/' /etc/lightdm/lightdm.conf
fi

echo ""
echo "=============================================="
echo "  Setup Complete!"
echo "=============================================="
echo ""
echo "River Watch will auto-start on boot in kiosk mode."
echo ""
echo "To start manually:"
echo "  /home/kiosk/start-riverwatch.sh"
echo ""
echo "To change the server URL, edit:"
echo "  /home/kiosk/start-riverwatch.sh"
echo ""
echo "Reboot to apply changes:"
echo "  sudo reboot"
echo ""
