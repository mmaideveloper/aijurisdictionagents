---
name: chatsimulatr
description: Start the local chat simulator app at http://127.0.0.1:8090/chat-simulator from this repository. Use when the user asks for "/chatsimulatr", "start chat simulator", or wants a local UI to test API chat flows. This launcher always bootstraps local API + local PostgreSQL + `azurefoundry` first, then starts the simulator.
---

# Chat Simulator

## Workflow

1. Run the bundled launcher from repository root:
   `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1`
2. The launcher starts local API through `start-api` with:
   - `-DatabaseOption postgres` (local PostgreSQL)
   - `-LlmProvider azurefoundry`
   - API endpoint `http://127.0.0.1:8081`
3. Verify endpoints are reachable:
   - `http://127.0.0.1:8081/health` (API)
   - `http://127.0.0.1:8090/health` (simulator)
   - `http://127.0.0.1:8090/chat-simulator` (UI)
4. Report simulator URL plus API URL and stop commands when running in background mode.

## Commands

- Foreground start:
  `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1`
- Background start:
  `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1 -Background`
- Visible console window:
  `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1 -ConsoleWindow`
- Custom API binding (still local postgres + azurefoundry):
  `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1 -ApiHost 127.0.0.1 -ApiPort 8081`
