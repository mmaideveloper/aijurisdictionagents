#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/jurisdigta}"
APP_DIR="${APP_DIR:-$DEPLOY_ROOT/app}"
ENV_FILE="${ENV_FILE:-$DEPLOY_ROOT/secrets/jurisdigta.env}"
REPO_REF="${REPO_REF:-main}"
API_PORT="${API_PORT:-8080}"
MCP_PORT="${MCP_PORT:-8070}"
WEB_PORT="${WEB_PORT:-8090}"
WEB_API_BASE_URL="${WEB_API_BASE_URL:-https://api.jurisdigta.eu}"
RUN_SCHEMA_MIGRATIONS="${RUN_SCHEMA_MIGRATIONS:-1}"
INSTALL_LAWS_CRON="${INSTALL_LAWS_CRON:-1}"
INSTALL_STATUS_CRON="${INSTALL_STATUS_CRON:-1}"
START_MONITORING="${START_MONITORING:-0}"

log() {
  printf '[jurisdigta-deploy] %s\n' "$*"
}

fail() {
  printf '[jurisdigta-deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

postgres_url() {
  local host="$1"
  local database="$2"
  python3 - "$host" "$database" <<'PY'
import os
import sys
from urllib.parse import quote

host = sys.argv[1]
database = sys.argv[2]
user = quote(os.environ.get("LOCAL_POSTGRES_USER", "postgres"), safe="")
password = quote(os.environ.get("LOCAL_POSTGRES_PASSWORD", "postgres"), safe="")
port = os.environ.get("LOCAL_POSTGRES_PORT", "5432")
print(f"postgresql://{user}:{password}@{host}:{port}/{database}")
PY
}

load_env() {
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
}

require_azurefoundry_settings() {
  local provider="${LLM_PROVIDER:-azurefoundry}"
  if [ "$provider" != "azurefoundry" ]; then
    fail "Production deploy requires LLM_PROVIDER=azurefoundry. Current value: $provider"
  fi

  local missing=()
  for key in AZURE_OPENAI_ENDPOINT AZURE_OPENAI_DEPLOYMENT AZURE_OPENAI_EMBEDDINGS_MODEL AZURE_OPENAI_API_VERSION AZURE_OPENAI_API_KEY; do
    if [ -z "${!key:-}" ]; then
      missing+=("$key")
    fi
  done

  if [ "${#missing[@]}" -gt 0 ]; then
    printf '[jurisdigta-deploy] Missing required Azure Foundry settings:\n' >&2
    printf '  - %s\n' "${missing[@]}" >&2
    exit 1
  fi
}

ensure_runtime_layout() {
  mkdir -p \
    "$DEPLOY_ROOT/ops" \
    "$DEPLOY_ROOT/runs/logs" \
    "$DEPLOY_ROOT/runs/locks" \
    "$DEPLOY_ROOT/runs/status" \
    "$DEPLOY_ROOT/runs/storage/api/postgres/data" \
    "$DEPLOY_ROOT/runs/storage/api/sqlite" \
    "$DEPLOY_ROOT/runs/storage/api/files" \
    "$DEPLOY_ROOT/runs/storage/laws-collector/postgres/data" \
    "$DEPLOY_ROOT/runs/storage/laws-collector/files" \
    "$DEPLOY_ROOT/runs/storage/laws-collector/sqlite"

  if [ -e "$APP_DIR/runs" ] && [ ! -L "$APP_DIR/runs" ]; then
    fail "$APP_DIR/runs exists and is not a symlink. Move runtime data to $DEPLOY_ROOT/runs before deployment."
  fi
  if [ ! -e "$APP_DIR/runs" ]; then
    ln -s "$DEPLOY_ROOT/runs" "$APP_DIR/runs"
  fi
}

update_checkout() {
  log "updating repository checkout to ${REPO_REF}"
  git -C "$APP_DIR" fetch --all --prune
  git -C "$APP_DIR" checkout "$REPO_REF"
  git -C "$APP_DIR" pull --ff-only origin "$REPO_REF"
}

compose_env() {
  LOCAL_POSTGRES_DB="${LOCAL_POSTGRES_DB:-aijurisdiction}"
  LOCAL_POSTGRES_USER="${LOCAL_POSTGRES_USER:-postgres}"
  LOCAL_POSTGRES_PASSWORD="${LOCAL_POSTGRES_PASSWORD:-postgres}"
  LOCAL_POSTGRES_PORT="${LOCAL_POSTGRES_PORT:-5432}"
  API_PORT="$API_PORT"
  MCP_PORT="$MCP_PORT"
  export LOCAL_POSTGRES_DB LOCAL_POSTGRES_USER LOCAL_POSTGRES_PASSWORD LOCAL_POSTGRES_PORT API_PORT MCP_PORT
}

start_postgres_and_build_image() {
  log "building API image and starting PostgreSQL"
  compose_env
  cd "$APP_DIR/api/aijuristiction-api"
  docker compose --env-file "$ENV_FILE" up -d postgres
  docker compose --env-file "$ENV_FILE" build api
}

start_api_and_mcp() {
  log "starting API and MCP"
  compose_env
  local api_db_cloud
  local laws_db_cloud
  api_db_cloud="$(postgres_url "postgres" "${LOCAL_POSTGRES_DB:-aijurisdiction}")"
  laws_db_cloud="$(postgres_url "postgres" "${AZURE_LAWS_POSTGRES_DATABASE_NAME_SK:-laws_sk}")"
  docker rm -f jurisdigta-api jurisdigta-mcp >/dev/null 2>&1 || true
  docker run -d \
    --name jurisdigta-api \
    --restart unless-stopped \
    --network aijuristiction-api_default \
    -p "127.0.0.1:${API_PORT}:8080" \
    --env-file "$ENV_FILE" \
    -e DB_OPTION=postgres \
    -e DB_CLOUD="$api_db_cloud" \
    -e DB_LOCAL=/workspace/runs/storage/api/sqlite/api.sqlite3 \
    -e STORAGE_OPTION=local \
    -e STORE_LOCAL=/workspace/runs/storage/api/files \
    -e LAWS_COUNTRY="${LAWS_COUNTRY:-SK}" \
    -e LAWS_DB_BACKEND=postgres \
    -e LAWS_DB_CLOUD="$laws_db_cloud" \
    -e MCP_PUBLIC_BASE_URL="${MCP_PUBLIC_BASE_URL:-https://mcp.jurisdigta.eu}" \
    -e SYSTEM_STATUS_FILE=/workspace/runs/status/system-status.json \
    -v "$DEPLOY_ROOT/runs:/workspace/runs" \
    aijuristiction-api:local >/dev/null

  docker run -d \
    --name jurisdigta-mcp \
    --restart unless-stopped \
    --network aijuristiction-api_default \
    -p "127.0.0.1:${MCP_PORT}:8070" \
    --health-cmd "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8070/health')\"" \
    --health-interval 30s \
    --health-timeout 5s \
    --health-start-period 10s \
    --health-retries 3 \
    --env-file "$ENV_FILE" \
    -e DB_OPTION=postgres \
    -e DB_CLOUD="$api_db_cloud" \
    -e DB_LOCAL=/workspace/runs/storage/api/sqlite/api.sqlite3 \
    -e STORAGE_OPTION=local \
    -e STORE_LOCAL=/workspace/runs/storage/api/files \
    -e LAWS_COUNTRY="${LAWS_COUNTRY:-SK}" \
    -e LAWS_DB_BACKEND=postgres \
    -e LAWS_DB_CLOUD="$laws_db_cloud" \
    -e SYSTEM_STATUS_FILE=/workspace/runs/status/system-status.json \
    -v "$DEPLOY_ROOT/runs:/workspace/runs" \
    aijuristiction-api:local \
    uvicorn app.mcp_main:app --host 0.0.0.0 --port 8070 >/dev/null
}

create_laws_database() {
  local db="${AZURE_LAWS_POSTGRES_DATABASE_NAME_SK:-laws_sk}"
  local pg_user="${LOCAL_POSTGRES_USER:-postgres}"
  log "ensuring laws PostgreSQL database exists"
  docker exec aijurisdiction-postgres psql -U "$pg_user" -d "${LOCAL_POSTGRES_DB:-aijurisdiction}" -tc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1 || \
    docker exec aijurisdiction-postgres psql -U "$pg_user" -d "${LOCAL_POSTGRES_DB:-aijurisdiction}" -c "CREATE DATABASE $db;"
  docker exec aijurisdiction-postgres psql -U "$pg_user" -d "$db" -c "CREATE EXTENSION IF NOT EXISTS vector;"
}

run_schema_migrations() {
  if [ "$RUN_SCHEMA_MIGRATIONS" != "1" ]; then
    log "schema migrations skipped by RUN_SCHEMA_MIGRATIONS=$RUN_SCHEMA_MIGRATIONS"
    return
  fi

  log "applying API and laws database schema migrations in the API image"
  local api_db_cloud
  local laws_db_cloud
  api_db_cloud="$(postgres_url "postgres" "${LOCAL_POSTGRES_DB:-aijurisdiction}")"
  laws_db_cloud="$(postgres_url "postgres" "${AZURE_LAWS_POSTGRES_DATABASE_NAME_SK:-laws_sk}")"

  docker run --rm \
    --network aijuristiction-api_default \
    --env-file "$ENV_FILE" \
    -v "$DEPLOY_ROOT/runs:/workspace/runs" \
    -e DB_OPTION=postgres \
    -e DB_CLOUD="$api_db_cloud" \
    -e DB_LOCAL=/workspace/runs/storage/api/sqlite/api.sqlite3 \
    -e STORAGE_OPTION=local \
    -e STORE_LOCAL=/workspace/runs/storage/api/files \
    -e LAWS_DB_BACKEND=postgres \
    -e LAWS_DB_CLOUD="$laws_db_cloud" \
    aijuristiction-api:local \
    python /workspace/scripts/databases/apply_api_db_schema.py

  docker run --rm \
    --network aijuristiction-api_default \
    --env-file "$ENV_FILE" \
    -v "$DEPLOY_ROOT/runs:/workspace/runs" \
    -e DB_OPTION=postgres \
    -e DB_CLOUD="$api_db_cloud" \
    -e DB_LOCAL=/workspace/runs/storage/api/sqlite/api.sqlite3 \
    -e STORAGE_OPTION=local \
    -e STORE_LOCAL=/workspace/runs/storage/api/files \
    -e LAWS_DB_BACKEND=postgres \
    -e LAWS_DB_CLOUD="$laws_db_cloud" \
    aijuristiction-api:local \
    python /workspace/scripts/databases/apply_laws_db_schema.py
}

deploy_web() {
  log "building and starting frontend web container"
  cd "$APP_DIR/frontend/aijurisdictionfronend"
  docker build \
    --build-arg "VITE_API_BASE_URL=$WEB_API_BASE_URL" \
    -t jurisdigta-web:local .
  docker rm -f jurisdigta-web >/dev/null 2>&1 || true
  docker run -d \
    --name jurisdigta-web \
    --restart unless-stopped \
    -p "127.0.0.1:${WEB_PORT}:80" \
    jurisdigta-web:local >/dev/null
}

build_laws_collector() {
  log "building laws collector image"
  cd "$APP_DIR"
  docker build -t jurisdigta-laws-collector:local -f src/services/laws_collector/Dockerfile .
}

install_laws_wrapper() {
  if [ "$INSTALL_LAWS_CRON" != "1" ]; then
    log "laws collector cron skipped by INSTALL_LAWS_CRON=$INSTALL_LAWS_CRON"
    return
  fi

  log "installing laws collector daily wrapper and cron"
  cat > "$DEPLOY_ROOT/ops/run_laws_collector_daily.sh" <<'WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/jurisdigta}"
APP_DIR="${APP_DIR:-$DEPLOY_ROOT/app}"
ENV_FILE="${ENV_FILE:-$DEPLOY_ROOT/secrets/jurisdigta.env}"
LOG_DIR="$DEPLOY_ROOT/runs/logs"
LOCK_FILE="$DEPLOY_ROOT/runs/locks/laws-collector-daily.lock"
LOG_FILE="$LOG_DIR/laws-collector-daily-$(date -u +%Y%m%dT%H%M%SZ).log"
LATEST_LOG="$LOG_DIR/laws-collector-daily-latest.log"

mkdir -p "$LOG_DIR" "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[laws-collector] another run is already active" | tee -a "$LOG_FILE"
  exit 0
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

docker rm -f jurisdigta-laws-collector-daily >/dev/null 2>&1 || true

LAWS_DB_CLOUD_VALUE="$(docker inspect jurisdigta-api --format '{{range .Config.Env}}{{println .}}{{end}}' | awk -F= '$1=="LAWS_DB_CLOUD" {sub(/^LAWS_DB_CLOUD=/, ""); print; exit}')"
if [ -z "$LAWS_DB_CLOUD_VALUE" ]; then
  LAWS_DB_CLOUD_VALUE="$(python3 - "${AZURE_LAWS_POSTGRES_DATABASE_NAME_SK:-laws_sk}" <<'PY'
import os
import sys
from urllib.parse import quote

database = sys.argv[1]
user = quote(os.environ.get("LOCAL_POSTGRES_USER", "postgres"), safe="")
password = quote(os.environ.get("LOCAL_POSTGRES_PASSWORD", "postgres"), safe="")
port = os.environ.get("LOCAL_POSTGRES_PORT", "5432")
print(f"postgresql://{user}:{password}@postgres:{port}/{database}")
PY
)"
fi

docker run --rm \
  --name jurisdigta-laws-collector-daily \
  --network aijuristiction-api_default \
  --env-file "$ENV_FILE" \
  -e LAWS_COUNTRY="${LAWS_COUNTRY:-SK}" \
  -e LAWS_DB_BACKEND=postgres \
  -e LAWS_DB_CLOUD="$LAWS_DB_CLOUD_VALUE" \
  -e LAWS_WORKER_FIXTURE=live \
  -e LAWS_WORKER_MAX_CYCLES=1 \
  -e LAWS_WORKER_MAX_PROBES="${LAWS_WORKER_MAX_PROBES:-25}" \
  -e LAWS_WORKER_POLL_SECONDS="${LAWS_WORKER_POLL_SECONDS:-3600}" \
  -e LAWS_COLLECTOR_IMPORT="${LAWS_COLLECTOR_IMPORT:-zip}" \
  -e LAWS_COLLECTOR_MAX_RUNNING_TIME="${LAWS_COLLECTOR_MAX_RUNNING_TIME:-60}" \
  -v "$DEPLOY_ROOT/runs:/workspace/runs" \
  -v "$APP_DIR/archivelaws:/app/archivelaws" \
  -v "$APP_DIR/aimodels:/app/aimodels" \
  jurisdigta-laws-collector:local 2>&1 | tee -a "$LOG_FILE"

ln -sfn "$LOG_FILE" "$LATEST_LOG"
WRAPPER
  chmod 700 "$DEPLOY_ROOT/ops/run_laws_collector_daily.sh"

  (crontab -l 2>/dev/null | grep -v 'run_laws_collector_daily.sh' || true; \
    echo '15 2 * * * /srv/jurisdigta/ops/run_laws_collector_daily.sh >/dev/null 2>&1') | crontab -
}

install_status_writer_cron() {
  if [ "$INSTALL_STATUS_CRON" != "1" ]; then
    log "system status cron skipped by INSTALL_STATUS_CRON=$INSTALL_STATUS_CRON"
    return
  fi

  log "installing system status writer cron"
  (crontab -l 2>/dev/null | grep -v 'write_system_status.py' || true; \
    echo '* * * * * cd /srv/jurisdigta/app && python3 scripts/server/write_system_status.py --output /srv/jurisdigta/runs/status/system-status.json --laws-log /srv/jurisdigta/runs/logs/laws-collector-daily-latest.log >/dev/null 2>&1') | crontab -
}

start_monitoring() {
  if [ "$START_MONITORING" != "1" ]; then
    log "monitoring stack not started by START_MONITORING=$START_MONITORING"
    return
  fi
  if [ ! -f "$APP_DIR/Deployment/monitoring/.env" ]; then
    fail "Create $APP_DIR/Deployment/monitoring/.env with GRAFANA_ADMIN_PASSWORD before START_MONITORING=1"
  fi
  log "starting monitoring stack"
  cd "$APP_DIR/Deployment/monitoring"
  docker compose up -d
}

validate_health() {
  log "validating local health endpoints"
  curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null
  curl -fsS "http://127.0.0.1:${MCP_PORT}/health" >/dev/null
  curl -fsS "http://127.0.0.1:${WEB_PORT}/health" >/dev/null
  python3 "$APP_DIR/scripts/server/write_system_status.py" \
    --output "$DEPLOY_ROOT/runs/status/system-status.json" \
    --laws-log "$DEPLOY_ROOT/runs/logs/laws-collector-daily-latest.log" >/dev/null
}

require_command git
require_command docker
require_command python3
require_command curl

[ -f "$ENV_FILE" ] || fail "Missing environment file: $ENV_FILE"
load_env
require_azurefoundry_settings
ensure_runtime_layout
update_checkout
load_env
require_azurefoundry_settings
start_postgres_and_build_image
create_laws_database
run_schema_migrations
start_api_and_mcp
deploy_web
build_laws_collector
install_laws_wrapper
install_status_writer_cron
start_monitoring
validate_health

log "production deployment complete"
