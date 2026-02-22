from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

SIMULATOR_PACKAGE = "chat-simulator-app"


app = FastAPI(
    title="AI Juristiction Chat Simulator App",
    version="0.1.1",
    description="Standalone chat simulator application for validating core chat APIs.",
)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {
        "service": "chat-simulator-app",
        "version": app.version,
        "simulator_version": _get_simulator_version(),
    }


@app.get("/", include_in_schema=False)
@app.get("/chat-simulator", include_in_schema=False)
def simulator_page() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


def _get_simulator_version() -> str:
    try:
        return package_version(SIMULATOR_PACKAGE)
    except PackageNotFoundError:
        return app.version
