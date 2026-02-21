from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="AI Juristiction Chat Simulator App",
    version="0.1.0",
    description="Standalone chat simulator application for validating core chat APIs.",
)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
@app.get("/chat-simulator", include_in_schema=False)
def simulator_page() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")
