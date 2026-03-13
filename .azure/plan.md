# Task 153 Plan

Status: In progress

## Mode

- Mode: MODIFY
- Task: Upgrade database approach from local SQLite-first to PostgreSQL + pgvector for local Docker and Azure deployment

## Current State

- The API metadata store supports `DB_OPTION=local|postgres|azure` in [src/aijurisdictionagents/api_db/config.py](../src/aijurisdictionagents/api_db/config.py).
- Local PostgreSQL support exists only as a simple service in [api/aijuristiction-api/docker-compose.yml](../api/aijuristiction-api/docker-compose.yml).
- Schema bootstrap is code-driven via `ApiDatabaseStore.initialize()` and `scripts/apply_api_db_schema.py`; there is no shared migration project yet.
- Azure infra currently provisions one Container App for the API plus storage/identity/ACR in [infra/bicep/main.bicep](../infra/bicep/main.bicep).
- GitHub deployment workflows deploy the API Container App and infra, but do not provision or migrate a dedicated database container/service.

## Requirements Interpreted From Issue #153

1. Create a new root-level database project under `databases/` for Dockerized PostgreSQL + pgvector.
2. Add a reusable migration project that can apply schema/data changes for project databases.
3. Support local flow: start database container, then run migrations.
4. Support cloud flow with Azure Database for PostgreSQL Flexible Server named `db-juris-dev`.
5. Update `.env` / `.env.example` and deployment automation.
6. Ensure deployment updates do not delete existing database data.
7. Ensure schema updates can be applied both locally and in cloud/GitHub deployment flow.

## Proposed Architecture

### Local

- Add `databases/docker-compose.yml` for PostgreSQL 16 + `pgvector` image.
- Persist PostgreSQL data under repository `databases/postgres/` (bind mount or named volume backed by root `databases/` path).
- Add a migration project under `databases/migrations/` using Alembic, configured for PostgreSQL connection strings.
- Keep SQLite support for existing local workflows unless the task explicitly removes it.

### Cloud

- Extend infra to create Azure Database for PostgreSQL Flexible Server named from `AZURE_POSTGRES_SERVER_NAME`.
- Add env wiring for API to point `DB_OPTION=azure` and `DB_CLOUD` at the Flexible Server endpoint.
- Update deployment scripts/workflows so database infrastructure is provisioned/updated before API rollout.
- Add a migration execution step to deployment flow after database availability and before/with API startup.

## Planned Changes

1. Add `databases/` project structure:
   - `databases/docker-compose.yml`
   - `databases/README.md`
   - `databases/.env.example` or root env integration
   - `databases/migrations/` (Alembic config, env, versions package)
2. Add reusable migration commands/scripts:
   - likely `scripts/db_migrate.ps1`
   - optionally extend `scripts/apply_api_db_schema.py` or replace with migration runner wrapper
3. Update API configuration/docs:
   - `.env.example`
   - API README
   - local start instructions / scripts
4. Extend Azure infra and deployment:
   - `infra/bicep/main.bicep`
   - `infra/scripts/deploy_api.ps1`
   - `.github/workflows/infra_deploy.yml`
   - `.github/workflows/api_build_deploy.yml`
5. Add minimal verification/docs:
   - documented local Docker + migration steps
   - documented cloud deployment variables and order

## Assumptions / Risks

- The Azure target is now Flexible Server instead of a database Container App.
- The migration project will target PostgreSQL first. Existing SQLite bootstrap can remain for backward compatibility unless removed later.
- The current issue text names `db-juris-dev`; I will generalize via `AZURE_POSTGRES_SERVER_NAME` and use `db-juris-dev` as the dev default/example.

## Validation Plan

- Local:
  - start `databases/docker-compose.yml`
  - confirm PostgreSQL/pgvector readiness
  - run migration command against local DB
- Code checks:
  - relevant pytest coverage for migration/config helpers where practical
  - Bicep compile validation
- Documentation:
  - update root/API/database docs with a runnable local example

## Proposed Azure Context

- Subscription: from current repo env/config
- Location: `austriaeast`
- Resource group: `rg-juris-dev`
- Existing API Container App: `api-juris-dev`
- Planned Azure PostgreSQL Flexible Server: `db-juris-dev`

## Execution Notes

- SQLite stays the default local option.
- Docker PostgreSQL + pgvector is the local PostgreSQL option.
- Azure uses PostgreSQL Flexible Server.
