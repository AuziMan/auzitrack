#!/bin/bash
# deploy.sh — push latest files to the Pi
# Usage: ./deploy.sh [html|server|all]
#   html   — deploy only index.html (default)
#   server — deploy only server files
#   all    — deploy everything

set -e

PI_USER="auziman"
PI_HOST="192.168.0.100"
WEB_ROOT="$PI_USER@$PI_HOST:/home/auziman/projects/flight-tracker-antenna/dump1090/public_html"
SERVER_ROOT="$PI_USER@$PI_HOST:/home/auziman/projects/flight-tracker-antenna/auzitrack"

MODE="${1:-html}"

deploy_html() {
  echo "→ Deploying index.html ..."
  scp public_html/index.html "$WEB_ROOT/index.html"
  echo "  Done. View at http://$PI_HOST"
}

deploy_server() {
  echo "→ Deploying server files ..."
  ssh "$PI_USER@$PI_HOST" "mkdir -p /home/auziman/projects/flight-tracker-antenna/auzitrack/server"
  scp server/tracker.py   "$SERVER_ROOT/server/tracker.py"
  scp server/requirements.txt "$SERVER_ROOT/server/requirements.txt"

  echo "→ Installing dependencies on Pi ..."
  ssh "$PI_USER@$PI_HOST" "
    cd /home/auziman/projects/flight-tracker-antenna/auzitrack
    python3 -m venv venv
    venv/bin/pip install -q -r server/requirements.txt
  "

  echo "→ Installing & restarting systemd service ..."
  scp server/tracker.service "$PI_USER@$PI_HOST:/tmp/tracker.service"
  ssh "$PI_USER@$PI_HOST" "
    sudo mv /tmp/tracker.service /etc/systemd/system/tracker.service
    sudo systemctl daemon-reload
    sudo systemctl enable tracker
    sudo systemctl restart tracker
    echo '  Service status:' && sudo systemctl is-active tracker
  "
  echo "  Done. API at http://$PI_HOST:5000/aircraft"
}

case "$MODE" in
  html)   deploy_html ;;
  server) deploy_server ;;
  all)    deploy_html; deploy_server ;;
  *)      echo "Usage: ./deploy.sh [html|server|all]"; exit 1 ;;
esac
