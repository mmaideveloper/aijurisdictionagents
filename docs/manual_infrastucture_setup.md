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

## Production Qwen Hardware Acceleration

Purpose: remove the CPU-only latency observed when Qwen 4B is explicitly tested or used. Qwen is
not part of the automatic production post-deployment gate; that gate uses Azure Foundry
`gpt-5-mini` only.

### Provider And Owner

- Provider: self-managed `jurisdigta-server` hardware and Ubuntu NVIDIA driver packages.
- Required owner: JurisDigta infrastructure operator with physical server and non-interactive sudo access.
- Environments: validate on a non-production host first, then schedule a production maintenance window.

### Current Confirmed State

- Installed GPU: NVIDIA GeForce GT 630 (`GF108`, PCI ID `10de:0f00`).
- Installed driver: NVIDIA `610.43.02`.
- Kernel log states that the GT 630 is supported only by the legacy `390.xx` driver and is ignored by 610.
- `nvidia-smi` cannot communicate with the driver, no NVIDIA device is available to Ollama, and the Qwen 4B Q4 model is loaded into CPU memory.
- A synthetic 689-token production legal prompt took approximately 126 seconds; prompt evaluation alone took approximately 53 seconds.

### Required Remediation

1. Do not downgrade production blindly to the legacy 390 driver. First verify kernel compatibility and security support on an isolated host; the current kernel is `7.0.0-30-generic`.
2. Prefer replacing the GT 630 with a currently supported NVIDIA GPU with enough VRAM for the 2.3 GiB Qwen 4B weights, KV cache, runtime buffers, and operational headroom. Use at least 8 GiB VRAM for this workload.
3. Install the vendor-supported production driver for the replacement GPU and reboot during the approved maintenance window.
4. Confirm `nvidia-smi` reports the replacement GPU without NVRM errors.
5. Restart Ollama and confirm `/api/ps` reports non-zero `size_vram` for `qwen3:4b` during a synthetic request.
6. Run an explicitly approved manual synthetic Qwen performance probe and record prompt-evaluation,
   generation, and total latency without logging the prompt or model reasoning. Do not add Qwen
   back to the automatic issue #646 post-deployment gate.

### Validation And Rollback

- The MCP result identity and citation must remain unchanged after hardware acceleration.
- Qwen must remain `qwen3:4b`; never treat a fallback to another model as acceptance.
- If the replacement driver or GPU is unstable, stop Ollama, restore the previous hardware/boot
  configuration, and verify CPU inference remains functional. This does not affect the automatic
  Azure-only post-deployment gate.

### Privacy And Compliance

- Use only synthetic prompts for performance validation.
- Do not log production customer prompts, legal documents, model reasoning, credentials, or tokens.
- Hardware acceleration changes latency only; it must not weaken source attribution, human-review notices, traceable model routing, or MCP citation checks.

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

## Court Decision Collector PostgreSQL Setup

Purpose: create the dedicated PostgreSQL database for Slovak court decisions (`sudne rozhodnutia`) and enable vector-backed MCP/API search without mixing this data into laws collector tables.

Required owner: infrastructure operator with PostgreSQL administrator access.

### Manual Setup Steps

1. Create a separate database such as `court_decisions_sk`.
2. Enable `pgvector` with `CREATE EXTENSION IF NOT EXISTS vector;`.
3. Apply `databases/court-decision-collector/initdb/001_schema.sql`, then run the tracked SQL migrations in `databases/court-decision-collector/migrations/` when upgrading an existing database. Keep the metadata full-text search index expression immutable for PostgreSQL production deploys.
4. Store the connection string only in local/server secrets as `COURT_DECISIONS_DB_CLOUD`.
5. Set `COURT_DECISIONS_DB_BACKEND=postgres`, `COURT_DECISIONS_STORAGE_LOCAL=./runs/storage/court-decision-collector/files/sk`, `COURT_DECISIONS_MAX_PDF_BYTES=26214400`, `COURT_DECISION_MCP_SEARCH_TIMEOUT_MS=600000`, and `COURT_DECISIONS_WORKER_POLL_HOURS=1`. Apply `databases/court-decision-collector/migrations/0002_on_demand_enrichment.sql`, install/validate the existing local PDF/OCR runtime, and grant write access only to the dedicated storage path. Validate the Komárno example twice (cache miss then hit). Roll back by disabling enrichment before removing the new tables; retain PDFs until the approved deletion workflow handles them.
6. Run a bounded fixture import first: `python -m services.court_decision_collector --fixture`.
7. Validate console logs include `processing_judicial_decision reference_hash=...` and no raw source GUID, decision body, ECLI/file number, or personal identifier is logged.
8. Validate MCP `tools/list` advertises `searchCourtDecisions` and `getCourtDecision`.
9. Roll back by disabling MCP court-decision tools through configuration or clearing `COURT_DECISIONS_DB_CLOUD`, then stop any collector worker before dropping the database.

### Privacy And Compliance Notes

- Treat raw court decisions, extracted text, vectors, logs, and backups as sensitive operational data.
- User-facing MCP results must default to pseudonymized snippets/text.
- Do not send raw court-decision personal data to external model providers without a separate compliance review.

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

Purpose: prepare the Ubuntu server `jurisdigta-server` at `192.168.1.25` for SSH access from Codex using public-key authentication.

### Provider And Owner

- Provider: self-managed Ubuntu Server on the local/private network.
- Required owner: infrastructure operator with console access to `jurisdigta-server`.
- Target environments: manual server setup before any test or production deployment work.

### Manual Setup Steps

1. Install Ubuntu Server and create the non-root administrator user `jurisdigta-admin`.
2. Install and enable OpenSSH Server with `sudo apt install openssh-server` and `sudo systemctl enable --now ssh`.
3. Validate port `22` locally with `ss -tlnp | grep ':22'`.
4. Validate workstation connectivity with `Test-NetConnection -ComputerName 192.168.1.25 -Port 22`.
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
- Server host/IP: `192.168.1.25`.

### Validation Steps

- `systemctl status ssh --no-pager` shows the SSH service is active.
- `Test-NetConnection` from Windows returns `TcpTestSucceeded : True`.
- `ssh jurisdigta-server` accepts the host key and logs in as `jurisdigta-admin`.
- Non-interactive validation returns `jurisdigta-server` and `jurisdigta-admin`.
- Production deploys that install or configure Ollama require `jurisdigta-admin`
  to have non-interactive sudo for system package installation and systemd
  service management, including writing
  `/etc/systemd/system/ollama.service.d/jurisdigta-localhost.conf`.

### Rollback Notes

- Remove the public key line ending in `maton-jurisdigta-server` from `/home/jurisdigta-admin/.ssh/authorized_keys`.
- Remove or update `C:\Users\maton\.ssh\config` if the host alias changes.
- Remove local private/public key files only after confirming they are not reused by any other host.

### LAN-only Ollama proxy

Purpose: allow trusted laptops on `192.168.1.0/24` to reach the server-local
Ollama service without changing its private Docker binding.

- Required owner: the `jurisdigta-server` infrastructure operator.
- Configuration source: `Deployment/server/nginx-ollama-lan.conf`.
- Listener: `192.168.1.25:11434`; upstream: `172.18.0.1:11434`.
- Keep TCP `11434` absent from router/NAT forwarding and Cloudflare Tunnel
  configuration. The nginx subnet allowlist is the access boundary.
- Validate on a trusted laptop with
  `Invoke-RestMethod http://192.168.1.25:11434/api/tags`.
- Validate on the server with `sudo nginx -t`, `systemctl is-active nginx`, and
  `curl -fsS http://192.168.1.25:11434/api/tags`.
- Roll back with
  `sudo rm /etc/nginx/sites-enabled/jurisdigta-ollama-lan.conf && sudo systemctl reload nginx`.

Because Ollama does not authenticate these LAN requests, every device on the
allowlisted subnet can invoke installed models. Use a narrower allowlist or an
SSH tunnel on networks that are not fully trusted. Avoid placing personal data
or confidential case content in prompts from unmanaged devices.

### Privacy And Compliance Notes

- Use public-key authentication and least-privilege server accounts.
- Do not commit private keys, passwords, host inventories with sensitive access details, or deployment secrets.
- Preserve SSH and deployment logs for traceability, but avoid logging personal data or legal-risk user outputs.
- Require human review before using this access for production changes that affect legal-risk workflows.

## Dynamic DNS For Local JurisDigta Subdomains

Related runbook: `Deployment/local-dynamic-dns-domain-setup.md`

Purpose: point `web.jurisdigta.eu`, `agent.jurisdigta.eu`, `api.jurisdigta.eu`, `mcp.jurisdigta.eu`, and `admin.jurisdigta.eu` to the local Ubuntu 26.04 server when the internet connection does not have a static public IP address.

### Provider And Owner

- DNS provider: setup.sk DNS zone for `jurisdigta.eu`.
- DNS provider remains setup.sk for `jurisdigta.eu`; Cloudflare Tunnel is the preferred ingress path using partial DNS/CNAME setup with records maintained in setup.sk.
- Required owner: infrastructure operator with setup.sk, router/firewall, and Ubuntu server administrator access.
- Target environments: test first; production only after external DNS, TLS, authentication, logging, backup, and human-oversight validation are complete.

### Manual Setup Steps

1. Keep `jurisdigta.eu` DNS authoritative in setup.sk and use Cloudflare Tunnel partial DNS/CNAME setup for ingress.
2. Create a named Cloudflare Tunnel in Cloudflare Zero Trust, copy the generated connector token, and install `cloudflared` on the Ubuntu server as a systemd service.
3. Configure Cloudflare public hostnames for `web`, `agent`, `api`, `mcp`, and `admin` pointing to local services on the server; validate local ports with `curl` before publishing DNS.
4. In setup.sk, create `CNAME` records for those subdomains pointing to the Cloudflare-provided partial DNS targets, typically `<full-hostname>.cdn.cloudflare.net`.
5. Keep router port forwards for TCP `80` and `443` disabled for the tunnel path; public traffic should arrive through outbound `cloudflared` connections.
6. Configure UFW so local services are reachable only from loopback/LAN as needed; do not rely on direct public router NAT for tunnel traffic.
7. Configure local nginx or service listeners for `web`, `api`, `mcp`, and `admin`.
8. Validate HTTPS externally from outside the LAN after DNS propagation.
9. Protect `agent.jurisdigta.eu` with JurisDigta account login against the API users table for the current release, and protect `admin.jurisdigta.eu` plus MCP endpoints with Cloudflare Access, authentication, rate limits, audit logging, and preferably VPN/IP allow-list before production use.
10. If external HTTPS validation fails before an HTTP response, inspect the served certificate issuer. A local antivirus or enterprise proxy issuer such as `Avast Web/Mail Shield Root` means the failure is on the client TLS-inspection path, not on the Cloudflare Tunnel app route. Disable or exclude HTTPS scanning for JurisDigta MCP/API validation clients, or configure the client runtime to use the operating-system trust store where appropriate.
11. Optional MCP fallback: install `jurisdigta-mcp-trycloudflare.service` on `jurisdigta-server` with `bash /srv/jurisdigta/app/Deployment/server/install_mcp_trycloudflared_fallback.sh install`. It creates a temporary `trycloudflare.com` URL to `http://127.0.0.1:8070` for diagnostics when the named `mcp.jurisdigta.eu` route is blocked by Cloudflare Access, WAF, bot challenges, partial DNS errors, or tunnel hostname mapping issues. The current URL created on 2026-07-08 is `https://remote-neighbors-lions-councils.trycloudflare.com/MCP`; retrieve the latest URL with `ssh jurisdigta-server "/srv/jurisdigta/app/Deployment/server/install_mcp_trycloudflared_fallback.sh url"`.

### Secrets And Access Values

- setup.sk account credentials; never commit them.
- Cloudflare Tunnel token/connector credentials; keep them server-local only and never commit them, paste them into tickets, or expose them in screenshots/logs.
- The `trycloudflare.com` fallback uses no checked-in token, but its generated URL is public while the service runs. Treat it as an operational endpoint and stop it when the diagnostic window ends.
- Router administrator credentials; never commit them.
- TLS is terminated/managed by Cloudflare for the public tunnel hostname path; do not commit any origin certificates if optional origin TLS is later added.

### Validation Steps

- Cloudflare Zero Trust shows the tunnel as healthy.
- `web.jurisdigta.eu`, `agent.jurisdigta.eu`, `api.jurisdigta.eu`, `mcp.jurisdigta.eu`, and `admin.jurisdigta.eu` resolve through setup.sk CNAME records to the Cloudflare tunnel targets.
- Router forwards for public TCP `80` and `443` remain disabled unless a separate documented exception exists.
- `cloudflared --version`, `systemctl status cloudflared --no-pager`, and `journalctl -u cloudflared -n 100 --no-pager` succeed on the server.
- External checks such as `curl -fsS https://api.jurisdigta.eu/health` succeed from outside the LAN.
- Strict client checks such as `curl.exe -Iv https://mcp.jurisdigta.eu/health` and `python scripts/prod_mcp_claude_smoke.py --retries 1 --retry-delay 1` succeed without `--ssl-no-revoke`, `-k`, or disabled verification. If they fail and the peer issuer is an antivirus/proxy root rather than Cloudflare or a public CA, fix the local TLS-inspection configuration before testing Claude again.
- For fallback diagnostics, `curl -fsS https://remote-neighbors-lions-councils.trycloudflare.com/health` returns MCP health and `curl -fsS https://remote-neighbors-lions-councils.trycloudflare.com/.well-known/oauth-protected-resource/mcp` returns metadata whose canonical resource remains `https://mcp.jurisdigta.eu/MCP`.

### Rollback Notes

- Remove setup.sk `CNAME` records for the service subdomains.
- Disable the Cloudflare Tunnel public hostnames and stop/disable `cloudflared`; if any direct router forwards were created as an exception, disable them too.
- Stop and remove the temporary MCP quick tunnel with `bash /srv/jurisdigta/app/Deployment/server/install_mcp_trycloudflared_fallback.sh uninstall`.
- Disable the nginx virtual hosts and reload nginx.
- Revoke Cloudflare tunnel tokens if no longer needed or if exposed.
- Keep replacement DNS/TLS/ingress in place before disabling active production traffic.

### Privacy And Compliance Notes

- Use privacy-by-design: expose only the reverse proxy and keep databases/internal ports private.
- Minimize access logs and configure retention; do not log legal case contents, uploaded document text, tokens, API keys, or credentials.
- Require strong authentication and human oversight for legal-risk admin and MCP operations before production exposure.
- Provide user transparency when legal workflows use AI assistance, and retain traceable but privacy-safe audit logs.

## JurisDigta Server Eaton UPS Shutdown Protection

Purpose: install and validate Network UPS Tools (NUT) on the self-managed Ubuntu
server `jurisdigta-server` so the server receives UPS power-loss notifications
and shuts down gracefully when the UPS reports low battery or forced shutdown.

### Provider And Owner

- Provider: local self-managed Ubuntu server with Eaton USB HID UPS.
- Required owner: infrastructure operator with SSH, sudo, and physical access to
  the server and UPS.
- Target environment: production `jurisdigta-server` on the local/private
  network.

### Actual Server Setup

Validated on 2026-07-03:

- Server: `jurisdigta-server` at `192.168.1.25`.
- Server user: `jurisdigta-admin`.
- Motherboard: Gigabyte `Z77X-UD3H`, BIOS `F7`.
- USB UPS vendor: `0463` (`MGE UPS Systems` / Eaton USB HID).
- NUT device name: `eaton5p`.
- UPS-reported model during validation: `Eaton 5E 900 G2`.
- NUT driver: `usbhid-ups`.
- NUT version: `2.8.4`.
- UPS status during validation: online and charging.
- UPS low-battery threshold reported by the device: `20%`.

NUT is installed with:

```bash
sudo apt-get update
sudo apt-get install -y nut nut-client nut-server
```

The server-local NUT configuration is:

- `/etc/nut/nut.conf`: `MODE=standalone`
- `/etc/nut/ups.conf`: `[eaton5p]`, `driver = usbhid-ups`,
  `port = auto`, `vendorid = 0463`
- `/etc/nut/upsd.conf`: listens only on `127.0.0.1:3493` and `[::1]:3493`
- `/etc/nut/upsd.users`: local `upsmon` monitor user with a random password
- `/etc/nut/upsmon.conf`: monitors `eaton5p@localhost` as primary and runs
  `/sbin/shutdown -h +0` when NUT reaches the shutdown condition
- `/etc/nut/upssched.conf`: sends UPS events to `/etc/nut/upssched-cmd`
- `/etc/nut/upssched-cmd`: writes privacy-safe operational events to syslog
  with tag `jurisdigta-ups`

NUT services are enabled and active:

```bash
sudo systemctl enable --now nut-driver@eaton5p.service nut-server.service nut-monitor.service
systemctl is-enabled nut-driver@eaton5p.service nut-server.service nut-monitor.service
systemctl is-active nut-driver@eaton5p.service nut-server.service nut-monitor.service
```

The conservative shutdown policy is:

- Notify immediately when mains power is lost (`ONBATT`).
- Keep the server online during short outages.
- Shut down gracefully when the UPS reports `LOWBATT` or forced shutdown.
- Do not expose NUT over the network; local-only monitoring is sufficient for
  this server.

### Validation Steps

Run the repository validation helper from a Windows workstation:

```powershell
powershell -ExecutionPolicy Bypass -File examples/check_jurisdigta_ups_nut.ps1
```

Manual equivalent:

```bash
systemctl is-active nut-driver@eaton5p.service nut-server.service nut-monitor.service
systemctl is-enabled nut-driver@eaton5p.service nut-server.service nut-monitor.service
ss -ltnp | grep ':3493'
upsc eaton5p@localhost
journalctl -t jurisdigta-ups -n 20 --no-pager
```

Expected results:

- All three NUT services are `active` and `enabled`.
- `ss` shows NUT listening only on `127.0.0.1:3493` and `[::1]:3493`.
- `upsc eaton5p@localhost` returns Eaton UPS telemetry including
  `ups.status`, `battery.charge`, `battery.runtime`, and `input.voltage`.
- Simulated notification validation with `sudo /etc/nut/upssched-cmd onbatt`
  creates a `jurisdigta-ups` syslog event.

### Power Return And Auto-Start Check

The UPS supports delayed output restart commands such as `shutdown.return`,
`load.on.delay`, and writable `ups.delay.start`. This means the UPS can turn
the protected outlet back on after utility power returns.

The server itself also needs firmware support to boot when AC power returns
after a full outage. On the Gigabyte `Z77X-UD3H`, verify in BIOS/UEFI that the
AC power recovery setting is enabled, usually named `AC BACK`, `Restore on AC
Power Loss`, `Power On After Power Fail`, or similar. This setting is not
reliably exposed through Linux, so it cannot be proven from SSH alone.

Controlled physical validation:

1. Confirm JurisDigta services are healthy before testing.
2. Confirm the server power cable is connected to a battery-backed UPS outlet,
   not only surge protection.
3. Confirm the BIOS/UEFI AC-back setting is `Power On` or `Memory/Last State`.
4. Disconnect utility power from the UPS, not the server.
5. Confirm `journalctl -t jurisdigta-ups -f` logs the `ONBATT` notification.
6. Reconnect utility power before low battery for a non-shutdown smoke test.
7. For a full shutdown/restart test, schedule a maintenance window, back up
   critical data, let NUT reach low battery, and confirm the server shuts down
   cleanly and starts again after UPS output returns.

### Rollback Notes

To disable the NUT setup without removing packages:

```bash
sudo systemctl disable --now nut-monitor.service nut-server.service nut-driver@eaton5p.service
```

To restore the previous NUT configuration, copy files back from the latest
`/etc/nut/jurisdigta-backup-*` directory and restart the services.

To fully remove NUT:

```bash
sudo apt-get remove -y nut nut-client nut-server
```

### Privacy And Compliance Notes

- UPS telemetry and power events are operational infrastructure data, not legal
  case content.
- Logs must remain privacy-safe: do not include user names, case names,
  document contents, access tokens, API keys, or secrets in UPS notifications.
- Graceful shutdown protects database and document-processing integrity, which
  supports GDPR availability and integrity expectations for personal data.
- Human operators must review any full power-fail test because it can interrupt
  legal-risk workflows and user-facing services.

## JurisDigta Self-Managed Server Deployment Preparation

Related runbooks and scripts:

- `Deployment/manual-server-setup.md`
- `Deployment/self-managed-server-deployment.md`
- `Deployment/server/setup_jurisdigta_server.sh`
- `Deployment/server/deploy_jurisdigta_prod.sh`
- `.github/workflows/self_managed_prod_deploy.yml`
- `docs/ENV_SYNC.md`

Purpose: install and validate the software needed to deploy JurisDigta API, system code, document processor, laws connector, and PostgreSQL database from GitHub onto the self-managed Ubuntu server `jurisdigta-server`.

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
7. Install Ollama as a separate local model service on `jurisdigta-server`; keep it bound to localhost or the private Docker gateway and never expose it directly through Cloudflare Tunnel or public firewall rules.
8. Pull the configured local model, for example `ollama pull qwen3:1.7b`, and pull a smaller fallback model when server RAM/VRAM cannot safely run the preferred model.
9. Validate Ollama through localhost endpoints before wiring it into the model-router configuration.
10. Create `/srv/jurisdigta` deployment, runtime storage, log, and secrets directories.
11. Clone `https://github.com/mmaideveloper/aijurisdictionagents.git` to `/srv/jurisdigta/app`.
12. Create server-local environment configuration under `/srv/jurisdigta/secrets/` and keep it out of Git.
13. Start and validate PostgreSQL through Docker using repository storage layout.
14. Build and smoke-test the API with `curl -fsS http://127.0.0.1:8080/health`.
15. Build the laws connector image and apply laws database migrations before live import.
16. Before any laws collector redeploy, gracefully stop active collector containers with `docker stop --time 120 jurisdigta-laws-collector jurisdigta-laws-collector-daily`; use forced removal only after the grace period fails.
17. Build the document processor image and install the locked cron wrapper through `Deployment/server/deploy_jurisdigta_prod.sh`; validate `/srv/jurisdigta/ops/run_document_processor.sh` before relying on asynchronous document extraction.
18. Install or update the server-local laws collector only after the collector image, PostgreSQL database, migrations, and one bounded live smoke run are validated. Use `LAWS_COLLECTOR_RUN_MODE=continuous` for self-managed prod so the restartable container keeps polling hourly; use `scheduled` only to keep the legacy daily cron wrapper.
19. Install the server status writer cron from `docs/SYSTEM_STATUS_MONITORING.md` so API/system/laws collector status is updated every minute.
20. Optional but recommended: install the Prometheus/Grafana stack from `Deployment/monitoring/README.md` for real-time dashboards, host metrics, Docker metrics, API probes, and laws collector metrics.
21. Configure Cloudflare Tunnel public hostnames only after local health checks pass.
22. Configure firewall to keep direct public ingress closed except SSH or explicitly approved maintenance access.
23. Use nginx/Certbot only as a future static-IP fallback; for the current no-static-IP production server, Cloudflare Tunnel is the public HTTPS path.
24. Add systemd units or timers only after the exact smoke deployment commands are validated.
25. Configure the GitHub `prod` Environment values documented in `docs/GITHUB_ENVIRONMENTS.md`.
26. Register a repository self-hosted GitHub Actions runner on the trusted server or private network with labels `self-hosted`, `Linux`, `X64`, and `jurisdigta-prod`.
27. Before production deployment, resolve the exact deployment commit SHA and verify that every applicable build, lint, type-check, unit/integration test, E2E gate, image build, and required check is successful for that SHA. A failed, cancelled, pending, or missing applicable check blocks deployment until the underlying issue is fixed and all affected checks are rerun successfully. Record the SHA and successful run links in sanitized deployment evidence.
28. Run `Self-Managed Prod Deploy` from GitHub Actions only after the repository-wide production build gate passes and the server-local environment file is complete. The workflow first runs the frontend Playwright E2E gate on GitHub-hosted Ubuntu; if any E2E test fails, the SSH deployment job does not start. Confirm the self-hosted runner can pull and run `mcr.microsoft.com/playwright:v1.58.2-noble`; the post-deployment MCP browser test intentionally uses this pinned container because Playwright 1.58.2 cannot install Chromium directly on Ubuntu 26.04. Validate with `docker run --rm mcr.microsoft.com/playwright:v1.58.2-noble node --version`. Roll back only by reverting the workflow and documentation together to another Playwright runtime supported by the runner OS. Do not use manual deployment or another workflow entry point to bypass a failed check.

### Ollama Local Model Service Setup

Install Ollama from a trusted server shell and review the installer before production use:

```bash
curl -fsSL https://ollama.com/install.sh -o /tmp/install-ollama.sh
less /tmp/install-ollama.sh
sh /tmp/install-ollama.sh
```

Bind the Ollama service to localhost only:

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
cat <<'EOF' | sudo tee /etc/systemd/system/ollama.service.d/jurisdigta-localhost.conf >/dev/null
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
sudo systemctl restart ollama
```

Pull the configured model and inspect the installed inventory:

```bash
ollama pull qwen3:1.7b
ollama list
ollama ps
```

If `qwen3:1.7b` does not fit the available CPU/RAM/VRAM on `jurisdigta-server`, choose and document a smaller validated fallback model, pull it with Ollama, and update the free/default `ai_model_profiles` row instead of allowing production startup to fail silently.

Validate the local service:

```bash
systemctl is-active --quiet ollama
curl -fsS http://127.0.0.1:11434/api/tags
curl -fsS http://127.0.0.1:11434/v1/models
```

Keep Ollama outside the API container and outside the FastAPI process. JurisDigta API should call Ollama over localhost or the private Docker gateway through the model router; Ollama owns model download, storage, loading, unloading, and runtime memory pressure.

The self-managed production deployment script performs the Ollama install, private bind, `qwen3:1.7b` pull, and health validation by default when `INSTALL_OLLAMA=1`. Set `INSTALL_OLLAMA=0` only for a controlled rollback or a server where Ollama has already been installed and validated manually.

### Secrets And Environment Values

- Server-local environment file path: `/srv/jurisdigta/secrets/jurisdigta.env`.
- Keep secret file permissions at `600`.
- Workstation `.env` files are synced from `.env.example` with `.\scripts\sync_jurisdigta_env.ps1`. Missing keys from `.env.example` must be written as `unknown-variable` so local startup and sync checks can warn without guessing secrets.
- The sync script copies SSH key material from `E:\jurisdigta\ssh` to `%USERPROFILE%\.ssh\jurisdigta` and uses SSH/SCP to publish the full local `.env` to `/srv/jurisdigta/secrets/jurisdigta.env`.
- Keep the dedicated SSH folder local to the workstation. Only public keys belong in `/home/jurisdigta-admin/.ssh/authorized_keys` on the server.
- Required model-credential encryption secret: `AI_MODEL_CREDENTIAL_ENCRYPTION_KEY`.
- Chat provider/model/deployment routing is stored in API database tables, not `LLM_PROVIDER`, `LOCAL_LLM_*`, `OPENAI_MODEL`, or `AZURE_OPENAI_DEPLOYMENT`.
- Local Ollama requests use `LOCAL_LLM_REQUEST_TIMEOUT_SECONDS=600`; the assistant emits a replaceable localized progress status every `LOCAL_LLM_REQUEST_VISIBLE_PROGRESS=15` seconds. Both values must be finite and greater than zero or API startup fails. A local timeout is reported as `local_model_timeout`, never as a network failure and never as permission to fall back to an external provider.
- Seeded free/default local route: provider `local_ollama`, exact model `qwen3:1.7b`, profile `local_ollama_default`. In self-managed Docker production, the API stores the private Docker gateway URL such as `http://172.18.0.1:11434/v1` because `127.0.0.1` inside the API container is not the host Ollama service.
- Production admins can manage local Ollama registry models from the protected AI Model Admin page. The Admin tool lists models through the server-local Ollama API, starts registry pulls, and can physically remove unused models. Ollama must stay bound to localhost or the private Docker gateway; do not expose it through Cloudflare Tunnel, nginx, router NAT, or a public firewall rule.
- Admin removal is intentionally blocked when the model is the seeded/default local model, marked `is_default_for_free`, referenced by an enabled route policy, selected by `LOCAL_LLM_MODEL`, or currently loaded while configured for active routing. Change route policies/defaults first, verify the new model works, then remove the old unused model.
- Seeded paid route for `case`, `basic`, `premium`, and `unlimited`: provider `azure_foundry`, exact model/deployment `gpt-4o-mini`, profile `azure_foundry_gpt_4o_mini`.
- Required Azure Foundry paid-route setup after database initialization: set `ai_model_providers.base_url` and add the API key or token through `/v1/admin/ai-models/providers/{provider_id}/credentials` so the secret is encrypted in `ai_model_credentials`.
- Required embedding values when cloud embeddings are enabled: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_EMBEDDINGS_MODEL`, `AZURE_OPENAI_API_VERSION`, and one of `AZURE_OPENAI_API_KEY` or `AZURE_OPENAI_AD_TOKEN`.
- PostgreSQL usernames, passwords, and connection strings must remain server-local or in a secret manager.
- Required MCP OAuth values in `/srv/jurisdigta/secrets/jurisdigta.env`: `MCP_API_JWT_SECRET`, `MCP_PUBLIC_BASE_URL=https://mcp.jurisdigta.eu`, `MCP_OAUTH_ALLOWED_REDIRECT_HOSTS=chatgpt.com,chat.openai.com,claude.ai,vscode.dev,www.perplexity.ai,localhost,127.0.0.1,::1`, and `MCP_OTP_REUSE_WINDOW_HOURS=24`. This allows hosted callbacks including `https://vscode.dev/redirect`, `https://claude.ai/api/mcp/auth_callback`, and `https://www.perplexity.ai/rest/connections/oauth_callback`. The MCP service accepts loopback `http://localhost/...`, `http://127.0.0.1/...`, and `http://[::1]/...` callbacks directly for Claude Desktop, Claude Code, and local OAuth proxy flows.
- Optional controlled MCP OAuth E2E values in `/srv/jurisdigta/secrets/jurisdigta.env`: keep `MCP_OAUTH_TEST_MFA_BYPASS_ENABLED=false` by default. For explicit Claude connector validation, set `MCP_OAUTH_TEST_MFA_BYPASS_ENABLED=true`, `MCP_OAUTH_TEST_MFA_BYPASS_EMAILS=mcp-claude-test-free@jurisdigta.eu,mcp-claude-test-paid@jurisdigta.eu`, `MCP_OAUTH_TEST_MFA_BYPASS_EXPIRES_AT=2030-01-01T00:00:00Z`, and `JURISDIGTA_E2E_TEST_USER_PASSWORD` in secret storage. Provision or refresh the synthetic accounts with `python scripts/provision_e2e_users.py` from the deployed API environment. Roll back by setting `MCP_OAUTH_TEST_MFA_BYPASS_ENABLED=false`, redeploying/restarting the MCP service, and confirming OAuth login returns the OTP page for those test users.
- Required privileged test-account value in `/srv/jurisdigta/secrets/jurisdigta.env`: `JURISDIGTA_UNLIMITED_ACCESS_EMAILS=mmaideveloper@gmail.com`. Keep this allowlist restricted to approved test/operator accounts, validate it before deploy, and roll back by removing the email from the server-local env file and redeploying/restarting the API.
- Required admin value in `/srv/jurisdigta/secrets/jurisdigta.env`: `JURISDIGTA_ADMIN_EMAILS=mmaideveloper@gmail.com` or another approved operator list. Required owner: JurisDigta infrastructure operator with Cloudflare Access admin rights. Cloudflare Access must protect the admin hostname and forward `cf-access-authenticated-user-email`; validate with an admin role or allowlisted account opening `/app/admin`, seeing Users/model/credential controls, and a non-admin account receiving `403` from admin APIs. Roll back by removing the email from `JURISDIGTA_ADMIN_EMAILS` or changing the user role back to `user`, redeploying/restarting the API, and confirming the admin API rejects the account.
- Required web MFA reuse value in the encrypted USB `codex-agent.env` profile and `/srv/jurisdigta/secrets/jurisdigta.env`: `MFA_REUSE_WINDOW_HOURS=12`. Required owner: JurisDigta infrastructure operator. Apply it with an atomic, permission-preserving update that does not print other environment values, then recreate the API container through the standard production deployment so Docker reloads the env file. Validate with a redacted equality/count check and by confirming a user who completed MFA can log out and sign in again within 12 hours without another MFA challenge. Roll back by setting `MFA_REUSE_WINDOW_HOURS=0`, redeploying/restarting the API, and confirming every new sign-in requires MFA.
- The self-managed deploy script injects `INTERNAL_MCP_BASE_URL=http://jurisdigta-mcp:8070` into the API container so internal assistant law lookups call the dedicated MCP service over the Docker network.
- Public DNS/TLS values may include `jurisdigta.eu`, `www.jurisdigta.eu`, `api.jurisdigta.eu`, `web.jurisdigta.eu`, `agent.jurisdigta.eu`, `services.jurisdigta.eu`, and `admin.jurisdigta.eu`.
- Self-managed court-decision collector default: container `jurisdigta-court-decision-collector`, database `court_decisions_sk`, Docker restart policy `unless-stopped`, no Docker HTTP healthcheck because it is a worker, and log path `/srv/jurisdigta/runs/logs/court-decision-collector.log`.
- Self-managed court-decision collector InfoSud request hardening defaults: `COURT_DECISIONS_SOURCE_TIMEOUT_SECONDS=90`, `COURT_DECISIONS_SOURCE_RETRY_ATTEMPTS=3`, and `COURT_DECISIONS_SOURCE_RETRY_BACKOFF_SECONDS=5`. Retry logs must stay privacy-safe and include only stage/page/size or hashed GUID request context.
- Court-decision priority scheduler defaults: `COURT_DECISIONS_DAILY_NEW_LIMIT=10000`, `COURT_DECISIONS_DISCOVERY_OVERLAP_PAGES=2`, and `COURT_DECISIONS_BACKFILL_PAGES_PER_CYCLE=10`. Apply migration `0003_priority_scheduler.sql` before starting the new worker. Validate that new queue overflow survives restart and UTC rollover, then confirm backfill advances only when the new queue is empty. Roll back by stopping the worker, deploying the previous image, and preserving the scheduler/queue tables for audit and a later retry; do not drop imported decisions or queue state.
- The self-managed deploy script creates/applies the `court_decisions_sk` schema, injects `COURT_DECISIONS_DB_CLOUD` into API/MCP, and starts the court-decision collector with `python -m services.court_decision_collector --run-service`.
- Before starting the collector, the self-managed deploy script creates `/srv/jurisdigta/runs/logs/court-decision-collector.log` and grants the API image runtime user ownership of that file and `/srv/jurisdigta/runs/storage/court-decision-collector/`. Keep the shared `/srv/jurisdigta/runs/logs/` directory owned by the deploy user so host cron jobs can continue writing their own logs.
- Self-managed laws collector default: `LAWS_COLLECTOR_RUN_MODE=continuous`, container `jurisdigta-laws-collector`, `LAWS_WORKER_POLL_SECONDS=3600`, and Docker restart policy `unless-stopped`.
- Legacy scheduled laws collector wrapper path: `/srv/jurisdigta/ops/run_laws_collector_daily.sh`.
- Legacy scheduled laws collector log path: `/srv/jurisdigta/runs/logs/laws-collector-daily-latest.log`.
- Legacy daily cron schedule on `jurisdigta-server`: `15 2 * * *`, using the server timezone.
- Server-local document processor cron wrapper path: `/srv/jurisdigta/ops/run_document_processor.sh`.
- Server-local document processor log path: `/srv/jurisdigta/runs/logs/document-processor-latest.log`.
- Default document processor cron schedule on `jurisdigta-server`: `*/15 * * * *`.
- Default document processor batch limit: `DOCUMENT_PROCESSOR_LIMIT=20`.
- Production API document processing mode: `DOCUMENT_PROCESSOR_OPTION=azure`.
- Server-local status file path: `/srv/jurisdigta/runs/status/system-status.json`.
- API status endpoint: `GET /v1/system/status?minutes=60`, protected by `x-api-key`.
- Service health rule: HTTP-serving services expose privacy-minimized
  `GET /health`; worker and scheduled services report supervisor state,
  freshness, latest run result, and sanitized errors through protected status
  and monitoring paths. Do not publish worker-only services just to expose
  health checks.
- Optional Prometheus exporter path: `/srv/jurisdigta/app/scripts/server/export_system_status_metrics.py`.
- Optional Prometheus exporter port: `127.0.0.1:9108`.
- Optional Ollama Prometheus exporter path: `/srv/jurisdigta/app/scripts/server/export_ollama_metrics.py`.
- Optional Ollama Prometheus exporter port: `127.0.0.1:9109`.
- Optional monitoring stack path: `/srv/jurisdigta/app/Deployment/monitoring`.
- Optional monitoring Docker network setting: `MONITORING_APP_DOCKER_NETWORK=aijuristiction-api_default`, used by status-exporter and Blackbox Exporter to reach `jurisdigta-api` and `jurisdigta-mcp` without exposing API/MCP beyond loopback host ports.
- Optional Grafana default dashboard setting: `GRAFANA_DEFAULT_HOME_DASHBOARD_PATH=/var/lib/grafana/dashboards/jurisdigta-application-performance.json`.
- Cloudflare Tunnel service: `cloudflared.service` on `jurisdigta-server`.
- Cloudflare Tunnel API hostname: `api.jurisdigta.eu` -> `http://127.0.0.1:8080`.
- Cloudflare Tunnel MCP hostname: `mcp.jurisdigta.eu` -> `http://127.0.0.1:8070`, with MCP served by the dedicated MCP service at `/mcp`.
- Cloudflare Tunnel admin hostname: `admin.jurisdigta.eu` -> `http://127.0.0.1:3000`, with Grafana served at `/grafana/`.
- Cloudflare Tunnel web hostname: `web.jurisdigta.eu` -> `http://127.0.0.1:8090` only after the `jurisdigta-web` frontend container serves the intended web app.
- Cloudflare Tunnel assistant hostname: `agent.jurisdigta.eu` -> `http://127.0.0.1:8090`, with JurisDigta account login required before legal users access `/app/assistant`.
- Optional Grafana local URL: `http://127.0.0.1:3000`, accessed by SSH tunnel or through `admin.jurisdigta.eu` protected by Cloudflare Access.
- Optional Grafana public mobile entry URL through Cloudflare Tunnel: `https://admin.jurisdigta.eu/grafana/`.
- Required Grafana secret for local stack: `GRAFANA_ADMIN_PASSWORD`, stored only in `/srv/jurisdigta/app/Deployment/monitoring/.env` or a server-local secret manager.
- GitHub `prod` Environment variable `JURISDIGTA_SSH_HOST`.
- GitHub `prod` Environment secret `JURISDIGTA_SSH_PRIVATE_KEY`, preferably a deploy-only key.
- Optional GitHub `prod` Environment variables: `JURISDIGTA_SSH_PORT`, `JURISDIGTA_SSH_USER`, `JURISDIGTA_DEPLOY_ROOT`, `JURISDIGTA_ENV_FILE`, `JURISDIGTA_WEB_API_BASE_URL`, `JURISDIGTA_API_PORT`, `JURISDIGTA_MCP_PORT`, `JURISDIGTA_WEB_PORT`, and `JURISDIGTA_COURT_DECISIONS_DATABASE_NAME`.
- Repository self-hosted GitHub Actions runner labels: `self-hosted`, `Linux`, `X64`, `jurisdigta-prod`.

### Validation Steps

- `sudo -n true` succeeds for automation-enabled setup.
- `docker --version`, `docker compose version`, `node --version`, `npm --version`, `python3 --version`, `psql --version`, and `gh --version` succeed.
- `systemctl is-active --quiet ollama` succeeds and `curl -fsS http://127.0.0.1:11434/api/tags` lists the configured local model.
- `curl -fsS http://127.0.0.1:11434/v1/models` succeeds for OpenAI-compatible local model clients.
- AI Model Admin can list local Ollama inventory and reports the configured/default model as protected from removal.
- `bash /srv/jurisdigta/app/Deployment/server/setup_jurisdigta_server.sh` is idempotent and completes without package or permission errors.
- `docker run --rm hello-world` succeeds after reconnecting with Docker group membership.
- Repository checkout under `/srv/jurisdigta/app` is on the intended branch.
- PostgreSQL health check succeeds.
- API health check returns HTTP 200 at `http://127.0.0.1:8080/health`.
- Admin model route check with both API keys returns the seeded `local_ollama_default` and `azure_foundry_gpt_4o_mini` profiles, and credential reads are redacted unless `reveal=true` is used by an authorized admin.
- MCP health check returns HTTP 200 at `http://127.0.0.1:8070/health`.
- MCP OAuth metadata at `https://mcp.jurisdigta.eu/.well-known/oauth-protected-resource/mcp` advertises `https://mcp.jurisdigta.eu/mcp` as the protected resource.
- `docker ps --filter name=jurisdigta-court-decision-collector` shows the court-decision collector container running.
- `tail -n 80 /srv/jurisdigta/runs/logs/court-decision-collector.log` shows `processing_judicial_decision` or `waiting_for_new_judicial_decisions` without raw decision text.
- `docker exec aijurisdiction-postgres psql -U "${LOCAL_POSTGRES_USER:-postgres}" -d "${COURT_DECISIONS_DATABASE_NAME:-court_decisions_sk}" -c "SELECT count(*) AS versions, count(embedding_vector) AS versions_with_vector FROM court_decision_versions;"` confirms imported court-decision vectors.
- Repository minimal runnable example succeeds: `python examples/minimal_demo.py`.
- For default continuous mode, `docker ps --filter name=jurisdigta-laws-collector` shows the collector container running and `crontab -l` has no `run_laws_collector_daily.sh` entry.
- For legacy scheduled mode, `crontab -l` contains the daily laws collector wrapper entry and `docker ps -a --filter name=jurisdigta-laws-collector-daily` shows no stuck active collector container after deployment validation.
- A bounded manual scheduled collector run succeeds with `LAWS_WORKER_MAX_PROBES=1 LAWS_COLLECTOR_MAX_RUNNING_TIME=5 LAWS_COLLECTOR_RUN_MODE=scheduled /srv/jurisdigta/ops/run_laws_collector_daily.sh`.
- The latest collector log contains skipped completed ZIP state and either one imported sequential law or `No new laws for SK`.
- `python3 /srv/jurisdigta/app/scripts/server/write_system_status.py --output /srv/jurisdigta/runs/status/system-status.json` writes valid JSON.
- `curl -fsS -H "x-api-key: ${API_KEY:-aijuris}" "http://127.0.0.1:8080/v1/system/status?minutes=60"` returns API, system, laws collector, and error-count sections.
- If Prometheus/Grafana monitoring is enabled, `systemctl status jurisdigta-status-exporter.service --no-pager` shows the exporter active.
- If Prometheus/Grafana monitoring is enabled, `curl -fsS http://127.0.0.1:9108/metrics | head` returns Prometheus text metrics.
- If Prometheus/Grafana monitoring is enabled, `curl -fsS http://127.0.0.1:9109/metrics | grep jurisdigta_ollama_up` returns the Ollama exporter health gauge.
- If Prometheus/Grafana monitoring is enabled, `docker compose -f /srv/jurisdigta/app/Deployment/monitoring/docker-compose.yml ps` shows Prometheus, Grafana, Ollama Exporter, Node Exporter, cAdvisor, and Blackbox Exporter running.
- If Prometheus/Grafana monitoring is enabled, `curl -fsS http://127.0.0.1:9091/-/ready` and `curl -fsS http://127.0.0.1:3000/grafana/api/health` succeed.
- If Prometheus/Grafana monitoring is enabled, `cd /srv/jurisdigta/app && PROMETHEUS_BASE_URL=http://127.0.0.1:9091 python3 examples/monitoring_scrape_demo.py` reports all scrapes and HTTP probes healthy.
- If Prometheus/Grafana monitoring is enabled, Prometheus queries for `jurisdigta_http_requests_total_window`, `jurisdigta_http_request_duration_seconds_avg`, `jurisdigta_users_total`, `jurisdigta_cases_total`, `jurisdigta_ollama_up`, and `jurisdigta_ai_model_output_tokens_window` return aggregate samples.
- `systemctl status cloudflared --no-pager` shows the Cloudflare tunnel active when public hostnames are enabled.
- If Cloudflare Tunnel public hostnames are enabled, `curl -fsS https://api.jurisdigta.eu/health`, `curl -fsS https://agent.jurisdigta.eu/health`, `curl -I https://agent.jurisdigta.eu/app/assistant`, `curl -I https://mcp.jurisdigta.eu/.well-known/oauth-protected-resource/mcp`, and `curl -I https://admin.jurisdigta.eu/grafana/` succeed from outside the server.
- If the frontend web container is enabled, `curl -fsS http://127.0.0.1:8090/health` and `curl -I http://127.0.0.1:8090/privacy` succeed on the server.
- GitHub Actions workflow `Self-Managed Prod Deploy` completes for `repo_ref=main` only after the frontend Playwright E2E gate passes.
- Cloudflare Access protects `agent.jurisdigta.eu` and `admin.jurisdigta.eu` before public use.
- UFW allows only expected ingress, typically SSH; do not expose PostgreSQL, API, Grafana, Prometheus, or exporter ports directly.

### Rollback Notes

- Stop Docker Compose workloads before changing runtime configuration.
- Remove the daily laws collector cron entry with `crontab -l | grep -v 'run_laws_collector_daily.sh' | crontab -`.
- Stop the continuous collector container with `docker stop --time 120 jurisdigta-laws-collector`; use `docker rm -f jurisdigta-laws-collector` only if the container remains stuck.
- Stop the court-decision collector with `docker stop --time 120 jurisdigta-court-decision-collector`; use `docker rm -f jurisdigta-court-decision-collector` only if the container remains stuck.
- Remove the status writer cron entry with `crontab -l | grep -v 'write_system_status.py' | crontab -`.
- Stop the optional status metrics exporter with `sudo systemctl disable --now jurisdigta-status-exporter.service`.
- Stop Ollama with `sudo systemctl disable --now ollama` if local model serving must be rolled back; remove pulled models with `ollama rm <model-tag>` before uninstalling when disk space or licensing requires cleanup.
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

### Production Docker Image Retention

- Required owner: the `jurisdigta-admin` deployment operator with Docker access.
- Every successful `Deployment/server/deploy_jurisdigta_prod.sh` run keeps `:local` plus one `:previous` tag for API, web, document processor, document engine, and laws collector images.
- Retention is finalized only after health validation. Older dangling images and unused build cache are then removed; Docker volumes and `/srv/jurisdigta/runs` are never cleanup targets.
- Validate with `docker image ls --format '{{.Repository}}:{{.Tag}}' | grep -E '^(aijuristiction-api|jurisdigta-(web|document-processor|document-engine|laws-collector)):(local|previous)$'` and `docker system df`.
- Roll back by tagging the affected `:previous` image as `:local`, recreating that service with its normal production arguments, and validating its local health endpoint.
- If cleanup itself causes an operational concern, omit `finalize_image_retention` in a controlled rollback deployment; do not replace it with global volume or runtime-storage deletion.
- Keep `/srv/jurisdigta/secrets/jurisdigta.env` owned by `root:jurisdigta-admin` at mode `0640`; validate with `stat -c '%a %U %G %n' /srv/jurisdigta/secrets/jurisdigta.env`. This is distinct from encrypted USB profile files, which remain mode `0600`.

### Privacy And Compliance Notes

- Treat server environment files, PostgreSQL data, document storage, logs, and backups as sensitive operational data.
- Do not commit or print API keys, PostgreSQL passwords, full connection strings, access tokens, or generated legal documents.
- Keep PostgreSQL and document runtime files outside `databases/` and under `/srv/jurisdigta/.../runs/storage`.
- Preserve deployment and collector logs for traceability, while avoiding personal data and legal-risk content in logs.
- Use database-backed model routing for production-like local starts; `LLM_PROVIDER=mock` is only for deterministic offline testing when explicitly requested.
- Run Ollama as a separate private host model service; do not expose `11434` through Cloudflare, nginx, router NAT, or a public firewall. The self-managed deploy script binds Ollama to the API Docker network gateway so only local containers on the server can reach it, and free-user case data is not sent to external model providers by default.
- Local model routing keeps case content inside JurisDigta-controlled infrastructure, but normal server access controls, retention, deletion, and privacy-safe logging still apply.
- Keep legal-risk outputs subject to human oversight before production traffic is enabled.
- For Cloudflare Tunnel and Access, avoid logging personal data, legal documents, API keys, database credentials, or full user prompts in edge, dashboard, or application logs.

### Encrypted USB environment profile store

- Owner: JurisDigta server operator. The USB encryption/recovery key must be held outside the USB and outside Git/Codex context.
- Prerequisite: complete issue #395 encryption, stable UUID mount, integrity, retention, and recovery controls for `/mnt/jurisdigta-backup`.
- Store profiles under `/mnt/jurisdigta-backup/jurisdigta-env/profiles` with directory mode `0700` and files mode `0600`.
- Install or rotate a profile with `sudo Deployment/server/install_env_usb_profile.sh <profile> <operator-source-file>`; the command never prints values.
- Validate from a developer laptop with `.\scripts\sync_env_profile.ps1 -Mode Pull -Profile codex-agent`. Pinned SSH host verification and per-developer keys are mandatory.
- Revoke a departing developer's SSH key, delete their local `.env`/`.env.dev` and protected backups, and retain only the approved server audit event containing actor, profile, key names, version/checksum, and result.
- Rollback uses the encrypted/versioned USB backup repository from issue #395. Restore into an isolated location, audit names/checksums without values, then materialize atomically.
- If the USB is missing, has the wrong UUID, is read-only/full, or fails integrity validation, fail closed and alert through privacy-safe monitoring. Never fall back to a plaintext laptop push.
