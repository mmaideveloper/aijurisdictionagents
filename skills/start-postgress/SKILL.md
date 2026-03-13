---
name: start-postgress
description: Start and verify the local PostgreSQL database for `aijurisdictionagents`. Use when asked to "start postgres", "start postgress", "bring up local db", "run local postgres docker", or "apply local database schema". Prefer this workflow when the user wants a reusable local PostgreSQL instance with persistent storage under `databases/postgress`, automatic reuse of an existing `aijurisdictionagents` database container, and schema updates after startup.
---

# Start Postgress

## Workflow

1. Run the bundled startup script from repository root:
   `.\skills\start-postgress\scripts\start_postgress.ps1`
2. Reuse an existing `aijurisdiction-postgres-local` or `aijurisdiction-postgres` container when available.
3. If no project container exists, create a new one from `databases/docker-compose.yml`.
4. Wait for the container health check to report `healthy`.
5. Apply schema updates with:
   `python .\databases\scripts\apply_api_db_schema.py`

## Commands

- Start or reuse the default local PostgreSQL instance:
  `.\skills\start-postgress\scripts\start_postgress.ps1`
- Use a custom host port:
  `.\skills\start-postgress\scripts\start_postgress.ps1 -DatabasePort 5433`
- Use custom database credentials:
  `.\skills\start-postgress\scripts\start_postgress.ps1 -DatabaseName aijurisdiction -DatabaseUser postgres -DatabasePassword postgres`
- Skip schema updates:
  `.\skills\start-postgress\scripts\start_postgress.ps1 -SkipSchemaUpdate`

## Stop Database

- Dedicated database-only stack:
  `cd databases; docker compose down`
- Reused API stack database container:
  `docker stop aijurisdiction-postgres`

## Environment Notes

- Persistent Docker database files live under `databases/postgress/data`.
- Initialization SQL files live under `databases/postgress/initdb`.
- The schema update step uses `DB_OPTION=postgres` and `DB_CLOUD=postgresql://...`.
- If legacy data exists under `databases/postgres/data` and the new `databases/postgress/data` folder is empty, the startup script copies that data into the new location before creating a fresh container.
