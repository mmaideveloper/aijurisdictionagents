# System Status Monitoring

This runbook describes the near-real-time status view for API, system, and laws collector operations on `jurisdigta-server`, with the same telemetry model usable in Azure.

## Goal

Provide one protected status endpoint:

```text
GET /v1/system/status?minutes=60
```

The endpoint returns safe operational status only:

- API health, API version, core system version, database status, and LLM provider status.
- Host status from `jurisdigta-server`: disk, memory, Git commit, Docker container state.
- Laws collector status: total imported laws over time, last imported law number/year, next law to check, import state, totals, latest run duration.
- Error counts by application for the requested time window.

The endpoint requires the existing `x-api-key` header.

## Daily Stats API

Use the read-only daily stats endpoint for scheduled operational summaries:

```bash
curl -fsS \
  -H "Authorization: Bearer ${JURISDIGTA_DAILY_STATS_TOKEN}" \
  "https://api.jurisdigta.eu/v1/monitoring/daily-stats?window=24h"
```

The endpoint returns one row per monitored system with `status`,
`minutes_down`, `error_count`, and `notes`. Downtime minutes come from
Prometheus probe/component history when `PROMETHEUS_BASE_URL` is configured.
Error counts come from Application Insights when available, with local server
status as a limited fallback. If a historical source is unavailable, the field
is returned as `"unknown"` and the row notes explain which source is missing.

Set `JURISDIGTA_DAILY_STATS_TOKEN` in production to allow external scheduled
read-only checks without exposing Grafana, Prometheus, Loki, or server
credentials. If the token is unset, the endpoint falls back to the normal
`x-api-key` guard for local development.

## Compliance Baseline

- Do not expose API keys, database passwords, full connection strings, chat text, generated legal documents, user emails, or legal-risk user outputs.
- Status JSON must contain aggregate operational facts only.
- Logs can support traceability and human oversight, but monitoring payloads should stay minimal and redacted.
- The laws collector freshness status is an operational safeguard because stale legal corpus data can affect legal-risk outputs.

## Service Health Model

HTTP-serving services provide `GET /health` for lightweight readiness and
dependency checks. Worker and scheduler services use supervisor/container state,
freshness timestamps, latest run result, error counts, and sanitized logs through
this protected status model instead of public worker health endpoints. See
`docs/SERVICE_HEALTHCHECKS.md` for the reusable rule and the current service
contracts.

## Server Status Writer

On `jurisdigta-server`, write host/container status every minute:

```bash
cd /srv/jurisdigta/app
mkdir -p /srv/jurisdigta/runs/status
python3 scripts/server/write_system_status.py \
  --output /srv/jurisdigta/runs/status/system-status.json \
  --laws-log /srv/jurisdigta/runs/logs/laws-collector-daily-latest.log
```

The status writer reads only a bounded recent tail of runtime log files so long-lived collectors cannot exhaust memory, and the emitted payload remains aggregate and redacted.

Install the minute cron:

```bash
( crontab -l 2>/dev/null | grep -v 'write_system_status.py' || true; \
  echo '* * * * * cd /srv/jurisdigta/app && python3 scripts/server/write_system_status.py --output /srv/jurisdigta/runs/status/system-status.json --laws-log /srv/jurisdigta/runs/logs/laws-collector-daily-latest.log >/dev/null 2>&1' \
) | crontab -
```

Validate:

```bash
crontab -l | grep write_system_status.py
python3 /srv/jurisdigta/app/scripts/server/write_system_status.py \
  --output /srv/jurisdigta/runs/status/system-status.json \
  --laws-log /srv/jurisdigta/runs/logs/laws-collector-daily-latest.log
jq . /srv/jurisdigta/runs/status/system-status.json
```

## API Configuration

The API reads:

```text
SYSTEM_STATUS_FILE=./runs/status/system-status.json
```

On the current Docker deployment, `/srv/jurisdigta/runs` is mounted to `/workspace/runs`, so the default path resolves correctly inside the API container.

Query from the server:

```bash
curl -fsS \
  -H "x-api-key: ${API_KEY:-aijuris}" \
  "http://127.0.0.1:8080/v1/system/status?minutes=60" | jq .
```

Minimal runnable example:

```bash
API_BASE_URL=http://127.0.0.1:8080 API_KEY=aijuris python examples/system_status_demo.py
```

## Error Counts

When `APPLICATIONINSIGHTS_CONNECTION_STRING` and Log Analytics settings are configured, `/v1/system/status` returns error counts from Application Insights for:

- `api`
- `laws_collector`
- `document_processor`

When Azure telemetry is not configured, the endpoint falls back to local counts written by `scripts/server/write_system_status.py`.

## Prometheus, Loki, Alloy, And Grafana Dashboard

Recommended self-managed dashboard stack for `jurisdigta-server`:

- Prometheus for metrics storage and alert rule evaluation.
- Loki for queryable server-local troubleshooting logs.
- Grafana Alloy for Docker and local job log collection into Loki.
- Grafana for dashboards and alert visualization.
- Node Exporter for Linux host CPU, memory, disk, filesystem, and kernel metrics.
- cAdvisor for Docker container CPU, memory, filesystem, and restart behavior.
- Blackbox Exporter for HTTP availability probes. In Docker Compose it probes API and MCP through the internal service URLs `http://jurisdigta-api:8080/health` and `http://jurisdigta-mcp:8070/health` on `MONITORING_APP_DOCKER_NETWORK`, keeping host ports bound to loopback.
- `scripts/server/export_system_status_metrics.py` for JurisDigta-specific Prometheus metrics from `/v1/system/status`.
- `scripts/server/export_ollama_metrics.py` for localhost-only Ollama runtime health, model inventory, loaded model VRAM, and configured-model presence.
- `scripts/server/write_system_status.py` also records privacy-minimized aggregate request metrics from API/MCP Docker logs and aggregate PostgreSQL user/case counts. It does not persist request IDs, user IDs, case IDs, prompts, documents, or response bodies in Prometheus labels.
- Raw troubleshooting logs are available through Grafana Explore using the Loki data source. Loki retention defaults to `LOKI_RETENTION_DAYS=7`.

The protected AI Model Admin page can also list server-local Ollama inventory and start registry pull/remove jobs. Operators should use Grafana/Ollama metrics plus the Admin audit table to validate that a pull or remove succeeded. Physical removal is blocked while a model is the seeded/default local model or is referenced by active route policy, so a planned model replacement should first update routing, verify the new model, and then remove the old unused model.

Deployment assets are in:

```text
Deployment/monitoring/
```

Start the JurisDigta status exporter on the server:

```bash
cd /srv/jurisdigta/app
API_KEY="${API_KEY:-aijuris}" \
python3 scripts/server/export_system_status_metrics.py \
  --host 127.0.0.1 \
  --port 9108 \
  --status-url "http://127.0.0.1:8080/v1/system/status?minutes=60"
```

Validate:

```bash
curl -fsS http://127.0.0.1:9108/metrics | head
```

Start Prometheus, Loki, Alloy, and Grafana:

```bash
cd /srv/jurisdigta/app/Deployment/monitoring
# Create .env with GRAFANA_ADMIN_PASSWORD and SMTP settings from the server-local .env.
# See Deployment/monitoring/README.md for the full command.
docker compose up -d
```

The monitoring Compose stack expects the API/MCP Docker network to exist.
On the self-managed server this is normally `aijuristiction-api_default`,
created by the API PostgreSQL Compose project and reused by the API/MCP
containers. Override it with `MONITORING_APP_DOCKER_NETWORK` only if the
production API network name changes.

Access Grafana through an SSH tunnel first:

```bash
ssh -L 3000:127.0.0.1:3000 jurisdigta-server
```

Open:

```text
http://127.0.0.1:3000
```

From the server itself, validate Grafana with:

```bash
curl -fsS http://127.0.0.1:3000/api/health
```

If the server has a browser session, open `http://127.0.0.1:3000` locally. On a headless server, use the SSH tunnel flow above.

For mobile/public HTTPS access on the current no-static-IP production server,
publish only Grafana through Cloudflare Tunnel and protect it with Cloudflare
Access. Do not publish Prometheus, Loki, Alloy, exporters, or status exporter
directly:

```text
https://admin.jurisdigta.eu/grafana/
```

Cloudflare Tunnel hostname mapping:

```text
admin.jurisdigta.eu -> http://127.0.0.1:3000
```

Grafana is configured to serve from `/grafana/`, so validate the public route
with:

```bash
curl -I https://admin.jurisdigta.eu/grafana/
```

Validate Prometheus scrape and HTTP probe health with the minimal runnable
example:

```bash
cd /srv/jurisdigta/app
PROMETHEUS_BASE_URL=http://127.0.0.1:9091 python3 examples/monitoring_scrape_demo.py
```

The older nginx/Certbot template at `Deployment/monitoring/nginx-admin-grafana.conf`
is only a fallback for a future static-IP or NAT deployment where inbound TCP
`80` and `443` are intentionally opened.

Keep Grafana and Prometheus private by default. Do not expose ports `3000`,
`9090`, `9100`, `9108`, or `9115` directly to the public internet. If
`admin.jurisdigta.eu` is enabled, require Cloudflare Access before Grafana and
keep Grafana's own login enabled.

Useful Grafana panels:

- `jurisdigta_component_status{component="overall"}`
- `jurisdigta_component_status{component="api"}`
- `jurisdigta_component_status{component="system"}`
- `jurisdigta_component_status{component="ai_model_usage"}`
- `jurisdigta_component_status{component="laws_collector"}`
- `jurisdigta_errors_window`
- `jurisdigta_laws_last_processed_info`
- `jurisdigta_laws_last_processed_number`
- `jurisdigta_laws_last_processed_year`
- `jurisdigta_laws_total{name="laws_imported"}`
- `jurisdigta_laws_next_number`
- `jurisdigta_laws_runtime_last_run_started_at_timestamp_seconds`
- `jurisdigta_laws_runtime_last_run_finished_at_timestamp_seconds`
- `jurisdigta_laws_runtime_duration_seconds`
- `jurisdigta_system_disk_used_percent`
- `jurisdigta_system_memory_used_percent`
- `probe_success{service="jurisdigta-api"}`
- `jurisdigta_http_requests_total_window{service="api"}`
- `jurisdigta_http_request_duration_seconds_avg{service="api"}`
- `jurisdigta_users_total`
- `jurisdigta_users_new_window{window="24h"}`
- `jurisdigta_cases_total{state="active"}`
- `jurisdigta_cases_new_window{window="24h"}`
- `jurisdigta_ollama_up`
- `jurisdigta_ollama_configured_model_present`
- `jurisdigta_ollama_running_model_vram_bytes`
- `jurisdigta_ai_model_requests_window`
- `jurisdigta_ai_model_input_tokens_window`
- `jurisdigta_ai_model_cached_input_tokens_window`
- `jurisdigta_ai_model_output_tokens_window`
- `jurisdigta_ai_model_total_tokens_window`
- `jurisdigta_ai_model_estimated_cost_eur_window`
- `jurisdigta_ai_model_top_case_total_tokens_window`
- `jurisdigta_ai_model_top_case_estimated_cost_eur_window`

The provisioned `JurisDigta Application Performance` dashboard includes
aggregate AI model panels for usage status, EUR cost, requests by route, and
tokens by provider/model/route for 1h, 24h, 7d, and 30d windows. The provisioned
`JurisDigta Ollama And AI Models` dashboard also includes local/Ollama tokens,
paid-model tokens, and a masked top-10 case consumption table. Keep shared
dashboard queries aggregate-only. Raw case IDs, user IDs, subscription IDs,
prompts, answers, generated documents, filenames, emails, phone numbers,
addresses, or legal-case facts must not be added to Prometheus labels or
legends. Case-level Grafana triage must use the masked `case_ref` label only.
- `jurisdigta_ai_model_input_tokens_window`
- `jurisdigta_ai_model_output_tokens_window`
- `jurisdigta_ai_model_estimated_cost_eur_window`

Prometheus loads `Deployment/monitoring/prometheus-rules/jurisdigta-ai-models.yml`
for Ollama red-state and paid-model usage alerts. The initial thresholds are:
Ollama exporter/API down for 2 minutes, configured Ollama model missing for 5
minutes, paid-model tokens above 200,000 in the 1h API-ledger window for 10
minutes, and paid-model estimated cost above 10 EUR in the 1h API-ledger window
for 10 minutes.

Email notification setup:

- Grafana SMTP is configured from `Deployment/monitoring/.env`.
- The setup flow copies values from `/srv/jurisdigta/secrets/jurisdigta.env` keys `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`, `EMAIL_SMTP_USERNAME`, `EMAIL_SMTP_PASSWORD`, and `EMAIL_SENDER`.
- A provisioned `JurisDigta Email` contact point uses `GRAFANA_ALERT_EMAIL_TO`.
- If `EMAIL_SMTP_PASSWORD` is missing, the stack starts but email notification sending remains disabled until SMTP credentials are added.

## Azure Parity

Azure deployments already use Application Insights and Log Analytics for API and worker logs. Keep these settings aligned:

- `APPLICATIONINSIGHTS_CONNECTION_STRING`
- `AZURE_LOG_ANALYTICS_WORKSPACE_NAME`
- `AZURE_MANAGED_IDENTITY_NAME`
- `AZURE_RESOURCE_GROUP`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_CLIENT_ID`

On Azure, the host-level server status file is normally unavailable, but API/laws/document processor errors still come from Application Insights through the same endpoint.

For Azure-hosted dashboards, prefer Azure Managed Grafana connected to Azure Monitor/Application Insights. If the application is later moved to AKS or another Prometheus-scrapable runtime, Azure Monitor managed service for Prometheus can ingest equivalent metrics. The self-managed Prometheus/Grafana stack remains useful for `jurisdigta-server` because it observes local Docker containers, cron-driven collector state, and host resources.

## Rollback

Remove the server status cron:

```bash
crontab -l | grep -v 'write_system_status.py' | crontab -
rm -f /srv/jurisdigta/runs/status/system-status.json
```

The API remains functional if `SYSTEM_STATUS_FILE` is missing; `/v1/system/status` reports system status as `unknown` while still returning API and laws collector state.

Stop the Prometheus/Grafana stack:

```bash
cd /srv/jurisdigta/app/Deployment/monitoring
docker compose down
sudo systemctl disable --now jurisdigta-status-exporter.service
```
