---
name: chat-simulator
description: Start and verify local chat simulator UI at http://127.0.0.1:8090/chat-simulator. This skill checks `juris-api` on port 8080 and starts it if needed.
---

# Chat Simulator

## Workflow

1. Run:
   `.\skills\chat-simulator\scripts\start_chat_simulator.ps1`
2. The launcher delegates to `chatsimulatr` launcher.
3. It checks API health on `http://127.0.0.1:8080/health`; if API is down, it starts `juris-api`.
4. It starts simulator on `http://127.0.0.1:8090/chat-simulator`.

## Commands

- Foreground start:
  `.\skills\chat-simulator\scripts\start_chat_simulator.ps1`
- Background start:
  `.\skills\chat-simulator\scripts\start_chat_simulator.ps1 -Background`
- Visible console window:
  `.\skills\chat-simulator\scripts\start_chat_simulator.ps1 -ConsoleWindow`
