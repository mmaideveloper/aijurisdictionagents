---
name: start-email
description: Start and monitor the local email scheduler for `aijuristiction-api`. Use when asked to "start email scheduler", "run local email worker", "start email outbox processor", or "deliver queued emails locally". Prefer this workflow for reliable local scheduler startup with the repo `.env`, shared local PostgreSQL on `127.0.0.1:5432`, and log capture under `runs/`.
---

# Start Email

## Workflow

1. Run the bundled startup script from repository root:
   `.\skills\start-email\scripts\start_email_scheduler.ps1`
2. The launcher loads default values from the repository `.env` when the shell does not already define them.
3. If the scheduler uses PostgreSQL and no explicit `EMAIL_DB_CLOUD` is set, the launcher reuses or starts the local API PostgreSQL instance through `start-postgres`.
4. It starts `python -m app.email_scheduler_main` from `api/aijuristiction-api`.
5. In background mode it writes logs to `runs/email-scheduler-local.log` and `runs/email-scheduler-local.err.log`.

## Commands

- Foreground start:
  `.\skills\start-email\scripts\start_email_scheduler.ps1`
- Background start:
  `.\skills\start-email\scripts\start_email_scheduler.ps1 -Background`
- Visible console window with live logs:
  `.\skills\start-email\scripts\start_email_scheduler.ps1 -ConsoleWindow`
- Background start without opening a log-tail window:
  `.\skills\start-email\scripts\start_email_scheduler.ps1 -Background -SkipLogTail`

## Stop Scheduler

- If started with `-Background`:
  `Stop-Process -Id (Get-Content .\runs\email-scheduler-local.pid) -Force`

## Environment Notes

- Default scheduler mode is enabled with `EMAIL_SCHEDULER_ENABLED=true`.
- Default local email DB should point to the shared local PostgreSQL API database, for example:
  `EMAIL_DB_CLOUD=postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction`
- When `EMAIL_DB_CLOUD` is unset and PostgreSQL is selected, the launcher resolves it from the local API Postgres skill.
- Queue rows are read from `email_outbox`.
- Background log files live under `runs/`.
