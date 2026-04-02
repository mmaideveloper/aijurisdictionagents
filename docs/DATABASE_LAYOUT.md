# Database Layout

`databases/` is schema-only. Keep SQL migrations, init SQL, and seed data there.

Top-level database projects:

- `databases/api`
- `databases/laws-collector`

Local runtime database data lives under `runs/storage/<project>/`.

Examples:

- API SQLite: `runs/storage/api/sqlite/api.sqlite3`
- API email SQLite: `runs/storage/api/sqlite/email.sqlite3`
- API PostgreSQL cluster data: `runs/storage/api/postgres/data`
- API local file storage: `runs/storage/api/files`
- Laws collector SQLite: `runs/storage/laws-collector/sqlite/sk_laws.sqlite3`
- Laws collector PostgreSQL cluster data: `runs/storage/laws-collector/postgres/data`
- Laws collector local file storage: `runs/storage/laws-collector/files/<country>`

## SQL Asset Layout

API:

- `databases/api/initdb/*.sql`
- `databases/api/migrations/*.sql`
- `databases/api/email/*.sql`

Laws collector:

- `databases/laws-collector/initdb/*.sql`
- `databases/laws-collector/migrations/*.sql`

## Local PostgreSQL

Use the startup skill from repository root:

```powershell
.\skills\start-postgres\scripts\start_postgres.ps1
```

API defaults:

- host: `127.0.0.1`
- port: `5432`
- database: `aijurisdiction`
- user: `postgres`
- storage: `runs/storage/api/postgres/data`

Laws collector defaults:

- host: `127.0.0.1`
- port: `5433`
- database: `laws_sk`
- user: `postgres`
- storage: `runs/storage/laws-collector/postgres/data`

The Docker image enables `pgvector`, and the init SQL creates the `vector` extension on first startup.

## Migration Commands

Apply API schema:

```powershell
$env:DB_OPTION="postgres"
$env:DB_CLOUD="postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction"
python .\scripts\databases\apply_api_db_schema.py
```

Apply API/email SQL migrations directly:

```powershell
python .\scripts\databases\apply_db_migrations.py --project api
python .\scripts\databases\apply_db_migrations.py --project email
```

Provision a local laws database and apply laws migrations:

```powershell
python .\scripts\databases\provision_country_laws_db.py --admin-uri "postgresql://postgres:postgres@127.0.0.1:5433/postgres" --country SK
$env:DB_OPTION="postgres"
$env:DB_CLOUD="postgresql://postgres:postgres@127.0.0.1:5433/laws_sk"
python .\scripts\databases\apply_db_migrations.py --project laws
```

## Rule For New Projects

For any new project:

1. Put database SQL assets under `databases/<projectname>/`.
2. Put local runtime DB data under `runs/storage/<projectname>/`.
3. Use `runs/storage/<projectname>/postgres/data` for local PostgreSQL.
4. Use `runs/storage/<projectname>/sqlite/` for local SQLite files.
