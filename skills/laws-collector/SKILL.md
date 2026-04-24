---
name: laws-collector
description: Start and monitor the local laws collector worker. By default it uses local PostgreSQL on Docker Desktop. Use when asked to run/monitor Slov-Lex collection locally, validate periodic sync behavior, or test laws collector ingestion loops.
---

# Laws Collector

## Workflow

1. Run the startup script from repository root:
   `./skills/laws-collector/scripts/start_laws_collector.ps1`
2. The script resolves Python from `./conda`, `./.conda`, or `PATH`.
3. By default it starts or reuses the local PostgreSQL Docker Desktop instance for the laws collector project.
4. It sets the collector environment for PostgreSQL or SQLite, depending on `-DatabaseOption`.
5. It imports default environment variables from the repository `.env` when they are not already set.
6. It starts the worker loop (`services.laws_collector.worker`) and keeps logs visible in the current console or a spawned log window.

## Commands

- Foreground worker:
  `./skills/laws-collector/scripts/start_laws_collector.ps1`
- Background worker with live log tail:
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -Background`
- Visible console window with live logs:
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -ConsoleWindow`
- One-shot validation (single poll cycle):
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -MaxCycles 1`
- One-shot live probe with one law:
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -Fixture live -MaxCycles 1 -MaxProbes 1`
- Delta fixture test mode:
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -Fixture delta -MaxCycles 1`
- SQLite fallback:
  `./skills/laws-collector/scripts/start_laws_collector.ps1 -DatabaseOption sqlite -MaxCycles 1`

## Environment Notes

- Default backend: PostgreSQL (`LAWS_DB_BACKEND=postgres`)
- If `LAWS_DB_CLOUD` is already set (for example in `.env`), the launcher uses that connection directly.
- Otherwise the default PostgreSQL connection comes from `.\skills\start-postgres\scripts\start_postgres.ps1 -ProjectName laws-collector`
- Real embeddings use the shared `LLM_PROVIDER` and embedding settings from `.env` unless the shell already defines them
- SQLite fallback DB path: `./runs/storage/laws-collector/sqlite/sk_laws.sqlite3`
- Default local files path: `./runs/storage/laws-collector/files/sk`
- Poll interval is controlled by `LAWS_WORKER_POLL_SECONDS`
- Live probe batch size is controlled by `LAWS_WORKER_MAX_PROBES` and defaults to `1` for local starts
- `-Background` writes logs to `runs/laws-collector-local.log` and `runs/laws-collector-local.err.log`, then opens a log-tail console automatically.
