# chat-simulator-app

Standalone test application for simulating chat flows against `aijuristiction-api` before frontend deployment.

## Run locally

```bash
cd api/chat-simulator-app
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8090
```

Open `http://localhost:8090/chat-simulator` and set **API base URL** to your API service (default `http://localhost:8080`).

The simulator now supports:
- creating chat sessions with country/language/discussion type
- submitting a case instruction and uploading text documents
- starting `POST /v1/chat/sessions/{session_id}/stream` and viewing streamed events in real time
- using the new right-side **End User Chat View** panel that renders core messages as user-facing chat bubbles
- selecting reply mode (`ReadUser` or `AIUserSimulatorAgent`) from the right-side bottom chat panel
- setting communication minutes for AI user simulation responses
- sending manual end-user answers from the bottom input box (stored via `POST /v1/chat/messages`)
- fetching result payload and downloading exports as JSON or PDF

## Default simulator inputs

Default values are loaded from:

- `static/default-inputs.json`

Current defaults:
- `language`: `SK`
- `instruction`: `Priprav vzor o prenajme`

## Endpoints

- `GET /health`
- `GET /chat-simulator`
- `GET /version`
- `GET /static/*` (simulator assets)

## Minimal runnable example

```bash
cd api/chat-simulator-app
uvicorn app.main:app --port 8090
```


Version check:

```bash
curl http://localhost:8090/version
```
