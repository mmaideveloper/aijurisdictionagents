# Azure Application Insights Infra Plan

Status: Validated

## Mode

- Mode: MODIFY
- Task: Add workspace-based Azure Application Insights to the existing ACA infrastructure deployment with the default name `ai-juris-dev`, and wire the API deployment to consume its connection string automatically.

## Workspace Analysis

- The infra template in [infra/bicep/main.bicep](../infra/bicep/main.bicep) already provisions:
  - Log Analytics Workspace
  - Azure Container Apps Environment
  - Azure Container Registry
  - Storage Account
  - PostgreSQL Flexible Server
  - Container App
- The API runtime already supports Azure Monitor via `APPLICATIONINSIGHTS_CONNECTION_STRING` in [api/aijuristiction-api/app/telemetry.py](../api/aijuristiction-api/app/telemetry.py).
- Local and GitHub deployment entrypoints already know how to set secret-backed ACA environment variables:
  - [infra/scripts/deploy_api.ps1](../infra/scripts/deploy_api.ps1)
  - [.github/workflows/api_build_deploy.yml](../.github/workflows/api_build_deploy.yml)

## Requirements

1. Provision Application Insights through infra deployment.
2. Use the resource name `ai-juris-dev` by default.
3. Link it to the existing Log Analytics workspace.
4. Apply the resulting connection string to the API Container App automatically.
5. Update docs and deployment samples.

## Implemented Architecture

### Infrastructure

- Added a workspace-based `Microsoft.Insights/components` resource to [infra/bicep/main.bicep](../infra/bicep/main.bicep).
- Linked it to the Log Analytics workspace via `WorkspaceResourceId`.
- Added outputs for:
  - Application Insights name
  - Application Insights connection string

### Deployment

- Updated [infra/scripts/deploy_api.ps1](../infra/scripts/deploy_api.ps1) to:
  - accept and default `AZURE_APPLICATION_INSIGHTS_NAME` to `ai-juris-dev`
  - detect whether the resource already exists
  - pass the new parameter into the Bicep deployment
  - consume the deployment output connection string
  - set `APPLICATIONINSIGHTS_CONNECTION_STRING=secretref:applicationinsights-connection-string` on the Container App automatically
- Updated [.github/workflows/infra_deploy.yml](../.github/workflows/infra_deploy.yml) to provision or reuse the Application Insights resource.
- Updated [.github/workflows/api_build_deploy.yml](../.github/workflows/api_build_deploy.yml) to query the Application Insights connection string from Azure if no explicit secret is provided.

### Docs and Samples

- Updated [.env.example](../.env.example)
- Updated [infra/bicep/main.parameters.example.json](../infra/bicep/main.parameters.example.json)
- Updated [infra/README.md](../infra/README.md)
- Updated [api/aijuristiction-api/README.md](../api/aijuristiction-api/README.md)

## Validation Proof

- Command: `az bicep build --file infra/bicep/main.bicep`
  - Result: passed with existing non-blocking Bicep warnings
- Command: PowerShell parser check for [infra/scripts/deploy_api.ps1](../infra/scripts/deploy_api.ps1)
  - Result: passed

## Notes

- The API build/deploy workflow still accepts an explicit `APPLICATIONINSIGHTS_CONNECTION_STRING` secret, but it no longer requires one when the infra-managed Application Insights resource exists.
- This task provisions the Application Insights resource and wires its connection string into the API deployment path. It does not add alert rules yet.
