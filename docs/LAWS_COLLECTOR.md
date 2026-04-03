# Laws Collector

Architecture diagrams and component-level design are documented in `docs/LAWS_COLLECTOR_ARCHITECTURE.md`.

## Goal

`laws_collector` is a service under `src/services` that selects a country-specific collector implementation and stores the resulting law corpus in a country-specific database.

Current scope:

- pluggable collector selection by `LAWS_COUNTRY`,
- `slovak_laws_collector` implemented now for country `SK`,
- canonical Slovak source model based on `Slov-Lex`,
- draft monitoring model for `NR SR`,
- local runnable SQLite implementation with documents stored in the database,
- schema that can move later to PostgreSQL on Azure.

## Project location

- `src/services/laws_collector/`

## Local database recommendation

If your real target is Azure Database for PostgreSQL and later `pgvector`, the best long-term local choice is:

- PostgreSQL 16 locally, ideally in Docker,
- `pgvector` enabled from the start,
- the same relational model used by the local SQLite bootstrap.

That gives you the cleanest path for:

- SQL compatibility,
- indexing strategy,
- future vector search,
- fewer migration surprises.

However, for this repository I implemented SQLite first because it is:

- already consistent with the current repo style,
- zero-dependency,
- runnable immediately in local demos and tests.

Pragmatic recommendation:

- use the included SQLite store for bootstrapping and tests,
- switch the service to PostgreSQL before large backfills,
- when you move to Azure, use Azure Database for PostgreSQL Flexible Server.

## Cloud target

Recommended production stack:

- Azure Database for PostgreSQL Flexible Server for metadata, versions, and stored documents,
- `pgvector` in PostgreSQL for provision embeddings,
- Azure Container Apps Jobs for scheduled syncs.

## Database storage model

The current solution now stores the actual law documents in the database:

- HTML in `source_artifacts.content_text`
- PDF in `source_artifacts.content_blob`
- normalized structured JSON in `law_versions.normalized_json`

That works in:

- SQLite locally
- PostgreSQL later in Azure using `TEXT` and `BYTEA`

## Important columns

You asked for the fields needed to know what was stored and when to re-download.
These are the most important columns now:

`law_documents`

- `official_name`: the official law name as published
- `lawyer_title`: the practical title lawyers are likely to search for
- `publication_date`
- `law_year`
- `law_number`
- `first_effective_date`
- `parent_law_year` (optional amendment target reference)
- `parent_law_number` (optional amendment target reference)
- `first_stored_at`
- `last_stored_at`
- `last_checked_at`
- `last_download_status`
- `last_download_error`
- `download_attempt_count`
- `source_url`

`law_versions`

- `version_token`
- `effective_from`
- `version_checksum`
- `html_checksum`
- `pdf_checksum`
- `html_bytes`
- `pdf_bytes`
- `normalized_json`
- `stored_at`

`source_artifacts`

- `artifact_kind`
- `source_url`
- `checksum`
- `content_text`
- `content_blob`
- `content_bytes`
- `http_etag`
- `http_last_modified`
- `should_redownload`
- `verification_status`
- `download_error`
- `fetched_at`
- `last_checked_at`

Those columns are the core of the retry/redownload decision.

## Re-download rule

The service should mark a law for re-download when any of these happens:

- source checksum changed
- `ETag` changed
- `Last-Modified` changed
- content length changed unexpectedly
- parser failed
- PDF missing while HTML exists
- HTML missing while metadata says the version exists
- future-effective version is close to becoming active
- previous download ended with an error

## Scheduling recommendation

I would not deploy this as an always-on web container just to poll.
I would deploy it as scheduled jobs.

Recommended split:

1. Delta job:
   - Azure Container Apps Job
   - every 3 hours by default
   - polls recent Slov-Lex changes and future-effective versions

2. Reconciliation job:
   - Azure Container Apps Job
   - once nightly
   - re-checks recent windows, parser failures, and future-effective acts

If you need more freshness, hourly is acceptable for the delta job. I would still keep the nightly reconciliation job because missed updates and delayed consolidated versions are the bigger operational risk than raw polling frequency.

## Vector database path

Do not create a separate vector database first.
The cleanest next step is:

1. Keep normalized provisions in the relational schema.
2. Add an embeddings table keyed by `version_id + anchor`.
3. Store vectors in PostgreSQL with `pgvector`.
4. Combine lexical filters with semantic search.

That keeps:

- exact legal text,
- effective-date filtering,
- provenance,
- embeddings,

in the same persistence boundary.

## Current schema

The SQLite service creates these tables:

- `law_documents`
- `law_versions`
- `law_provisions`
- `source_artifacts`
- `update_events`

This supports:

- immutable version storage,
- provision-level normalization,
- raw artifact retention,
- update event tracking.

## Minimal demo

```powershell
conda activate .\.conda
python examples/laws_collector_minimal_demo.py
```

## CLI seed/update

```powershell
conda activate .\.conda
python -m services.laws_collector --fixture baseline
python -m services.laws_collector --fixture delta
```

## Sequential Slov-Lex process

The Slovak collector now keeps a persisted sequential crawl state in `collector_progress`.

Rules:

- the starting year is fixed to `1993`
- the first target is `1/1993`
- within a year the next probe is `number + 1`
- when a missing law is hit in a past year, the collector jumps to `1/<next year>`
- when a missing law is hit in the current year, the run stops and keeps that missing law as the next probe target
- the database stores the latest collector run timestamp and the last successfully processed law like `234/2026`

Inspect the persisted state:

```powershell
conda activate .\.conda
python -m services.laws_collector --plan-import
```

Run a live sequential Slov-Lex probe loop:

```powershell
conda activate .\.conda
python -m services.laws_collector --run-sequential-import --max-probes 25
```

The live sequential import now downloads the law text from the Slov-Lex static HTML and PDF endpoints, stores that text in the local database, persists `collector_progress`, and computes a real embedding vector through the shared `aijurisdictionagents.llm.embeddings` client before moving to the next law number/year. Large laws are embedded in multiple chunks and averaged into one stored law vector so local runs do not fail on model input limits.
The shared embedding switch now supports:

- `SYSTEM_EMBEDDING_MODEL_OPTION=local` as the default runtime mode
- `SYSTEM_EMBEDDING_MODEL=all-MiniLM-L6-v2` as the default local sentence-transformer model
- repo-local model caching under `aimodels/`
- `SYSTEM_EMBEDDING_MODEL_OPTION=local` as the default for Azure worker deployments
The same live HTML source now also persists structured metadata from the `Informácie o predpise` panel into `law_metadata` and stores dependency edges from the `Vzťahy predpisu` panel in `law_metadata_relations`. That includes:

- law identifier, title, type, approval/publication/effective dates, author, issue reference, legal areas
- `Predpis mení`
- `Predpis je menený`
- `Vykonávacie predpisy`
- `Predpis ruší`

The normalized relation table is intended for later graph traversal, chain visualization, and reconstructing dependencies between final law versions.

Local startup through `.\skills\laws-collector\scripts\start_laws_collector.ps1` also imports defaults from the repository `.env`, so the visible-console path can reuse the configured embedding provider for local PostgreSQL runs.
For local debugging, the worker now defaults to `LAWS_WORKER_MAX_PROBES=1` so a single visible run processes one live SlovLex law instead of exhausting the embedding rate limit with a long batch.
The service also exposes semantic ranking over persisted law vectors through `LawsCollectorService.search_semantic(...)`, which is used by the local-mode tests to verify end-to-end retrieval.

Local execution logs now show:

- the startup embedding runtime line with `embedding_option` and `embedding_model`
- when a law starts processing
- when the document upload reaches the database and its status
- when vectorization starts
- when vectorization finishes with final status
- the total per-law processing time
- an explicit `No new laws for <country>...` message when the run finds nothing new

Example startup log:

- `[laws-collector] startup country=SK db_backend=postgres embedding_option=local embedding_model=all-MiniLM-L6-v2`
- When the Azure ACA job receives `APPLICATIONINSIGHTS_CONNECTION_STRING`, the same worker logs are exported to Application Insights under application name `laws_collector`, which lets the API observability endpoint filter them separately from `api` and `document_processor`.


## Live SlovLex probe test (year/number)

To prove the collector can resolve SlovLex entries by legal act **number/year** starting at **1/1993** and probing forward up to the current date, run:

```bash
RUN_SLOVLEX_LIVE_TEST=1 python -m pytest tests/test_slovlex_live_probe.py -q
```

Optional tuning:

- `SLOVLEX_MAX_NUMBER_PER_YEAR` (default `80`) limits probing depth per year.

A minimal runnable probe example is also available:

```bash
python examples/slovlex_live_probe_demo.py
```

A minimal metadata/relations parsing example is also available:

```powershell
.\.conda\python.exe examples/laws_collector_metadata_demo.py
```

## Environment variables

Add these to `.env` when you start wiring the service into real runs:

- `LAWS_DB_BACKEND=sqlite`
- `LAWS_DB_LOCAL=./runs/storage/laws-collector/sqlite/sk_laws.sqlite3`
- `LAWS_STORAGE_LOCAL=./runs/storage/laws-collector/files/sk`
- `LAWS_DELTA_POLL_HOURS=3`

`LAWS_COUNTRY` selects the country-specific collector implementation. The current implementation supports only `SK`, so the service still defaults to `SK` when the variable is unset.

For Slovakia, the sequential Slov-Lex crawl always starts from `1/1993`. That starting point is no longer environment-configurable.

For PostgreSQL naming, keep the database mapping country-specific:

- Slovakia remains `laws_sk`
- future countries should use `laws_<country_code_lower>`

The current Azure deployment keeps the Slovak override variable `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK`, which feeds the PostgreSQL database used by the Slovak run. It still defaults to `laws_sk`, but you can override it, for example to `laws_collector_sk`.
The laws collector deployment now applies the SQL migrations under `databases/laws-collector/migrations` to that database before updating the Azure Container Apps job.
Azure deployments default the worker embeddings to the local sentence-transformer path through GitHub Environment variables:

- `SYSTEM_EMBEDDING_MODEL_OPTION=local`
- `SYSTEM_EMBEDDING_MODEL=all-MiniLM-L6-v2`

Future cloud settings:

- `LAWS_DB_BACKEND=postgres`
- `LAWS_DB_CLOUD=postgresql://...`
- `LAWS_STORAGE_CLOUD=...`

## 2026 upgrade: full collection + monitoring + per-country PostgreSQL

Implemented upgrades include:

- monitor logic (`plan_updates`) that compares known snapshots vs latest snapshots and flags updates by:
  - missing document/version,
  - changed HTTP headers (`etag` or `last-modified`),
  - changed normalized content checksum.
- richer law metadata stored with each document:
  - `applicable_to`,
  - `superseded_by_url` (link to newer law),
  - `parent_law_year` / `parent_law_number` for Slovak amendment acts that update another law,
  - existing lifecycle timestamps and status fields.
- normalized SlovLex law metadata and dependency storage:
  - `law_metadata` stores the `Informácie o predpise` panel for each stored version,
  - `law_metadata_relations` stores parsed relation edges for `amends`, `amended_by`, `implements`, and `repeals`.
- deterministic vector generation per law version (`embedding_vector`) for semantic retrieval bootstrap.
- PostgreSQL store support (`LAWS_DB_BACKEND=postgres`) plus migration project `databases/laws-collector/migrations`.
- Azure laws deployment now applies those PostgreSQL migrations automatically before the ACA job update.
- per-country database provisioning helper:
  - `python scripts/databases/provision_country_laws_db.py --admin-uri <postgres-admin-uri> --country SK`
  - database name format: `laws_<country_code_lower>` with Slovakia remaining `laws_sk`.

### PostgreSQL migration flow

1) Provision country DB:

```bash
python scripts/databases/provision_country_laws_db.py \
  --admin-uri postgresql://postgres:postgres@127.0.0.1:5433/postgres \
  --country SK
```

2) Apply laws schema migration:

```bash
DB_OPTION=postgres \
DB_CLOUD=postgresql://postgres:postgres@127.0.0.1:5433/laws_sk \
PYTHONPATH=src python scripts/databases/apply_db_migrations.py --project laws
```

3) Run collector against PostgreSQL:

```bash
LAWS_DB_BACKEND=postgres \
LAWS_DB_CLOUD=postgresql://postgres:postgres@127.0.0.1:5433/laws_sk \
PYTHONPATH=src python -m services.laws_collector --fixture baseline
```

## Local worker skill

Start the local worker loop with the new project skill:

```powershell
./skills/laws-collector/scripts/start_laws_collector.ps1 -Fixture baseline -MaxCycles 1
```

This now runs the collector worker (`services.laws_collector.worker`) with local PostgreSQL by default and is useful for repeatable smoke tests against the same local database layout used by the rest of the repo.

For live Slov-Lex sequential probing, set:

```powershell
$env:LAWS_WORKER_FIXTURE = "live"
./skills/laws-collector/scripts/start_laws_collector.ps1 -Fixture live -MaxCycles 1
```

Start it in the background and keep logs visible in a separate console window:

```powershell
./skills/laws-collector/scripts/start_laws_collector.ps1 -Background -Fixture live -MaxCycles 0
```

Open a dedicated foreground console window for collector logs:

```powershell
./skills/laws-collector/scripts/start_laws_collector.ps1 -ConsoleWindow -Fixture live -MaxCycles 0
```

Use SQLite explicitly only when needed:

```powershell
./skills/laws-collector/scripts/start_laws_collector.ps1 -DatabaseOption sqlite -Fixture baseline -MaxCycles 1
```

## Azure Container App deployment (laws-collector)

Deployment assets for a dedicated Azure Container App named `laws-collector` are now included:

- `infra/bicep/laws_collector.job.bicep`
- `infra/scripts/deploy_laws_collector.ps1`
- `infra/bicep/laws_collector.job.parameters.example.json`
- container image definition: `src/services/laws_collector/Dockerfile`
- GitHub Actions workflow: `.github/workflows/laws_collector_build_deploy.yml`

The deploy script builds the image in ACR and deploys it to Azure Container Apps with PostgreSQL env configuration.
The Azure job now runs the real sequential live collector path (`LAWS_WORKER_FIXTURE=live`) and uses `AZURE_LAWS_COLLECTOR_MAX_PROBES` to control how many Slov-Lex probes execute in each scheduled run. The deployment default is `1`.


## Local PostgreSQL debugging

Start the shared local PostgreSQL Docker container:

```powershell
./skills/start-postgres/scripts/start_postgres.ps1 -ProjectName laws-collector -SkipSchemaUpdate
```

This requires the local Docker daemon to be running.

Provision the dedicated laws schema locally:

```powershell
.\.conda\python.exe scripts/databases/provision_country_laws_db.py --admin-uri postgresql://postgres:postgres@127.0.0.1:5433/postgres --country SK
$env:DB_OPTION = "postgres"
$env:DB_CLOUD = "postgresql://postgres:postgres@127.0.0.1:5433/laws_sk"
.\.conda\python.exe scripts/databases/apply_db_migrations.py --project laws
```

Then run the PostgreSQL debug example:

```powershell
$env:LAWS_DB_CLOUD = "postgresql://postgres:postgres@127.0.0.1:5433/laws_sk"
.\.conda\python.exe examples/laws_collector_postgres_debug_demo.py
```

To search the local PostgreSQL `laws_sk` database for a Slovak phrase such as `nájomna zmluva`, run:

```powershell
$env:LAWS_DB_CLOUD = "postgresql://postgres:postgres@127.0.0.1:5433/laws_sk"
$env:LAWS_SEARCH_PHRASE = "nájomna zmluva"
.\.conda\python.exe examples/laws_collector_postgres_phrase_search_demo.py
```

There is also a gated pytest integration test for the same query path:

```powershell
$env:RUN_LOCAL_POSTGRES_LAWS_SEARCH_TEST = "1"
$env:LAWS_DB_CLOUD = "postgresql://postgres:postgres@127.0.0.1:5433/laws_sk"
$env:LAWS_SEARCH_PHRASE = "nájomna zmluva"
.\.conda\python.exe -m pytest tests/test_laws_collector_postgres_phrase_search.py -s
```

The search normalizes Slovak diacritics before matching, so `nájomna zmluva` also matches stored text containing `nájomná zmluva`.

To verify the very first Slovak law (`1/1993`) is downloaded, stored as text, embedded, and reflected in `collector_progress`, run:

```powershell
$env:LAWS_DB_CLOUD = "postgresql://postgres:postgres@127.0.0.1:5433/laws_sk"
.\.conda\python.exe examples/laws_collector_live_first_law_demo.py
```

For interactive debugging of the real sequential collector with logs visible in VS Code, use the workspace launch profiles in [`.vscode/launch.json`](/c:/Projects/aijuristiction/aijurisdictionagents/.vscode/launch.json):

- `Launch Laws Collector (Postgres, Stop On Entry)`:
  starts `python -m services.laws_collector --run-sequential-import --max-probes 1` against `laws_sk` on `127.0.0.1:5433`, stops on the first executable line, loads `.env`, keeps `justMyCode` enabled, and prints collector output in the integrated terminal.
- `Launch Laws Collector (Postgres, Console Logs)`:
  runs the same Postgres-backed sequential import path without forcing the initial stop, while keeping collector logs in the integrated terminal.
- `Launch Laws Collector (Postgres, Mock Embeddings)`:
  runs the same local PostgreSQL ingest path with `LLM_PROVIDER=mock`, which is the easiest way to debug collector flow without stepping into the OpenAI SDK or waiting on provider limits.
- `Attach Laws Collector`:
  attaches to an already running `debugpy` listener on `127.0.0.1:5678`; logs stay in whichever terminal launched that process.
