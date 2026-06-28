#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/jurisdigta}"
APP_DIR="${APP_DIR:-$DEPLOY_ROOT/app}"
ENV_FILE="${ENV_FILE:-$DEPLOY_ROOT/secrets/jurisdigta.env}"
REPO_REF="${REPO_REF:-main}"
API_PORT="${API_PORT:-8080}"
MCP_PORT="${MCP_PORT:-8070}"
WEB_PORT="${WEB_PORT:-8090}"
DOCUMENT_ENGINE_ENABLED="${DOCUMENT_ENGINE_ENABLED:-1}"
DOCUMENT_ENGINE_API_PORT="${DOCUMENT_ENGINE_API_PORT:-8060}"
DOCUMENT_ENGINE_DATABASE_NAME="${DOCUMENT_ENGINE_DATABASE_NAME:-document_engine}"
WEB_API_BASE_URL="${WEB_API_BASE_URL:-https://api.jurisdigta.eu}"
RUN_SCHEMA_MIGRATIONS="${RUN_SCHEMA_MIGRATIONS:-1}"
INSTALL_LAWS_CRON="${INSTALL_LAWS_CRON:-1}"
LAWS_COLLECTOR_RUN_MODE="${LAWS_COLLECTOR_RUN_MODE:-continuous}"
INSTALL_DOCUMENT_PROCESSOR_CRON="${INSTALL_DOCUMENT_PROCESSOR_CRON:-1}"
DOCUMENT_PROCESSOR_CRON_EXPRESSION="${DOCUMENT_PROCESSOR_CRON_EXPRESSION:-*/15 * * * *}"
DOCUMENT_PROCESSOR_LIMIT="${DOCUMENT_PROCESSOR_LIMIT:-20}"
EMAIL_SCHEDULER_INTERVAL_SECONDS="${EMAIL_SCHEDULER_INTERVAL_SECONDS:-5}"
INSTALL_STATUS_CRON="${INSTALL_STATUS_CRON:-1}"
INSTALL_LOG_RETENTION_CRON="${INSTALL_LOG_RETENTION_CRON:-1}"
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-7}"
DOCKER_LOG_MAX_SIZE="${DOCKER_LOG_MAX_SIZE:-50m}"
DOCKER_LOG_MAX_FILE="${DOCKER_LOG_MAX_FILE:-5}"
START_MONITORING="${START_MONITORING:-0}"
INSTALL_OLLAMA="${INSTALL_OLLAMA:-1}"
LOCAL_LLM_PROVIDER="${LOCAL_LLM_PROVIDER:-ollama}"
LOCAL_LLM_MODEL="${LOCAL_LLM_MODEL:-qwen3.6:27b}"
LOCAL_LLM_BASE_URL="${LOCAL_LLM_BASE_URL:-http://127.0.0.1:11434}"
LOCAL_LLM_OPENAI_BASE_URL="${LOCAL_LLM_OPENAI_BASE_URL:-http://127.0.0.1:11434/v1}"
LOCAL_LLM_HEALTH_URL="${LOCAL_LLM_HEALTH_URL:-http://127.0.0.1:11434/api/tags}"
OLLAMA_HOST_BIND="${OLLAMA_HOST_BIND:-}"
export DOCKER_BUILDKIT=0

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

postgres_sqlalchemy_url() {
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
print(f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}")
PY
}

load_env() {
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
}

append_csv_value() {
  local existing="$1"
  local required="$2"
  if [ -z "$existing" ]; then
    printf '%s' "$required"
    return
  fi
  case ",$existing," in
    *",$required,"*) printf '%s' "$existing" ;;
    *) printf '%s,%s' "$existing" "$required" ;;
  esac
}

production_api_cors_origins() {
  local origins="${CORS_ALLOW_ORIGINS:-}"
  origins="$(append_csv_value "$origins" "https://jurisdigta.eu")"
  origins="$(append_csv_value "$origins" "https://www.jurisdigta.eu")"
  origins="$(append_csv_value "$origins" "https://web.jurisdigta.eu")"
  origins="$(append_csv_value "$origins" "https://agent.jurisdigta.eu")"
  printf '%s' "$origins"
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

require_email_delivery_settings() {
  local transport="${EMAIL_TRANSPORT:-}"
  if [ "$transport" != "smtp" ]; then
    fail "Production deploy requires EMAIL_TRANSPORT=smtp for sign-up and OTP email delivery. Current value: ${transport:-unset}"
  fi

  local missing=()
  for key in EMAIL_SENDER EMAIL_SMTP_HOST EMAIL_SMTP_PORT EMAIL_SMTP_USERNAME EMAIL_SMTP_PASSWORD; do
    if [ -z "${!key:-}" ]; then
      missing+=("$key")
    fi
  done

  if [ "${#missing[@]}" -gt 0 ]; then
    printf '[jurisdigta-deploy] Missing required email delivery settings:\n' >&2
    printf '  - %s\n' "${missing[@]}" >&2
    exit 1
  fi
}

require_cron_expression() {
  local name="$1"
  local value="$2"
  local field_count
  field_count="$(printf '%s\n' "$value" | awk '{print NF}')"
  if [ "$field_count" != "5" ] || ! printf '%s' "$value" | grep -Eq '^[0-9*,/ -]+$'; then
    fail "$name must be a five-field cron expression using numbers, '*', ',', '-', '/', and spaces. Current value: $value"
  fi
}

require_positive_integer() {
  local name="$1"
  local value="$2"
  if ! printf '%s' "$value" | grep -Eq '^[1-9][0-9]{0,3}$'; then
    fail "$name must be a positive integer up to 9999. Current value: $value"
  fi
}

require_boolean_flag() {
  local name="$1"
  local value="$2"
  if ! printf '%s' "$value" | grep -Eq '^[01]$'; then
    fail "$name must be 0 or 1. Current value: $value"
  fi
}

require_laws_collector_run_mode() {
  local value="$1"
  if [ "$value" != "scheduled" ] && [ "$value" != "continuous" ]; then
    fail "LAWS_COLLECTOR_RUN_MODE must be scheduled or continuous. Current value: $value"
  fi
}

app_docker_gateway() {
  docker network inspect aijuristiction-api_default \
    --format '{{(index .IPAM.Config 0).Gateway}}'
}

local_llm_container_base_url() {
  local gateway
  gateway="$(app_docker_gateway)"
  if [ -z "$gateway" ] || [ "$gateway" = "<no value>" ]; then
    fail "Cannot resolve Docker gateway for aijuristiction-api_default"
  fi
  printf 'http://%s:11434' "$gateway"
}

effective_ollama_host_bind() {
  if [ -n "$OLLAMA_HOST_BIND" ]; then
    printf '%s' "$OLLAMA_HOST_BIND"
    return
  fi
  local gateway
  gateway="$(app_docker_gateway)"
  if [ -z "$gateway" ] || [ "$gateway" = "<no value>" ]; then
    fail "Cannot resolve Docker gateway for Ollama bind"
  fi
  printf '%s:11434' "$gateway"
}

require_local_model_settings() {
  if [ "$LOCAL_LLM_PROVIDER" != "ollama" ]; then
    fail "Self-managed prod local model routing currently requires LOCAL_LLM_PROVIDER=ollama. Current value: $LOCAL_LLM_PROVIDER"
  fi
  if [ -z "$LOCAL_LLM_MODEL" ]; then
    fail "LOCAL_LLM_MODEL must be set for Ollama deployment"
  fi
  local bind
  bind="$(effective_ollama_host_bind)"
  if printf '%s' "$bind" | grep -Eq '^(\*|0\.0\.0\.0):11434$'; then
    fail "OLLAMA_HOST_BIND must not expose Ollama on all interfaces. Current value: $bind"
  fi
}

require_tcp_port() {
  local name="$1"
  local value="$2"
  if ! printf '%s' "$value" | grep -Eq '^[1-9][0-9]{1,4}$' || [ "$value" -lt 1024 ] || [ "$value" -gt 65535 ]; then
    fail "$name must be a TCP port between 1024 and 65535. Current value: $value"
  fi
}

require_postgres_identifier() {
  local name="$1"
  local value="$2"
  if ! printf '%s' "$value" | grep -Eq '^[A-Za-z_][A-Za-z0-9_]{0,62}$'; then
    fail "$name must be a PostgreSQL-safe identifier. Current value: $value"
  fi
}

install_ollama_service() {
  if [ "$INSTALL_OLLAMA" != "1" ]; then
    log "Ollama install skipped by INSTALL_OLLAMA=$INSTALL_OLLAMA"
    return
  fi
  require_local_model_settings
  require_command systemctl
  local bind
  local host_base_url
  bind="$(effective_ollama_host_bind)"
  host_base_url="http://$bind"

  if ! command -v ollama >/dev/null 2>&1; then
    log "installing Ollama"
    local installer="/tmp/install-ollama.sh"
    curl -fsSL https://ollama.com/install.sh -o "$installer"
    sh "$installer"
  else
    log "Ollama already installed"
  fi

  log "configuring Ollama private bind at $bind"
  sudo install -d -m 755 /etc/systemd/system/ollama.service.d
  cat <<EOF | sudo tee /etc/systemd/system/ollama.service.d/jurisdigta-localhost.conf >/dev/null
[Service]
Environment="OLLAMA_HOST=$bind"
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now ollama
  sudo systemctl restart ollama

  wait_for_http "Ollama" "$host_base_url/api/tags" 30 2
  log "pulling Ollama model $LOCAL_LLM_MODEL"
  OLLAMA_HOST="$bind" ollama pull "$LOCAL_LLM_MODEL"
  OLLAMA_HOST="$bind" ollama list | grep -F "$LOCAL_LLM_MODEL" >/dev/null || fail "Ollama model was not found after pull: $LOCAL_LLM_MODEL"
  curl -fsS "$host_base_url/api/tags" >/dev/null
  curl -fsS "$host_base_url/v1/models" >/dev/null
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
    "$DEPLOY_ROOT/runs/storage/document-processor" \
    "$DEPLOY_ROOT/runs/storage/document-engine/generated-documents" \
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
  local api_cors_allow_origins
  local prometheus_base_url
  local local_llm_base_url
  api_db_cloud="$(postgres_url "postgres" "${LOCAL_POSTGRES_DB:-aijurisdiction}")"
  laws_db_cloud="$(postgres_url "postgres" "${AZURE_LAWS_POSTGRES_DATABASE_NAME_SK:-laws_sk}")"
  api_cors_allow_origins="$(production_api_cors_origins)"
  prometheus_base_url="${API_PROMETHEUS_BASE_URL:-http://jurisdigta-prometheus:9090}"
  local_llm_base_url="$(local_llm_container_base_url)"
  docker rm -f jurisdigta-api jurisdigta-mcp jurisdigta-email-scheduler >/dev/null 2>&1 || true
  docker run -d \
    --name jurisdigta-api \
    --restart unless-stopped \
    --log-opt "max-size=$DOCKER_LOG_MAX_SIZE" \
    --log-opt "max-file=$DOCKER_LOG_MAX_FILE" \
    --network aijuristiction-api_default \
    -p "127.0.0.1:${API_PORT}:8080" \
    --env-file "$ENV_FILE" \
    -e DB_OPTION=postgres \
    -e DB_CLOUD="$api_db_cloud" \
    -e DB_LOCAL=/workspace/runs/storage/api/sqlite/api.sqlite3 \
    -e CORS_ALLOW_ORIGINS="$api_cors_allow_origins" \
    -e EMAIL_DB_OPTION=postgres \
    -e EMAIL_DB_CLOUD="$api_db_cloud" \
    -e EMAIL_DB_LOCAL=/workspace/runs/storage/api/sqlite/email.sqlite3 \
    -e STORAGE_OPTION=local \
    -e STORE_LOCAL=/workspace/runs/storage/api/files \
    -e DOCUMENT_PROCESSOR_OPTION=azure \
    -e LOCAL_LLM_BASE_URL="$local_llm_base_url" \
    -e LOCAL_LLM_OPENAI_BASE_URL="$local_llm_base_url/v1" \
    -e LOCAL_LLM_HEALTH_URL="$local_llm_base_url/api/tags" \
    -e LAWS_COUNTRY="${LAWS_COUNTRY:-SK}" \
    -e LAWS_DB_BACKEND=postgres \
    -e LAWS_DB_CLOUD="$laws_db_cloud" \
    -e INTERNAL_MCP_BASE_URL=http://jurisdigta-mcp:8070 \
    -e PROMETHEUS_BASE_URL="$prometheus_base_url" \
    -e SYSTEM_STATUS_FILE=/workspace/runs/status/system-status.json \
    -v "$DEPLOY_ROOT/runs:/workspace/runs" \
    aijuristiction-api:local >/dev/null

  docker run -d \
    --name jurisdigta-mcp \
    --restart unless-stopped \
    --log-opt "max-size=$DOCKER_LOG_MAX_SIZE" \
    --log-opt "max-file=$DOCKER_LOG_MAX_FILE" \
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
    -e EMAIL_DB_OPTION=postgres \
    -e EMAIL_DB_CLOUD="$api_db_cloud" \
    -e EMAIL_DB_LOCAL=/workspace/runs/storage/api/sqlite/email.sqlite3 \
    -e STORAGE_OPTION=local \
    -e STORE_LOCAL=/workspace/runs/storage/api/files \
    -e LOCAL_LLM_BASE_URL="$local_llm_base_url" \
    -e LOCAL_LLM_OPENAI_BASE_URL="$local_llm_base_url/v1" \
    -e LOCAL_LLM_HEALTH_URL="$local_llm_base_url/api/tags" \
    -e LAWS_COUNTRY="${LAWS_COUNTRY:-SK}" \
    -e LAWS_DB_BACKEND=postgres \
    -e LAWS_DB_CLOUD="$laws_db_cloud" \
    -e MCP_PUBLIC_BASE_URL="${MCP_PUBLIC_BASE_URL:-https://mcp.jurisdigta.eu}" \
    -e SYSTEM_STATUS_FILE=/workspace/runs/status/system-status.json \
    -v "$DEPLOY_ROOT/runs:/workspace/runs" \
    aijuristiction-api:local \
    uvicorn app.mcp_main:app --host 0.0.0.0 --port 8070 >/dev/null

  docker run -d \
    --name jurisdigta-email-scheduler \
    --restart unless-stopped \
    --log-opt "max-size=$DOCKER_LOG_MAX_SIZE" \
    --log-opt "max-file=$DOCKER_LOG_MAX_FILE" \
    --no-healthcheck \
    --network aijuristiction-api_default \
    --env-file "$ENV_FILE" \
    -e DB_OPTION=postgres \
    -e DB_CLOUD="$api_db_cloud" \
    -e DB_LOCAL=/workspace/runs/storage/api/sqlite/api.sqlite3 \
    -e EMAIL_DB_OPTION=postgres \
    -e EMAIL_DB_CLOUD="$api_db_cloud" \
    -e EMAIL_DB_LOCAL=/workspace/runs/storage/api/sqlite/email.sqlite3 \
    -e EMAIL_SCHEDULER_ENABLED=true \
    -e EMAIL_SCHEDULER_INTERVAL_SECONDS="$EMAIL_SCHEDULER_INTERVAL_SECONDS" \
    -v "$DEPLOY_ROOT/runs:/workspace/runs" \
    aijuristiction-api:local \
    python -m app.email_scheduler_main >/dev/null
}

create_laws_database() {
  local db="${AZURE_LAWS_POSTGRES_DATABASE_NAME_SK:-laws_sk}"
  local pg_user="${LOCAL_POSTGRES_USER:-postgres}"
  log "ensuring laws PostgreSQL database exists"
  docker exec aijurisdiction-postgres psql -U "$pg_user" -d "${LOCAL_POSTGRES_DB:-aijurisdiction}" -tc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1 || \
    docker exec aijurisdiction-postgres psql -U "$pg_user" -d "${LOCAL_POSTGRES_DB:-aijurisdiction}" -c "CREATE DATABASE $db;"
  docker exec aijurisdiction-postgres psql -U "$pg_user" -d "$db" -c "CREATE EXTENSION IF NOT EXISTS vector;"
}

create_document_engine_database() {
  if [ "$DOCUMENT_ENGINE_ENABLED" != "1" ]; then
    log "document engine database skipped by DOCUMENT_ENGINE_ENABLED=$DOCUMENT_ENGINE_ENABLED"
    return
  fi

  local db="$DOCUMENT_ENGINE_DATABASE_NAME"
  local pg_user="${LOCAL_POSTGRES_USER:-postgres}"
  log "ensuring document engine PostgreSQL database exists"
  docker exec aijurisdiction-postgres psql -U "$pg_user" -d "${LOCAL_POSTGRES_DB:-aijurisdiction}" -tc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1 || \
    docker exec aijurisdiction-postgres psql -U "$pg_user" -d "${LOCAL_POSTGRES_DB:-aijurisdiction}" -c "CREATE DATABASE $db;"
}

run_schema_migrations() {
  if [ "$RUN_SCHEMA_MIGRATIONS" != "1" ]; then
    log "schema migrations skipped by RUN_SCHEMA_MIGRATIONS=$RUN_SCHEMA_MIGRATIONS"
    return
  fi

  log "applying API and laws database schema migrations in the API image"
  local api_db_cloud
  local laws_db_cloud
  local local_llm_base_url
  api_db_cloud="$(postgres_url "postgres" "${LOCAL_POSTGRES_DB:-aijurisdiction}")"
  laws_db_cloud="$(postgres_url "postgres" "${AZURE_LAWS_POSTGRES_DATABASE_NAME_SK:-laws_sk}")"
  local_llm_base_url="$(local_llm_container_base_url)"

  docker run --rm \
    --network aijuristiction-api_default \
    --env-file "$ENV_FILE" \
    -v "$DEPLOY_ROOT/runs:/workspace/runs" \
    -e DB_OPTION=postgres \
    -e DB_CLOUD="$api_db_cloud" \
    -e DB_LOCAL=/workspace/runs/storage/api/sqlite/api.sqlite3 \
    -e STORAGE_OPTION=local \
    -e STORE_LOCAL=/workspace/runs/storage/api/files \
    -e LOCAL_LLM_BASE_URL="$local_llm_base_url" \
    -e LOCAL_LLM_OPENAI_BASE_URL="$local_llm_base_url/v1" \
    -e LOCAL_LLM_HEALTH_URL="$local_llm_base_url/api/tags" \
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
    -e LOCAL_LLM_BASE_URL="$local_llm_base_url" \
    -e LOCAL_LLM_OPENAI_BASE_URL="$local_llm_base_url/v1" \
    -e LOCAL_LLM_HEALTH_URL="$local_llm_base_url/api/tags" \
    -e LAWS_DB_BACKEND=postgres \
    -e LAWS_DB_CLOUD="$laws_db_cloud" \
    aijuristiction-api:local \
    python /workspace/scripts/databases/apply_laws_db_schema.py
}

deploy_web() {
  log "building and starting frontend web container"
  cd "$APP_DIR/frontend/aijurisdictionfronend"
  local chat_model_label="${AZURE_OPENAI_DEPLOYMENT:-Azure Foundry model}"
  docker build \
    --build-arg "VITE_API_BASE_URL=$WEB_API_BASE_URL" \
    --build-arg "VITE_CHAT_MODEL_LABEL=$chat_model_label" \
    -t jurisdigta-web:local .
  docker rm -f jurisdigta-web >/dev/null 2>&1 || true
  docker run -d \
    --name jurisdigta-web \
    --restart unless-stopped \
    --log-opt "max-size=$DOCKER_LOG_MAX_SIZE" \
    --log-opt "max-file=$DOCKER_LOG_MAX_FILE" \
    -p "127.0.0.1:${WEB_PORT}:80" \
    jurisdigta-web:local >/dev/null
}

build_laws_collector() {
  log "building laws collector image"
  cd "$APP_DIR"
  docker build -t jurisdigta-laws-collector:local -f src/services/laws_collector/Dockerfile .
}

build_document_processor() {
  log "building document processor image"
  cd "$APP_DIR"
  docker build -t jurisdigta-document-processor:local -f src/services/document_processor/Dockerfile .
}

build_document_engine() {
  if [ "$DOCUMENT_ENGINE_ENABLED" != "1" ]; then
    log "document engine build skipped by DOCUMENT_ENGINE_ENABLED=$DOCUMENT_ENGINE_ENABLED"
    return
  fi

  log "building document engine image"
  cd "$APP_DIR/services/document-engine-service"
  docker build -t jurisdigta-document-engine:local .
}

start_document_engine() {
  if [ "$DOCUMENT_ENGINE_ENABLED" != "1" ]; then
    log "document engine start skipped by DOCUMENT_ENGINE_ENABLED=$DOCUMENT_ENGINE_ENABLED"
    docker rm -f jurisdigta-document-engine-api jurisdigta-document-engine-worker >/dev/null 2>&1 || true
    return
  fi

  log "starting document engine API and worker"
  local document_engine_db_url
  document_engine_db_url="$(postgres_sqlalchemy_url "postgres" "$DOCUMENT_ENGINE_DATABASE_NAME")"

  docker rm -f jurisdigta-document-engine-api jurisdigta-document-engine-worker >/dev/null 2>&1 || true

  docker run -d \
    --name jurisdigta-document-engine-api \
    --restart unless-stopped \
    --log-opt "max-size=$DOCKER_LOG_MAX_SIZE" \
    --log-opt "max-file=$DOCKER_LOG_MAX_FILE" \
    --network aijuristiction-api_default \
    --user "$(id -u):$(id -g)" \
    -p "127.0.0.1:${DOCUMENT_ENGINE_API_PORT}:8000" \
    -e DATABASE_URL="$document_engine_db_url" \
    -e GENERATED_DOCUMENTS_DIR=/data/generated-documents \
    -v "$DEPLOY_ROOT/runs/storage/document-engine/generated-documents:/data/generated-documents" \
    jurisdigta-document-engine:local >/dev/null

  docker run -d \
    --name jurisdigta-document-engine-worker \
    --restart unless-stopped \
    --log-opt "max-size=$DOCKER_LOG_MAX_SIZE" \
    --log-opt "max-file=$DOCKER_LOG_MAX_FILE" \
    --network aijuristiction-api_default \
    --user "$(id -u):$(id -g)" \
    -e DATABASE_URL="$document_engine_db_url" \
    -e GENERATED_DOCUMENTS_DIR=/data/generated-documents \
    -e WORKER_POLL_INTERVAL_SECONDS="${DOCUMENT_ENGINE_WORKER_POLL_INTERVAL_SECONDS:-2}" \
    -e WORKER_BATCH_SIZE="${DOCUMENT_ENGINE_WORKER_BATCH_SIZE:-5}" \
    -v "$DEPLOY_ROOT/runs/storage/document-engine/generated-documents:/data/generated-documents" \
    jurisdigta-document-engine:local \
    python -m document_engine.worker >/dev/null
}

install_document_processor_wrapper() {
  if [ "$INSTALL_DOCUMENT_PROCESSOR_CRON" != "1" ]; then
    log "document processor cron skipped by INSTALL_DOCUMENT_PROCESSOR_CRON=$INSTALL_DOCUMENT_PROCESSOR_CRON"
    return
  fi

  require_cron_expression "DOCUMENT_PROCESSOR_CRON_EXPRESSION" "$DOCUMENT_PROCESSOR_CRON_EXPRESSION"

  log "installing document processor wrapper and cron"
  cat > "$DEPLOY_ROOT/ops/run_document_processor.sh" <<'WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/jurisdigta}"
APP_DIR="${APP_DIR:-$DEPLOY_ROOT/app}"
ENV_FILE="${ENV_FILE:-$DEPLOY_ROOT/secrets/jurisdigta.env}"
LOG_DIR="$DEPLOY_ROOT/runs/logs"
LOCK_FILE="$DEPLOY_ROOT/runs/locks/document-processor.lock"
LOG_FILE="$LOG_DIR/document-processor-$(date -u +%Y%m%dT%H%M%SZ).log"
LATEST_LOG="$LOG_DIR/document-processor-latest.log"

mkdir -p "$LOG_DIR" "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[document-processor] another run is already active" | tee -a "$LOG_FILE"
  exit 0
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

docker rm -f jurisdigta-document-processor >/dev/null 2>&1 || true

API_DB_CLOUD_VALUE="$(python3 - "${LOCAL_POSTGRES_DB:-aijurisdiction}" <<'PY'
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

DOCUMENT_PROCESSOR_LIMIT_VALUE="${DOCUMENT_PROCESSOR_LIMIT:-20}"
DOCUMENT_PROCESSOR_MAX_RUNNING_TIME_VALUE="${DOCUMENT_PROCESSOR_MAX_RUNNING_TIME:-15}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] starting document processor job" | tee -a "$LOG_FILE"
docker run --rm \
  --name jurisdigta-document-processor \
  --network aijuristiction-api_default \
  --env-file "$ENV_FILE" \
  -e DB_OPTION=postgres \
  -e DB_CLOUD="$API_DB_CLOUD_VALUE" \
  -e DB_LOCAL=/workspace/runs/storage/api/sqlite/api.sqlite3 \
  -e STORAGE_OPTION=local \
  -e STORE_LOCAL=/workspace/runs/storage/api/files \
  -e DOCUMENT_PROCESSOR_OPTION=azure \
  -e DOCUMENT_PROCESSOR_MAX_RUNNING_TIME="$DOCUMENT_PROCESSOR_MAX_RUNNING_TIME_VALUE" \
  -v "$DEPLOY_ROOT/runs:/workspace/runs" \
  -v "$APP_DIR/aimodels:/app/aimodels" \
  jurisdigta-document-processor:local \
  python -m services.document_processor --limit "$DOCUMENT_PROCESSOR_LIMIT_VALUE" 2>&1 | tee -a "$LOG_FILE"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] document processor job finished" | tee -a "$LOG_FILE"

ln -sfn "$LOG_FILE" "$LATEST_LOG"
WRAPPER
  chmod 700 "$DEPLOY_ROOT/ops/run_document_processor.sh"

  (crontab -l 2>/dev/null | grep -v 'run_document_processor.sh' || true; \
    echo "$DOCUMENT_PROCESSOR_CRON_EXPRESSION /srv/jurisdigta/ops/run_document_processor.sh >/dev/null 2>&1") | crontab -
}

install_laws_wrapper() {
  if [ "$INSTALL_LAWS_CRON" != "1" ]; then
    log "laws collector setup skipped by INSTALL_LAWS_CRON=$INSTALL_LAWS_CRON"
    return
  fi

  if [ "$LAWS_COLLECTOR_RUN_MODE" = "continuous" ]; then
    log "starting continuous laws collector container"
    (crontab -l 2>/dev/null | grep -v 'run_laws_collector_daily.sh' || true) | crontab -
    docker rm -f jurisdigta-laws-collector jurisdigta-laws-collector-daily >/dev/null 2>&1 || true

    local laws_db_cloud_value
    laws_db_cloud_value="$(postgres_url "postgres" "${AZURE_LAWS_POSTGRES_DATABASE_NAME_SK:-laws_sk}")"

    docker run -d \
      --name jurisdigta-laws-collector \
      --restart unless-stopped \
      --log-opt "max-size=$DOCKER_LOG_MAX_SIZE" \
      --log-opt "max-file=$DOCKER_LOG_MAX_FILE" \
      --network aijuristiction-api_default \
      --env-file "$ENV_FILE" \
      -e LAWS_COUNTRY="${LAWS_COUNTRY:-SK}" \
      -e LAWS_DB_BACKEND=postgres \
      -e LAWS_DB_CLOUD="$laws_db_cloud_value" \
      -e LAWS_WORKER_FIXTURE=live \
      -e LAWS_COLLECTOR_RUN_MODE=continuous \
      -e LAWS_WORKER_MAX_CYCLES=0 \
      -e LAWS_WORKER_MAX_PROBES="${LAWS_WORKER_MAX_PROBES:-25}" \
      -e LAWS_WORKER_POLL_SECONDS="${LAWS_WORKER_POLL_SECONDS:-3600}" \
      -e LAWS_COLLECTOR_IMPORT="${LAWS_COLLECTOR_IMPORT:-zip}" \
      -e LAWS_COLLECTOR_MAX_RUNNING_TIME=0 \
      -v "$DEPLOY_ROOT/runs:/workspace/runs" \
      -v "$APP_DIR/archivelaws:/app/archivelaws" \
      -v "$APP_DIR/aimodels:/app/aimodels" \
      jurisdigta-laws-collector:local >/dev/null
    return
  fi

  log "installing scheduled laws collector daily wrapper and cron"
  docker rm -f jurisdigta-laws-collector >/dev/null 2>&1 || true
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

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] starting laws collector daily job" | tee -a "$LOG_FILE"
docker run --rm \
  --name jurisdigta-laws-collector-daily \
  --network aijuristiction-api_default \
  --env-file "$ENV_FILE" \
  -e LAWS_COUNTRY="${LAWS_COUNTRY:-SK}" \
  -e LAWS_DB_BACKEND=postgres \
  -e LAWS_DB_CLOUD="$LAWS_DB_CLOUD_VALUE" \
  -e LAWS_WORKER_FIXTURE=live \
  -e LAWS_COLLECTOR_RUN_MODE=scheduled \
  -e LAWS_WORKER_MAX_CYCLES=1 \
  -e LAWS_WORKER_MAX_PROBES="${LAWS_WORKER_MAX_PROBES:-25}" \
  -e LAWS_WORKER_POLL_SECONDS="${LAWS_WORKER_POLL_SECONDS:-3600}" \
  -e LAWS_COLLECTOR_IMPORT="${LAWS_COLLECTOR_IMPORT:-zip}" \
  -e LAWS_COLLECTOR_MAX_RUNNING_TIME="${LAWS_COLLECTOR_MAX_RUNNING_TIME:-60}" \
  -v "$DEPLOY_ROOT/runs:/workspace/runs" \
  -v "$APP_DIR/archivelaws:/app/archivelaws" \
  -v "$APP_DIR/aimodels:/app/aimodels" \
  jurisdigta-laws-collector:local 2>&1 | tee -a "$LOG_FILE"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] laws collector daily job finished" | tee -a "$LOG_FILE"

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

  local laws_container_name="jurisdigta-laws-collector-daily"
  if [ "$LAWS_COLLECTOR_RUN_MODE" = "continuous" ]; then
    laws_container_name="jurisdigta-laws-collector"
  fi

  log "installing system status writer cron"
  (crontab -l 2>/dev/null | grep -v 'write_system_status.py' || true; \
    echo "* * * * * cd /srv/jurisdigta/app && python3 scripts/server/write_system_status.py --output /srv/jurisdigta/runs/status/system-status.json --laws-container $laws_container_name --laws-log /srv/jurisdigta/runs/logs/laws-collector-daily-latest.log --document-processor-log /srv/jurisdigta/runs/logs/document-processor-latest.log >/dev/null 2>&1") | crontab -
}

install_log_retention_cron() {
  if [ "$INSTALL_LOG_RETENTION_CRON" != "1" ]; then
    log "log retention cron skipped by INSTALL_LOG_RETENTION_CRON=$INSTALL_LOG_RETENTION_CRON"
    return
  fi

  log "installing log retention cleanup with LOG_RETENTION_DAYS=$LOG_RETENTION_DAYS"
  cat > "$DEPLOY_ROOT/ops/cleanup_logs.sh" <<'WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/jurisdigta}"
ENV_FILE="${ENV_FILE:-$DEPLOY_ROOT/secrets/jurisdigta.env}"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-7}"
if ! printf '%s' "$LOG_RETENTION_DAYS" | grep -Eq '^[1-9][0-9]{0,3}$'; then
  echo "[log-retention] invalid LOG_RETENTION_DAYS=$LOG_RETENTION_DAYS" >&2
  exit 1
fi

LOG_DIR="$DEPLOY_ROOT/runs/logs"
mkdir -p "$LOG_DIR"
find "$LOG_DIR" -type f -name '*.log' -mtime +"$LOG_RETENTION_DAYS" -delete
WRAPPER
  chmod 700 "$DEPLOY_ROOT/ops/cleanup_logs.sh"

  (crontab -l 2>/dev/null | grep -v 'cleanup_logs.sh' || true; \
    echo '35 3 * * * /srv/jurisdigta/ops/cleanup_logs.sh >/dev/null 2>&1') | crontab -
}

start_monitoring() {
  if [ "$START_MONITORING" != "1" ]; then
    log "monitoring stack not started by START_MONITORING=$START_MONITORING"
    return
  fi
  log "configuring and starting monitoring stack"
  cd "$APP_DIR/Deployment/monitoring"
  python3 configure_monitoring.py --project-env "$ENV_FILE" --validate --start
}

connect_api_to_monitoring_network() {
  local network="${MONITORING_DOCKER_NETWORK:-monitoring_default}"
  if ! docker network inspect "$network" >/dev/null 2>&1; then
    log "monitoring network $network not found; API Prometheus access may be unavailable"
    return
  fi
  if docker inspect -f '{{json .NetworkSettings.Networks}}' jurisdigta-api | grep -q "\"$network\""; then
    log "API container already connected to $network"
    return
  fi
  log "connecting API container to monitoring network $network"
  docker network connect "$network" jurisdigta-api
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local attempts="${3:-30}"
  local sleep_seconds="${4:-2}"
  local attempt

  for attempt in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null; then
      log "$name is healthy at $url"
      return 0
    fi
    log "waiting for $name at $url ($attempt/$attempts)"
    sleep "$sleep_seconds"
  done

  curl -fsS "$url" >/dev/null
}

validate_health() {
  log "validating local health endpoints"
  if [ "$INSTALL_OLLAMA" = "1" ]; then
    local local_llm_base_url
    local_llm_base_url="$(local_llm_container_base_url)"
    wait_for_http "Ollama" "$local_llm_base_url/api/tags"
    curl -fsS "$local_llm_base_url/v1/models" >/dev/null
    OLLAMA_HOST="$(effective_ollama_host_bind)" ollama list | grep -F "$LOCAL_LLM_MODEL" >/dev/null
  fi
  wait_for_http "API" "http://127.0.0.1:${API_PORT}/health"
  wait_for_http "MCP" "http://127.0.0.1:${MCP_PORT}/health"
  wait_for_http "web" "http://127.0.0.1:${WEB_PORT}/health"
  docker inspect -f '{{.State.Running}}' jurisdigta-email-scheduler | grep -qx true
  if [ "$DOCUMENT_ENGINE_ENABLED" = "1" ]; then
    wait_for_http "document engine" "http://127.0.0.1:${DOCUMENT_ENGINE_API_PORT}/health"
    docker inspect -f '{{.State.Running}}' jurisdigta-document-engine-worker | grep -qx true
  fi
  docker image inspect jurisdigta-document-processor:local >/dev/null
  if [ "$INSTALL_DOCUMENT_PROCESSOR_CRON" = "1" ]; then
    test -x "$DEPLOY_ROOT/ops/run_document_processor.sh"
  fi
  local laws_container_name="jurisdigta-laws-collector-daily"
  if [ "$LAWS_COLLECTOR_RUN_MODE" = "continuous" ]; then
    laws_container_name="jurisdigta-laws-collector"
    docker inspect -f '{{.State.Running}}' "$laws_container_name" | grep -qx true
  elif [ "$INSTALL_LAWS_CRON" = "1" ]; then
    test -x "$DEPLOY_ROOT/ops/run_laws_collector_daily.sh"
  fi
  python3 "$APP_DIR/scripts/server/write_system_status.py" \
    --output "$DEPLOY_ROOT/runs/status/system-status.json" \
    --laws-container "$laws_container_name" \
    --laws-log "$DEPLOY_ROOT/runs/logs/laws-collector-daily-latest.log" \
    --document-processor-log "$DEPLOY_ROOT/runs/logs/document-processor-latest.log" >/dev/null
}

require_command git
require_command docker
require_command python3
require_command curl

[ -f "$ENV_FILE" ] || fail "Missing environment file: $ENV_FILE"
load_env
require_azurefoundry_settings
require_email_delivery_settings
require_cron_expression "DOCUMENT_PROCESSOR_CRON_EXPRESSION" "$DOCUMENT_PROCESSOR_CRON_EXPRESSION"
require_positive_integer "DOCUMENT_PROCESSOR_LIMIT" "$DOCUMENT_PROCESSOR_LIMIT"
require_positive_integer "LOG_RETENTION_DAYS" "$LOG_RETENTION_DAYS"
require_positive_integer "DOCKER_LOG_MAX_FILE" "$DOCKER_LOG_MAX_FILE"
require_boolean_flag "DOCUMENT_ENGINE_ENABLED" "$DOCUMENT_ENGINE_ENABLED"
require_boolean_flag "INSTALL_LOG_RETENTION_CRON" "$INSTALL_LOG_RETENTION_CRON"
require_boolean_flag "INSTALL_OLLAMA" "$INSTALL_OLLAMA"
require_laws_collector_run_mode "$LAWS_COLLECTOR_RUN_MODE"
require_tcp_port "DOCUMENT_ENGINE_API_PORT" "$DOCUMENT_ENGINE_API_PORT"
require_postgres_identifier "DOCUMENT_ENGINE_DATABASE_NAME" "$DOCUMENT_ENGINE_DATABASE_NAME"
ensure_runtime_layout
update_checkout
load_env
require_azurefoundry_settings
require_email_delivery_settings
require_cron_expression "DOCUMENT_PROCESSOR_CRON_EXPRESSION" "$DOCUMENT_PROCESSOR_CRON_EXPRESSION"
require_positive_integer "DOCUMENT_PROCESSOR_LIMIT" "$DOCUMENT_PROCESSOR_LIMIT"
require_positive_integer "LOG_RETENTION_DAYS" "$LOG_RETENTION_DAYS"
require_positive_integer "DOCKER_LOG_MAX_FILE" "$DOCKER_LOG_MAX_FILE"
require_boolean_flag "DOCUMENT_ENGINE_ENABLED" "$DOCUMENT_ENGINE_ENABLED"
require_boolean_flag "INSTALL_LOG_RETENTION_CRON" "$INSTALL_LOG_RETENTION_CRON"
require_boolean_flag "INSTALL_OLLAMA" "$INSTALL_OLLAMA"
require_laws_collector_run_mode "$LAWS_COLLECTOR_RUN_MODE"
require_tcp_port "DOCUMENT_ENGINE_API_PORT" "$DOCUMENT_ENGINE_API_PORT"
require_postgres_identifier "DOCUMENT_ENGINE_DATABASE_NAME" "$DOCUMENT_ENGINE_DATABASE_NAME"
start_postgres_and_build_image
install_ollama_service
create_laws_database
create_document_engine_database
run_schema_migrations
start_api_and_mcp
deploy_web
build_document_processor
install_document_processor_wrapper
build_document_engine
start_document_engine
build_laws_collector
install_laws_wrapper
install_status_writer_cron
install_log_retention_cron
start_monitoring
connect_api_to_monitoring_network
validate_health

log "production deployment complete"
