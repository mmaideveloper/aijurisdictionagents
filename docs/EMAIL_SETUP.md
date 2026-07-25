# Email Setup

The repository uses `info@jurisdigta.eu` as the public contact address and `no-reply@jurisdigta.eu` as the outbound SMTP sender.

## SMTP settings

Set these values when real delivery is required:

```env
EMAIL_TRANSPORT=smtp
EMAIL_SENDER=no-reply@jurisdigta.eu
EMAIL_SMTP_HOST=mail.webhouse.sk
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USE_TLS=true
EMAIL_SMTP_USERNAME=no-reply@jurisdigta.eu
EMAIL_SMTP_PASSWORD=<set from environment or secret store>
```

For local queue-only testing, keep `EMAIL_TRANSPORT=log`. The API still writes messages to the email outbox, but the scheduler logs only safe delivery metadata instead of the full email body.

## Branded non-OTP templates

Non-OTP outbound emails use the JurisDigta branded HTML template in `api/aijuristiction-api/app/services/email_templates.py` with a readable plain-text fallback. The template uses inline CID SVG header and footer assets so mail clients do not load remote tracking images.

Styled templates currently cover:

- account welcome / registration-complete notification
- subscription change requested
- subscription status and payment notifications
- generated case-document package delivery
- legacy non-OTP outbox messages normalized by the email scheduler before delivery

Generated case-document emails contain one revocable guest link scoped to one
rendered PDF. They do not attach legal-document bytes and do not grant case,
chat, source-text, or other-document access. The recipient does not need an
account: opening `/shared-documents/{opaque_token}` requests a six-digit code at
the email address selected by the sender. The code expires after 10 minutes and
the verified document session after 30 minutes of inactivity.

The sender's active UI language is captured when sharing and controls the
invitation, verification email, and guest viewer (EN/SK/DE; unsupported values
explicitly fall back to EN). `JURISDIGTA_AGENT_BASE_URL` controls the link base.
`DOCUMENT_SHARE_LIFETIME_DAYS` defaults to 7 and is bounded to 1-30 days.

Share tokens, OTPs, and document sessions are stored only as hashes. Recipient
email is encrypted at rest with the existing application credential-protection
key chain. Responses use no-store/no-referrer/no-index protections. Audit events
record only the share id, action, outcome, and timestamp—never email, token,
OTP, case title, filename, document text, or PDF bytes. A case owner can revoke
a share through `DELETE /v1/cases/{case_id}/documents/shares/{share_id}`.

Rollback: disable the frontend share action or revert to the prior API version;
existing shares can be revoked without deleting cases/documents. Purge expired
or revoked operational share rows according to the case retention policy after
retaining only the minimum required audit evidence.

OTP and one-time-code emails remain plain text. This avoids placing verification codes in richer HTML previews or related image payloads and keeps code messages minimal.

Privacy and compliance rules for templates:

- Do not include SMTP secrets, API keys, raw legal document text, or unnecessary special-category personal data in templates.
- Keep generated legal-document emails generic and limited to one protected share link; do not include case/document metadata or attachments.
- The log transport records recipient, subject, body length, HTML presence, and attachment count, not full HTML or OTP body content.

## Local scheduler

Start the local email scheduler with the project skill:

```powershell
.\skills\start-email\scripts\start_email_scheduler.ps1 -Background
```

Default local PostgreSQL target:

```env
EMAIL_DB_OPTION=postgres
EMAIL_DB_CLOUD=postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction
```

Background mode writes:

- `runs/email-scheduler-local.log`
- `runs/email-scheduler-local.err.log`
- `runs/email-scheduler-local.pid`

Stop it with:

```powershell
Stop-Process -Id (Get-Content .\runs\email-scheduler-local.pid) -Force
```

## Self-managed server scheduler

`Deployment/server/deploy_jurisdigta_prod.sh` starts one long-running
`jurisdigta-email-scheduler` Docker container from the API image. API and MCP
containers only enqueue messages into `email_outbox`; the scheduler container
claims pending rows and performs delivery.

Self-managed production defaults `EMAIL_SCHEDULER_INTERVAL_SECONDS=5` for the
scheduler container, so queued transactional emails are claimed within about
five seconds under normal load. Keep the value at or above `5`, which is the
runtime minimum enforced by the scheduler.

The scheduler, API, and MCP containers are wired to the same PostgreSQL API
database for email outbox access:

```env
EMAIL_DB_OPTION=postgres
EMAIL_DB_CLOUD=postgresql://<user>:<password>@postgres:5432/<database>
```

For self-managed Docker deployments, `EMAIL_DB_CLOUD` must use the Docker
network host `postgres` inside the API and MCP containers. Do not rely on the
server-local `.env` value if it uses `127.0.0.1`; browser sign-up, login, and
OAuth OTP flows enqueue email from inside containers and will fail against a
loopback-only PostgreSQL URL even when `/health` succeeds.

For production delivery, set the server-local
`/srv/jurisdigta/secrets/jurisdigta.env` to SMTP transport and include the SMTP
password:

```env
EMAIL_TRANSPORT=smtp
EMAIL_SENDER=no-reply@jurisdigta.eu
EMAIL_SMTP_HOST=mail.webhouse.sk
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=no-reply@jurisdigta.eu
EMAIL_SMTP_PASSWORD=<set in the server-local secret file>
```

The self-managed production deploy fails fast when these SMTP settings are
missing, because log transport would mark queued OTP messages as processed
without delivering them to users.

Validate the scheduler without exposing OTP codes:

```bash
docker inspect -f '{{.State.Running}}' jurisdigta-email-scheduler
docker logs --tail 50 jurisdigta-email-scheduler
docker exec aijurisdiction-postgres psql -U "${LOCAL_POSTGRES_USER:-postgres}" -d "${LOCAL_POSTGRES_DB:-aijurisdiction}" -c "SELECT recipient, subject, status, attempts, updated_at FROM email_outbox WHERE metadata_json::text LIKE '%mcp_sign_up_code%' ORDER BY created_at DESC LIMIT 5;"
```

Do not query or paste `email_outbox.body` for OTP messages because it contains
the verification code.

## Azure deployment

`API Build and Deploy` and `infra/scripts/deploy_api.ps1` pass email settings into the API Container App. In GitHub Environments, configure:

- variables: `EMAIL_TRANSPORT=smtp`, `EMAIL_SENDER`, `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`, `EMAIL_SMTP_USE_TLS`, `EMAIL_SMTP_USERNAME`
- secret: `EMAIL_SMTP_PASSWORD`

The deployment stores `EMAIL_SMTP_PASSWORD` as a Container Apps secret and injects it through `secretref:email-smtp-password`. It also sets `EMAIL_DB_OPTION=azure` and `EMAIL_DB_CLOUD=secretref:db-cloud` so the email outbox uses Azure PostgreSQL.

## Azure email scheduler ACA job

Use the dedicated workflow and deploy script when email delivery should run as a scheduled Azure Container Apps Job instead of inside the API process:

- workflow: `.github/workflows/email_build_deploy.yml`
- script: `infra/scripts/deploy_email_scheduler.ps1`
- template: `infra/bicep/email_scheduler.job.bicep`

Recommended GitHub Environment variables:

- `AZURE_EMAIL_SCHEDULER_JOB_NAME=email-scheduler`
- `AZURE_EMAIL_SCHEDULER_CRON_EXPRESSION=*/5 * * * *`

`infra_deploy` now provisions the initial ACA job shell for this scheduler in the selected GitHub Environment. That shell uses a no-op placeholder container so the job can exist before the real image is published. Run `Email Scheduler Build and Deploy` afterward with the manual `deploy=true` input to publish the real image, apply migrations, and inject SMTP secrets. Pull requests and pushes to `main` only run the scheduler tests and image build by default.
Legacy values such as `email_scheduler` are normalized to `email-scheduler` during deployment.

The deploy path applies the PostgreSQL email schema migrations from `databases/api/email` before it updates the ACA Job, and the job runs `python -m app.email_scheduler_job_main` once per trigger.

When this dedicated Azure job is deployed, set `EMAIL_SCHEDULER_ENABLED=false` on the API Container App so API replicas only enqueue emails and the scheduled job performs delivery.

## Test emails

Start the API and chat simulator, then open:

```text
http://127.0.0.1:8090/email-tests
```

The page can trigger:

- registration test email
- mobile-app OTP test email
- payment confirmation test email
- generated documents email

Use **Transport** to choose how the simulator sends the test message:

- `Log`: writes the message as an `.eml` preview and appends a JSON line to the simulator email log. This is the safest local default because it does not send real email.
- `SMTP`: sends through the configured SMTP host and also writes the same `.eml` preview/log entry for auditing.

The page includes direct links to:

- `/internal/email-tests/logs` for the transport log
- `/internal/email-tests/emails` for generated `.eml` previews

Local log transport files are stored under:

```text
runs/chat-simulator-email-tests/
```

## Corporate web contact form

The corporate web contact form posts to the first-party API endpoint `POST /v1/contact`, which sends an email to `info@jurisdigta.eu` from the backend through the configured SMTP transport.

The static page does not open the user's local mail client. Client-side protections include HTML validation, a hidden honeypot field, a minimum submit delay, disposable/test-domain blocking, link blocking, and Cloudflare Turnstile when configured. The topic must be at least 2 characters and the message at least 5 characters. The API repeats the critical email, honeypot, length, link, and Turnstile token checks before sending.

Production anti-spam settings:

```env
CONTACT_CAPTCHA_REQUIRED=true
TURNSTILE_SITE_KEY=<public Turnstile site key injected into corporate web>
TURNSTILE_SECRET_KEY=<private Turnstile secret configured on the API>
CONTACT_RATE_LIMIT_MAX_REQUESTS=5
CONTACT_RATE_LIMIT_WINDOW_SECONDS=600
```

Minimal runnable example:

```bash
python examples/minimal_demo.py
```
