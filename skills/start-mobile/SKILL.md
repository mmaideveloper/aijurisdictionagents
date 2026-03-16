---
name: start-mobile
description: Start the local Flutter mobile application from this repository, with support for the same skill name used in the local Codex profile. Use when the user asks for "/start-mobile", "start mobile app locally", "run flutter app", "test as android", or "test as iPhone 14". This repo-local alias keeps the skill available on another computer.
---

# Start Mobile

## Workflow

1. Run the project mobile launcher from repository root:
   `.\skills\start-mobile-app\scripts\start_mobile_app.ps1`
2. Choose `localApi` or `publicDevApi` if the mode is not already specified.
3. For `localApi`, choose database mode (`local`, `postgres`, `azure`) and storage mode (`local`, `azure`) unless they are passed as parameters.
4. Verify the app is reachable at `http://127.0.0.1:7357` when using a web device.

## Commands

- Foreground start:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1`
- Background start:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background`
- Visible console window:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -ConsoleWindow`
- Explicit local API:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -ApiMode localApi`
- Local API with PostgreSQL metadata:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -ApiMode localApi -DatabaseOption postgres -DbCloud "postgresql://postgres:postgres@localhost:5432/aijurisdiction"`
- Local API with Azure database and Azure storage:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -ApiMode localApi -DatabaseOption azure -DbCloud "<postgres-connection-string>" -StorageOption azure -StoreCloud "<azure-storage-connection-string>"`
- Explicit public dev API:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -ApiMode publicDevApi -PublicDevApiBaseUrl https://your-dev-api.example.com`

When using `localApi`, `-ConsoleWindow` opens a visible Flutter console and also tails API logs in a separate console window when the API is already running in the background.
