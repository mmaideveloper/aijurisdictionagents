# JurisDigta Prometheus, Loki, Alloy, And Grafana Monitoring

This stack is the recommended self-managed monitoring layer for `jurisdigta-server`.

It complements the protected API endpoint documented in `docs/SYSTEM_STATUS_MONITORING.md`:

```text
GET /v1/system/status?minutes=60
```

## What It Monitors

- API and MCP availability through Blackbox Exporter probing the internal Docker service URLs `http://jurisdigta-api:8080/health` and `http://jurisdigta-mcp:8070/health`.
- API and MCP request counts plus average/max request latency from privacy-minimized Docker log aggregation.
- Aggregate user and case totals plus new users/cases in one-hour and 24-hour windows from PostgreSQL counts.
- API/database/LLM/system/email scheduler/document processor/laws collector status through `scripts/server/export_system_status_metrics.py`.
- Error counts for API, laws collector, and PostgreSQL from the status endpoint.
- Total imported laws over time, last imported law number/year, next law to check, latest laws collector run timestamps, and latest run duration.
- Email sent counts, email queue counts, and aggregate email send duration from the outbox.
- Document processor queue counts, processed document counts, latest run duration, and aggregate processing duration.
- Court-decision collector status, imported decision/version counts, embedding-vector coverage, worker activity counts, activity timestamps, and sanitized recent errors.
- AI model token and cost telemetry: input tokens, cached input tokens, output tokens, total tokens, estimated EUR cost, request count, and fallback count by provider, model, task type, plan, route type, route class, and 1h/24h/7d/30d window.
- Host CPU, memory, disk, filesystem, and kernel metrics through Node Exporter.
- Docker container CPU, memory, filesystem, and restart behavior through cAdvisor.
- Prometheus health and scrape status.
- Docker stdout/stderr logs and server job log files through Grafana Alloy and Loki.
- Provisioned AI model usage panels in `JurisDigta Application Performance` for aggregate status, cost, requests by route, input/output/total tokens by model, and top cost by plan/task/provider/model route.
- Provisioned masked top-10 case token panels in `JurisDigta Ollama And AI Models` for Grafana-only operational triage.

## Security Baseline

- Grafana, Prometheus, Loki, and Alloy bind only to `127.0.0.1` by default.
- Monitoring containers join the existing API Docker network through `MONITORING_APP_DOCKER_NETWORK`, defaulting to `aijuristiction-api_default`, so API and MCP host ports can remain bound to `127.0.0.1`.
- Access Grafana through SSH tunneling first:

```bash
ssh -L 3000:127.0.0.1:3000 jurisdigta-server
```

Then open:

```text
http://127.0.0.1:3000
```

- Do not expose ports `3000`, `9090`, `9100`, `9108`, `9115`, `3100`, or `12345` directly to the public internet.
- If Grafana must be reachable through `admin.jurisdigta.eu`, publish it through Cloudflare Tunnel and protect it with Cloudflare Access plus Grafana login.
- Keep dashboard panels operational only. Do not display user chat text, generated legal documents, API keys, database connection strings, or legal-risk user outputs.
- Email and document processor panels must stay aggregate-only: queue counts, sent/processed counts, and timing gauges. Do not add recipients, filenames, case titles, extracted document text, verification codes, embeddings, or raw connection strings as labels.
- Court-decision panels must stay aggregate-only: status, counts, timestamps, and sanitized operational errors. Do not add raw decision text, party names, file content, source URLs, source GUIDs, ECLI values, file numbers, prompts, retrieved snippets, embeddings, or personal data as labels or table fields.
- Shared AI model panels must stay aggregate-only. Allowed labels include categories such as plan code, provider, model, task type, route type, route class, status, fallback reason, and window. Do not add raw case IDs, user IDs, subscription IDs, prompts, answers, document text, filenames, party names, citations, emails, phone numbers, addresses, or other legal-case facts as metric labels. The top-case Grafana panel uses masked `case_ref` values only.

## AI Model Token And Cost Monitoring

Model routing must emit or export Prometheus-compatible metrics for input and
output token usage per model/route, plus a masked top-case operational view. The
source of truth is the API usage ledger; Prometheus/Grafana reads aggregate
counters/gauges derived from that ledger rather than raw prompts, documents, or
raw user/case identifiers.

Required ledger fields for every model call:

- `user_id`
- `subscription_id`
- `plan_code`
- `case_id`
- `task_type`
- `model_group_id`
- `provider`
- `model`
- `route_type`
- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `total_tokens`
- `estimated_cost_provider_currency`
- `estimated_cost_eur`
- `provider_currency`
- `exchange_rate_used`
- `request_started_at`
- `request_completed_at`
- `latency_ms`
- `status`
- `fallback_reason`
- `confidentiality_warning_ack_id`

Current metric names:

- `jurisdigta_ai_model_requests_window`
- `jurisdigta_ai_model_input_tokens_window`
- `jurisdigta_ai_model_cached_input_tokens_window`
- `jurisdigta_ai_model_output_tokens_window`
- `jurisdigta_ai_model_total_tokens_window`
- `jurisdigta_ai_model_estimated_cost_eur_window`
- `jurisdigta_ai_model_top_case_requests_window`
- `jurisdigta_ai_model_top_case_total_tokens_window`
- `jurisdigta_ai_model_top_case_estimated_cost_eur_window`

Recommended labels:

- `provider`
- `model`
- `task_type`
- `route_type`
- `route_class`
- `plan_code`
- `case_ref` only on masked top-case metrics
- `status`
- `fallback_reason`
- `window_minutes`

Provisioned Grafana panels:

- AI model usage status
- AI model cost in the current status window
- AI model requests by task, provider, model, route type, route class, and status
- local/Ollama and paid-model total tokens by provider/model/route
- masked top 10 cases by token volume and estimated cost
- input, cached input, output, and total tokens by model
- top AI model cost by plan, task, provider, model, and route type

Case-level drill-down remains limited to masked top-case Grafana rows. Raw
case/user/subscription identifiers stay in the API usage ledger and case audit
APIs, not in shared Prometheus labels.
- total tokens by model and task type
- estimated EUR cost by model for the selected case
- model cost per user over hour/day/month windows
- top models by output-token cost
- paid budget remaining per active case/subscription
- local versus external model traffic share
- fallback count by reason and model
- latency by provider/model

`1M output tokens` in provider pricing means one million generated tokens. For document workflows, this is the legal text, clauses, summaries, structured fields, or JSON the model generates before the document renderer creates DOCX/PDF. Rendering a PDF from already-generated text does not create provider output-token cost unless another model call is made.

## Logs

Use Grafana Loki for troubleshooting logs. Prometheus remains the metrics and
alerting store; it is not the right backend for stack traces or raw log lines.
Grafana Alloy collects:

- Docker stdout/stderr from containers named `jurisdigta-*`.
- Server-side job logs from `runs/logs/*.log`, including document processor and laws collector wrapper logs.

Default retention:

```text
LOG_RETENTION_DAYS=7
LOKI_RETENTION_DAYS=7
PROMETHEUS_RETENTION_DAYS=30
DOCKER_LOG_MAX_SIZE=50m
DOCKER_LOG_MAX_FILE=5
```

`LOG_RETENTION_DAYS` controls cleanup for files under `/srv/jurisdigta/runs/logs`.
`LOKI_RETENTION_DAYS` controls queryable Loki log retention. Docker raw
`json-file` logs are capped by size through `DOCKER_LOG_MAX_SIZE` and
`DOCKER_LOG_MAX_FILE`; Loki is the intended operational log store.

For current development debugging, set application verbosity in the
server-local env file:

```text
API_LOG_LEVEL=DEBUG
LOG_LEVEL=DEBUG
```

Do not intentionally log plaintext access tokens, OTP codes, SMTP passwords,
private keys, or full database URLs. If a temporary incident requires unusually
verbose payload logging, keep access limited to Grafana behind Cloudflare
Access, lower retention, and remove the setting after the incident. Audit trail
events for legal actions should be a separate structured event store, not the
debug log stream.

Useful Grafana Explore queries:

```logql
{stack="jurisdigta"} |= "ERROR"
{stack="jurisdigta", container="jurisdigta-api"}
{stack="jurisdigta", service="jurisdigta-job-log"} |= "failed"
```

The provisioned `JurisDigta System Logs` dashboard is the normal operator view
for logs. It reads from Loki and provides:

- `Source` filter for API, MCP, web, document engine, email scheduler,
  Grafana, Prometheus, Loki, Alloy, status exporter, and server job log files.
- `Level` filter for all logs, errors, warnings, info, or debug lines.
- `Stream` filter for Docker `stdout`/`stderr`.
- `Search Regex` textbox for incident-specific text matching.
- Panels for log rate by source, error events by source, recent logs, and
  errors only.

Because current application logs are mostly unstructured, the severity filter is
text-based. Prefer structured log levels in new application code so this
dashboard can later filter on a real `level` label instead of matching message
text.

## JurisDigta Metrics Exporter

By default, Docker Compose starts `status-exporter` as a private container and Prometheus scrapes it at:

```text
http://status-exporter:9108/metrics
```

The Compose-managed exporter calls the API through the shared Docker network:

```text
http://jurisdigta-api:8080/v1/system/status?minutes=60
```

For manual troubleshooting, run the exporter on the server host:

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

## Ollama Metrics Exporter

Self-managed production also starts `ollama-exporter` when the monitoring stack is enabled. It runs with host networking and reads Ollama through `LOCAL_LLM_BASE_URL` in `Deployment/monitoring/.env`. `configure_monitoring.py` derives that value from `OLLAMA_HOST_BIND`, an already non-loopback `LOCAL_LLM_BASE_URL`, or the `MONITORING_APP_DOCKER_NETWORK` gateway. This keeps the exporter aligned with Docker production, where Ollama is bound to the private API Docker gateway instead of `127.0.0.1`.

When Docker gateway detection is unavailable, the fallback remains:

```text
http://127.0.0.1:11434
```

Prometheus scrapes it at:

```text
http://host.docker.internal:9109/metrics
```

Validate the exporter target on the server:

```bash
grep '^LOCAL_LLM_BASE_URL=' /srv/jurisdigta/app/Deployment/monitoring/.env
curl -fsS "$(grep '^LOCAL_LLM_BASE_URL=' /srv/jurisdigta/app/Deployment/monitoring/.env | cut -d= -f2-)/api/tags" >/dev/null
curl -fsS http://127.0.0.1:9109/metrics | grep jurisdigta_ollama_up
curl -fsS 'http://127.0.0.1:9091/api/v1/query?query=jurisdigta_ollama_up'
```

Keep host port `9109` blocked from public ingress the same way as Prometheus, Grafana, and the status exporter. It is only for the private Prometheus scrape path.

The exporter emits privacy-preserving runtime metrics only:

- `jurisdigta_ollama_up`
- `jurisdigta_ollama_probe_duration_seconds`
- `jurisdigta_ollama_configured_model_present`
- `jurisdigta_ollama_models_total`
- `jurisdigta_ollama_running_models_total`
- `jurisdigta_ollama_model_size_bytes`
- `jurisdigta_ollama_running_model_vram_bytes`
- `jurisdigta_ollama_running_model_expires_timestamp_seconds`

It does not send prompts, legal documents, model responses, or case facts to Prometheus.

Optional fallback systemd unit:

```ini
[Unit]
Description=JurisDigta system status Prometheus exporter
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/srv/jurisdigta/app
EnvironmentFile=/srv/jurisdigta/secrets/jurisdigta.env
ExecStart=/usr/bin/python3 /srv/jurisdigta/app/scripts/server/export_system_status_metrics.py --host 127.0.0.1 --port 9108 --status-url http://127.0.0.1:8080/v1/system/status?minutes=60
Restart=always
RestartSec=10
User=jurisdigta-admin
Group=jurisdigta-admin

[Install]
WantedBy=multi-user.target
```

Install only if you choose to run the exporter outside Docker Compose:

```bash
sudo tee /etc/systemd/system/jurisdigta-status-exporter.service >/dev/null <<'EOF'
[Unit]
Description=JurisDigta system status Prometheus exporter
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/srv/jurisdigta/app
EnvironmentFile=/srv/jurisdigta/secrets/jurisdigta.env
ExecStart=/usr/bin/python3 /srv/jurisdigta/app/scripts/server/export_system_status_metrics.py --host 127.0.0.1 --port 9108 --status-url http://127.0.0.1:8080/v1/system/status?minutes=60
Restart=always
RestartSec=10
User=jurisdigta-admin
Group=jurisdigta-admin

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now jurisdigta-status-exporter.service
systemctl status jurisdigta-status-exporter.service --no-pager
```

## Start Prometheus, Loki, Alloy, And Grafana

Create or update server-local Prometheus/Grafana settings:

```bash
cd /srv/jurisdigta/app/Deployment/monitoring
python3 configure_monitoring.py --validate --start
```

The script reads `/srv/jurisdigta/secrets/jurisdigta.env`, writes
`Deployment/monitoring/.env` with file mode `600`, validates dashboard JSON and
Compose config, then starts the stack. It carries `JURISDIGTA_API_KEY` from
`JURISDIGTA_API_KEY` or `API_KEY` so the status exporter can authenticate to
`/v1/system/status`. The status exporter also mounts `../../runs` read-only so
laws collector runtime details can be merged from `SYSTEM_STATUS_FILE` when the
API image does not expose those fields yet. It preserves an existing
`GRAFANA_ADMIN_PASSWORD` unless the project env provides one. It also writes
`MONITORING_APP_DOCKER_NETWORK`, defaulting to `aijuristiction-api_default`,
so status-exporter and Blackbox Exporter can resolve `jurisdigta-api` and
`jurisdigta-mcp` without opening API/MCP host bindings beyond loopback. It
sets `GRAFANA_DEFAULT_HOME_DASHBOARD_PATH` to the provisioned JurisDigta
Application Performance dashboard so that dashboard is the default view after
login, and applies the same `homeDashboardUID` through Grafana org preferences
after stack startup.

If `GRAFANA_ADMIN_PASSWORD` changed after Grafana was already initialized,
also reset the persisted Grafana admin password:

```bash
python3 configure_monitoring.py --validate --start --reset-grafana-password
```

Validate:

```bash
docker compose ps
curl -fsS http://127.0.0.1:9091/-/ready
curl -fsS http://127.0.0.1:3000/grafana/api/health
python3 ../../examples/monitoring_scrape_demo.py
```

## Access Grafana

### From The Server

The stack binds Grafana to `127.0.0.1:3000`, so it is reachable directly from the server:

```bash
curl -fsS http://127.0.0.1:3000/api/health
```

If the server has a desktop/browser session, open:

```text
http://127.0.0.1:3000
```

If the server is headless, use the remote SSH tunnel flow below.

### Remotely From Your Workstation

Open an SSH tunnel:

```bash
ssh -L 3000:127.0.0.1:3000 jurisdigta-server
```

Then open this on your workstation:

```text
http://127.0.0.1:3000
```

Prometheus and Loki can be tunneled the same way when needed:

```bash
ssh -L 9091:127.0.0.1:9091 jurisdigta-server
ssh -L 3100:127.0.0.1:3100 jurisdigta-server
```

Then open:

```text
http://127.0.0.1:9091
```

### From Mobile Over Public HTTPS

For the current no-static-IP production server, use Cloudflare Tunnel rather
than public-IP DNS, router port forwarding, and Certbot. Use this public route
only after Cloudflare Access protects the hostname.

Target mobile URL:

```text
https://admin.jurisdigta.eu/grafana/
```

Cloudflare Tunnel public hostname:

```text
Hostname: admin.jurisdigta.eu
Service type: HTTP
Service URL: http://127.0.0.1:3000
```

Prerequisites:

- `cloudflared.service` must be active on `jurisdigta-server`.
- `admin.jurisdigta.eu` must be configured as a public hostname on the Cloudflare Tunnel.
- Cloudflare Access must allow only approved operator identities before Grafana is used publicly.
- Grafana must stay bound to `127.0.0.1:3000`; do not expose container port `3000` publicly.

Current expected Grafana settings in `Deployment/monitoring/.env`:

```text
GRAFANA_SERVER_DOMAIN=admin.jurisdigta.eu
GRAFANA_ROOT_URL=https://admin.jurisdigta.eu/grafana/
GRAFANA_SERVE_FROM_SUB_PATH=true
```

After changing these values:

```bash
cd /srv/jurisdigta/app/Deployment/monitoring
docker compose up -d --force-recreate grafana
```

Validate from outside the server network:

```bash
curl -I https://admin.jurisdigta.eu/grafana/
```

### Reset Grafana Login

Grafana stores the admin password in its persistent database after the first
startup. Updating `GRAFANA_ADMIN_PASSWORD` in `Deployment/monitoring/.env` does
not change the password for an existing `grafana-data` volume. If login fails
with the documented credentials, reset the admin password from the running
container after loading it from the server-local secret file:

```bash
cd /srv/jurisdigta/app/Deployment/monitoring
set -a
. ./.env
set +a
docker exec jurisdigta-grafana grafana cli admin reset-admin-password "$GRAFANA_ADMIN_PASSWORD"
curl -fsS http://127.0.0.1:3000/grafana/api/health
```

Keep the reset command out of shell history when operating a shared terminal.
The preferred repeatable flow is:

```bash
cd /srv/jurisdigta/app/Deployment/monitoring
python3 configure_monitoring.py --validate --start --reset-grafana-password
```

The nginx template `Deployment/monitoring/nginx-admin-grafana.conf` remains a
static-IP fallback only. Use it only when `admin.jurisdigta.eu` intentionally
resolves to the server or NAT endpoint and inbound TCP `80` and `443` are open:

```bash
sudo cp /srv/jurisdigta/app/Deployment/monitoring/nginx-admin-grafana.conf \
  /etc/nginx/sites-available/jurisdigta-admin-grafana.conf
sudo ln -sf /etc/nginx/sites-available/jurisdigta-admin-grafana.conf \
  /etc/nginx/sites-enabled/jurisdigta-admin-grafana.conf
sudo nginx -t
sudo certbot --nginx -d admin.jurisdigta.eu
sudo nginx -t
sudo systemctl reload nginx
```

Security notes:

- Keep Grafana's own login enabled with a strong password.
- Do not publish Prometheus, Loki, Alloy, Node Exporter, cAdvisor, Blackbox Exporter, or status exporter ports.
- Use Cloudflare Access for operator identity control before production use.
- Do not display personal data, legal documents, chat contents, API keys, SMTP passwords, or database connection strings on dashboards.

## Provisioned Grafana Dashboards

Prometheus is provisioned automatically as a Grafana data source:

```text
http://prometheus:9090
```

Loki is provisioned automatically as a Grafana data source:

```text
http://loki:3100
```

Grafana loads JurisDigta dashboards from `grafana/dashboards` into the
`JurisDigta` folder:

- `JurisDigta Server Performance`: CPU, RAM, disk, load, network, disk I/O, and container memory.
- `JurisDigta Application Performance`: API/MCP/web/Grafana HTTP probes, component status, email queue/sent/time, document queue/processed/time, laws processing cursor and runtime, and application error counts.
- `JurisDigta Ollama And AI Models`: Ollama API health, configured model presence, installed/running model counts, model size, loaded model VRAM, probe latency, local/Ollama tokens, paid-model tokens, requests, estimated cost, and masked top cases by token volume.
- `JurisDigta Laws Collector`: total imported laws over time, latest imported law number/year, execution time, imported laws per latest run, processed entries/documents, and recent sanitized collector errors.
- `JurisDigta Court Decision Service`: collector status, imported decisions, stored versions, versions with embeddings, processing/processed/idle activity, storage totals, and recent sanitized collector errors.
- `JurisDigta Errors`: total errors, error telemetry status, error counts by source, HTTP probe status codes, and scrape target health.
- `JurisDigta System Logs`: Loki log stream with source, severity, stream, and regex search filters for Docker container logs and server job log files.

To create or update the dashboards on `jurisdigta-server`, commit the JSON file
under `Deployment/monitoring/grafana/dashboards`, deploy the repo, then run:

```bash
cd /srv/jurisdigta/app/Deployment/monitoring
python3 configure_monitoring.py --validate --start
```

Grafana reloads provisioned dashboards from `/var/lib/grafana/dashboards`
automatically. If the dashboard does not appear within about 30 seconds, restart
Grafana without exposing any monitoring ports publicly:

```bash
docker compose up -d --force-recreate grafana
```

The application dashboards use privacy-preserving aggregate metrics only. Do
not add panels that expose user chat text, generated legal documents, API keys,
database connection strings, SMTP passwords, raw legal-risk outputs, or raw
collector logs. The laws collector error table uses sanitized, truncated
operational log lines only.

Useful starter queries:

- `jurisdigta_component_status{component="overall"}`
- `jurisdigta_component_status{component="api"}`
- `jurisdigta_component_status{component="system"}`
- `jurisdigta_component_status{component="laws_collector"}`
- `jurisdigta_errors_window`
- `jurisdigta_laws_last_processed_number`
- `jurisdigta_laws_last_processed_year`
- `jurisdigta_laws_total{name="laws_imported"}`
- `jurisdigta_laws_next_number`
- `jurisdigta_laws_runtime_last_run_started_at_timestamp_seconds`
- `jurisdigta_laws_runtime_last_run_finished_at_timestamp_seconds`
- `jurisdigta_laws_runtime_duration_seconds`
- `jurisdigta_laws_runtime_imported_laws`
- `jurisdigta_laws_runtime_entries_processed`
- `jurisdigta_laws_runtime_processed`
- `jurisdigta_laws_recent_error_info`
- `jurisdigta_component_status{component="court_decision_collector"}`
- `jurisdigta_court_decisions_total{status="all"}`
- `jurisdigta_court_decisions_total{status="published"}`
- `jurisdigta_court_decision_versions_total`
- `jurisdigta_court_decision_versions_with_embeddings_total`
- `jurisdigta_court_decision_collector_events_total{event="processed"}`
- `jurisdigta_court_decision_collector_last_activity_timestamp_seconds`
- `jurisdigta_court_decision_latest_imported_timestamp_seconds`
- `jurisdigta_court_decision_recent_error_info`
- `jurisdigta_system_disk_used_percent`
- `jurisdigta_system_memory_used_percent`
- `probe_success{service="jurisdigta-api"}`
- `probe_success{service="jurisdigta-mcp"}`
- `jurisdigta_http_requests_total_window{service="api"}`
- `jurisdigta_http_request_duration_seconds_avg{service="api"}`
- `jurisdigta_http_request_duration_seconds_avg{service="mcp"}`
- `jurisdigta_users_total`
- `jurisdigta_users_new_window{window="24h"}`
- `jurisdigta_cases_total{state="active"}`
- `jurisdigta_cases_new_window{window="24h"}`
- `jurisdigta_email_sent_total`
- `jurisdigta_email_sent_window{window="24h"}`
- `jurisdigta_email_queue_total`
- `jurisdigta_email_send_duration_seconds_avg{window="24h"}`
- `jurisdigta_email_send_duration_seconds_max{window="24h"}`
- `jurisdigta_documents_processed_total`
- `jurisdigta_documents_processed_window{window="24h"}`
- `jurisdigta_document_processor_queue_total`
- `jurisdigta_document_processing_duration_seconds_avg{window="24h"}`
- `jurisdigta_document_processing_duration_seconds_max{window="24h"}`
- `jurisdigta_document_processor_last_run_duration_seconds`
- `jurisdigta_ai_model_input_tokens_window{provider="...",model="...",route_class="...",window_minutes="..."}`
- `jurisdigta_ai_model_cached_input_tokens_window{provider="...",model="...",route_class="...",window_minutes="..."}`
- `jurisdigta_ai_model_output_tokens_window{provider="...",model="...",route_class="...",window_minutes="..."}`
- `jurisdigta_ai_model_total_tokens_window{provider="...",model="...",route_class="...",window_minutes="..."}`
- `jurisdigta_ai_model_estimated_cost_eur_window{provider="...",model="...",route_class="...",window_minutes="..."}`
- `jurisdigta_ai_model_top_case_total_tokens_window{case_ref="case-....",route_class="...",window_minutes="..."}`
- `jurisdigta_ai_model_top_case_estimated_cost_eur_window{case_ref="case-....",route_class="...",window_minutes="..."}`
- `up{job="node-exporter"}`
- `up{job="cadvisor"}`

Suggested alert rules:

- Overall JurisDigta status below `1` for more than 5 minutes.
- API blackbox probe failure for more than 2 minutes.
- Any `jurisdigta_errors_window` above `0` for 10 minutes.
- Paid case model budget remaining below 10%.
- Ollama exporter/API down for more than 2 minutes.
- Configured Ollama model missing for more than 5 minutes.
- Paid-model token usage above 200,000 tokens in the 1h API-ledger window for more than 10 minutes.
- Paid-model estimated cost above 10 EUR in the 1h API-ledger window for more than 10 minutes.
- Disk used above 80%.
- Memory used above 85%.
- Laws collector last run older than 36 hours.

## Email Notifications

Grafana OSS requires SMTP settings before email notifications work. The compose file maps these Grafana variables from the server-local `Deployment/monitoring/.env`:

- `GRAFANA_SMTP_ENABLED`
- `GRAFANA_SMTP_HOST`
- `GRAFANA_SMTP_USER`
- `GRAFANA_SMTP_PASSWORD`
- `GRAFANA_SMTP_FROM_ADDRESS`
- `GRAFANA_SMTP_FROM_NAME`
- `GRAFANA_ALERT_EMAIL_TO`

The recommended setup script above reads existing project email settings from `/srv/jurisdigta/secrets/jurisdigta.env`:

- `EMAIL_SMTP_HOST`
- `EMAIL_SMTP_PORT`
- `EMAIL_SMTP_USERNAME`
- `EMAIL_SMTP_PASSWORD`
- `EMAIL_SENDER`

`GRAFANA_SMTP_STARTTLS_POLICY=OpportunisticStartTLS` means Grafana tries to upgrade SMTP to STARTTLS when the mail server supports it. This is a pragmatic default for port `587`. If the provider requires encrypted SMTP, change it to a stricter provider-supported policy and restart Grafana.

The `JurisDigta Email` contact point is provisioned automatically from `grafana/provisioning/alerting/contact-points.yml`. To test it:

1. Open Grafana.
2. Go to `Alerts & IRM` -> `Alerting` -> `Notification configuration` -> `Contact points`.
3. Open `JurisDigta Email`.
4. Click `Test`.

If `EMAIL_SMTP_PASSWORD` is missing, Grafana still starts, but email notifications remain disabled until the SMTP password is added to the server-local secret file and `Deployment/monitoring/.env` is regenerated.

## Azure Parity

For Azure-hosted services, keep Application Insights and Log Analytics as the system of record for application traces and request failures. Grafana can still be used in two ways:

- Azure Managed Grafana with Azure Monitor data source for Application Insights and Log Analytics.
- Prometheus-compatible metrics through Azure Monitor managed service for Prometheus if the app is later hosted on AKS or another Prometheus-scrapable runtime.

The self-managed server stack remains useful because it monitors the private server, Docker containers, and local laws collector cron that Azure Monitor cannot see directly unless an Azure agent is installed.

## Rollback

Stop the stack:

```bash
cd /srv/jurisdigta/app/Deployment/monitoring
docker compose down
```

Remove persistent monitoring data only after confirming it is not needed:

```bash
docker volume rm monitoring_prometheus-data monitoring_grafana-data monitoring_loki-data
```

Stop and remove the exporter service:

```bash
sudo systemctl disable --now jurisdigta-status-exporter.service
sudo rm -f /etc/systemd/system/jurisdigta-status-exporter.service
sudo systemctl daemon-reload
```
