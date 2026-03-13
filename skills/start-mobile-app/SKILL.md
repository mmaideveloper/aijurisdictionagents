---
name: start-mobile-app
description: Start and verify the local Flutter mobile app in this monorepo. Use when asked to "start mobile app", "run flutter app locally", "launch mobile web target", "open the mobile client in Chrome", or "bring up the Flutter frontend against the local API or public dev API". Prefer this workflow for reliable local startup with the installed Flutter SDK, default Chrome target, an explicit API mode choice (`localApi` or `publicDevApi`), and web readiness verification.
---

# Start Mobile App

## Workflow

1. Ask which API mode to use: `localApi` or `publicDevApi`.
2. If `localApi` is selected, choose database mode: `local`, `postgres`, or `azure`, and storage mode: `local` or `azure`.
3. Run the bundled launcher from repository root:
   `.\skills\start-mobile-app\scripts\start_mobile_app.ps1`
4. If `localApi` is selected and the API is not already up, start the local API in a visible console window so live logs stay on screen.
5. When local API mode uses `DatabaseOption=postgres`, the API startup path reuses or starts the local Docker PostgreSQL instance and upgrades schema automatically.
6. Verify the Flutter web target responds at `http://127.0.0.1:7357`.

## Commands

- Foreground start on Chrome:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1`
- Visible console window with Flutter logs:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -ConsoleWindow`
- Background start on Chrome:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background`
- Background start without opening a browser tab:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -NoOpen`
- Explicit local API mode:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -ApiMode localApi`
- Explicit local API mode with PostgreSQL metadata:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -ApiMode localApi -DatabaseOption postgres -DbCloud "postgresql://postgres:postgres@localhost:5432/aijurisdiction"`
- Explicit local API mode with Azure database and Azure storage:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -ApiMode localApi -DatabaseOption azure -DbCloud "<postgres-connection-string>" -StorageOption azure -StoreCloud "<azure-storage-connection-string>"`
- Explicit public dev API mode:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -ApiMode publicDevApi -PublicDevApiBaseUrl https://your-dev-api.example.com`
- Use a different Flutter device:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Device windows`
- Override API base URL:
  `.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -ApiBaseUrl http://10.0.2.2:8080`

## Stop Mobile App

If started with `-Background`, stop via:

`Stop-Process -Id (Get-Content .\runs\mobile-app.pid) -Force`

## Environment Notes

- Default Flutter device is `chrome`.
- Default web URL is `http://127.0.0.1:7357`.
- By default, the launcher opens the app URL in the browser after the web target becomes ready.
- Use `-ConsoleWindow` when you want live Flutter logs in a separate terminal window instead of background log files.
- For `localApi`, default API URL is `http://127.0.0.1:8080`.
- For `localApi`, the launcher now also asks for database mode (`local`, `postgres`, `azure`) and storage mode (`local`, `azure`) unless they are passed as parameters.
- `-DatabaseOption postgress` is accepted and normalized to `postgres`.
- If `DatabaseOption` is `postgres` or `azure`, the launcher requires `DB_CLOUD` or `-DbCloud`.
- If `StorageOption` is `azure`, the launcher requires `STORE_CLOUD` or `-StoreCloud`.
- For `publicDevApi`, the launcher uses `-PublicDevApiBaseUrl`, `PUBLIC_DEV_API_BASE_URL`, or `AIJ_PUBLIC_DEV_API_URL`. If none are set, it prompts for the URL.
- The local API path uses `start-api -ConsoleWindow`, so request logs stay visible in the API console window.
- The local API path inherits PostgreSQL schema upgrades from `start-api` when `DatabaseOption=postgres`.
- Default API key is `aijuris`.
- The launcher prefers Flutter from `%USERPROFILE%\develop\flutter\bin\flutter.bat`, then falls back to `flutter` on `PATH`.
