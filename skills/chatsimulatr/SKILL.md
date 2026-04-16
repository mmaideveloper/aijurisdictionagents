---
name: chatsimulatr
description: Start the local chat simulator app at http://127.0.0.1:8090/chat-simulator from this repository. Use when the user asks for "/chatsimulatr", "start chat simulator", or wants a local UI to test API chat flows. This launcher checks whether `juris-api` is already running on port 8080; if not, it starts `juris-api` (local PostgreSQL + azurefoundry) first, then starts the simulator.
---

# Chat Simulator

## Workflow

1. Run the bundled launcher from repository root:
   `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1`
2. The launcher checks local API on `http://127.0.0.1:8080/health`.
3. If API is not healthy, the launcher starts `juris-api` with:
   - local PostgreSQL (Docker Desktop)
   - `LLM_PROVIDER=azurefoundry`
   - API endpoint `http://127.0.0.1:8080`
4. Verify endpoints are reachable:
   - `http://127.0.0.1:8080/health` (API)
   - `http://127.0.0.1:8090/health` (simulator)
   - `http://127.0.0.1:8090/chat-simulator` (UI)
5. Report simulator URL plus API URL and stop commands when running in background mode.

## Commands

- Foreground start:
  `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1`
- Background start:
  `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1 -Background`
- Visible console window:
  `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1 -ConsoleWindow`
- Custom API binding (still checks/starts `juris-api` on that target):
  `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1 -ApiHost 127.0.0.1 -ApiPort 8080`
