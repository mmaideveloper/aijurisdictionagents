# API database layer (local + PostgreSQL Docker + Azure-ready)

## Recommended approach

For your feature set, use a **hybrid model**:

1. **Relational SQL database** for metadata and relationships.
2. **Object storage** for document/audio binaries.

## Environment variables (local + cloud)

Use these environment variables in local `.env`, Docker, and GitHub environment secrets.

- `DB_OPTION`: `local`, `postgres`, or `azure`
- `STORAGE_OPTION`: `local` or `azure`
- `DB_LOCAL`: local SQLite path relative to the repo root (example: `./databases/api.sqlite3`)
- `DB_CLOUD`: cloud database connection string (PostgreSQL in Azure)
- `STORE_LOCAL`: local storage root path (example: `./storage`)
- `STORE_CLOUD`: Azure Blob URL prefix for case artifacts (example: `https://<storage-account>.blob.core.windows.net/<container-name>`)

If you set:
- `DB_OPTION=postgres`, then `DB_CLOUD` is required.
- `DB_OPTION=azure`, then `DB_CLOUD` is required.
- `STORAGE_OPTION=azure`, then `STORE_CLOUD` is required.

This aligns with your GitHub environment secrets plan:
- `DB_OPTION=azure`
- `STORAGE_OPTION=azure`
- `DB_CLOUD=...`
- `STORE_CLOUD=...`

Azure Database for PostgreSQL Flexible Server uses the login format
`<admin>@<server>` in the connection string username. In the URI, that `@`
must be percent-encoded as `%40`. Example:

```text
postgresql://jurisadmin%40db-juris-dev:<password>@db-juris-dev.postgres.database.azure.com:5432/aijurisdiction?sslmode=require
```

## Concrete technology choice

### Phase 1 (now): local + Docker + basic cloud portability

- **SQLite** for metadata (`databases/api.sqlite3`) when `DB_OPTION=local`.
- **PostgreSQL** for metadata when `DB_OPTION=postgres` (recommended via Docker locally).
- Filesystem blob folder for stored assets.

### Phase 2 (production): scalable and resilient

- **Azure Database for PostgreSQL** for metadata.
- **Azure Blob Storage** for documents/audio/generated files.


## Case-scoped storage layout

For both local and azure modes, all case artifacts are written under a `case_id` folder/prefix:

- Documents: `<case_id>/<kind>/v<version>_<filename>`
- Communications: `<case_id>/communications/<communication_id>.<ext>`

This guarantees every case has an isolated storage namespace.

## Supported domain entities

- `users`: sign-up and login metadata.
- `companies`: company profile.
- `company_users`: user/company association and role.
- `cases`: user/company legal cases.
- `case_documents`: source/generated document metadata + versions.
- `case_communications`: chat/audio transcript references and summaries.

## Minimal demo

```bash
PYTHONPATH=src python examples/api_database_minimal_demo.py
```

Azure config-only demo:

```bash
PYTHONPATH=src python examples/azure_api_postgres_config_demo.py
```

## Docker notes

Run local PostgreSQL stack:
```bash
cd databases
docker compose up -d
```

Or from repository root:

```powershell
.\skills\start-postgress\scripts\start_postgress.ps1
```

Mount volumes for local mode:
- repo `databases/` for SQLite fallback and PostgreSQL data
- API-local `storage/` for `STORE_LOCAL`
- Docker PostgreSQL persistence root: `databases/postgress/data`

Run the full local Docker stack (API + PostgreSQL):

```bash
cd api/aijuristiction-api
docker compose up --build
```

The API compose build now uses the repository root as context so the container includes the shared `src/aijurisdictionagents` package plus SQL migrations under `databases/migrations/`.
Do not run the API compose stack and the dedicated `databases/` stack at the same time because both use the same PostgreSQL data directory.


## Schema update workflow

`ApiDatabaseStore.initialize()` is idempotent and now serves as the schema bootstrap/migration step for SQLite and PostgreSQL.

Run migrations explicitly before testing/deploying:

```bash
PYTHONPATH=src python databases/scripts/apply_api_db_schema.py --dry-run
PYTHONPATH=src python databases/scripts/apply_api_db_schema.py
```

### Local PostgreSQL + Docker

```bash
cd databases
docker compose up -d
cd ../..
DB_OPTION=postgres DB_CLOUD=postgresql://postgres:postgres@localhost:5432/aijurisdiction STORAGE_OPTION=local PYTHONPATH=src python databases/scripts/apply_api_db_schema.py
```

### Cloud rollout checklist (Azure)

1. Deploy code/image to Container Apps.
2. Ensure Container App configuration includes:
   - `DB_OPTION=azure`
   - `DB_CLOUD` sourced from a Container Apps secret
   - `STORAGE_OPTION=azure`
   - `STORE_CLOUD` set to the Azure Blob URL prefix
3. Restart/revision rollout the Container App; startup now runs schema initialization automatically.
4. Verify with health endpoint and logs (`db_option=azure` at startup).

## Azure Container Apps notes

- Use a secret for `DB_CLOUD`.
- `STORE_CLOUD` is a blob URL prefix, not a storage account key/connection string.
- Keep `DB_OPTION=azure` and `STORAGE_OPTION=azure`.
- `infra/scripts/deploy_api.ps1` now generates the Azure PostgreSQL connection string, stores it as a Container Apps secret, and points `DB_CLOUD` at that secret reference automatically.
- This commit validates env contracts; production adapters can be plugged in next.

## Subscription model (Task #86)

The API database now seeds four subscription plans and tracks user subscription lifecycle:

- `free` (`none`): assigned on sign-up, max 5 cases, 1 day case TTL.
- `case` (`perCase`): €10, max 1 case, unlimited case time, assigned to user/case usage.
- `basic` (`monthly`): €30/month, max 10 cases.
- `premium` (`monthly`): €100/month, max 100 cases.

Status model: `pending`, `paying`, `paid`, `canceled`, `expired`.
For monthly plans, `starts_at` and `ends_at` are set when status switches to `paid`.

Minimal runnable example:

```bash
python examples/subscription_minimal_demo.py
```
