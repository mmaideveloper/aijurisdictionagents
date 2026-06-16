# Manual Infrastructure Setup

This document tracks infrastructure setup that cannot be completed only by repository code, CI, or local scripts.

## Rule

Whenever a task adds or changes manual infrastructure requirements, update this file in the same change. Include:

- Provider or portal name.
- Required account or owner.
- Test and production environment steps.
- Secrets, environment variables, certificates, keys, callback URLs, domains, or app identifiers.
- Validation steps after setup.
- Rollback or deletion steps.
- GDPR and EU AI Act notes when personal data, legal-risk outputs, or user transparency are involved.

Do not commit real secrets, private keys, certificates, Firebase config files containing sensitive project data, or Apple credentials.

## Azure PostgreSQL Laws Collector Migration

Related runbook: `docs/AZURE_POSTGRES_MIGRATION.md`

Purpose: migrate the existing local PostgreSQL laws collector database into Azure PostgreSQL Flexible Server and run the laws collector as an Azure Container Apps Job that resumes from completed archive/monthly ZIP state, probes one sequential Slovak law per run, and exits when no new law exists.

### Provider And Owner

- Provider: Microsoft Azure.
- Required owner: repository Azure service principal from `.env`; do not use a personally signed-in Azure CLI account for repository Azure work.
- Target environments: `test` first, then `prod` after backup restore and job validation.

### Manual Setup Steps

1. Authenticate with `.\infra\scripts\login_service_principal.ps1 -EnvFilePath .env`.
2. Confirm Azure subscription, resource group, PostgreSQL Flexible Server, Container Apps environment, ACR, storage account, managed identity, and Application Insights names for the target environment.
3. Back up the local `laws_sk` PostgreSQL database with `pg_dump --format custom` into an ignored operator path such as `runs/storage/laws-collector/backups/`.
4. Create or select the Azure PostgreSQL Flexible Server and database named by `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK`.
5. Enable required database extensions, including `vector`, before restoring embeddings.
6. Restore the dump with `pg_restore --no-owner --no-privileges` using `sslmode=require`.
7. Apply current laws collector schema migrations with `scripts/databases/apply_laws_db_schema.py`.
8. Validate restored row counts, `collector_import_state`, and `collector_progress`.
9. Deploy `laws-collector` with `LAWS_COLLECTOR_IMPORT=zip`, live fixture, one worker cycle, `AZURE_LAWS_COLLECTOR_MAX_PROBES=1`, `LAWS_COLLECTOR_MAX_RUNNING_TIME=60`, and single job parallelism/completion.
10. Start one manual Azure Container Apps Job execution and inspect logs for skipped completed ZIP state and either one imported sequential law or `No new laws for SK`.
11. Remove temporary operator firewall rules after validation.
12. Repeat for production only after the test migration and manual job execution are verified.

### Secrets And Environment Values

- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_POSTGRES_SERVER_NAME`
- `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK`
- `AZURE_POSTGRES_ADMIN_USERNAME`
- `AZURE_POSTGRES_ADMIN_PASSWORD`
- `AZURE_CONTAINERAPPS_ENVIRONMENT`
- `AZURE_CONTAINER_REGISTRY`
- `AZURE_MANAGED_IDENTITY_NAME`
- `AZURE_STORAGE_ACCOUNT_NAME`
- `AZURE_LAWS_STORAGE_CONTAINER_NAME`
- `MCP_API_JWT_SECRET` as a long random per-environment secret for remote MCP OAuth/JWT token signing

### Validation Steps

- `pg_restore --list <dump>` succeeds before restore.
- Azure `law_documents` count matches the source database.
- `collector_import_state` shows completed archive/monthly state expected for the migrated database.
- `collector_progress` contains the latest imported law and next probe cursor.
- A manual Azure job run completes successfully and does not replay completed archive ZIP work.
- Logs contain `No new laws for SK` when the live tail is current.

### Rollback Notes

- Delete the scheduled Container Apps Job or redeploy it as a manual job to stop scheduled executions.
- Restore the local dump into a replacement Azure database or restore from Azure PostgreSQL backup.
- Point the job back to the previous validated database connection string if available.
- Delete temporary firewall rules and revoke any temporary credentials after rollback.
- Keep the local dump until at least one scheduled Azure job run has completed and the restored database has been validated.

### Privacy And Compliance Notes

- Treat database dumps and connection strings as sensitive operational data.
- Do not commit dumps, passwords, or full connection strings.
- Use least-privilege Azure identities and remove temporary operator network access after migration.
- Preserve collector state tables for traceability and human oversight of legal data ingestion.
- Avoid logging personal data or legal-risk user outputs during migration and validation.

## Firebase Cloud Messaging For Document-Ready Mobile Push

Related task: https://github.com/mmaideveloper/aijurisdictionagents/issues/343

Purpose: send privacy-safe Android and iOS push notifications when a user's document package is ready.

### Provider Decision

Use Firebase Cloud Messaging directly.

- Android receives push notifications through FCM.
- iOS receives push notifications through APNs configured in Firebase/FCM.
- Do not use Azure Notification Hubs for this task unless a later task explicitly changes the provider decision.

### Manual Setup Steps

1. Create or select the Firebase project for JurisDigta.
2. Enable Firebase Cloud Messaging.
3. Register the Android app using the production Android package name.
4. Download the Android Firebase configuration file required by Flutter/Android setup.
5. Register the iOS app using the production iOS bundle identifier.
6. Download the iOS Firebase configuration file required by Flutter/iOS setup.
7. In Apple Developer, create or identify the APNs key/certificate for JurisDigta push notifications.
8. Upload the APNs key/certificate details to Firebase for the iOS app.
9. Create a Firebase service account or workload identity configuration for the backend sender.
10. Store backend Firebase credentials in GitHub Environments and Azure runtime secrets for `test` and `prod`.
11. Add documented example entries to `.env.example` for any new local configuration variables.
12. Update `docs/GITHUB_ENVIRONMENTS.md` with the exact required GitHub Environment secrets and variables for `test` and `prod`.
13. Configure mobile deep links/universal links for opening the ready document view from a notification.
14. Verify Android push delivery on a physical or emulator device with Google Play services.
15. Verify iOS push delivery on a physical iOS device.
16. Verify notification tap opens the authenticated document view or a safe loading/error state.

### Privacy And Compliance Notes

- Require explicit user opt-in before registering a device token for document-ready notifications.
- Provide localized consent and notification text per supported country/language.
- Delete or deactivate device tokens on opt-out, logout where applicable, and account deletion.
- Push payloads must not contain document text, legal facts, case names, party names, email addresses, or other personal data beyond the minimum routing data.
- Notification text should stay generic, for example: `Documents are ready` and `Open JurisDigta to review them`.
- Document URLs or deep links must be authenticated or short-lived/signed and must not expose document contents or sensitive metadata.
- Logs must redact device tokens and avoid document contents or legal facts.

### Rollback Notes

- Disable the backend push sender configuration if push delivery causes operational issues.
- Keep document generation and in-app document-ready status functional even when push sending is disabled.
- Revoke compromised Firebase service account credentials immediately and rotate the corresponding GitHub/Azure secrets.

## JurisDigta Server SSH Access

Related runbook: `Deployment/manual-server-setup.md`

Purpose: prepare the Ubuntu server `jurisdigta-server` at `192.168.1.50` for SSH access from Codex using public-key authentication.

### Provider And Owner

- Provider: self-managed Ubuntu Server on the local/private network.
- Required owner: infrastructure operator with console access to `jurisdigta-server`.
- Target environments: manual server setup before any test or production deployment work.

### Manual Setup Steps

1. Install Ubuntu Server and create the non-root administrator user `jurisdigta-admin`.
2. Install and enable OpenSSH Server with `sudo apt install openssh-server` and `sudo systemctl enable --now ssh`.
3. Validate port `22` locally with `ss -tlnp | grep ':22'`.
4. Validate workstation connectivity with `Test-NetConnection -ComputerName 192.168.1.50 -Port 22`.
5. Generate an Ed25519 SSH key on the Codex workstation.
6. Copy only the public key to a USB drive.
7. Mount the USB partition on Ubuntu, avoiding `/boot/efi`.
8. Append the public key to `/home/jurisdigta-admin/.ssh/authorized_keys`.
9. Create the local SSH alias `jurisdigta-server` in `C:\Users\maton\.ssh\config`.
10. Validate with `ssh -o BatchMode=yes jurisdigta-server "hostname && whoami"`.

### Secrets And Access Values

- Private key: `C:\Users\maton\.ssh\id_ed25519`; keep local and never commit or copy to the server.
- Public key: `C:\Users\maton\.ssh\id_ed25519.pub`; safe to copy into `authorized_keys`.
- Server user: `jurisdigta-admin`.
- Server host/IP: `192.168.1.50`.

### Validation Steps

- `systemctl status ssh --no-pager` shows the SSH service is active.
- `Test-NetConnection` from Windows returns `TcpTestSucceeded : True`.
- `ssh jurisdigta-server` accepts the host key and logs in as `jurisdigta-admin`.
- Non-interactive validation returns `jurisdigta-server` and `jurisdigta-admin`.

### Rollback Notes

- Remove the public key line ending in `maton-jurisdigta-server` from `/home/jurisdigta-admin/.ssh/authorized_keys`.
- Remove or update `C:\Users\maton\.ssh\config` if the host alias changes.
- Remove local private/public key files only after confirming they are not reused by any other host.

### Privacy And Compliance Notes

- Use public-key authentication and least-privilege server accounts.
- Do not commit private keys, passwords, host inventories with sensitive access details, or deployment secrets.
- Preserve SSH and deployment logs for traceability, but avoid logging personal data or legal-risk user outputs.
- Require human review before using this access for production changes that affect legal-risk workflows.

## Dynamic DNS For Local JurisDigta Subdomains

Related runbook: `Deployment/local-dynamic-dns-domain-setup.md`

Purpose: point `web.jurisdigta.eu`, `api.jurisdigta.eu`, `mcp.jurisdigta.eu`, and `admin.jurisdigta.eu` to the local Ubuntu 26.04 server when the internet connection does not have a static public IP address.

### Provider And Owner

- DNS provider: setup.sk DNS zone for `jurisdigta.eu`.
- DNS provider remains setup.sk for `jurisdigta.eu`; Cloudflare Tunnel is the preferred ingress path using partial DNS/CNAME setup with records maintained in setup.sk.
- Required owner: infrastructure operator with setup.sk, router/firewall, and Ubuntu server administrator access.
- Target environments: test first; production only after external DNS, TLS, authentication, logging, backup, and human-oversight validation are complete.

### Manual Setup Steps

1. Keep `jurisdigta.eu` DNS authoritative in setup.sk and use Cloudflare Tunnel partial DNS/CNAME setup for ingress.
2. Create a named Cloudflare Tunnel in Cloudflare Zero Trust, copy the generated connector token, and install `cloudflared` on the Ubuntu server as a systemd service.
3. Configure Cloudflare public hostnames for `web`, `api`, `mcp`, and `admin` pointing to local services on the server; validate local ports with `curl` before publishing DNS.
4. In setup.sk, create `CNAME` records for those subdomains pointing to the Cloudflare-provided partial DNS targets, typically `<full-hostname>.cdn.cloudflare.net`.
5. Keep router port forwards for TCP `80` and `443` disabled for the tunnel path; public traffic should arrive through outbound `cloudflared` connections.
6. Configure UFW so local services are reachable only from loopback/LAN as needed; do not rely on direct public router NAT for tunnel traffic.
7. Configure local nginx or service listeners for `web`, `api`, `mcp`, and `admin`.
8. Validate HTTPS externally from outside the LAN after DNS propagation.
9. Protect `admin.jurisdigta.eu` and MCP endpoints with Cloudflare Access, authentication, rate limits, audit logging, and preferably VPN/IP allow-list before production use.

### Secrets And Access Values

- setup.sk account credentials; never commit them.
- Cloudflare Tunnel token/connector credentials; keep them server-local only and never commit them, paste them into tickets, or expose them in screenshots/logs.
- Router administrator credentials; never commit them.
- TLS is terminated/managed by Cloudflare for the public tunnel hostname path; do not commit any origin certificates if optional origin TLS is later added.

### Validation Steps

- Cloudflare Zero Trust shows the tunnel as healthy.
- `web.jurisdigta.eu`, `api.jurisdigta.eu`, `mcp.jurisdigta.eu`, and `admin.jurisdigta.eu` resolve through setup.sk CNAME records to the Cloudflare tunnel targets.
- Router forwards for public TCP `80` and `443` remain disabled unless a separate documented exception exists.
- `cloudflared --version`, `systemctl status cloudflared --no-pager`, and `journalctl -u cloudflared -n 100 --no-pager` succeed on the server.
- External checks such as `curl -fsS https://api.jurisdigta.eu/health` succeed from outside the LAN.

### Rollback Notes

- Remove setup.sk `CNAME` records for the service subdomains.
- Disable the Cloudflare Tunnel public hostnames and stop/disable `cloudflared`; if any direct router forwards were created as an exception, disable them too.
- Disable the nginx virtual hosts and reload nginx.
- Revoke Cloudflare tunnel tokens if no longer needed or if exposed.
- Keep replacement DNS/TLS/ingress in place before disabling active production traffic.

### Privacy And Compliance Notes

- Use privacy-by-design: expose only the reverse proxy and keep databases/internal ports private.
- Minimize access logs and configure retention; do not log legal case contents, uploaded document text, tokens, API keys, or credentials.
- Require strong authentication and human oversight for legal-risk admin and MCP operations before production exposure.
- Provide user transparency when legal workflows use AI assistance, and retain traceable but privacy-safe audit logs.

## JurisDigta Self-Managed Server Deployment Preparation

Related runbooks and scripts:

- `Deployment/manual-server-setup.md`
- `Deployment/self-managed-server-deployment.md`
- `Deployment/server/setup_jurisdigta_server.sh`
- `Deployment/server/deploy_jurisdigta_prod.sh`
- `.github/workflows/self_managed_prod_deploy.yml`
- `docs/ENV_SYNC.md`

Purpose: install and validate the software needed to deploy JurisDigta API, system code, laws connector, and PostgreSQL database from GitHub onto the self-managed Ubuntu server `jurisdigta-server`.

### Provider And Owner

- Provider: self-managed Ubuntu Server on the local/private network, with optional public DNS and TLS for JurisDigta subdomains.
- Required owner: infrastructure operator with server administrator access.
- Target environments: test first; production only after package validation, API health check, laws connector migration validation, backup policy, and human oversight process are confirmed.

### Manual Setup Steps

1. Verify SSH access with `ssh -o BatchMode=yes jurisdigta-server "hostname && whoami"`.
2. Enable non-interactive sudo for the deployment account only if Codex or automation will install packages remotely.
3. Run the checked-in bootstrap script from the server after SSH works:

```bash
cd /srv/jurisdigta/app 2>/dev/null || cd /tmp
bash Deployment/server/setup_jurisdigta_server.sh
```

If the repository is not cloned yet, run the same script from a temporary copy of `Deployment/server/setup_jurisdigta_server.sh` or manually clone the repository first.
4. The bootstrap script installs base packages: `git`, `curl`, `unzip`, `jq`, `rsync`, `ufw`, `nginx`, `certbot`, Python venv/pip tooling, PostgreSQL client tools, Docker, Docker Compose v2, Node.js, npm, and OpenSSH.
5. Reconnect SSH after the script adds `jurisdigta-admin` to the `docker` group.
6. Install Cloudflare Tunnel with `INSTALL_CLOUDFLARED=1 bash Deployment/server/setup_jurisdigta_server.sh` when this server will expose public subdomains through Cloudflare.
7. Create `/srv/jurisdigta` deployment, runtime storage, log, and secrets directories.
8. Clone `https://github.com/mmaideveloper/aijurisdictionagents.git` to `/srv/jurisdigta/app`.
9. Create server-local environment configuration under `/srv/jurisdigta/secrets/` and keep it out of Git.
10. Start and validate PostgreSQL through Docker using repository storage layout.
11. Build and smoke-test the API with `curl -fsS http://127.0.0.1:8080/health`.
12. Build the laws connector image and apply laws database migrations before live import.
13. Before any laws collector redeploy, gracefully stop an active `jurisdigta-laws-collector-daily` container with `docker stop --time 120 jurisdigta-laws-collector-daily`; use forced removal only after the grace period fails.
14. Install or update the server-local daily laws collector cron wrapper only after the collector image, PostgreSQL database, migrations, and one bounded live smoke run are validated.
15. Install the server status writer cron from `docs/SYSTEM_STATUS_MONITORING.md` so API/system/laws collector status is updated every minute.
16. Optional but recommended: install the Prometheus/Grafana stack from `Deployment/monitoring/README.md` for real-time dashboards, host metrics, Docker metrics, API probes, and laws collector metrics.
17. Configure Cloudflare Tunnel public hostnames only after local health checks pass.
18. Configure firewall to keep direct public ingress closed except SSH or explicitly approved maintenance access.
19. Use nginx/Certbot only as a future static-IP fallback; for the current no-static-IP production server, Cloudflare Tunnel is the public HTTPS path.
20. Add systemd units or timers only after the exact smoke deployment commands are validated.
21. Configure the GitHub `prod` Environment values documented in `docs/GITHUB_ENVIRONMENTS.md`.
22. Run `Self-Managed Prod Deploy` from GitHub Actions after the server-local environment file is complete.

### Secrets And Environment Values

- Server-local environment file path: `/srv/jurisdigta/secrets/jurisdigta.env`.
- Keep secret file permissions at `600`.
- Workstation `.env` files are synced from `.env.example` with `.\scripts\sync_jurisdigta_env.ps1`. Missing keys from `.env.example` must be written as `unknown-variable` so local startup and sync checks can warn without guessing secrets.
- The sync script copies SSH key material from `E:\jurisdigta\ssh` to `%USERPROFILE%\.ssh\jurisdigta` and uses SSH/SCP to publish the full local `.env` to `/srv/jurisdigta/secrets/jurisdigta.env`.
- Keep the dedicated SSH folder local to the workstation. Only public keys belong in `/home/jurisdigta-admin/.ssh/authorized_keys` on the server.
- Required production LLM default: `LLM_PROVIDER=azurefoundry`.
- Required Azure Foundry values when `LLM_PROVIDER=azurefoundry`: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_EMBEDDINGS_MODEL`, `AZURE_OPENAI_API_VERSION`, and `AZURE_OPENAI_API_KEY`.
- PostgreSQL usernames, passwords, and connection strings must remain server-local or in a secret manager.
- Public DNS/TLS values may include `jurisdigta.eu`, `www.jurisdigta.eu`, `api.jurisdigta.eu`, `web.jurisdigta.eu`, `services.jurisdigta.eu`, and `admin.jurisdigta.eu`.
- Server-local laws collector cron wrapper path: `/srv/jurisdigta/ops/run_laws_collector_daily.sh`.
- Server-local laws collector log path: `/srv/jurisdigta/runs/logs/laws-collector-daily-latest.log`.
- Daily cron schedule on `jurisdigta-server`: `15 2 * * *`, using the server timezone.
- Server-local status file path: `/srv/jurisdigta/runs/status/system-status.json`.
- API status endpoint: `GET /v1/system/status?minutes=60`, protected by `x-api-key`.
- Optional Prometheus exporter path: `/srv/jurisdigta/app/scripts/server/export_system_status_metrics.py`.
- Optional Prometheus exporter port: `127.0.0.1:9108`.
- Optional monitoring stack path: `/srv/jurisdigta/app/Deployment/monitoring`.
- Optional monitoring Docker network setting: `MONITORING_APP_DOCKER_NETWORK=aijuristiction-api_default`, used by status-exporter and Blackbox Exporter to reach `jurisdigta-api` and `jurisdigta-mcp` without exposing API/MCP beyond loopback host ports.
- Optional Grafana default dashboard setting: `GRAFANA_DEFAULT_HOME_DASHBOARD_PATH=/var/lib/grafana/dashboards/jurisdigta-application-performance.json`.
- Cloudflare Tunnel service: `cloudflared.service` on `jurisdigta-server`.
- Cloudflare Tunnel API hostname: `api.jurisdigta.eu` -> `http://127.0.0.1:8080`.
- Cloudflare Tunnel MCP hostname: `mcp.jurisdigta.eu` -> `http://127.0.0.1:8070`, with MCP served by the dedicated MCP service at `/MCP`.
- Cloudflare Tunnel admin hostname: `admin.jurisdigta.eu` -> `http://127.0.0.1:3000`, with Grafana served at `/grafana/`.
- Cloudflare Tunnel web hostname: `web.jurisdigta.eu` -> `http://127.0.0.1:8090` only after the `jurisdigta-web` frontend container serves the intended web app.
- Optional Grafana local URL: `http://127.0.0.1:3000`, accessed by SSH tunnel or through `admin.jurisdigta.eu` protected by Cloudflare Access.
- Optional Grafana public mobile entry URL through Cloudflare Tunnel: `https://admin.jurisdigta.eu/grafana/`.
- Required Grafana secret for local stack: `GRAFANA_ADMIN_PASSWORD`, stored only in `/srv/jurisdigta/app/Deployment/monitoring/.env` or a server-local secret manager.
- GitHub `prod` Environment variable `JURISDIGTA_SSH_HOST`.
- GitHub `prod` Environment secret `JURISDIGTA_SSH_PRIVATE_KEY`, preferably a deploy-only key.
- Optional GitHub `prod` Environment variables: `JURISDIGTA_SSH_PORT`, `JURISDIGTA_SSH_USER`, `JURISDIGTA_DEPLOY_ROOT`, `JURISDIGTA_ENV_FILE`, `JURISDIGTA_WEB_API_BASE_URL`, `JURISDIGTA_API_PORT`, `JURISDIGTA_MCP_PORT`, and `JURISDIGTA_WEB_PORT`.

### Validation Steps

- `sudo -n true` succeeds for automation-enabled setup.
- `docker --version`, `docker compose version`, `node --version`, `npm --version`, `python3 --version`, `psql --version`, and `gh --version` succeed.
- `bash /srv/jurisdigta/app/Deployment/server/setup_jurisdigta_server.sh` is idempotent and completes without package or permission errors.
- `docker run --rm hello-world` succeeds after reconnecting with Docker group membership.
- Repository checkout under `/srv/jurisdigta/app` is on the intended branch.
- PostgreSQL health check succeeds.
- API health check returns HTTP 200 at `http://127.0.0.1:8080/health`.
- MCP health check returns HTTP 200 at `http://127.0.0.1:8070/health`.
- Repository minimal runnable example succeeds: `python examples/minimal_demo.py`.
- `crontab -l` contains the daily laws collector wrapper entry.
- `docker ps -a --filter name=jurisdigta-laws-collector-daily` shows no stuck active collector container after deployment validation.
- A bounded manual collector cron run succeeds with `LAWS_WORKER_MAX_PROBES=1 LAWS_COLLECTOR_MAX_RUNNING_TIME=5 /srv/jurisdigta/ops/run_laws_collector_daily.sh`.
- The latest collector log contains skipped completed ZIP state and either one imported sequential law or `No new laws for SK`.
- `python3 /srv/jurisdigta/app/scripts/server/write_system_status.py --output /srv/jurisdigta/runs/status/system-status.json` writes valid JSON.
- `curl -fsS -H "x-api-key: ${API_KEY:-aijuris}" "http://127.0.0.1:8080/v1/system/status?minutes=60"` returns API, system, laws collector, and error-count sections.
- If Prometheus/Grafana monitoring is enabled, `systemctl status jurisdigta-status-exporter.service --no-pager` shows the exporter active.
- If Prometheus/Grafana monitoring is enabled, `curl -fsS http://127.0.0.1:9108/metrics | head` returns Prometheus text metrics.
- If Prometheus/Grafana monitoring is enabled, `docker compose -f /srv/jurisdigta/app/Deployment/monitoring/docker-compose.yml ps` shows Prometheus, Grafana, Node Exporter, cAdvisor, and Blackbox Exporter running.
- If Prometheus/Grafana monitoring is enabled, `curl -fsS http://127.0.0.1:9091/-/ready` and `curl -fsS http://127.0.0.1:3000/grafana/api/health` succeed.
- If Prometheus/Grafana monitoring is enabled, `cd /srv/jurisdigta/app && PROMETHEUS_BASE_URL=http://127.0.0.1:9091 python3 examples/monitoring_scrape_demo.py` reports all scrapes and HTTP probes healthy.
- If Prometheus/Grafana monitoring is enabled, Prometheus queries for `jurisdigta_http_requests_total_window`, `jurisdigta_http_request_duration_seconds_avg`, `jurisdigta_users_total`, and `jurisdigta_cases_total` return aggregate samples.
- `systemctl status cloudflared --no-pager` shows the Cloudflare tunnel active when public hostnames are enabled.
- If Cloudflare Tunnel public hostnames are enabled, `curl -fsS https://api.jurisdigta.eu/health`, `curl -I https://mcp.jurisdigta.eu/.well-known/oauth-protected-resource/MCP`, and `curl -I https://admin.jurisdigta.eu/grafana/` succeed from outside the server.
- If the frontend web container is enabled, `curl -fsS http://127.0.0.1:8090/health` and `curl -I http://127.0.0.1:8090/privacy` succeed on the server.
- GitHub Actions workflow `Self-Managed Prod Deploy` completes for `repo_ref=main`.
- Cloudflare Access protects `admin.jurisdigta.eu` before public use.
- UFW allows only expected ingress, typically SSH; do not expose PostgreSQL, API, Grafana, Prometheus, or exporter ports directly.

### Rollback Notes

- Stop Docker Compose workloads before changing runtime configuration.
- Remove the daily laws collector cron entry with `crontab -l | grep -v 'run_laws_collector_daily.sh' | crontab -`.
- Remove the status writer cron entry with `crontab -l | grep -v 'write_system_status.py' | crontab -`.
- Stop the optional status metrics exporter with `sudo systemctl disable --now jurisdigta-status-exporter.service`.
- Stop the optional Prometheus/Grafana stack with `cd /srv/jurisdigta/app/Deployment/monitoring && docker compose down`.
- Stop the frontend web container with `docker rm -f jurisdigta-web` and remove the local image with `docker image rm jurisdigta-web:local`.
- Stop any active daily collector container gracefully with `docker stop --time 120 jurisdigta-laws-collector-daily`; use `docker rm -f jurisdigta-laws-collector-daily` only if the container remains stuck.
- Remove `/srv/jurisdigta/ops/run_laws_collector_daily.sh` only after confirming no other scheduler uses it.
- Back up `/srv/jurisdigta/app/runs/storage` before removing containers, volumes, or the repository checkout.
- Remove `/etc/sudoers.d/jurisdigta-admin-codex` to revoke Codex passwordless sudo.
- Disable Cloudflare Tunnel hostnames or stop `cloudflared.service` only after DNS is routed to a rollback target or the service is intentionally offline.
- Remove nginx site config or Certbot certificates only after DNS is routed away or rollback target is ready.
- Remove Docker/GitHub CLI/nginx packages only if the server is being decommissioned.
- Remove the deploy-only public key from `/home/jurisdigta-admin/.ssh/authorized_keys` and delete/rotate `JURISDIGTA_SSH_PRIVATE_KEY` if GitHub deployment access must be revoked.

### Privacy And Compliance Notes

- Treat server environment files, PostgreSQL data, document storage, logs, and backups as sensitive operational data.
- Do not commit or print API keys, PostgreSQL passwords, full connection strings, access tokens, or generated legal documents.
- Keep PostgreSQL and document runtime files outside `databases/` and under `/srv/jurisdigta/.../runs/storage`.
- Preserve deployment and collector logs for traceability, while avoiding personal data and legal-risk content in logs.
- Use `azurefoundry` for production-like local starts unless deterministic offline testing was explicitly requested.
- Keep legal-risk outputs subject to human oversight before production traffic is enabled.
- For Cloudflare Tunnel and Access, avoid logging personal data, legal documents, API keys, database credentials, or full user prompts in edge, dashboard, or application logs.
