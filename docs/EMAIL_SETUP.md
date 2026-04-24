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

For local queue-only testing, keep `EMAIL_TRANSPORT=log`. The API still writes messages to the email outbox, but the scheduler logs the email instead of sending it.

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

- `AZURE_EMAIL_SCHEDULER_JOB_NAME=email_scheduler`
- `AZURE_EMAIL_SCHEDULER_CRON_EXPRESSION=*/5 * * * *`

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

The corporate web contact form opens a user email draft addressed to `info@jurisdigta.eu`. Because the site is static, spam protection is client-side only: HTML validation, a hidden honeypot field, a minimum submit delay, disposable/test-domain blocking, and link blocking in the message field.

Minimal runnable example:

```bash
python examples/minimal_demo.py
```
