# API database layer (local + PostgreSQL Docker + Azure-ready)

## Recommended approach

For your feature set, use a **hybrid model**:

1. **Relational SQL database** for metadata and relationships.
2. **Object storage** for document/audio binaries.

## Environment variables (local + cloud)

Use these environment variables in local `.env`, Docker, and GitHub environment secrets.

- `DB_OPTION`: `local`, `postgres`, or `azure`
- `STORAGE_OPTION`: `local` or `azure`
- `DB_LOCAL`: local SQLite path relative to the repo root (example: `./runs/storage/api/sqlite/api.sqlite3`)
- `DB_CLOUD`: cloud database connection string (PostgreSQL in Azure)
- `STORE_LOCAL`: local storage root path (example: `./runs/storage/api/files`)
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

Azure Database for PostgreSQL Flexible Server uses the configured
administrator login as the connection string username. Example:

```text
postgresql://jurisadmin:<password>@db-juris-dev.postgres.database.azure.com:5432/aijurisdiction?sslmode=require
```

## Concrete technology choice

### Phase 1 (now): local + Docker + basic cloud portability

- **SQLite** for metadata (`runs/storage/api/sqlite/api.sqlite3`) when `DB_OPTION=local`.
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

Run local PostgreSQL stack from repository root:

```powershell
.\skills\start-postgres\scripts\start_postgres.ps1
```

Mount volumes for local mode:
- repo `runs/storage/api/sqlite` for API SQLite metadata
- repo `runs/storage/api/files` for `STORE_LOCAL`
- Docker PostgreSQL persistence root: `runs/storage/api/postgres/data`
- Legacy local PostgreSQL data is migrated into `runs/storage/api/postgres` on first managed startup.

Run the full local Docker stack (API + PostgreSQL):

```bash
cd api/aijuristiction-api
docker compose up --build
```

The API compose build now uses the repository root as context so the container includes the shared `src/aijurisdictionagents` package plus SQL assets under `databases/api/` and `databases/laws-collector/`.
Do not run the API compose stack and the standalone `start-postgres` API instance at the same time because both use the same PostgreSQL data directory.


## Schema update workflow

`ApiDatabaseStore.initialize()` is idempotent and now serves as the schema bootstrap/migration step for SQLite and PostgreSQL.

Run migrations explicitly before testing/deploying:

```bash
PYTHONPATH=src python scripts/databases/apply_api_db_schema.py --dry-run
PYTHONPATH=src python scripts/databases/apply_api_db_schema.py
```

### Local PostgreSQL + Docker

```bash
.\skills\start-postgres\scripts\start_postgres.ps1 -SkipSchemaUpdate
DB_OPTION=postgres DB_CLOUD=postgresql://postgres:postgres@localhost:5432/aijurisdiction STORAGE_OPTION=local PYTHONPATH=src python scripts/databases/apply_api_db_schema.py
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

- `free` (`none`): assigned on sign-up, max 1 case, 1 day case TTL.
- `case` (`perCase`): €10, max 1 case, unlimited case time, assigned to user/case usage.
- `basic` (`monthly`): €30/month, max 10 cases.
- `premium` (`monthly`): €100/month, max 100 cases.

Status model: `pending`, `paying`, `paid`, `canceled`, `expired`.
For monthly plans, `starts_at` and `ends_at` are set when status switches to `paid`.

`JURISDIGTA_UNLIMITED_ACCESS_EMAILS` defines a comma- or semicolon-separated
case-insensitive allowlist for controlled test/operator accounts. Allowlisted users
receive an internal synthetic `unlimited` plan at runtime so case-count limits,
document-upload limits, and free-plan write TTL restrictions do not apply. The
setting defaults to `mmaideveloper@gmail.com` and should stay limited to explicitly
approved accounts for GDPR/EU AI Act traceability and human-oversight controls.

Minimal runnable example:

```bash
python examples/subscription_minimal_demo.py
```

## AI Model Routing And Usage Ledger (Task #365)

The API database now includes a policy-driven model routing foundation:

- `ai_model_providers`: local or external provider metadata such as `local_ollama`, `azure_foundry`, `openai`, base URL, region, data zone, API version, and health URL.
- `ai_model_profiles`: provider model/deployment metadata plus context window, default-free-plan marker, and price-per-1M-token metadata.
- `ai_model_credentials`: encrypted provider secrets such as API keys or Azure AD tokens. The runtime decrypts these only when a selected route needs them; admin endpoints redact secret values unless an authorized admin explicitly requests reveal.
- `ai_model_groups` and `ai_model_group_users`: optional assignment of users to model groups for staged rollout or premium routing.
- `ai_task_route_policies`: task type plus plan policy with preferred local/external profile, external acknowledgement, EU data-zone requirement, and local fallback flags.
- `ai_model_usage_ledger`: per-request token and estimated cost ledger by user, subscription, case, task type, provider, model, route, and time. Case audit fields also store `session_id`, `question_id`, bounded `question_preview`, `question_sha256`, `answer_id`, and minimal audit metadata so JurisDigta can show which model answered which question without duplicating full legal prompts outside the case history.

Chat model provider, model, deployment, and credentials are resolved from these database tables, not from `LLM_PROVIDER`, `LOCAL_LLM_*`, `OPENAI_MODEL`, or `AZURE_OPENAI_DEPLOYMENT` environment settings. The only supported `LLM_PROVIDER` chat override is explicit `mock` for deterministic offline tests.

Seeded defaults:

- Free/default users route to `local_ollama_default`, provider `local_ollama`, model `qwen3.6:27b`, base URL `http://127.0.0.1:11434/v1`.
- `case`, `basic`, `premium`, and `unlimited` plan routes prefer `azure_foundry_gpt_4o_mini`, provider `azure_foundry`, model/deployment `gpt-4o-mini`, EU data-zone capable. Operators must set the Azure provider endpoint and encrypted credential before paid traffic can use this route.

Authorized case users can inspect this trail through:

```bash
curl -H "x-api-key: $API_KEY" \
  "$API_BASE_URL/v1/cases/$CASE_ID/ai-model-audit?user_id=$USER_ID&limit=50"
```

SQLite bootstrap is handled by `ApiDatabaseStore.initialize()`. PostgreSQL/Azure upgrades are handled by:

```bash
PYTHONPATH=src python scripts/databases/apply_api_db_schema.py
```

Minimal runnable example:

```bash
python examples/minimal_demo.py
python examples/model_routing_minimal_demo.py
```
