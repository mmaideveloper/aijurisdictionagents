# Self-Managed Server Deployment Preparation

This runbook documents the software and server preparation needed to deploy JurisDigta API, system code, laws connector, and PostgreSQL database from GitHub onto the Ubuntu host reachable as `jurisdigta-server`.

Checked-in automation:

- `Deployment/server/setup_jurisdigta_server.sh` installs Ubuntu packages, Docker, deployment directories, firewall baseline, and the first repository checkout.
- `Deployment/server/deploy_jurisdigta_prod.sh` updates the server checkout, deploys PostgreSQL/API/MCP/email scheduler/web/document processor/laws collector/status monitoring, and validates local health checks.
- `.github/workflows/self_managed_prod_deploy.yml` runs the production deploy script over SSH from the protected GitHub `prod` Environment.

Current target verified from Codex on 2026-06-13:

- SSH alias: `jurisdigta-server`
- Hostname: `jurisdigta-server`
- Server user: `jurisdigta-admin`
- OS: Ubuntu 26.04 LTS
- Available capacity: about `409G` free disk and `11GiB` RAM
- Installed before deployment prep: `git`, `python3`, `curl`, `rsync`, `ufw`
- Missing before deployment prep: Docker, Docker Compose, Node.js, npm, pip, PostgreSQL client tools, GitHub CLI, nginx, unzip

## Compliance And Security Baseline

- Use the non-root account `jurisdigta-admin` for SSH and deployment operations.
- Keep application secrets in server-local environment files or runtime secret stores, never in Git.
- Restrict environment files to the deployment user and root: `chmod 600`.
- Keep PostgreSQL runtime data under `/srv/jurisdigta/runs/storage/...` to mirror the repository layout.
- Keep SQL assets in the repository under `databases/`; do not place database runtime files there.
- Enable logs for traceability, but avoid logging personal data, legal facts, document contents, access tokens, API keys, or full PostgreSQL connection strings.
- Require human review before production rollout of legal-risk workflows.
- For GDPR and EU AI Act expectations, preserve data minimization, retention/deletion controls, user transparency, traceable operational logging, and human oversight for legal outputs.

## 1. Confirm Sudo Access

Codex needs non-interactive sudo to install packages and configure services. If this check fails, perform the console step below.

From the Windows workstation:

```powershell
ssh -o BatchMode=yes jurisdigta-server "sudo -n true && echo SUDO_READY"
```

Expected output:

```text
SUDO_READY
```

If the command reports that interactive authentication is required, run this once in an interactive server console or interactive SSH session:

```bash
sudo usermod -aG sudo jurisdigta-admin
echo 'jurisdigta-admin ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/jurisdigta-admin-codex
sudo chmod 440 /etc/sudoers.d/jurisdigta-admin-codex
```

Rollback for passwordless sudo:

```bash
sudo rm -f /etc/sudoers.d/jurisdigta-admin-codex
```

## 2. Install Base Packages

Install operating-system packages required for repository checkout, containers, PostgreSQL administration, reverse proxy, and TLS.

Preferred repeatable path:

```bash
cd /srv/jurisdigta/app
bash Deployment/server/setup_jurisdigta_server.sh
```

Set `INSTALL_CLOUDFLARED=1` when the same run should also install `cloudflared`:

```bash
INSTALL_CLOUDFLARED=1 bash Deployment/server/setup_jurisdigta_server.sh
```

Manual equivalent:

```bash
sudo apt update
sudo apt install -y \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  git \
  unzip \
  jq \
  rsync \
  ufw \
  nginx \
  certbot \
  python3-certbot-nginx \
  python3 \
  python3-venv \
  python3-pip \
  postgresql-client \
  apt-transport-https \
  software-properties-common
```

## 3. Install Docker Engine And Compose

Use Docker for the API image, laws collector image, and local PostgreSQL with `pgvector`.

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

. /etc/os-release
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker jurisdigta-admin
sudo systemctl enable --now docker
```

After group membership changes, reconnect SSH before running Docker without `sudo`.

Validate:

```bash
docker --version
docker compose version
docker run --rm hello-world
```

## 4. Install Node.js And GitHub CLI

Node.js is needed for frontend/system build paths. GitHub CLI is useful for authenticated repository and workflow operations.

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
  sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | \
  sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null

sudo apt update
sudo apt install -y gh
```

Validate:

```bash
node --version
npm --version
gh --version
```

GitHub authentication must be done by an operator. Do not paste tokens into shell history. Prefer device/browser auth:

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth status
```

Required scopes when project automation is used later:

```bash
gh auth refresh -s read:project,project
```

## 4a. Install Ollama Local Model Service

Install Ollama as a separate local model service for free-plan traffic and paid fallback routing. Do not load large model files directly inside the API process for normal production traffic; the API should stay lightweight and call the local model service through the model router.

The self-managed production deployment script runs this step by default with `INSTALL_OLLAMA=1`. It installs Ollama when missing, keeps it bound to a private host interface, pulls the default free-plan model `qwen3:1.7b`, and validates both `/api/tags` and `/v1/models`. For Docker production, the script binds Ollama to the API Docker network gateway and stores that private URL in the `local_ollama` provider row, because `127.0.0.1` inside the API container is not the host. The API model router stores the exact free-plan model in `ai_model_profiles`, so later local model changes should be made in the database/admin route setup after the model is pulled and validated.

Install from a trusted server shell and review the installer before production use:

```bash
curl -fsSL https://ollama.com/install.sh -o /tmp/install-ollama.sh
less /tmp/install-ollama.sh
sh /tmp/install-ollama.sh
```

Bind Ollama to a private host interface only. The deployment script computes the
API Docker network gateway and writes it as `OLLAMA_HOST`; manual setups can use
`127.0.0.1:11434` only when every local caller runs on the host network:

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
cat <<'EOF' | sudo tee /etc/systemd/system/ollama.service.d/jurisdigta-localhost.conf >/dev/null
[Service]
Environment="OLLAMA_HOST=<private-host-or-docker-gateway-ip>:11434"
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
sudo systemctl restart ollama
```

Pull the configured local model:

```bash
ollama pull qwen3:1.7b
ollama list
ollama ps
```

If `qwen3:1.7b` does not fit the server hardware, pull and configure a smaller validated fallback model rather than changing free-plan routing to a paid cloud provider.

Validate the service:

```bash
systemctl is-active --quiet ollama
curl -fsS http://<private-host-or-docker-gateway-ip>:11434/api/tags
curl -fsS http://<private-host-or-docker-gateway-ip>:11434/v1/models
```

Security rule: do not expose port `11434` through Cloudflare Tunnel, nginx, router NAT, or public firewall rules. Only the API/model-router should call Ollama on localhost or the private Docker server network.

## 5. Prepare Deployment Directories

Use `/srv/jurisdigta` as the server deployment root and keep runtime data out of Git.

```bash
sudo mkdir -p /srv/jurisdigta
sudo chown -R jurisdigta-admin:jurisdigta-admin /srv/jurisdigta
mkdir -p /srv/jurisdigta/runs/storage/api/postgres/data
mkdir -p /srv/jurisdigta/runs/storage/laws-collector/postgres/data
mkdir -p /srv/jurisdigta/runs/logs
mkdir -p /srv/jurisdigta/secrets
chmod 700 /srv/jurisdigta/secrets
```

## 6. Clone Or Update From GitHub

Clone the repository once:

```bash
cd /srv/jurisdigta
git clone https://github.com/mmaideveloper/aijurisdictionagents.git app
cd /srv/jurisdigta/app
git status --short --branch
```

Update an existing checkout:

```bash
cd /srv/jurisdigta/app
git fetch --all --prune
git checkout main
git pull --ff-only origin main
```

## 7. Configure Server Environment

Create a server-local environment file from the repository example and edit it manually.

```bash
cd /srv/jurisdigta/app
cp .env.example /srv/jurisdigta/secrets/jurisdigta.env
chmod 600 /srv/jurisdigta/secrets/jurisdigta.env
nano /srv/jurisdigta/secrets/jurisdigta.env
```

Minimum deployment values to decide before production:

- `AI_MODEL_CREDENTIAL_ENCRYPTION_KEY` as a long random secret for encrypted database model credentials.
- `JURISDIGTA_ADMIN_API_KEY` for protected `/v1/admin/ai-models` management endpoints.
- Ollama installed on localhost or the private Docker gateway with `qwen3:1.7b` pulled for the seeded free/default route.
- API database route `local_ollama_default` mapped to exact model `qwen3:1.7b`.
- API database route `azure_foundry_gpt_4o_mini` mapped to exact Azure Foundry deployment/model `gpt-4o-mini`.
- Azure Foundry provider endpoint stored in `ai_model_providers.base_url`.
- Azure Foundry API key or token stored encrypted in `ai_model_credentials`.
- `AZURE_OPENAI_EMBEDDINGS_MODEL`
- `AZURE_OPENAI_API_VERSION`
- `DB_OPTION=postgres`
- `LAWS_DB_BACKEND=postgres`
- Strong PostgreSQL usernames and passwords.
- Public origins and domain values for `jurisdigta.eu`, `www.jurisdigta.eu`, `api.jurisdigta.eu`, `web.jurisdigta.eu`, `services.jurisdigta.eu`, and `admin.jurisdigta.eu` when those hosts are routed to this server.

Do not switch production-like starts to `mock` just because a database route is incomplete. If model routing is incomplete, stop and report the exact missing provider, profile, endpoint, or encrypted credential setup.

## 8. PostgreSQL Deployment Option

The repository already contains a Docker Compose stack for API plus PostgreSQL at:

```text
api/aijuristiction-api/docker-compose.yml
```

For the first server deployment, prefer Docker PostgreSQL using `pgvector/pgvector:pg16`, because that matches the repository local PostgreSQL path and keeps runtime files under `runs/storage/`.

Minimal API/PostgreSQL smoke start:

```bash
cd /srv/jurisdigta/app/api/aijuristiction-api
docker compose --env-file /srv/jurisdigta/secrets/jurisdigta.env up -d postgres
docker compose --env-file /srv/jurisdigta/secrets/jurisdigta.env ps
```

Validate PostgreSQL:

```bash
docker exec aijurisdiction-postgres pg_isready -U postgres -d aijurisdiction
```

The laws collector uses a separate logical database by default, usually `laws_sk`. Create it before running laws collector migrations if the deployment does not create it automatically:

```bash
docker exec -it aijurisdiction-postgres psql -U postgres -d aijurisdiction -c "CREATE DATABASE laws_sk;"
docker exec -it aijurisdiction-postgres psql -U postgres -d laws_sk -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

## 9. API Deployment Smoke Start

After PostgreSQL is healthy, start the API container from the repository Compose file:

```bash
cd /srv/jurisdigta/app/api/aijuristiction-api
docker compose --env-file /srv/jurisdigta/secrets/jurisdigta.env up -d --build api
docker compose --env-file /srv/jurisdigta/secrets/jurisdigta.env ps
```

Minimal runnable validation example:

```bash
curl -fsS http://127.0.0.1:8080/health
```

Expected result is an HTTP 200 response. If the API fails during startup with missing Azure Foundry settings, add the missing `AZURE_OPENAI_*` values rather than silently changing to `mock`.

## 10. Laws Connector Preparation

The laws connector image is defined at:

```text
src/services/laws_collector/Dockerfile
```

Build the image from the repository root:

```bash
cd /srv/jurisdigta/app
docker build -t jurisdigta-laws-collector:local -f src/services/laws_collector/Dockerfile .
```

Run migrations for the laws PostgreSQL database before a long-running import:

```bash
docker run --rm \
  --network aijuristiction-api_default \
  --env-file /srv/jurisdigta/secrets/jurisdigta.env \
  -e LAWS_DB_BACKEND=postgres \
  -e LAWS_DB_CLOUD="postgresql://postgres:<password>@postgres:5432/laws_sk" \
  aijuristiction-api:local \
  python /workspace/scripts/databases/apply_laws_db_schema.py
```

Do not place the real password in shell history for production. Prefer deriving the connection string from the running `jurisdigta-api` container or loading it from `/srv/jurisdigta/secrets/jurisdigta.env` or a root-readable systemd environment file.

Production-style laws connector defaults:

- Use PostgreSQL.
- Use ZIP import/resume mode unless a smoke test or fixture was explicitly requested.
- Continue from stored collector state instead of replaying completed ZIP imports.
- Preserve collector state and logs for auditability.

### Laws Collector Deployment Update Steps

Use this sequence whenever deploying a new laws collector image or changing the daily collector cron wrapper on `jurisdigta-server`.

1. Check the current collector state:

```bash
docker ps -a --filter name=jurisdigta-laws-collector-daily --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
tail -n 80 /srv/jurisdigta/runs/logs/laws-collector-daily-latest.log 2>/dev/null || true
```

2. Gracefully stop any active laws collector run before rebuilding or replacing the wrapper:

```bash
if docker ps --filter name=jurisdigta-laws-collector-daily --format '{{.Names}}' | grep -qx jurisdigta-laws-collector-daily; then
  docker stop --time 120 jurisdigta-laws-collector-daily
fi
```

The `--time 120` grace period gives the Python worker time to receive `SIGTERM`, close database work, and let Docker stop the container cleanly. Do not start a second collector while the first one is still running; the wrapper also uses `flock`, but deployment should still stop the container explicitly before image rebuilds.

3. If the container did not stop after the grace period, inspect logs before forcing cleanup:

```bash
docker logs --tail 200 jurisdigta-laws-collector-daily 2>/dev/null || true
docker rm -f jurisdigta-laws-collector-daily
```

Use forced removal only after the graceful stop fails or the container is already stuck. Record the failure in the deployment notes because interrupted collector runs may leave the next law cursor unchanged for retry.

4. Update the repository and rebuild the collector image:

```bash
cd /srv/jurisdigta/app
git fetch --all --prune
git checkout main
git pull --ff-only origin main
docker build -t jurisdigta-laws-collector:local -f src/services/laws_collector/Dockerfile .
```

5. Apply laws schema migrations before the first run after deployment:

```bash
docker run --rm \
  --network aijuristiction-api_default \
  --env-file /srv/jurisdigta/secrets/jurisdigta.env \
  -e LAWS_DB_BACKEND=postgres \
  -e LAWS_DB_CLOUD="$(docker inspect jurisdigta-api --format '{{range .Config.Env}}{{println .}}{{end}}' | awk -F= '$1=="LAWS_DB_CLOUD" {sub(/^LAWS_DB_CLOUD=/, ""); print; exit}')" \
  aijuristiction-api:local \
  python /workspace/scripts/databases/apply_laws_db_schema.py
```

The production deployment script runs API and laws migrations inside the
`aijuristiction-api:local` Docker image. Do not create a host Python virtual
environment for migrations on Ubuntu 26.04; the default host Python can be
newer than third-party OCR wheels support, while the API image uses the
supported Python runtime.

6. Validate with a bounded live run:

```bash
LAWS_WORKER_MAX_PROBES=1 LAWS_COLLECTOR_MAX_RUNNING_TIME=5 /srv/jurisdigta/ops/run_laws_collector_daily.sh
tail -n 80 /srv/jurisdigta/runs/logs/laws-collector-daily-latest.log
```

Expected result is either one imported sequential law or `No new laws for SK`, followed by a clean worker stop message.

## 11. Cloudflare Tunnel, Reverse Proxy, And Firewall

For production deployments without a static public IP, use Cloudflare Tunnel as
the public edge for `jurisdigta.eu` subdomains. The tunnel replaces the older
public-IP/NAT/Certbot path for normal public access: Cloudflare terminates
public HTTPS and `cloudflared` connects outbound from `jurisdigta-server`.

Install `cloudflared` on `jurisdigta-server`:

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | \
  sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | \
  sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update
sudo apt-get install -y cloudflared
```

Create the tunnel in Cloudflare Zero Trust, then run the generated service
install command directly on the server. Do not paste tunnel tokens into chat,
issue trackers, shell history committed to Git, or documentation:

```bash
sudo cloudflared service install <fresh-cloudflare-tunnel-token>
sudo systemctl status cloudflared --no-pager
```

Configure these Cloudflare Tunnel public hostnames:

| Hostname | Tunnel service | Current server target | Notes |
| --- | --- | --- | --- |
| `api.jurisdigta.eu` | HTTP | `http://127.0.0.1:8080` | API container; validate with `/health`. |
| `mcp.jurisdigta.eu` | HTTP | `http://127.0.0.1:8070` | Dedicated MCP service; metadata is under `/.well-known/oauth-protected-resource/mcp`. |
| `admin.jurisdigta.eu` | HTTP | `http://127.0.0.1:3000` | Grafana path is `/grafana/`; protect with Cloudflare Access. |
| `web.jurisdigta.eu` | HTTP | `http://127.0.0.1:8090` after web deployment | Frontend web container `jurisdigta-web`; validate with `/health`. |
| `agent.jurisdigta.eu` | HTTP | `http://127.0.0.1:8090` after web deployment | Authenticated assistant route `/app/assistant`; current production uses JurisDigta account login against the API users table. |
| `www.jurisdigta.eu` | HTTP | `http://127.0.0.1:8090` after web deployment | Optional alias for the public web app. |
| `jurisdigta.eu` | HTTP | `http://127.0.0.1:8090` after web deployment | Optional root domain for the public web app. |

Minimal runnable validation examples:

```bash
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8070/health
curl -I http://127.0.0.1:8070/.well-known/oauth-protected-resource/mcp
docker inspect -f '{{.State.Running}}' jurisdigta-email-scheduler
docker image inspect jurisdigta-document-processor:local >/dev/null
test -x /srv/jurisdigta/ops/run_document_processor.sh
curl -I http://127.0.0.1:3000/grafana/
curl -fsS http://127.0.0.1:8090/health
sudo systemctl status cloudflared --no-pager
```

External validation after Cloudflare DNS and tunnel hostname routing are active:

```bash
curl -fsS https://api.jurisdigta.eu/health
curl -fsS https://web.jurisdigta.eu/health
curl -fsS https://agent.jurisdigta.eu/health
curl -I https://agent.jurisdigta.eu/app/assistant
curl -I https://mcp.jurisdigta.eu/.well-known/oauth-protected-resource/mcp
curl -I https://admin.jurisdigta.eu/grafana/
```

Protect `admin.jurisdigta.eu` with Cloudflare Access before using it from the
public internet. Allow only named operator emails, require MFA where available,
and keep Grafana's own login enabled with a strong password. Do not publish
Prometheus, PostgreSQL, Node Exporter, cAdvisor, Blackbox Exporter, or status
exporter ports. Keep `agent.jurisdigta.eu` behind JurisDigta account login before
legal users access `/app/assistant`; the frontend route is not a substitute for
backend-managed identity and Assistant Gateway authorization.

For a local LAN smoke deployment, expose only SSH and nginx:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx HTTP'
sudo ufw enable
sudo ufw status verbose
```

Keep direct PostgreSQL access closed unless there is a documented operational need. Prefer local-only container networking for PostgreSQL.

If a future static-IP deployment intentionally bypasses Cloudflare Tunnel, use
nginx plus Certbot only after DNS points at the server and inbound TCP `80` and
`443` are intentionally reachable. That fallback is not the preferred path for
the current no-static-IP production environment.

## 12. Service Management

For production, wrap Docker Compose or standalone containers with systemd units after the smoke deployment is validated. Recommended units:

- `jurisdigta-api.service`
- `jurisdigta-email-scheduler.service`
- `jurisdigta-document-processor.timer`
- `jurisdigta-laws-collector.service` or `jurisdigta-laws-collector.timer`
- optional `jurisdigta-system.service` for system/orchestration processes that are not part of the API container

Each unit should:

- use `/srv/jurisdigta/app` as working directory,
- load environment from `/srv/jurisdigta/secrets/jurisdigta.env`,
- restart on failure with backoff,
- write logs to journald,
- run under `jurisdigta-admin` or a narrower service account.

The production deployment script starts `jurisdigta-email-scheduler` as a single
long-running Docker container from the API image. It reads the same PostgreSQL
API database as API/MCP through `EMAIL_DB_OPTION=postgres` and
`EMAIL_DB_CLOUD`, then delivers queued `email_outbox` messages through the
configured `EMAIL_TRANSPORT`. For real verification-code delivery, the
server-local `/srv/jurisdigta/secrets/jurisdigta.env` must use
`EMAIL_TRANSPORT=smtp` and include `EMAIL_SENDER`, `EMAIL_SMTP_HOST`,
`EMAIL_SMTP_PORT`, `EMAIL_SMTP_USERNAME`, and `EMAIL_SMTP_PASSWORD`. The deploy
script fails before replacing containers when these production email delivery
settings are missing.

Inside the self-managed Docker network, API and MCP must use the container
hostname `postgres` for `EMAIL_DB_CLOUD`, not a server-local loopback value such
as `127.0.0.1`. This matters for MCP sign-up, login, and OAuth authorization
because those handlers enqueue OTP email from inside the API/MCP containers; a
bad email outbox URL can break those flows while the normal database health
check still reports healthy.

Privacy-safe OTP delivery validation:

```bash
docker ps --filter name=jurisdigta-email-scheduler
docker logs --tail 50 jurisdigta-email-scheduler
docker exec aijurisdiction-postgres psql -U "${LOCAL_POSTGRES_USER:-postgres}" -d "${LOCAL_POSTGRES_DB:-aijurisdiction}" -c "SELECT recipient, subject, status, attempts, updated_at FROM email_outbox WHERE metadata_json::text LIKE '%mcp_sign_up_code%' ORDER BY created_at DESC LIMIT 5;"
```

Do not print or paste `email_outbox.body` for OTP messages; it contains the
verification code.

The production deployment script also builds
`jurisdigta-document-processor:local` and installs
`/srv/jurisdigta/ops/run_document_processor.sh` into cron. The API container is
started with `DOCUMENT_PROCESSOR_OPTION=azure`, so uploaded case documents stay
pending until the worker claims them. The worker uses the same API PostgreSQL
database and local file store under `/srv/jurisdigta/runs/storage/api/files`.

Default self-managed document processor settings:

- `INSTALL_DOCUMENT_PROCESSOR_CRON=1`
- `DOCUMENT_PROCESSOR_CRON_EXPRESSION=*/15 * * * *`
- `DOCUMENT_PROCESSOR_LIMIT=20`
- `DOCUMENT_PROCESSOR_MAX_RUNNING_TIME=15` from the server-local env file when set

Document processor validation:

```bash
docker image inspect jurisdigta-document-processor:local >/dev/null
test -x /srv/jurisdigta/ops/run_document_processor.sh
crontab -l | grep run_document_processor.sh
/srv/jurisdigta/ops/run_document_processor.sh
tail -n 80 /srv/jurisdigta/runs/logs/document-processor-latest.log
```

The document processor logs stable document IDs, case IDs, filenames, extraction
methods, counts, and compact errors. Do not add logging of uploaded document
contents, extracted text, embeddings, API keys, or raw database connection
strings.

For the current self-managed server maintenance path, the default production mode is a continuously running Docker container. `LAWS_COLLECTOR_RUN_MODE=continuous` starts `jurisdigta-laws-collector` with `--restart unless-stopped`, keeps `LAWS_WORKER_MAX_CYCLES=0`, sets `LAWS_COLLECTOR_MAX_RUNNING_TIME=0`, and sleeps for `LAWS_WORKER_POLL_SECONDS=3600` after the collector reaches the current Slov-Lex tail.

The court-decision collector runs as a separate restartable worker container named `jurisdigta-court-decision-collector`. The production deploy creates the dedicated PostgreSQL database `${COURT_DECISIONS_DATABASE_NAME:-court_decisions_sk}`, applies `databases/court-decision-collector/initdb/001_schema.sql`, injects `COURT_DECISIONS_DB_CLOUD` into API/MCP, and starts:

```bash
python -m services.court_decision_collector --run-service --limit "${COURT_DECISIONS_IMPORT_LIMIT:-25}" --log-file /workspace/runs/logs/court-decision-collector.log
```

The worker keeps polling after it reaches the current source tail and writes privacy-safe progress lines to `/srv/jurisdigta/runs/logs/court-decision-collector.log`.

The legacy scheduled mode is still available with `LAWS_COLLECTOR_RUN_MODE=scheduled`. In that mode, a daily user cron entry can run the already-built laws collector image against the existing PostgreSQL container. The server-local wrapper is:

```text
/srv/jurisdigta/ops/run_laws_collector_daily.sh
```

It should:

- load shared runtime secrets from `/srv/jurisdigta/secrets/jurisdigta.env`,
- derive `LAWS_DB_CLOUD` from the running `jurisdigta-api` container instead of writing the database password into crontab,
- run `jurisdigta-laws-collector:local` on Docker network `aijuristiction-api_default`,
- set `LAWS_COLLECTOR_RUN_MODE=scheduled`, `LAWS_WORKER_FIXTURE=live`, `LAWS_WORKER_MAX_CYCLES=1`, and a bounded `LAWS_WORKER_MAX_PROBES`,
- mount `/srv/jurisdigta/runs` for logs/runtime files,
- mount `/srv/jurisdigta/app/archivelaws` and `/srv/jurisdigta/app/aimodels` so archive files and the local embedding model cache persist between cron runs,
- use `flock` to prevent overlapping collector executions,
- write logs under `/srv/jurisdigta/runs/logs/` and update `laws-collector-daily-latest.log`.

Daily cron schedule used on `jurisdigta-server`:

```cron
15 2 * * * /srv/jurisdigta/ops/run_laws_collector_daily.sh >/dev/null 2>&1
```

The schedule uses the server timezone. On the verified Ubuntu server this was UTC.

For near-real-time API/system/laws collector status, install the status writer cron documented in `docs/SYSTEM_STATUS_MONITORING.md`. It writes safe host/container status to:

```text
/srv/jurisdigta/runs/status/system-status.json
```

The API reads that file through `SYSTEM_STATUS_FILE` and exposes the combined protected endpoint:

```text
GET /v1/system/status?minutes=60
```

## 13. Validation Checklist

Run these checks after package installation and smoke deployment:

```bash
hostname
docker --version
docker compose version
node --version
npm --version
python3 --version
psql --version
gh --version
sudo ufw status verbose
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:11434/api/tags
curl -fsS http://127.0.0.1:11434/v1/models
crontab -l
test -x /srv/jurisdigta/ops/run_laws_collector_daily.sh
LAWS_WORKER_MAX_PROBES=1 LAWS_COLLECTOR_MAX_RUNNING_TIME=5 /srv/jurisdigta/ops/run_laws_collector_daily.sh
tail -n 80 /srv/jurisdigta/runs/logs/laws-collector-daily-latest.log
docker ps --filter name=jurisdigta-court-decision-collector
tail -n 80 /srv/jurisdigta/runs/logs/court-decision-collector.log
docker exec aijurisdiction-postgres psql -U "${LOCAL_POSTGRES_USER:-postgres}" -d "${COURT_DECISIONS_DATABASE_NAME:-court_decisions_sk}" -c "SELECT count(*) AS versions, count(embedding_vector) AS versions_with_vector FROM court_decision_versions;"
python3 /srv/jurisdigta/app/scripts/server/write_system_status.py --output /srv/jurisdigta/runs/status/system-status.json
curl -fsS -H "x-api-key: ${API_KEY:-aijuris}" "http://127.0.0.1:8080/v1/system/status?minutes=60"
```

Production GitHub deployment validation:

```text
GitHub Actions -> Self-Managed Prod Deploy -> Run workflow -> repo_ref=main
```

The workflow should complete the local server checks for:

```bash
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8070/health
curl -fsS http://127.0.0.1:8090/health
```

Then validate public Cloudflare Tunnel routing externally:

```bash
curl -fsS https://api.jurisdigta.eu/health
curl -I https://mcp.jurisdigta.eu/.well-known/oauth-protected-resource/mcp
curl -fsS https://web.jurisdigta.eu/health
```

Repository validation:

```bash
cd /srv/jurisdigta/app
git status --short --branch
python examples/minimal_demo.py
```

The repository minimal runnable example remains:

```bash
python examples/minimal_demo.py
```

## 14. Rollback

Stop containers:

```bash
cd /srv/jurisdigta/app/api/aijuristiction-api
docker compose --env-file /srv/jurisdigta/secrets/jurisdigta.env down
```

Preserve database volumes before deletion:

```bash
sudo tar -czf /srv/jurisdigta/runs/storage/postgres-backup-$(date +%Y%m%d%H%M%S).tar.gz /srv/jurisdigta/app/runs/storage
```

Remove deployment checkout only after backups are validated:

```bash
rm -rf /srv/jurisdigta/app
```

Remove package-level changes only if the server is being decommissioned:

```bash
sudo apt remove -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin gh nginx certbot
sudo rm -f /etc/sudoers.d/jurisdigta-admin-codex
```

## 15. Open Items Before Production

- Decide whether this self-managed server is test, production, or both.
- Confirm Cloudflare nameserver delegation, Cloudflare Tunnel public hostnames, and Cloudflare Access policies for protected `jurisdigta.eu` subdomains.
- Decide whether PostgreSQL stays as Docker `pgvector/pgvector:pg16` or moves to managed PostgreSQL.
- Create systemd unit files after the first smoke deployment proves the exact runtime command.
- Define backup retention for PostgreSQL and uploaded/generated documents.
- Confirm legal output human-oversight process before opening production traffic.

## 16. Executed Setup Log 2026-06-14

This section records the actual installation and restore performed on `jurisdigta-server` so the deployment can be audited or repeated.

### Server And Access

- SSH alias: `jurisdigta-server`
- Hostname: `jurisdigta-server`
- Deployment user: `jurisdigta-admin`
- OS: Ubuntu 26.04 LTS
- Deployment root: `/srv/jurisdigta`
- Repository checkout: `/srv/jurisdigta/app`
- Server environment file: `/srv/jurisdigta/secrets/jurisdigta.env`
- Runtime storage root: `/srv/jurisdigta/runs`
- Rollback backup root: `/srv/jurisdigta/rollback-backups`

Non-interactive sudo was enabled for Codex automation through:

```text
/etc/sudoers.d/jurisdigta-admin-codex
```

Rollback:

```bash
sudo rm -f /etc/sudoers.d/jurisdigta-admin-codex
```

### Installed Packages

Ubuntu repository packages installed or confirmed:

```bash
sudo apt update
sudo DEBIAN_FRONTEND=noninteractive apt install -y \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  git \
  unzip \
  jq \
  rsync \
  ufw \
  nginx \
  certbot \
  python3-certbot-nginx \
  python3 \
  python3-venv \
  python3-pip \
  postgresql-client \
  apt-transport-https \
  software-properties-common \
  docker.io \
  docker-compose-v2 \
  docker-buildx \
  nodejs \
  npm \
  gh
```

Docker was enabled and the deployment user was added to the `docker` group:

```bash
sudo systemctl enable --now docker
sudo usermod -aG docker jurisdigta-admin
```

Actual verified versions after installation:

```text
Docker version 29.1.3, build 29.1.3-0ubuntu4.1
Docker Compose version 2.40.3+ds1-0ubuntu1
docker buildx 0.30.1-0ubuntu1
Node.js v22.22.1
npm 9.2.0
Python 3.14.4
pip 25.1.1
psql PostgreSQL client 18.4
gh 2.46.0
nginx 1.28.3
certbot 4.0.0
unzip 6.00
jq 1.8.1
git 2.53.0
curl 8.18.0
rsync 3.4.1
ufw 0.36.2
```

### Docker DNS Fix

During image build, containers could not resolve `deb.debian.org`. Docker DNS was fixed with:

```json
{"dns":["1.1.1.1","8.8.8.8"]}
```

File:

```text
/etc/docker/daemon.json
```

Then Docker was restarted:

```bash
sudo systemctl reset-failed docker
sudo systemctl start docker
```

Validation:

```bash
docker run --rm debian:trixie-slim getent hosts deb.debian.org
```

### Deployment Directories

Created:

```bash
sudo mkdir -p /srv/jurisdigta/runs/storage/api/postgres/data
sudo mkdir -p /srv/jurisdigta/runs/storage/laws-collector/postgres/data
sudo mkdir -p /srv/jurisdigta/runs/logs
sudo mkdir -p /srv/jurisdigta/secrets
sudo chown -R jurisdigta-admin:jurisdigta-admin /srv/jurisdigta
chmod 700 /srv/jurisdigta/secrets
```

The repository `runs` path was linked to server runtime storage:

```bash
cd /srv/jurisdigta/app
ln -s /srv/jurisdigta/runs runs
```

The local workstation `.env` was copied to:

```text
/srv/jurisdigta/secrets/jurisdigta.env
```

Permissions:

```bash
chmod 600 /srv/jurisdigta/secrets/jurisdigta.env
```

### Repository And Images

Repository clone:

```bash
cd /srv/jurisdigta
git clone https://github.com/mmaideveloper/aijurisdictionagents.git app
cd /srv/jurisdigta/app
git checkout main
```

Verified commit at setup time:

```text
fe0d49b Migration Postress full databasse
```

Built images:

```bash
cd /srv/jurisdigta/app/api/aijuristiction-api
docker compose --env-file /srv/jurisdigta/secrets/jurisdigta.env build api

cd /srv/jurisdigta/app
docker build -t jurisdigta-laws-collector:local -f src/services/laws_collector/Dockerfile .
```

Images present after build:

```text
aijuristiction-api:local
jurisdigta-laws-collector:local
pgvector/pgvector:pg16
```

### PostgreSQL Setup

Started PostgreSQL through repository Compose:

```bash
cd /srv/jurisdigta/app/api/aijuristiction-api
docker compose --env-file /srv/jurisdigta/secrets/jurisdigta.env up -d postgres
```

Container:

```text
aijurisdiction-postgres
```

Image:

```text
pgvector/pgvector:pg16
```

Databases created or verified:

```text
aijurisdiction
aijurisdiction-dev
laws_sk
```

The `vector` extension was enabled in `laws_sk`.

API schema migrations were applied to `aijurisdiction-dev`:

```text
0001_create_api_metadata.sql
0002_case_document_embeddings.sql
0003_permanent_memory.sql
```

Laws schema migrations were applied to `laws_sk`:

```text
0001_create_laws_schema.sql
0002_add_collector_progress.sql
0003_enable_real_law_embeddings.sql
0004_add_law_metadata_tables.sql
0005_add_collector_import_state.sql
0006_add_archive_import_assets.sql
0007_add_source_artifact_storage_references.sql
```

### Laws Database Backup And Restore

The first USB backup found at:

```text
/mnt/usb/jurisdigtra/laws-collector-postgres/20260613-150831/laws_sk-20260613-150831.dump
```

had a readable table of contents but failed a full restore with:

```text
pg_restore: error: could not read from input file: end of file
```

A fresh complete dump was generated from the local workstation container:

```text
aijurisdiction-laws-collector-postgres-local
```

Source database:

```text
laws_sk
```

Fresh dump path on the workstation:

```text
runs/storage/postgres-transfers/20260614-133355/laws_sk-20260614-133355.dump
```

Fresh dump size:

```text
3,278,340,843 bytes
```

SHA-256:

```text
60fa273d2bd237c2c2d503e0c920f90154bc15b2c8c17911f6a00fb67bfebbf4
```

The same verified dump was copied to the USB on the workstation:

```text
D:\jurisdigta\laws-collector-postgres\20260614-133355\laws_sk-20260614-133355.dump
D:\jurisdigta\laws-collector-postgres\20260614-133355\SHA256SUMS.txt
D:\jurisdigta\laws-collector-postgres\20260614-133355\backup-info-20260614-133355.txt
```

The dump was transferred to the server:

```text
/srv/jurisdigta/laws_sk-20260614-133355.dump
```

Before restore, a rollback dump was created:

```text
/srv/jurisdigta/rollback-backups/laws_sk-server-before-complete-restore-20260614-114657.dump
```

Restore command pattern:

```bash
docker cp /srv/jurisdigta/laws_sk-20260614-133355.dump aijurisdiction-postgres:/tmp/laws_sk-complete-restore.dump
docker exec aijurisdiction-postgres pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  -U postgres \
  -d laws_sk \
  /tmp/laws_sk-complete-restore.dump
```

Post-restore counts:

```text
law_documents_count: 25732
law_versions_count: 72107
law_metadata_count: 72105
law_provisions_count: 16639141
versions_with_embeddings: 72107
total_versions: 72107
```

### API Runtime

Started API container:

```bash
docker run -d \
  --name jurisdigta-api \
  --restart unless-stopped \
  --network aijuristiction-api_default \
  -p 8080:8080 \
  --env-file /srv/jurisdigta/secrets/jurisdigta.env \
  -e DB_OPTION=postgres \
  -e DB_CLOUD="postgresql://postgres:postgres@postgres:5432/aijurisdiction-dev" \
  -e DB_LOCAL=/workspace/runs/storage/api/sqlite/api.sqlite3 \
  -e STORAGE_OPTION=local \
  -e STORE_LOCAL=/workspace/runs/storage/api/files \
  -e LAWS_COUNTRY=SK \
  -e LAWS_DB_BACKEND=postgres \
  -e LAWS_DB_CLOUD="postgresql://postgres:postgres@postgres:5432/laws_sk" \
  -v /srv/jurisdigta/runs:/workspace/runs \
  aijuristiction-api:local
```

Current containers after validation:

```text
jurisdigta-api: aijuristiction-api:local, port 8080, healthy
aijurisdiction-postgres: pgvector/pgvector:pg16, port 5432, healthy
```

Health check:

```bash
curl -fsS http://127.0.0.1:8080/health
```

Result:

```json
{"status":"ok","llm":{"status":"ok","provider":"model_routing"},"database":{"status":"ok","backend":"postgres"}}
```

### Laws Collector Daily Cron

Installed a daily `jurisdigta-admin` crontab entry:

```cron
15 2 * * * /srv/jurisdigta/ops/run_laws_collector_daily.sh >/dev/null 2>&1
```

The wrapper script:

```text
/srv/jurisdigta/ops/run_laws_collector_daily.sh
```

Run behavior:

- Starts `jurisdigta-laws-collector:local` as an ephemeral Docker container named `jurisdigta-laws-collector-daily`.
- Uses Docker network `aijuristiction-api_default` so the collector can reach PostgreSQL at the existing `postgres` network alias.
- Reads shared secrets from `/srv/jurisdigta/secrets/jurisdigta.env`.
- Reads the active `LAWS_DB_CLOUD` value from the running `jurisdigta-api` container at execution time, avoiding a separate plaintext database connection string in cron or the wrapper.
- Sets `LAWS_COUNTRY=SK`, `LAWS_DB_BACKEND=postgres`, `LAWS_WORKER_FIXTURE=live`, `LAWS_COLLECTOR_RUN_MODE=scheduled`, `LAWS_WORKER_MAX_CYCLES=1`, `LAWS_WORKER_MAX_PROBES=25`, `LAWS_WORKER_POLL_SECONDS=3600`, and `LAWS_COLLECTOR_IMPORT=zip`.
- Mounts `/srv/jurisdigta/runs` to `/workspace/runs`, `/srv/jurisdigta/app/archivelaws` to `/app/archivelaws`, and `/srv/jurisdigta/app/aimodels` to `/app/aimodels`.
- Uses `/srv/jurisdigta/runs/locks/laws-collector-daily.lock` with `flock` so overlapping daily runs exit without starting another collector.
- Writes timestamped logs under `/srv/jurisdigta/runs/logs/` and maintains `/srv/jurisdigta/runs/logs/laws-collector-daily-latest.log`.

Validation performed on 2026-06-14:

```bash
LAWS_WORKER_MAX_PROBES=1 LAWS_COLLECTOR_MAX_RUNNING_TIME=5 /srv/jurisdigta/ops/run_laws_collector_daily.sh
```

Observed result:

```text
[laws-collector] zip-import zip import skipped because live sequential cursor is active ...
[laws-collector] start processing country=SK law=121/2026 ...
[laws-collector] 121/2026 does not exists, system imports all laws and is up to date
[laws-collector] No new laws for SK, last processed law 120/2026 ...
[laws-collector] worker stopped because laws collector is up to date last_processed_law=120/2026 next_law_to_check=121/2026
```

Rollback:

```bash
crontab -l | grep -v 'run_laws_collector_daily.sh' | crontab -
docker stop --time 120 jurisdigta-laws-collector 2>/dev/null || true
docker rm -f jurisdigta-laws-collector 2>/dev/null || true
docker stop --time 120 jurisdigta-laws-collector-daily 2>/dev/null || true
docker rm -f jurisdigta-laws-collector-daily 2>/dev/null || true
rm -f /srv/jurisdigta/ops/run_laws_collector_daily.sh
```

### Compliance Notes From Execution

- Secrets were stored in `/srv/jurisdigta/secrets/jurisdigta.env` with `600` permissions.
- Full secret values are not documented in this runbook.
- The laws backup contains legal corpus data and embeddings; keep it under controlled storage and define retention/deletion policy.
- The restore created a rollback backup before replacing `laws_sk`.
- Logs and validation output record aggregate counts only, not legal document contents.
- API was started with database-backed model routing; chat provider/model/deployment came from the API database routing tables, not `.env`.
- The daily laws collector cron reuses server-local secrets and logs only operational collector status, not full database connection strings or legal-risk user outputs.

## Prometheus And Grafana Monitoring

Recommended dashboard stack:

```text
Deployment/monitoring/
```

Use this stack when you want a real-time UI for `jurisdigta-server`, API, PostgreSQL, Docker containers, laws collector status, error counts, and latest laws import state.

Components:

- Prometheus: metrics storage and alert rule evaluation.
- Grafana: dashboard and alert UI.
- Node Exporter: Linux host CPU, memory, disk, filesystem, and kernel metrics.
- cAdvisor: Docker container CPU, memory, filesystem, and restart metrics.
- Blackbox Exporter: API availability probes.
- Monitoring containers join `MONITORING_APP_DOCKER_NETWORK`, defaulting to `aijuristiction-api_default`, so API and MCP are probed by container name while their host ports stay bound to `127.0.0.1`.
- `scripts/server/export_system_status_metrics.py`: converts `GET /v1/system/status?minutes=60` into Prometheus text metrics, including API-ledger token/cost windows for 1h, 24h, 7d, and 30d.
- `scripts/server/export_ollama_metrics.py`: exports localhost-only Ollama health, model inventory, loaded model, and VRAM gauges.
- `scripts/server/write_system_status.py`: records aggregate API/MCP request counts, average/max request latency, total users, new users, total cases, and new cases without exposing personal data or legal case content in Prometheus labels.
- `Deployment/monitoring/prometheus-rules/jurisdigta-ai-models.yml`: evaluates Ollama red-state alerts and paid-model token/cost spike alerts.

Start the JurisDigta status exporter:

```bash
cd /srv/jurisdigta/app
API_KEY="${API_KEY:-aijuris}" \
python3 scripts/server/export_system_status_metrics.py \
  --host 127.0.0.1 \
  --port 9108 \
  --status-url "http://127.0.0.1:8080/v1/system/status?minutes=60"
```

For production use, install it as systemd service `jurisdigta-status-exporter.service` using `Deployment/monitoring/README.md`.

Configure and start Prometheus and Grafana:

```bash
cd /srv/jurisdigta/app/Deployment/monitoring
python3 configure_monitoring.py --validate --start
```

Use `--reset-grafana-password` as well when `GRAFANA_ADMIN_PASSWORD` changed
after Grafana was already initialized.

Validate:

```bash
curl -fsS http://127.0.0.1:9108/metrics | head
curl -fsS http://127.0.0.1:9091/-/ready
curl -fsS http://127.0.0.1:3000/grafana/api/health
docker compose ps
cd /srv/jurisdigta/app && PROMETHEUS_BASE_URL=http://127.0.0.1:9091 python3 examples/monitoring_scrape_demo.py
curl -fsS 'http://127.0.0.1:9091/api/v1/query?query=jurisdigta_users_total'
curl -fsS 'http://127.0.0.1:9091/api/v1/query?query=jurisdigta_http_requests_total_window'
curl -fsS 'http://127.0.0.1:9091/api/v1/query?query=jurisdigta_ai_model_total_tokens_window'
curl -fsS 'http://127.0.0.1:9091/api/v1/query?query=jurisdigta_ai_model_top_case_total_tokens_window'
curl -fsS 'http://127.0.0.1:9091/api/v1/rules'
```

Access Grafana by SSH tunnel first:

```bash
ssh -L 3000:127.0.0.1:3000 jurisdigta-server
```

Then open:

```text
http://127.0.0.1:3000
```

For mobile access in the current no-static-IP production setup, use Grafana
through Cloudflare Tunnel and Cloudflare Access at:

```text
https://admin.jurisdigta.eu/grafana/
```

Cloudflare Tunnel should route:

```text
admin.jurisdigta.eu -> http://127.0.0.1:3000
```

Before enabling this URL:

- Confirm `cloudflared.service` is active.
- Configure `admin.jurisdigta.eu` as a public hostname on the Cloudflare Tunnel.
- Protect `admin.jurisdigta.eu` with Cloudflare Access for approved operator identities.
- Keep Grafana bound only to `127.0.0.1:3000`.

Do not expose Grafana or Prometheus container ports directly to the internet.
Public mobile access must go through Cloudflare Access and Grafana login.
Use the nginx template `Deployment/monitoring/nginx-admin-grafana.conf` only
as a future static-IP/NAT fallback.

## Frontend Web Container

The self-managed server hosts `frontend/aijurisdictionfronend` as a static Vite
build served by nginx inside Docker. The container binds only to localhost on
port `8090`; public HTTPS should be provided by Cloudflare Tunnel.

Build and deploy:

```bash
cd /srv/jurisdigta/app/frontend/aijurisdictionfronend
docker build \
  --build-arg VITE_API_BASE_URL=https://api.jurisdigta.eu \
  --build-arg "VITE_CHAT_MODEL_LABEL=Azure Foundry model" \
  -t jurisdigta-web:local .
docker rm -f jurisdigta-web 2>/dev/null || true
docker run -d \
  --name jurisdigta-web \
  --restart unless-stopped \
  -p 127.0.0.1:8090:80 \
  jurisdigta-web:local
```

Validate:

```bash
curl -fsS http://127.0.0.1:8090/health
curl -I http://127.0.0.1:8090/
curl -I http://127.0.0.1:8090/app/assistant
curl -I http://127.0.0.1:8090/privacy
docker ps --filter name=jurisdigta-web
```

Rollback:

```bash
docker rm -f jurisdigta-web
docker image rm jurisdigta-web:local
```

Revoke GitHub self-managed deployment access:

```bash
nano /home/jurisdigta-admin/.ssh/authorized_keys
```

Remove the deploy-only public key line, then delete or rotate the `JURISDIGTA_SSH_PRIVATE_KEY` GitHub Environment secret.

Compliance notes:

- The frontend build embeds only public browser configuration. Do not embed
  secrets in `VITE_*` variables.
- Keep the API responsible for consent, retention/deletion controls, traceable
  legal-risk logging, and human-oversight safeguards.
- Keep the container bound to `127.0.0.1` and publish it through Cloudflare
  Tunnel rather than exposing Docker port `8090` directly to the internet.

If `cloudflared.service` is installed with `Type=notify` and repeatedly fails
startup with `timeout` even though connectivity prechecks pass, use a systemd
drop-in so systemd treats `cloudflared tunnel run` as a regular long-running
process:

```bash
sudo mkdir -p /etc/systemd/system/cloudflared.service.d
cat <<'EOF' | sudo tee /etc/systemd/system/cloudflared.service.d/override.conf >/dev/null
[Service]
Type=simple
TimeoutStartSec=120
EOF
sudo systemctl daemon-reload
sudo systemctl restart cloudflared
```

Rollback:

```bash
sudo systemctl disable --now jurisdigta-status-exporter.service
cd /srv/jurisdigta/app/Deployment/monitoring
docker compose down
```
