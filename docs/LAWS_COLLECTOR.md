# Laws Collector

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


## Live SlovLex probe test (year/number)

To prove the collector can resolve SlovLex entries by legal act **number/year** starting at **1/2025** and probing forward up to the current date, run:

```bash
RUN_SLOVLEX_LIVE_TEST=1 python -m pytest tests/test_slovlex_live_probe.py -q
```

Optional tuning:

- `SLOVLEX_MAX_NUMBER_PER_YEAR` (default `80`) limits probing depth per year.

A minimal runnable probe example is also available:

```bash
python examples/slovlex_live_probe_demo.py
```

## Environment variables

Add these to `.env` when you start wiring the service into real runs:

- `LAWS_DB_BACKEND=sqlite`
- `LAWS_DB_LOCAL=./databases/laws-collector/sk_laws.sqlite3`
- `LAWS_STORAGE_LOCAL=./storage/laws/sk`
- `LAWS_DELTA_POLL_HOURS=3`

`LAWS_COUNTRY` selects the country-specific collector implementation. The current implementation supports only `SK`, so the service still defaults to `SK` when the variable is unset.

For Slovakia, the sequential Slov-Lex crawl always starts from `1/1993`. That starting point is no longer environment-configurable.

For PostgreSQL naming, keep the database mapping country-specific:

- Slovakia remains `laws_sk`
- future countries should use `laws_<country_code_lower>`

The current Azure deployment keeps the Slovak override variable `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK`, which feeds the `laws_sk` PostgreSQL database for the default Slovak run.

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
- deterministic vector generation per law version (`embedding_vector`) for semantic retrieval bootstrap.
- PostgreSQL store support (`LAWS_DB_BACKEND=postgres`) plus migration project `databases/migrations/laws`.
- per-country database provisioning helper:
  - `python databases/scripts/provision_country_laws_db.py --admin-uri <postgres-admin-uri> --country SK`
  - database name format: `laws_<country_code_lower>` with Slovakia remaining `laws_sk`.

### PostgreSQL migration flow

1) Provision country DB:

```bash
python databases/scripts/provision_country_laws_db.py \
  --admin-uri postgresql://postgres:postgres@127.0.0.1:5432/postgres \
  --country SK
```

2) Apply laws schema migration:

```bash
DB_OPTION=postgres \
DB_CLOUD=postgresql://postgres:postgres@127.0.0.1:5432/laws_sk \
PYTHONPATH=src python databases/scripts/apply_db_migrations.py --project laws
```

3) Run collector against PostgreSQL:

```bash
LAWS_DB_BACKEND=postgres \
LAWS_DB_CLOUD=postgresql://postgres:postgres@127.0.0.1:5432/laws_sk \
PYTHONPATH=src python -m services.laws_collector --fixture baseline
```

## Local worker skill

Start the local worker loop with the new project skill:

```powershell
./skills/laws-collector/scripts/start_laws_collector.ps1 -Fixture baseline -MaxCycles 1
```

This runs the collector worker (`services.laws_collector.worker`) with local SQLite defaults and is useful for repeatable smoke tests.

For live Slov-Lex sequential probing, set:

```powershell
$env:LAWS_WORKER_FIXTURE = "live"
./skills/laws-collector/scripts/start_laws_collector.ps1 -Fixture live -MaxCycles 1
```

## Azure Container App deployment (laws-collector)

Deployment assets for a dedicated Azure Container App named `laws-collector` are now included:

- `infra/bicep/laws_collector.containerapp.bicep`
- `infra/scripts/deploy_laws_collector.ps1`
- `infra/bicep/laws_collector.containerapp.parameters.example.json`
- container image definition: `src/services/laws_collector/Dockerfile`
- GitHub Actions workflow: `.github/workflows/laws_collector_build_deploy.yml`

The deploy script builds the image in ACR and deploys it to Azure Container Apps with PostgreSQL env configuration.


## Local PostgreSQL debugging

Start the shared local PostgreSQL Docker container:

```powershell
./skills/start-postgress/scripts/start_postgress.ps1 -SkipSchemaUpdate
```

This requires the local Docker daemon to be running.

Provision the dedicated laws schema locally:

```powershell
.\.conda\python.exe databases/scripts/provision_country_laws_db.py --admin-uri postgresql://postgres:postgres@127.0.0.1:5432/postgres --country SK
$env:DB_OPTION = "postgres"
$env:DB_CLOUD = "postgresql://postgres:postgres@127.0.0.1:5432/laws_sk"
.\.conda\python.exe databases/scripts/apply_db_migrations.py --project laws
```

Then run the PostgreSQL debug example:

```powershell
$env:LAWS_DB_CLOUD = "postgresql://postgres:postgres@127.0.0.1:5432/laws_sk"
.\.conda\python.exe examples/laws_collector_postgres_debug_demo.py
```
