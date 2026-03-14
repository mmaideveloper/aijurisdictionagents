from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from uuid import uuid4

from collections.abc import Awaitable, Callable
import dotenv

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.cases_api import router as cases_router
from app.chat.api import router as chat_router
from app.logging_config import configure_logging
from app.telemetry import configure_telemetry
from app.services.email_scheduler import EmailScheduler, scheduler_enabled, scheduler_interval_seconds
from app.users.api import router as users_router
from app.versioning import get_api_version, get_core_version

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.db_migrations import apply_sql_migrations

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_ENV_PATH = _REPO_ROOT / ".env"
dotenv.load_dotenv(_REPO_ENV_PATH, override=False)

API_VERSION = get_api_version()
DEFAULT_API_LLM_PROVIDER = "azurefoundry"
os.environ.setdefault("LLM_PROVIDER", DEFAULT_API_LLM_PROVIDER)
EFFECTIVE_LLM_PROVIDER = os.getenv("LLM_PROVIDER", DEFAULT_API_LLM_PROVIDER).strip().lower()
LOG_LEVEL = configure_logging()
logger = logging.getLogger("aijuristiction-api.http")

_email_scheduler_task: asyncio.Task[None] | None = None


async def _email_scheduler_loop() -> None:
    scheduler = EmailScheduler.from_env()
    interval = scheduler_interval_seconds()
    while True:
        processed = scheduler.run_once(limit=50)
        if processed:
            logger.info("Email scheduler processed %s queued messages", processed)
        await asyncio.sleep(interval)



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
app.include_router(users_router)
app.include_router(cases_router)
configure_telemetry(app, service_name="aijuristiction-api", service_version=app.version)


@app.on_event("startup")
async def startup_log() -> None:
    global _email_scheduler_task
    store = ApiDatabaseStore.from_env()
    if store.uses_postgres:
        apply_sql_migrations(
            project="api",
            db_option=store.db_option,
            target=store.db_cloud,
            dry_run=False,
        )
    store.initialize()
    if scheduler_enabled() and _email_scheduler_task is None:
        _email_scheduler_task = asyncio.create_task(_email_scheduler_loop(), name="email-scheduler")

    logger.info(
        "API Starting | api_version=%s | core_version=%s | log_level=%s | llm_provider=%s | db_option=%s",
        app.version,
        get_core_version(),
        logging.getLevelName(LOG_LEVEL),
        EFFECTIVE_LLM_PROVIDER,
        store.db_option,
    )


@app.middleware("http")
async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("x-request-id", str(uuid4()))
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - started) * 1000)
    response.headers["x-request-id"] = request_id
    logger.info(
        "%s %s -> %s (%d ms) request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception for %s %s request_id=%s",
        request.method,
        request.url.path,
        getattr(request.state, "request_id", None),
    )
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


logger.info("API logging configured at level %s", logging.getLevelName(LOG_LEVEL))


@app.on_event("shutdown")
async def shutdown_email_scheduler() -> None:
    global _email_scheduler_task
    if _email_scheduler_task is None:
        return
    _email_scheduler_task.cancel()
    try:
        await _email_scheduler_task
    except asyncio.CancelledError:
        pass
    _email_scheduler_task = None
