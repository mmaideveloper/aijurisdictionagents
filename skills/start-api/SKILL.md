---
name: start-api
description: Start and verify the local `aijuristiction-api` service in this monorepo. Use when asked to "start api", "run backend locally", "bring up fastapi", "launch local server", or "health-check the API". Prefer this workflow for reliable local startup with the project `.conda` interpreter, strict default `LLM_PROVIDER=azurefoundry`, optional explicit mock mode, and explicit health verification.
---

# Start API

## Workflow

1. Run the bundled startup script from repository root:
   `.\skills\start-api\scripts\start_api.ps1`
2. Keep default provider (`azurefoundry`) unless deterministic offline testing is needed.
3. Choose database mode (`local`, `postgres`, `azure`) and storage mode (`local`, `azure`) when the API should not use the default local SQLite + local storage setup.
4. When `DatabaseOption=postgres`, the launcher reuses or starts the local Docker PostgreSQL instance through `start-postgres` and upgrades the database schema before starting the API.
5. Verify `GET /health` is reachable at `http://127.0.0.1:8080/health`.
6. Run the minimal example:
   `python examples/minimal_demo.py`

## Commands

- Foreground start (default):
  `.\skills\start-api\scripts\start_api.ps1`
- Background start:
  `.\skills\start-api\scripts\start_api.ps1 -Background`
- Visible console window with live logs:
  `.\skills\start-api\scripts\start_api.ps1 -ConsoleWindow`
- Background start with mock provider:
  `.\skills\start-api\scripts\start_api.ps1 -Background -LlmProvider mock`
- Background start with PostgreSQL metadata:
  `.\skills\start-api\scripts\start_api.ps1 -Background -DatabaseOption postgres -DbCloud "postgresql://postgres:postgres@localhost:5432/aijurisdiction"`
- Background start with Azure database and Azure storage:
  `.\skills\start-api\scripts\start_api.ps1 -Background -DatabaseOption azure -DbCloud "<postgres-connection-string>" -StorageOption azure -StoreCloud "<azure-storage-connection-string>"`
- Custom port:
  `.\skills\start-api\scripts\start_api.ps1 -Port 8081`

## Stop API

If started with `-Background`, stop via:

`Stop-Process -Id (Get-Content .\runs\api-local.pid) -Force`

## Environment Notes

- Default provider is `azurefoundry`.
- Azure Foundry default is strict: if `AZURE_OPENAI_*` settings are incomplete, startup fails instead of silently falling back to `mock`.
- Local starts now enable `LOCAL_LLM_IO_LOGGING=1` by default, so the API logs the exact model request payload and raw model answer in local runs only.
- Default document processing mode is direct in-API processing (`DOCUMENT_PROCESSOR_OPTION=api`, with `local` kept only as a legacy alias).
- Default database mode is `local`.
- Default storage mode is `local`.
- Legacy `-DatabaseOption postgress` is still accepted and normalized to `postgres`.
- For Azure Foundry requests, set:
  `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, and either `AZURE_OPENAI_API_KEY` or `AZURE_OPENAI_AD_TOKEN`.
- For `DatabaseOption=postgres|azure`, set `DB_CLOUD` or pass `-DbCloud`.
- For `DatabaseOption=postgres`, the launcher prefers the local Docker PostgreSQL skill and resolves `DB_CLOUD` from that running instance automatically.
- The PostgreSQL handoff calls `start_postgres.ps1` with explicit named parameters when reusing local connection metadata, so database name/user/password/port are not mis-bound positionally.
- Default local SQLite metadata path is `./runs/storage/api/sqlite/api.sqlite3`.
- Default local file storage path is `./runs/storage/api/files`.
- For `StorageOption=azure`, set `STORE_CLOUD` or pass `-StoreCloud`.
- Use `-LlmProvider mock` for local smoke checks without cloud credentials.
- `-Background` now also opens a live API log tail window automatically, so request/model logs remain visible even when the server is not attached to the current terminal.
