from __future__ import annotations

import html
import json
import logging
import os
import time
from typing import Any
from pathlib import Path
from uuid import uuid4

from collections.abc import Awaitable, Callable
import dotenv
import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.cases_api import router as cases_router
from app.chat.result_metadata import get_law_knowledge_snapshot
from app.chat.api import router as chat_router
from app.ai_model_admin_api import router as ai_model_admin_router
from app.contact_api import router as contact_router
from app.document_templates.api import router as document_templates_router
from app.flow_packs.api import router as flow_packs_router
from app.laws_api import router as laws_router
from app.logging_config import configure_logging
from app.monitoring_daily_stats_api import router as monitoring_daily_stats_router
from app.observability_api import router as observability_router
from app.telemetry import configure_telemetry, instrument_fastapi
from app.system_status_api import router as system_status_router
from app.users.api import router as users_router
from app.versioning import (
    get_api_version,
    get_core_version,
    get_mcp_server_version,
    get_mobile_app_apk_download_url,
    get_mobile_app_release_url,
    get_mobile_app_version,
    get_web_app_version,
)
from app.voice_intent_api import router as voice_intent_router

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.db_migrations import apply_sql_migrations

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_ENV_PATH = _REPO_ROOT / ".env"
dotenv.load_dotenv(_REPO_ENV_PATH, override=False)

API_VERSION = get_api_version()
DEFAULT_API_LLM_PROVIDER = "azurefoundry"
os.environ.setdefault("LLM_PROVIDER", DEFAULT_API_LLM_PROVIDER)
DOCUMENT_PROCESSOR_MODE = (
    os.getenv(
        "DOCUMENT_PROCESSOR_OPTION",
        os.getenv("DOCUMENT_PROCESSOR", "api"),
    ).strip().lower()
    or "api"
)
if DOCUMENT_PROCESSOR_MODE in {"local", "api"}:
    DOCUMENT_PROCESSOR_MODE = "api"
elif DOCUMENT_PROCESSOR_MODE != "azure":
    DOCUMENT_PROCESSOR_MODE = "api"
LOG_LEVEL = configure_logging()
TELEMETRY_MODE = configure_telemetry(
    service_name="aijuristiction-api",
    service_version=API_VERSION,
)
logger = logging.getLogger("aijuristiction-api.http")
_SUPPORTED_LAW_VERSION_COUNTRIES: tuple[str, ...] = ("SK",)
_DEFAULT_CORPORATE_WEB_ORIGINS: tuple[str, ...] = (
    "https://jurisdigta.eu",
    "https://www.jurisdigta.eu",
    "https://web.jurisdigta.eu",
    "https://agent.jurisdigta.eu",
    "https://juridigta.eu",
    "https://www.juridigta.eu",
    "https://web.juridigta.eu",
    "https://agent.juridigta.eu",
)


def _cors_allow_origins() -> list[str]:
    value = os.getenv("CORS_ALLOW_ORIGINS")
    if value:
        return [origin.strip() for origin in value.split(",") if origin.strip()]
    # Browser previews opened from file:// send Origin: null.
    return [*list(_DEFAULT_CORPORATE_WEB_ORIGINS), "null"]


def _cors_allow_origin_regex() -> str | None:
    if os.getenv("CORS_ALLOW_ORIGINS"):
        return None
    # Allow local web/mobile dev servers on localhost or loopback regardless of chosen port.
    return r"^https?://(localhost|127(?:\.\d{1,3}){3}|\[::1\])(?::\d+)?$"


def _configured_db_backend() -> str:
    raw_value = os.getenv("DB_OPTION", "local").strip().lower()
    if raw_value == "postgress":
        return "postgres"
    return raw_value or "local"


def _configured_llm_provider() -> str:
    raw_value = os.getenv("LLM_PROVIDER", DEFAULT_API_LLM_PROVIDER).strip().lower()
    if raw_value in {"", "azure", "azurefoundry"}:
        return "azurefoundry"
    return raw_value


def _llm_health_payload() -> dict[str, str]:
    provider = _configured_llm_provider()
    status = "ok" if provider in {"mock", "azurefoundry", "openai"} else "error"
    payload = {
        "status": status,
        "provider": provider,
    }
    if status == "error":
        payload["message"] = f'Unsupported LLM_PROVIDER "{provider}"'
    return payload


def _database_health_error_payload(*, backend: str) -> dict[str, Any]:
    return {
        "status": "error",
        "service": "aijuristiction-api",
        "error": "database_unavailable",
        "message": f'Database health check failed for backend "{backend}".',
        "database": {
            "status": "error",
            "backend": backend,
        },
    }


def _law_snapshot_payload(*, country_code: str | None) -> dict[str, Any]:
    snapshot = get_law_knowledge_snapshot(country_code)
    return {
        "country_code": (country_code or "").strip().upper() or None,
        "last_law_update_date": snapshot.last_law_update_date,
        "last_law_update_source": snapshot.last_law_update_source,
        "last_collector_run_at": snapshot.last_collector_run_at,
        "last_processed_law": snapshot.last_processed_law,
        "model_knowledge_cutoff_date": snapshot.model_knowledge_cutoff_date,
        "model_knowledge_cutoff_source": snapshot.model_knowledge_cutoff_source,
        "law_reference_links": list(snapshot.reference_links),
    }


def _version_payload() -> dict[str, Any]:
    law_payload = _law_snapshot_payload(country_code=None)
    laws_by_country = {
        country_code.lower(): _law_snapshot_payload(country_code=country_code)
        for country_code in _SUPPORTED_LAW_VERSION_COUNTRIES
    }
    return {
        "service": "aijuristiction-api",
        "version": app.version,
        "api_version": app.version,
        "mcp_server_version": get_mcp_server_version(),
        "core_version": get_core_version(),
        "last_law_update_date": law_payload["last_law_update_date"],
        "last_law_update_source": law_payload["last_law_update_source"],
        "last_collector_run_at": law_payload["last_collector_run_at"],
        "last_processed_law": law_payload["last_processed_law"],
        "model_knowledge_cutoff_date": law_payload["model_knowledge_cutoff_date"],
        "model_knowledge_cutoff_source": law_payload["model_knowledge_cutoff_source"],
        "law_reference_links": law_payload["law_reference_links"],
        "laws_by_country": laws_by_country,
        "mobile_app_version": get_mobile_app_version(),
        "web_app_version": get_web_app_version(),
        "mobile_app_release_url": get_mobile_app_release_url(),
        "mobile_app_apk_download_url": get_mobile_app_apk_download_url(),
    }


def _version_html(payload: dict[str, Any]) -> str:
    body = html.escape(json.dumps(payload, indent=2, sort_keys=True))
    service = html.escape(str(payload["service"]))
    api_version = html.escape(str(payload["api_version"]))
    core_version = html.escape(str(payload["core_version"]))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{service} version</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.5;
    }}
    body {{
      margin: 0;
      padding: 2rem;
      background: Canvas;
      color: CanvasText;
    }}
    main {{
      max-width: 960px;
      margin: 0 auto;
    }}
    h1 {{
      margin: 0 0 0.25rem;
      font-size: 1.8rem;
    }}
    .summary {{
      margin: 0 0 1.5rem;
      color: color-mix(in srgb, CanvasText 72%, Canvas 28%);
    }}
    pre {{
      overflow-x: auto;
      padding: 1rem;
      border: 1px solid color-mix(in srgb, CanvasText 18%, Canvas 82%);
      border-radius: 6px;
      background: color-mix(in srgb, CanvasText 6%, Canvas 94%);
    }}
    a {{
      color: LinkText;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{service}</h1>
    <p class="summary">API {api_version} | Core {core_version} | <a href="/version">JSON version output</a></p>
    <pre>{body}</pre>
  </main>
</body>
</html>"""

app = fastapi.FastAPI(
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
    allow_origin_regex=_cors_allow_origin_regex(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "x-request-id", "x-correlation-id"],
)
app.include_router(chat_router)
app.include_router(ai_model_admin_router)
app.include_router(contact_router)
app.include_router(document_templates_router)
app.include_router(flow_packs_router)
app.include_router(laws_router)
app.include_router(users_router)
app.include_router(cases_router)
app.include_router(voice_intent_router)
app.include_router(observability_router)
app.include_router(monitoring_daily_stats_router)
app.include_router(system_status_router)
instrument_fastapi(app)


@app.on_event("startup")
async def startup_log() -> None:
    store = ApiDatabaseStore.from_env()
    if store.uses_postgres:
        apply_sql_migrations(
            project="api",
            db_option=store.db_option,
            target=store.db_cloud,
            dry_run=False,
        )
    store.initialize()
    law_snapshot = get_law_knowledge_snapshot(None)
    logger.info(
        (
            "API Starting | api_version=%s | core_version=%s | log_level=%s "
            "| llm_provider=%s | db_option=%s | document_processor=%s | last_law_update_date=%s "
            "| law_source=%s | last_collector_run_at=%s | last_processed_law=%s"
        ),
        app.version,
        get_core_version(),
        logging.getLevelName(LOG_LEVEL),
        _configured_llm_provider(),
        store.db_option,
        DOCUMENT_PROCESSOR_MODE,
        law_snapshot.last_law_update_date,
        law_snapshot.last_law_update_source,
        law_snapshot.last_collector_run_at,
        law_snapshot.last_processed_law,
    )


@app.middleware("http")
async def request_id_middleware(
    request: fastapi.Request,
    call_next: Callable[[fastapi.Request], Awaitable[fastapi.Response]],
) -> fastapi.Response:
    request_id = request.headers.get("x-request-id", str(uuid4()))
    correlation_id = request.headers.get("x-correlation-id", request_id)
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - started) * 1000)
    response.headers["x-request-id"] = request_id
    response.headers["x-correlation-id"] = correlation_id
    logger.info(
        "%s %s -> %s (%d ms) request_id=%s correlation_id=%s origin=%s user_agent=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
        correlation_id,
        request.headers.get("origin"),
        request.headers.get("user-agent"),
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: fastapi.Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception for %s %s request_id=%s correlation_id=%s",
        request.method,
        request.url.path,
        getattr(request.state, "request_id", None),
        getattr(request.state, "correlation_id", None),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", None),
            "correlation_id": getattr(request.state, "correlation_id", None),
        },
    )


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    payload = _version_payload()
    return HTMLResponse(_version_html(payload))


@app.get("/health")
def health() -> JSONResponse:
    database_backend = _configured_db_backend()
    llm_payload = _llm_health_payload()
    try:
        store = ApiDatabaseStore.from_env()
        database_backend = store.db_option
        store.check_connection()
    except Exception as exc:
        logger.warning(
            'Database health check failed for backend "%s": %s',
            database_backend,
            exc.__class__.__name__,
        )
        payload = _database_health_error_payload(backend=database_backend)
        payload["llm"] = llm_payload
        return JSONResponse(
            status_code=503,
            content=payload,
        )
    return JSONResponse(
        {
            "status": "ok",
            "service": "aijuristiction-api",
            "llm": llm_payload,
            "database": {
                "status": "ok",
                "backend": database_backend,
            },
        }
    )


@app.get("/version")
def version() -> JSONResponse:
    return JSONResponse(_version_payload())


logger.info(
    "API logging configured at level %s telemetry_mode=%s",
    logging.getLevelName(LOG_LEVEL),
    TELEMETRY_MODE,
)
