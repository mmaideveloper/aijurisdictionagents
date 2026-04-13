---
name: frontend-api
description: Start the local React frontend connected to the dev API endpoint for chat simulation from this repository. Use when asked for "/frontend-api", "run frontend with backend", "launch web app against dev API", or "simulate chat from UI with API".
---

# Frontend API

## Workflow

1. Run the frontend+API launcher from repository root:
   `.\skills\start-frontend-api\scripts\start_frontend_api.ps1`
2. Verify the frontend is reachable at `http://127.0.0.1:5173`.
3. Sign in with demo credentials and send a message in a case chat.

## Commands

- Foreground start:
  `.\skills\start-frontend-api\scripts\start_frontend_api.ps1`
- Background start:
  `.\skills\start-frontend-api\scripts\start_frontend_api.ps1 -Background`
- Visible console window:
  `.\skills\start-frontend-api\scripts\start_frontend_api.ps1 -ConsoleWindow`
