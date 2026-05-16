#!/bin/bash
# River Watch - LysMarine Setup Script
# Adds River Watch as a web app to your existing LysMarine installation

set -e

echo "=============================================="
echo "  River Watch - LysMarine Setup"
echo "=============================================="

# Configuration
RIVERWATCH_URL="${RIVERWATCH_URL:-http://136.116.165.255:3000}"
INSTALL_DIR="/home/user/riverwatch"

echo ""
echo "River Watch URL: $RIVERWATCH_URL"
echo ""

# Create installation directory
mkdir -p "$INSTALL_DIR"

# Create launcher script
echo "[1/4] Creating River Watch launcher..."
cat > "$INSTALL_DIR/launch-riverwatch.sh" << LAUNCHER
#!/bin/bash
# Launch River Watch in Chromium

# Use existing Chromium or Firefox from LysMarine
if command -v chromium-browser &> /dev/null; then
    BROWSER="chromium-browser"
elif command -v chromium &> /dev/null; then
    BROWSER="chromium"
elif command -v firefox-esr &> /dev/null; then
    BROWSER="firefox-esr"
else
    BROWSER="firefox"
fi

# Launch in app mode (minimal UI, touch-friendly)
if [[ "\$BROWSER" == *"chromium"* ]]; then
    \$BROWSER \\
        --app=$RIVERWATCH_URL \\
        --start-fullscreen \\
        --noerrdialogs \\
        --disable-infobars \\
        --touch-events=enabled \\
        --enable-touch-drag-drop \\
        "\$@"
else
    \$BROWSER --kiosk "$RIVERWATCH_URL" "\$@"
fi
LAUNCHER
chmod +x "$INSTALL_DIR/launch-riverwatch.sh"

# Create desktop shortcut
echo "[2/4] Creating desktop shortcut..."
cat > "$HOME/Desktop/riverwatch.desktop" << 'DESKTOP'
[Desktop Entry]
Version=1.0
Type=Application
Name=River Watch
Comment=Mississippi River Lock Timing & Vessel Tracking
Exec=/home/user/riverwatch/launch-riverwatch.sh
Icon=network-workgroup
Terminal=false
Categories=Network;WebBrowser;
Keywords=ais;marine;river;locks;navigation;
DESKTOP
chmod +x "$HOME/Desktop/riverwatch.desktop"

# Also add to applications menu
echo "[3/4] Adding to applications menu..."
mkdir -p "$HOME/.local/share/applications"
cp "$HOME/Desktop/riverwatch.desktop" "$HOME/.local/share/applications/"

# Create SignalK integration script (optional - for future use)
echo "[4/4] Creating SignalK integration helper..."
cat > "$INSTALL_DIR/signalk-to-riverwatch.sh" << 'SIGNALK'
#!/bin/bash
# Forward SignalK AIS data to River Watch backend
# This creates a bridge between SignalK and River Watch

SIGNALK_URL="${SIGNALK_URL:-http://localhost:3000}"
RIVERWATCH_BACKEND="${RIVERWATCH_BACKEND:-http://136.116.165.255:8001}"

echo "SignalK to River Watch Bridge"
echo "SignalK: $SIGNALK_URL"
echo "River Watch: $RIVERWATCH_BACKEND"
echo ""
echo "Note: River Watch can receive AIS data directly via TCP."
echo "Configure your AIS feed in River Watch settings."
echo ""
echo "If you want to use SignalK as the AIS source:"
echo "1. Enable SignalK TCP output on a port (e.g., 10110)"
echo "2. Point River Watch to localhost:10110"
SIGNALK
chmod +x "$INSTALL_DIR/signalk-to-riverwatch.sh"

echo ""
echo "=============================================="
echo "  Setup Complete!"
echo "=============================================="
echo ""
echo "River Watch has been added to LysMarine."
echo ""
echo "To launch:"
echo "  - Click 'River Watch' icon on desktop"
echo "  - Or run: $INSTALL_DIR/launch-riverwatch.sh"
echo ""
echo "The app connects to: $RIVERWATCH_URL"
echo ""
echo "To change the URL, edit:"
echo "  $INSTALL_DIR/launch-riverwatch.sh"
echo ""
