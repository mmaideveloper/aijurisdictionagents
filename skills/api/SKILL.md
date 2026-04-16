---
name: api
description: Start the local aijuristiction API service at http://127.0.0.1:8080 from this repository. Use when the user asks for "/api", "start api locally", "run backend api", or wants API health verified before tests. This alias delegates to `juris-api` defaults: local PostgreSQL + `azurefoundry` on port 8080.
---

# API

## Workflow

1. Run the project API launcher from repository root:
   `.\skills\juris-api\scripts\start_juris_api.ps1`
2. This starts API with fixed defaults:
   - local PostgreSQL (Docker Desktop) via `start-postgres`
   - `LLM_PROVIDER=azurefoundry`
   - API endpoint `http://127.0.0.1:8080`
3. Use `start-api` skill directly only when you intentionally need non-default DB/storage/provider overrides.
4. Verify `GET /health` responds on `http://127.0.0.1:8080/health`.
5. Report the API URL and the stop command when running in background mode.

## Commands

- Foreground start:
  `.\skills\juris-api\scripts\start_juris_api.ps1`
- Background start:
  `.\skills\juris-api\scripts\start_juris_api.ps1 -Background`
- Visible console window:
  `.\skills\juris-api\scripts\start_juris_api.ps1 -ConsoleWindow`
