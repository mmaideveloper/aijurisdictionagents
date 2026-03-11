---
name: chatsimulatr
description: Start the local chat simulator app at http://127.0.0.1:8090/chat-simulator from this repository. Use when the user asks for "/chatsimulatr", "start chat simulator", or wants a local UI to test API chat flows. This repo-local copy keeps the same skill name available on another computer.
---

# Chat Simulator

## Workflow

1. Run the bundled launcher from repository root:
   `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1`
2. Verify both endpoints are reachable:
   - `http://127.0.0.1:8090/health`
   - `http://127.0.0.1:8090/chat-simulator`
3. Report the simulator URL and the stop command when running in background mode.

## Commands

- Foreground start:
  `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1`
- Background start:
  `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1 -Background`
- Visible console window:
  `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1 -ConsoleWindow`
