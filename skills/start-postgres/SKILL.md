---
name: start-postgres
description: Start and verify the local PostgreSQL database for `aijurisdictionagents`. Use when asked to "start postgres", "start postgress", "bring up local db", "run local postgres docker", or "apply local database schema". Prefer this workflow when the user wants reusable local PostgreSQL instances with project-specific storage under `runs/storage/<project>/postgres`, automatic reuse of existing project containers, and schema updates after startup.
---

# Start Postgres

## Workflow

1. Run the bundled startup script from repository root:
   `.\skills\start-postgres\scripts\start_postgres.ps1`
2. Reuse an existing `aijurisdiction-postgres-local` or `aijurisdiction-postgres` container when available.
3. If no project container exists, create a new one directly with Docker using the selected project's init SQL.
4. Wait for the container health check to report `healthy`.
5. Apply schema updates with:
   `python .\scripts\databases\apply_api_db_schema.py`

## Commands

- Start or reuse the default local PostgreSQL instance:
  `.\skills\start-postgres\scripts\start_postgres.ps1`
- Start or reuse the laws collector local PostgreSQL instance:
  `.\skills\start-postgres\scripts\start_postgres.ps1 -ProjectName laws-collector`
- Use a custom host port:
  `.\skills\start-postgres\scripts\start_postgres.ps1 -DatabasePort 5433`
- Use custom database credentials:
  `.\skills\start-postgres\scripts\start_postgres.ps1 -DatabaseName aijurisdiction -DatabaseUser postgres -DatabasePassword postgres`
- Skip schema updates:
  `.\skills\start-postgres\scripts\start_postgres.ps1 -SkipSchemaUpdate`

## Stop Database

- API local PostgreSQL:
  `docker rm -f aijurisdiction-postgres-local`
- Laws collector local PostgreSQL:
  `docker rm -f aijurisdiction-laws-collector-postgres-local`
- Reused API compose database container:
  `docker stop aijurisdiction-postgres`

## Environment Notes

- API PostgreSQL data lives under `runs/storage/api/postgres/data`.
- Laws collector PostgreSQL data lives under `runs/storage/laws-collector/postgres/data`.
- API init SQL lives under `databases/api/initdb`.
- Laws collector init SQL lives under `databases/laws-collector/initdb`.
- The schema update step uses `DB_OPTION=postgres` and `DB_CLOUD=postgresql://...`.
- If legacy data exists under earlier local PostgreSQL folders, the startup script copies the missing local layout into `runs/storage/<project>/postgres` before creating a fresh managed container.
- If an already-running managed container still mounts one of the legacy folders, stop it and rerun the script once so it can switch to `runs/storage/<project>/postgres`.
