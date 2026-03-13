# Databases

This folder contains the local PostgreSQL Docker setup and reusable SQL migration project.

## Local PostgreSQL with pgvector

Start the local database:

```powershell
cd databases
docker compose up -d
```

Default connection values:

- host: `127.0.0.1`
- port: `5432`
- database: `aijurisdiction`
- user: `postgres`
- password: `postgres`

Default local connection string:

```text
postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction
```

The Docker image enables `pgvector`, and the init script creates the `vector` extension on first startup.
The container stores PostgreSQL files under a `PGDATA` subdirectory so the tracked repo placeholder files do not break first-time initialization.

## Migrations

Migration files live under:

```text
databases/migrations/<project>/*.sql
```

Current project:

- `api`: API metadata schema

Apply API migrations against the current environment:

```powershell
$env:DB_OPTION="postgres"
$env:DB_CLOUD="postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction"
python .\scripts\apply_api_db_schema.py
```

Generic migration runner:

```powershell
python .\scripts\apply_db_migrations.py --project api
```

Dry run:

```powershell
python .\scripts\apply_db_migrations.py --project api --dry-run
```

## Azure PostgreSQL Flexible Server

For Azure deployments, use:

- `DB_OPTION=azure`
- `DB_CLOUD=postgresql://<user>:<password>@<server>.postgres.database.azure.com:5432/<database>?sslmode=require`

Then run:

```powershell
python .\scripts\apply_api_db_schema.py
```
