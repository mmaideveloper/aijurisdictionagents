---
name: laws-collector
description: Start and monitor the local laws collector worker. Use when asked to run/monitor Slov-Lex collection locally, validate periodic sync behavior, or test laws collector ingestion loops.
---

# Laws Collector

## Workflow

1. Run the startup script from repository root:
   `./skills/laws-collector/scripts/start_laws_collector.ps1`
2. The script resolves Python from `./conda`, `./.conda`, or `PATH`.
3. By default it starts or reuses the local PostgreSQL Docker instance for the laws collector project.
4. It sets the collector environment for PostgreSQL or SQLite, depending on `-DatabaseOption`.
5. It starts the worker loop (`services.laws_collector.worker`) and keeps logs visible in the current console or a spawned log window.

## Commands

- Foreground worker:
  `./skills/laws-collector/scripts/start_laws_collector.ps1`
- Background worker with live log tail:
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -Background`
- Visible console window with live logs:
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -ConsoleWindow`
- One-shot validation (single poll cycle):
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -MaxCycles 1`
- Delta fixture test mode:
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -Fixture delta -MaxCycles 1`
- SQLite fallback:
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -DatabaseOption sqlite -MaxCycles 1`

## Environment Notes

- Default backend: PostgreSQL (`LAWS_DB_BACKEND=postgres`)
- Default PostgreSQL connection comes from `.\skills\start-postgres\scripts\start_postgres.ps1 -ProjectName laws-collector`
- SQLite fallback DB path: `./runs/storage/laws-collector/sqlite/sk_laws.sqlite3`
- Default local files path: `./runs/storage/laws-collector/files/sk`
- Poll interval is controlled by `LAWS_WORKER_POLL_SECONDS`
- `-Background` writes logs to `runs/laws-collector-local.log` and `runs/laws-collector-local.err.log`, then opens a log-tail console automatically.
