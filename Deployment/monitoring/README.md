# JurisDigta Prometheus And Grafana Monitoring

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
- Last processed law, next law to check, latest laws collector run timestamps, and latest run duration.
- Email sent counts, email queue counts, and aggregate email send duration from the outbox.
- Document processor queue counts, processed document counts, latest run duration, and aggregate processing duration.
- Host CPU, memory, disk, filesystem, and kernel metrics through Node Exporter.
- Docker container CPU, memory, filesystem, and restart behavior through cAdvisor.
- Prometheus health and scrape status.

## Security Baseline

- Grafana and Prometheus bind only to `127.0.0.1` by default.
- Monitoring containers join the existing API Docker network through `MONITORING_APP_DOCKER_NETWORK`, defaulting to `aijuristiction-api_default`, so API and MCP host ports can remain bound to `127.0.0.1`.
- Access Grafana through SSH tunneling first:

```bash
ssh -L 3000:127.0.0.1:3000 jurisdigta-server
```

Then open:

```text
http://127.0.0.1:3000
```

- Do not expose ports `3000`, `9090`, `9100`, `9108`, or `9115` directly to the public internet.
- If Grafana must be reachable through `admin.jurisdigta.eu`, publish it through Cloudflare Tunnel and protect it with Cloudflare Access plus Grafana login.
- Keep dashboard panels operational only. Do not display user chat text, generated legal documents, API keys, database connection strings, or legal-risk user outputs.
- Email and document processor panels must stay aggregate-only: queue counts, sent/processed counts, and timing gauges. Do not add recipients, filenames, case titles, extracted document text, verification codes, embeddings, or raw connection strings as labels.

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

## Start Prometheus And Grafana

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

Prometheus can be tunneled the same way when needed:

```bash
ssh -L 9091:127.0.0.1:9091 jurisdigta-server
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
- Do not publish Prometheus, Node Exporter, cAdvisor, Blackbox Exporter, or status exporter ports.
- Use Cloudflare Access for operator identity control before production use.
- Do not display personal data, legal documents, chat contents, API keys, SMTP passwords, or database connection strings on dashboards.

## Provisioned Grafana Dashboards

Prometheus is provisioned automatically as a Grafana data source:

```text
http://prometheus:9090
```

Grafana loads JurisDigta dashboards from `grafana/dashboards` into the
`JurisDigta` folder:

- `JurisDigta Server Performance`: CPU, RAM, disk, load, network, disk I/O, and container memory.
- `JurisDigta Application Performance`: API/MCP/web/Grafana HTTP probes, component status, email queue/sent/time, document queue/processed/time, laws processing cursor and runtime, and application error counts.
- `JurisDigta Laws Collector`: execution time, imported laws per latest run, processed entries/documents, and recent sanitized collector errors.
- `JurisDigta Errors`: total errors, error telemetry status, error counts by source, HTTP probe status codes, and scrape target health.

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
- `jurisdigta_laws_next_number`
- `jurisdigta_laws_runtime_last_run_started_at_timestamp_seconds`
- `jurisdigta_laws_runtime_last_run_finished_at_timestamp_seconds`
- `jurisdigta_laws_runtime_duration_seconds`
- `jurisdigta_laws_runtime_imported_laws`
- `jurisdigta_laws_runtime_entries_processed`
- `jurisdigta_laws_runtime_processed`
- `jurisdigta_laws_recent_error_info`
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
- `up{job="node-exporter"}`
- `up{job="cadvisor"}`

Suggested alert rules:

- Overall JurisDigta status below `1` for more than 5 minutes.
- API blackbox probe failure for more than 2 minutes.
- Any `jurisdigta_errors_window` above `0` for 10 minutes.
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
docker volume rm monitoring_prometheus-data monitoring_grafana-data
```

Stop and remove the exporter service:

```bash
sudo systemctl disable --now jurisdigta-status-exporter.service
sudo rm -f /etc/systemd/system/jurisdigta-status-exporter.service
sudo systemctl daemon-reload
```
