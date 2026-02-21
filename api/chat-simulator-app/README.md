# chat-simulator-app

Standalone test application for simulating chat flows against `aijuristiction-api` before frontend deployment.

## Run locally

```bash
cd api/chat-simulator-app
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8090
```

Open `http://localhost:8090/chat-simulator` and set **API base URL** to your API service (default `http://localhost:8080`).

## Endpoints

- `GET /health`
- `GET /chat-simulator`
- `GET /static/*` (simulator assets)

## Minimal runnable example

```bash
cd api/chat-simulator-app
uvicorn app.main:app --port 8090
```
