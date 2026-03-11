---
name: api
description: Start the local aijuristiction API service at http://127.0.0.1:8080 from this repository. Use when the user asks for "/api", "start api locally", "run backend api", or wants API health verified before tests. This repo-local alias keeps the same skill name available on another computer.
---

# API

## Workflow

1. Run the project API launcher from repository root:
   `.\skills\start-api\scripts\start_api.ps1`
2. Choose database mode (`local`, `postgres`, `azure`) and storage mode (`local`, `azure`) when the API should not use the default local SQLite + local storage setup.
3. Verify `GET /health` responds on `http://127.0.0.1:8080/health`.
4. Report the API URL and the stop command when running in background mode.

## Commands

- Foreground start:
  `.\skills\start-api\scripts\start_api.ps1`
- Background start:
  `.\skills\start-api\scripts\start_api.ps1 -Background`
- Visible console window:
  `.\skills\start-api\scripts\start_api.ps1 -ConsoleWindow`
- Mock provider:
  `.\skills\start-api\scripts\start_api.ps1 -Background -LlmProvider mock`
- PostgreSQL metadata:
  `.\skills\start-api\scripts\start_api.ps1 -Background -DatabaseOption postgres -DbCloud "postgresql://postgres:postgres@localhost:5432/aijurisdiction"`
- Azure database and Azure storage:
  `.\skills\start-api\scripts\start_api.ps1 -Background -DatabaseOption azure -DbCloud "<postgres-connection-string>" -StorageOption azure -StoreCloud "<azure-storage-connection-string>"`
