---
name: laws-collector
description: Start and monitor the local laws collector worker. Use when asked to run/monitor Slov-Lex collection locally, validate periodic sync behavior, or test laws collector ingestion loops.
---

# Laws Collector

## Workflow

1. Run the startup script from repository root:
   `./skills/laws-collector/scripts/start_laws_collector.ps1`
2. The script resolves Python from `./conda`, `./.conda`, or `PATH`.
3. It sets default environment values for local SQLite collector execution.
4. It starts the worker loop (`services.laws_collector.worker`) to continuously ingest snapshots.

## Commands

- Foreground worker:
  `./skills/laws-collector/scripts/start_laws_collector.ps1`
- One-shot validation (single poll cycle):
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -MaxCycles 1`
- Delta fixture test mode:
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -Fixture delta -MaxCycles 1`

## Environment Notes

- Default backend: SQLite (`LAWS_DB_BACKEND=sqlite`)
- Default DB path: `./databases/laws-collector/sk_laws.sqlite3`
- Poll interval is controlled by `LAWS_WORKER_POLL_SECONDS`
