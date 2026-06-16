#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_USER="${DEPLOY_USER:-jurisdigta-admin}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/jurisdigta}"
REPO_URL="${REPO_URL:-https://github.com/mmaideveloper/aijurisdictionagents.git}"
REPO_REF="${REPO_REF:-main}"
SERVER_HOSTNAME="${SERVER_HOSTNAME:-jurisdigta-server}"
INSTALL_CLOUDFLARED="${INSTALL_CLOUDFLARED:-0}"

log() {
  printf '[jurisdigta-setup] %s\n' "$*"
}

require_root_or_sudo() {
  if [ "$(id -u)" -ne 0 ] && ! sudo -n true >/dev/null 2>&1; then
    printf 'This script needs sudo access. Run once interactively or configure sudo for %s.\n' "$DEPLOY_USER" >&2
    exit 1
  fi
}

apt_install() {
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

require_root_or_sudo

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  if [ "${ID:-}" != "ubuntu" ]; then
    printf 'Unsupported OS: %s. This script is intended for Ubuntu Server.\n' "${PRETTY_NAME:-unknown}" >&2
    exit 1
  fi
fi

log "configuring hostname ${SERVER_HOSTNAME}"
if [ "$(hostname)" != "$SERVER_HOSTNAME" ]; then
  sudo hostnamectl set-hostname "$SERVER_HOSTNAME"
fi

log "installing operating-system packages"
sudo apt-get update
apt_install \
  apt-transport-https \
  ca-certificates \
  certbot \
  curl \
  docker-buildx \
  docker-compose-v2 \
  docker.io \
  git \
  gnupg \
  jq \
  lsb-release \
  nginx \
  nodejs \
  npm \
  openssh-server \
  postgresql-client \
  python3 \
  python3-pip \
  python3-venv \
  python3-certbot-nginx \
  rsync \
  software-properties-common \
  ufw \
  unzip

log "enabling services"
sudo systemctl enable --now ssh
sudo systemctl enable --now docker
sudo usermod -aG docker "$DEPLOY_USER"

log "configuring firewall baseline"
sudo ufw allow OpenSSH
if sudo ufw status | grep -q inactive; then
  sudo ufw --force enable
fi

if [ "$INSTALL_CLOUDFLARED" = "1" ]; then
  log "installing cloudflared package"
  sudo mkdir -p --mode=0755 /usr/share/keyrings
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
  echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | \
    sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
  sudo apt-get update
  apt_install cloudflared
fi

log "creating deployment directories"
sudo mkdir -p \
  "$DEPLOY_ROOT" \
  "$DEPLOY_ROOT/ops" \
  "$DEPLOY_ROOT/secrets" \
  "$DEPLOY_ROOT/runs/logs" \
  "$DEPLOY_ROOT/runs/locks" \
  "$DEPLOY_ROOT/runs/status" \
  "$DEPLOY_ROOT/runs/storage/api/postgres/data" \
  "$DEPLOY_ROOT/runs/storage/api/sqlite" \
  "$DEPLOY_ROOT/runs/storage/api/files" \
  "$DEPLOY_ROOT/runs/storage/laws-collector/postgres/data" \
  "$DEPLOY_ROOT/runs/storage/laws-collector/sqlite" \
  "$DEPLOY_ROOT/runs/storage/laws-collector/files"
sudo chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_ROOT"
chmod 700 "$DEPLOY_ROOT/secrets"

if [ ! -d "$DEPLOY_ROOT/app/.git" ]; then
  log "cloning repository"
  git clone "$REPO_URL" "$DEPLOY_ROOT/app"
fi

log "updating repository checkout"
git -C "$DEPLOY_ROOT/app" fetch --all --prune
git -C "$DEPLOY_ROOT/app" checkout "$REPO_REF"
git -C "$DEPLOY_ROOT/app" pull --ff-only origin "$REPO_REF" || true

if [ ! -e "$DEPLOY_ROOT/app/runs" ]; then
  ln -s "$DEPLOY_ROOT/runs" "$DEPLOY_ROOT/app/runs"
fi

if [ ! -f "$DEPLOY_ROOT/secrets/jurisdigta.env" ]; then
  log "creating server-local environment template"
  cp "$DEPLOY_ROOT/app/.env.example" "$DEPLOY_ROOT/secrets/jurisdigta.env"
  chmod 600 "$DEPLOY_ROOT/secrets/jurisdigta.env"
fi

log "validating installed tools"
docker --version
docker compose version
node --version
npm --version
python3 --version
psql --version
git --version

log "setup complete. Reconnect SSH so docker group membership is active, then edit $DEPLOY_ROOT/secrets/jurisdigta.env."
