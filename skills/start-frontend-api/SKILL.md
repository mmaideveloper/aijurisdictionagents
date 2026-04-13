---
name: start-frontend-api
description: Start the local React frontend (`frontend/aijurisdictionfronend`) wired to the dev API endpoint by default. Use when asked to "start frontend with api", "run vite against backend", "launch web UI for chat simulation", "wire frontend to dev API", or "debug frontend API chat fetch errors".
---

# Start Frontend API

## Workflow

1. Run the bundled launcher from repository root:
   `.\skills\start-frontend-api\scripts\start_frontend_api.ps1`
2. The launcher verifies API health at `/health` for the configured API URL.
3. When the configured API URL is loopback (`127.0.0.1`/`localhost`) and API is down, it starts API via `start-api`.
4. The launcher starts Vite with `VITE_API_BASE_URL` and `VITE_API_KEY` set for the frontend process.
5. Open `http://127.0.0.1:5173` and sign in with demo credentials (`admin@admin.com` / `admin123`).
6. Create a new case and send a message to verify chat replies come from API.

## Commands

- Foreground start:
  `.\skills\start-frontend-api\scripts\start_frontend_api.ps1`
- Background start:
  `.\skills\start-frontend-api\scripts\start_frontend_api.ps1 -Background`
- Visible console window:
  `.\skills\start-frontend-api\scripts\start_frontend_api.ps1 -ConsoleWindow`
- Install dependencies before start:
  `.\skills\start-frontend-api\scripts\start_frontend_api.ps1 -Install`
- Use custom API URL:
  `.\skills\start-frontend-api\scripts\start_frontend_api.ps1 -ApiBaseUrl http://127.0.0.1:8081`
- Skip API auto-start (fail fast if API is down):
  `.\skills\start-frontend-api\scripts\start_frontend_api.ps1 -SkipApiStart`

## Stop Frontend

If started with `-Background`, stop via:

`Stop-Process -Id (Get-Content .\runs\frontend-local.pid) -Force`

## Environment Notes

- Default frontend URL: `http://127.0.0.1:5173`
- Default API base URL: `https://api-juris-dev.victoriousdesert-e45eec11.westeurope.azurecontainerapps.io`
- Default API key: `aijuris`
- The launcher only sets frontend API env vars for the launched process; it does not modify files.
