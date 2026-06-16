from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
import os
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

import dotenv
import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.chat.result_metadata import get_law_knowledge_snapshot
from app.logging_config import configure_logging
from app.mcp_api import oauth_router as mcp_oauth_router
from app.mcp_api import router as mcp_router
from app.telemetry import configure_telemetry, instrument_fastapi
from app.versioning import (
    get_core_version,
    get_mcp_server_version,
    get_mobile_app_apk_download_url,
    get_mobile_app_release_url,
    get_mobile_app_version,
    get_web_app_version,
)
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.db_migrations import apply_sql_migrations

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_ENV_PATH = _REPO_ROOT / ".env"
dotenv.load_dotenv(_REPO_ENV_PATH, override=False)

MCP_VERSION = get_mcp_server_version()
DEFAULT_MCP_LLM_PROVIDER = "azurefoundry"
os.environ.setdefault("LLM_PROVIDER", DEFAULT_MCP_LLM_PROVIDER)

LOG_LEVEL = configure_logging()
TELEMETRY_MODE = configure_telemetry(
    service_name="jurisdigta-mcp-server",
    service_version=MCP_VERSION,
)
logger = logging.getLogger("jurisdigta-mcp-server.http")
_SUPPORTED_LAW_VERSION_COUNTRIES: tuple[str, ...] = ("SK",)
_DEFAULT_MCP_ORIGINS: tuple[str, ...] = (
    "https://mcp.jurisdigta.eu",
    "https://mcp.juridigta.eu",
)


def _cors_allow_origins() -> list[str]:
    value = os.getenv("MCP_CORS_ALLOW_ORIGINS", os.getenv("CORS_ALLOW_ORIGINS", ""))
    if value:
        return [origin.strip() for origin in value.split(",") if origin.strip()]
    return [*list(_DEFAULT_MCP_ORIGINS), "null"]


def _cors_allow_origin_regex() -> str | None:
    if os.getenv("MCP_CORS_ALLOW_ORIGINS") or os.getenv("CORS_ALLOW_ORIGINS"):
        return None
    return r"^https?://(localhost|127(?:\.\d{1,3}){3}|\[::1\])(?::\d+)?$"


def _configured_db_backend() -> str:
    raw_value = os.getenv("DB_OPTION", "local").strip().lower()
    if raw_value == "postgress":
        return "postgres"
    return raw_value or "local"


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


def _public_base_url(request: fastapi.Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_proto and forwarded_host:
        proto = forwarded_proto.split(",")[0].strip()
        host = forwarded_host.split(",")[0].strip()
        return f"{proto}://{host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _mcp_instructions_html(*, base_url: str) -> str:
    mcp_url = f"{base_url}/MCP"
    protected_resource_url = f"{base_url}/.well-known/oauth-protected-resource/MCP"
    authorization_server_url = f"{base_url}/.well-known/oauth-authorization-server"
    login_url = f"{base_url}/MCP/login"
    sign_up_url = f"{base_url}/MCP/sign-up"
    version_url = f"{base_url}/version"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>JurisDigta MCP server</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    body {{
      margin: 0;
      background: #f7f7f4;
      color: #1f2933;
    }}
    main {{
      max-width: 960px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    h1, h2 {{
      line-height: 1.15;
    }}
    section {{
      border-top: 1px solid #d7d9d2;
      margin-top: 24px;
      padding-top: 20px;
    }}
    code, pre {{
      background: #eceee8;
      border-radius: 6px;
    }}
    code {{
      padding: 2px 5px;
    }}
    pre {{
      overflow-x: auto;
      padding: 12px;
    }}
    a {{
      color: #0f766e;
    }}
    @media (prefers-color-scheme: dark) {{
      body {{
        background: #151917;
        color: #edf2ef;
      }}
      section {{
        border-color: #39423d;
      }}
      code, pre {{
        background: #222a26;
      }}
      a {{
        color: #5eead4;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>JurisDigta MCP server</h1>
    <p>
      Connect AI assistants to JurisDigta public-law tools through the Model Context Protocol.
      The MCP endpoint is <code>{mcp_url}</code>.
    </p>

    <section>
      <h2>Registration</h2>
      <ol>
        <li>Open <a href="{sign_up_url}">{sign_up_url}</a>.</li>
        <li>Enter your email, phone number, profile details, ID card number, and explicit data-processing consent.</li>
        <li>Confirm the email OTP code to create the account.</li>
        <li>Open <a href="{login_url}">{login_url}</a> to generate a short-lived MCP API key, or let an OAuth-capable assistant complete the browser authorization flow.</li>
      </ol>
      <p>
        MCP API keys are shown once, expire by default after one day, and can be revoked from the user API.
      </p>
    </section>

    <section>
      <h2>Assistant setup</h2>
      <ul>
        <li><strong>ChatGPT custom connector:</strong> create a remote MCP connector and use <code>{mcp_url}</code> as the server URL. Prefer OAuth discovery when available.</li>
        <li><strong>Claude:</strong> add a custom connector or remote MCP server and use <code>{mcp_url}</code>. OAuth-capable Claude clients can discover authorization from this domain.</li>
        <li><strong>VS Code:</strong> add an HTTP MCP server in MCP settings with URL <code>{mcp_url}</code>. If your client cannot use OAuth, pass the generated key as <code>Authorization: Bearer &lt;key&gt;</code>.</li>
        <li><strong>Perplexity and other MCP clients:</strong> use the same remote server URL where custom MCP servers are supported. If custom remote MCP registration is not available in the product UI, use another MCP-compatible host.</li>
      </ul>
    </section>

    <section>
      <h2>Discovery URLs</h2>
      <ul>
        <li>MCP endpoint: <code>{mcp_url}</code></li>
        <li>Protected resource metadata: <a href="{protected_resource_url}">{protected_resource_url}</a></li>
        <li>Authorization server metadata: <a href="{authorization_server_url}">{authorization_server_url}</a></li>
        <li>Version and law freshness: <a href="{version_url}">{version_url}</a></li>
      </ul>
    </section>

    <section>
      <h2>Client documentation</h2>
      <ul>
        <li><a href="https://developers.openai.com/api/docs/mcp">OpenAI remote MCP documentation</a></li>
        <li><a href="https://platform.claude.com/docs/en/agents-and-tools/mcp-connector">Claude MCP connector documentation</a></li>
        <li><a href="https://code.visualstudio.com/docs/agent-customization/mcp-servers">VS Code MCP server documentation</a></li>
      </ul>
    </section>

    <section>
      <h2>Manual header example</h2>
      <pre><code>{{
  "mcpServers": {{
    "jurisdigta": {{
      "type": "http",
      "url": "{mcp_url}",
      "headers": {{
        "Authorization": "Bearer &lt;your-mcp-api-key&gt;"
      }}
    }}
  }}
}}</code></pre>
    </section>

    <section>
      <h2>Compliance notes</h2>
      <p>
        Public tools expose law metadata only. Protected tools require per-user authentication,
        use minimized JWT claims, and are logged with request and correlation IDs without storing
        raw prompts, law text, passwords, OTP codes, or tokens in application logs.
      </p>
    </section>
  </main>
</body>
</html>"""


app = fastapi.FastAPI(
    title="JurisDigta MCP Server",
    version=MCP_VERSION,
    description=(
        "Dedicated MCP service for JurisDigta assistant integrations. "
        "Tool access is separated from the public API runtime."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_origin_regex=_cors_allow_origin_regex(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id", "x-correlation-id"],
)
app.include_router(mcp_oauth_router)
app.include_router(mcp_router)
instrument_fastapi(app)


@app.get("/", response_class=HTMLResponse)
def mcp_instructions(request: fastapi.Request) -> HTMLResponse:
    return HTMLResponse(_mcp_instructions_html(base_url=_public_base_url(request)))


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
            "MCP Starting | mcp_version=%s | core_version=%s | log_level=%s "
            "| db_option=%s | last_law_update_date=%s | law_source=%s "
            "| last_collector_run_at=%s | last_processed_law=%s"
        ),
        app.version,
        get_core_version(),
        logging.getLevelName(LOG_LEVEL),
        store.db_option,
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


@app.get("/health")
def health() -> JSONResponse:
    database_backend = _configured_db_backend()
    try:
        store = ApiDatabaseStore.from_env()
        database_backend = store.db_option
        store.check_connection()
    except Exception as exc:
        message = f'Database health check failed for backend "{database_backend}": {exc}'
        logger.warning(message)
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "error": "database_unavailable",
                "message": message,
                "database": {
                    "status": "error",
                    "backend": database_backend,
                },
            },
        )
    return JSONResponse(
        {
            "status": "ok",
            "service": "jurisdigta-mcp-server",
            "database": {
                "status": "ok",
                "backend": database_backend,
            },
        }
    )


@app.get("/version")
def version() -> JSONResponse:
    law_payload = _law_snapshot_payload(country_code=None)
    laws_by_country = {
        country_code.lower(): _law_snapshot_payload(country_code=country_code)
        for country_code in _SUPPORTED_LAW_VERSION_COUNTRIES
    }
    return JSONResponse(
        {
            "service": "jurisdigta-mcp-server",
            "version": app.version,
            "api_version": app.version,
            "mcp_server_version": app.version,
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
    )


logger.info(
    "MCP logging configured at level %s telemetry_mode=%s",
    logging.getLevelName(LOG_LEVEL),
    TELEMETRY_MODE,
)
