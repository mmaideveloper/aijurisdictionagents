#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="${1:-install}"
SERVICE_NAME="${SERVICE_NAME:-jurisdigta-mcp-trycloudflare.service}"
MCP_ORIGIN_URL="${MCP_ORIGIN_URL:-http://127.0.0.1:8070}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/jurisdigta}"
LOG_FILE="${LOG_FILE:-$DEPLOY_ROOT/runs/logs/mcp-trycloudflare.log}"
UNIT_PATH="/etc/systemd/system/$SERVICE_NAME"

log() {
  printf '[mcp-trycloudflare] %s\n' "$*"
}

require_sudo() {
  if [ "$(id -u)" -ne 0 ] && ! sudo -n true >/dev/null 2>&1; then
    printf 'This script needs sudo access for systemd service management.\n' >&2
    exit 1
  fi
}

require_cloudflared() {
  if ! command -v cloudflared >/dev/null 2>&1; then
    printf 'cloudflared is required. Install it with setup_jurisdigta_server.sh or the Cloudflare apt repository first.\n' >&2
    exit 1
  fi
}

print_current_url() {
  sudo journalctl -u "$SERVICE_NAME" -n 200 --no-pager 2>/dev/null | \
    grep -Eo 'https://[A-Za-z0-9.-]+\.trycloudflare\.com' | tail -n 1 || true
  if [ -f "$LOG_FILE" ]; then
    grep -Eo 'https://[A-Za-z0-9.-]+\.trycloudflare\.com' "$LOG_FILE" | tail -n 1 || true
  fi
}

install_service() {
  require_sudo
  require_cloudflared

  sudo mkdir -p "$(dirname "$LOG_FILE")"
  sudo touch "$LOG_FILE"
  sudo chown "$(id -u):$(id -g)" "$LOG_FILE" 2>/dev/null || true

  cat <<EOF | sudo tee "$UNIT_PATH" >/dev/null
[Unit]
Description=JurisDigta MCP temporary trycloudflare.com tunnel
Documentation=https://github.com/mmaideveloper/aijurisdictionagents
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate --url ${MCP_ORIGIN_URL} --loglevel info --logfile ${LOG_FILE}
Restart=on-failure
RestartSec=10
User=$(id -un)
WorkingDirectory=${DEPLOY_ROOT}

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now "$SERVICE_NAME"
  log "installed and started $SERVICE_NAME"
  log "origin: $MCP_ORIGIN_URL"
  log "current quick tunnel URL, if already assigned:"
  print_current_url
}

case "$ACTION" in
  install)
    install_service
    ;;
  start)
    require_sudo
    sudo systemctl start "$SERVICE_NAME"
    print_current_url
    ;;
  stop)
    require_sudo
    sudo systemctl stop "$SERVICE_NAME"
    ;;
  status)
    sudo systemctl status "$SERVICE_NAME" --no-pager || true
    print_current_url
    ;;
  url)
    print_current_url
    ;;
  uninstall)
    require_sudo
    sudo systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
    sudo rm -f "$UNIT_PATH"
    sudo systemctl daemon-reload
    ;;
  *)
    printf 'Usage: %s [install|start|stop|status|url|uninstall]\n' "$0" >&2
    exit 2
    ;;
esac
