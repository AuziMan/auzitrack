#!/bin/bash
# setup.sh — first-time Pi setup after git clone
# Run once from the repo root: ./setup.sh

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DUMP1090_WEB="/home/auziman/projects/flight-tracker-antenna/dump1090/public_html"
SERVICE_NAME="tracker"

echo "=== AuziTrack Setup ==="
echo "Repo: $REPO_DIR"
echo ""

# ── 1. Python venv ────────────────────────────────────────────────────────────
echo "[1/4] Creating Python virtual environment..."
python3 -m venv "$REPO_DIR/venv"
"$REPO_DIR/venv/bin/pip" install -q --upgrade pip
"$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/server/requirements.txt"
echo "      Done."

# ── 2. Symlink index.html into dump1090 web root ─────────────────────────────
echo "[2/4] Linking index.html into dump1090 web root..."
if [ ! -d "$DUMP1090_WEB" ]; then
  echo "      ERROR: $DUMP1090_WEB not found."
  echo "      Is dump1090 installed? Run dump1090 first, then re-run this script."
  exit 1
fi
ln -sf "$REPO_DIR/public_html/index.html" "$DUMP1090_WEB/index.html"
echo "      Linked: $DUMP1090_WEB/index.html → $REPO_DIR/public_html/index.html"

# ── 3. Install systemd service (with correct repo path baked in) ──────────────
echo "[3/4] Installing systemd service..."
# Write the service file with the real repo path so it works wherever cloned
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=AuziTrack Flight Enrichment Service
After=network.target

[Service]
User=$(whoami)
WorkingDirectory=$REPO_DIR/server
ExecStart=$REPO_DIR/venv/bin/python tracker.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
echo "      Service installed and enabled."

# ── 4. Start the service ──────────────────────────────────────────────────────
echo "[4/4] Starting tracker service..."
sudo systemctl restart "$SERVICE_NAME"
sleep 2
STATUS=$(sudo systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "unknown")
if [ "$STATUS" = "active" ]; then
  echo "      Service is running."
else
  echo "      WARNING: Service status is '$STATUS'. Check logs:"
  echo "        sudo journalctl -u $SERVICE_NAME -n 20"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "=== Setup complete ==="
echo ""
echo "  Tracker API:  http://$(hostname -I | awk '{print $1}'):5000/aircraft"
echo "  Flight page:  http://$(hostname -I | awk '{print $1}')"
echo ""
echo "Future updates:"
echo "  git pull && sudo systemctl restart tracker"
echo ""
