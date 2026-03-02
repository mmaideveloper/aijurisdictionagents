from __future__ import annotations

import os
from uuid import uuid4

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.chat.api import router as chat_router
from app.telemetry import configure_telemetry
from app.versioning import get_api_version, get_core_version

API_VERSION = get_api_version()


def _cors_allow_origins() -> list[str]:
    value = os.getenv("CORS_ALLOW_ORIGINS")
    if value:
        return [origin.strip() for origin in value.split(",") if origin.strip()]
    return [
        "http://localhost:8090",
        "http://127.0.0.1:8090",
        "http://localhost:7357",
        "http://127.0.0.1:7357",
    ]

app = FastAPI(
    title="AI Juristiction API",
    version=API_VERSION,
    description=(
        "API for AI Juristiction services. "
        "Chat endpoints require `x-api-key` header."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "x-request-id"],
)
app.include_router(chat_router)
configure_telemetry(app, service_name="aijuristiction-api", service_version=app.version)


@app.middleware("http")
async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("x-request-id", str(uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/version")
def version() -> JSONResponse:
    return JSONResponse(
        {
            "service": "aijuristiction-api",
            "version": app.version,
            "api_version": app.version,
            "core_version": get_core_version(),
        }
    )
