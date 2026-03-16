# Azure API PostgreSQL Wiring Plan

Status: Validated

## Mode

- Mode: MODIFY
- Task: Update the API Azure deployment so the deployed Container App uses the provisioned Azure Database for PostgreSQL server and database correctly.

## Workspace Analysis

- The Azure infra template in [infra/bicep/main.bicep](../infra/bicep/main.bicep) already provisions:
  - Azure Container Apps environment
  - Azure Container Registry
  - Azure Storage account + blob container
  - Azure Database for PostgreSQL Flexible Server
  - PostgreSQL database on that server
- The deployment script in [infra/scripts/deploy_api.ps1](../infra/scripts/deploy_api.ps1) already:
  - deploys the infra
  - builds and pushes the API image
  - updates the Container App
  - applies the API schema to PostgreSQL
- The API runtime in [api/aijuristiction-api/app/main.py](../api/aijuristiction-api/app/main.py) and [src/aijurisdictionagents/api_db/config.py](../src/aijurisdictionagents/api_db/config.py) already supports `DB_OPTION=azure` with `DB_CLOUD`.

## Current Gaps

1. The deploy script currently injects `DB_CLOUD` through `az containerapp update --set-env-vars`, which exposes the database connection string as a normal environment variable instead of a Container Apps secret.
2. The Azure PostgreSQL connection string helper currently uses the admin username without the Azure Flexible Server login suffix format (`<admin>@<server>`), which is a common source of connection failures.
3. The docs/examples describe Azure PostgreSQL usage, but they do not align tightly enough with the actual secure deployment path for Container Apps.

## Requirements Interpreted From Request

1. Keep using Azure Database for PostgreSQL Flexible Server as the database backend for Azure deployment.
2. Ensure the API Container App is configured to use that PostgreSQL server and database on deploy.
3. Preserve the existing local-first developer workflow.
4. Update docs/examples so the deployment path is explicit and repeatable.

## Proposed Architecture

### Infrastructure

- Keep the existing PostgreSQL Flexible Server + database provisioning in Bicep.
- Reuse current outputs for host/database naming unless a small output adjustment is needed for cleaner script wiring.

### Deployment

- Continue generating the Azure PostgreSQL connection string during deploy.
- Correct the Azure PostgreSQL username format in that connection string.
- Store the database connection string in a Container Apps secret and reference it from the API container environment.
- Keep non-secret configuration as normal env vars.
- Continue running schema migrations against the same Azure PostgreSQL database after infra deployment.

### Runtime

- Keep `DB_OPTION=azure`.
- Keep the API runtime contract unchanged: the app still reads `DB_CLOUD` from env and applies migrations on startup for PostgreSQL/Azure modes.

## Planned Changes

1. Update [infra/scripts/deploy_api.ps1](../infra/scripts/deploy_api.ps1)
   - Fix Azure PostgreSQL connection string generation for Flexible Server login format.
   - Push `DB_CLOUD` as a Container Apps secret instead of plain env text.
   - Keep the migration step pointed at the same connection string.
2. Update [infra/bicep/main.bicep](../infra/bicep/main.bicep) only if needed to support cleaner deployment outputs or secret wiring.
3. Update deployment documentation in:
   - [infra/README.md](../infra/README.md)
   - [docs/API_DATABASE_LAYER.md](../docs/API_DATABASE_LAYER.md)
   - [api/aijuristiction-api/README.md](../api/aijuristiction-api/README.md)
   - [.env.example](../.env.example)
4. Add or update lightweight verification where practical for the changed deployment behavior.

## Validation Plan

- Run targeted tests for the Python API/database layer if the implementation touches runtime contracts.
- Validate the Bicep template compiles successfully.
- Validate the PowerShell deployment script parses and the changed command path is internally consistent.
- Confirm docs/examples reflect the same Azure PostgreSQL wiring that the script now performs.

## Assumptions

- Azure location remains `austriaeast` unless you want a different region.
- Existing resource naming defaults in `.env.example` and `infra/scripts/deploy_api.ps1` remain the desired dev defaults.
- This task is limited to wiring the deployed API to the Azure PostgreSQL server/database, not to adding private networking or Entra-auth database login.

## Execution Notes

- No destructive database changes are planned.
- The implementation should stay backward compatible with local `DB_OPTION=local|postgres` flows.

## Section 7: Validation Proof

- Timestamp: `2026-03-16T17:33:07.5793470+01:00`
- Command: `powershell parser check for infra/scripts/deploy_api.ps1`
  - Result: passed
- Command: `az bicep build --file infra/bicep/main.bicep`
  - Result: passed with pre-existing Bicep warnings only
- Command: `conda run -p ./.conda python examples/azure_api_postgres_config_demo.py`
  - Result: passed
- Command: `.\.conda\python.exe -m pytest tests/test_api_database_layer.py`
  - Result: `6 passed`
