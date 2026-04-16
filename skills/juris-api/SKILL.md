---
name: juris-api
description: Start and verify the local Jurisdiction API at http://127.0.0.1:8080 with local PostgreSQL (Docker Desktop) and `azurefoundry` model provider.
---

# Juris API

## Workflow

1. Run the launcher from repository root:
   `.\skills\juris-api\scripts\start_juris_api.ps1`
2. The launcher delegates to `start-api` with fixed defaults:
   - `-DatabaseOption postgres` (local Docker PostgreSQL)
   - `-LlmProvider azurefoundry`
   - `-BindHost 127.0.0.1`
   - `-Port 8080`
3. Verify API endpoint:
   - `http://127.0.0.1:8080/health`

## Commands

- Foreground start:
  `.\skills\juris-api\scripts\start_juris_api.ps1`
- Background start:
  `.\skills\juris-api\scripts\start_juris_api.ps1 -Background`
- Visible console window:
  `.\skills\juris-api\scripts\start_juris_api.ps1 -ConsoleWindow`
