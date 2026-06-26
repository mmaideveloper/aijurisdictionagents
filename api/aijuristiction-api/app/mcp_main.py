from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
import logging
import os
from pathlib import Path
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode
from uuid import uuid4

import dotenv
import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.datastructures import Headers

from app.chat.result_metadata import get_law_knowledge_snapshot
from app.logging_config import configure_logging
from app.mcp_api import oauth_router as mcp_oauth_router
from app.mcp_api import compat_router as mcp_compat_router
from app.mcp_api import lowercase_compat_router as mcp_lowercase_compat_router
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
DEFAULT_MCP_LLM_PROVIDER = "model_routing"

LOG_LEVEL = configure_logging()
_SUPPORTED_MCP_PAGE_LOCALES = {"en", "sk"}
_MCP_PAGE_TEXT: dict[str, dict[str, str]] = {
    "en": {
        "title": "JurisDigta MCP server",
        "intro": "Connect AI assistants to JurisDigta public-law tools through the Model Context Protocol.",
        "endpoint": "The MCP endpoint is",
        "registration": "Registration",
        "registration_open": "Open",
        "registration_profile": "Enter your email, phone number, profile details, ID card number, and explicit data-processing consent.",
        "registration_otp": "Confirm the email OTP code to create the account.",
        "registration_login": "Open {login_url} to generate a short-lived MCP API key, or let an OAuth-capable assistant complete the browser authorization flow.",
        "keys": "MCP API keys are shown once, expire by default after one day, and can be revoked from the user API.",
        "setup": "Assistant setup",
        "chatgpt": "create a remote MCP connector and use {mcp_url} as the server URL. Prefer OAuth discovery when available.",
        "claude": "add a custom connector or remote MCP server and use {mcp_url}. OAuth-capable Claude clients can discover authorization from this domain and register dynamically. If Claude asks for a client ID, open Advanced settings, set OAuth Client ID to claude, and leave the secret empty.",
        "vscode": "add an HTTP MCP server in MCP settings with URL {mcp_url}. If your client cannot use OAuth, pass the generated key as Authorization: Bearer <key>.",
        "other_clients": "use the same remote server URL where custom MCP servers are supported. If custom remote MCP registration is not available in the product UI, use another MCP-compatible host.",
        "perplexity": "Perplexity and other MCP clients",
        "discovery": "Discovery URLs",
        "mcp_endpoint": "MCP endpoint",
        "protected_resource": "Protected resource metadata",
        "authorization_server": "Authorization server metadata",
        "version": "Version and law freshness",
        "docs": "Client documentation",
        "manual": "Manual header example",
        "compliance": "Compliance notes",
        "compliance_text": "Public tools expose law metadata only. Protected tools require per-user authentication, use minimized JWT claims, and are logged with request and correlation IDs without storing raw prompts, law text, passwords, OTP codes, or tokens in application logs.",
    },
    "sk": {
        "title": "JurisDigta MCP server",
        "intro": "Pripojte AI asistentov k nastrojom JurisDigta pre slovenske verejne pravo cez Model Context Protocol.",
        "endpoint": "MCP endpoint je",
        "registration": "Registracia",
        "registration_open": "Otvorte",
        "registration_profile": "Zadajte e-mail, telefonne cislo, profilove udaje, cislo obcianskeho preukazu a vyslovny suhlas so spracovanim udajov.",
        "registration_otp": "Potvrďte e-mailovy OTP kod na vytvorenie uctu.",
        "registration_login": "Otvorte {login_url} na vygenerovanie kratkodobeho MCP API kluca alebo nechajte OAuth-kompatibilneho asistenta dokoncit autorizaciu v prehliadaci.",
        "keys": "MCP API kluce sa zobrazia iba raz, predvolene expiruju po jednom dni a daju sa odvolat cez pouzivatelske API.",
        "setup": "Nastavenie asistenta",
        "chatgpt": "vytvorte vzdialeny MCP connector a pouzite {mcp_url} ako URL servera. Ak je dostupne OAuth discovery, uprednostnite ho.",
        "claude": "pridajte vlastny connector alebo vzdialeny MCP server a pouzite {mcp_url}. OAuth-kompatibilni Claude klienti vedia z tejto domeny zistit autorizaciu a dynamicky sa registrovat. Ak Claude pyta client ID, v Advanced settings nastavte OAuth Client ID na claude a secret nechajte prazdny.",
        "vscode": "pridajte HTTP MCP server v MCP nastaveniach s URL {mcp_url}. Ak klient nevie pouzit OAuth, poslite vygenerovany kluc ako Authorization: Bearer <key>.",
        "other_clients": "pouzite rovnaku URL vzdialeneho servera tam, kde su podporovane vlastne MCP servery. Ak produkt nepodporuje vlastnu vzdialenu MCP registraciu, pouzite ineho MCP-kompatibilneho hostitela.",
        "perplexity": "Perplexity a dalsi MCP klienti",
        "discovery": "Discovery URL",
        "mcp_endpoint": "MCP endpoint",
        "protected_resource": "Metadata chraneneho zdroja",
        "authorization_server": "Metadata autorizacneho servera",
        "version": "Verzia a cerstvost zakonov",
        "docs": "Dokumentacia klientov",
        "manual": "Priklad manualnej hlavicky",
        "compliance": "Poznamky ku compliance",
        "compliance_text": "Verejne nastroje spristupnuju iba metadata zakonov. Chranene nastroje vyzaduju autentifikaciu pouzivatela, pouzivaju minimalizovane JWT claims a loguju sa s request a correlation ID bez ukladania raw promptov, textov zakonov, hesiel, OTP kodov alebo tokenov.",
    },
}
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
_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
    "x-mcp-api-key",
}
_SENSITIVE_FIELD_NAMES = {
    "access_token",
    "authorization",
    "client_secret",
    "code",
    "code_verifier",
    "email",
    "id_card",
    "identity_card_number",
    "mcp_api_key",
    "password",
    "pending_id",
    "refresh_token",
    "token",
    "verification_code",
}
_REDACTED = "[redacted]"


def _cors_allow_origins() -> list[str]:
    value = os.getenv("MCP_CORS_ALLOW_ORIGINS", os.getenv("CORS_ALLOW_ORIGINS", ""))
    if value:
        return [origin.strip() for origin in value.split(",") if origin.strip()]
    return [*list(_DEFAULT_MCP_ORIGINS), "null"]


def _cors_allow_origin_regex() -> str | None:
    if os.getenv("MCP_CORS_ALLOW_ORIGINS") or os.getenv("CORS_ALLOW_ORIGINS"):
        return None
    return r"^https?://(localhost|127(?:\.\d{1,3}){3}|\[::1\])(?::\d+)?$"


def _mcp_wire_logging_enabled() -> bool:
    value = os.getenv("MCP_WIRE_LOGGING_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _mcp_wire_log_max_bytes() -> int:
    raw_value = os.getenv("MCP_WIRE_LOG_MAX_BYTES", "20000").strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        parsed = 20000
    return max(1024, parsed)


def _redact_header_value(name: str, value: str) -> str:
    lowered = name.lower()
    if lowered in _SENSITIVE_HEADER_NAMES:
        return _REDACTED
    if lowered in {"location", "referer", "referrer"}:
        return _redact_url_query(value)
    return value


def _redact_value(name: str, value: Any) -> Any:
    lowered = name.lower()
    if lowered == "token_type":
        return _redact_payload(value)
    if lowered in _SENSITIVE_FIELD_NAMES or any(marker in lowered for marker in ("password", "secret", "token")):
        return _REDACTED
    return _redact_payload(value)


def _redact_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {str(key): _redact_value(str(key), value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_redact_payload(item) for item in payload]
    return payload


def _content_type_base(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def _decode_body_preview(*, body: bytes, content_type: str, max_bytes: int) -> dict[str, Any]:
    truncated = len(body) > max_bytes
    preview = body[:max_bytes]
    if not preview:
        return {"bytes": len(body), "truncated": truncated, "body": ""}
    text = preview.decode("utf-8", errors="replace")
    base_content_type = _content_type_base(content_type)
    if base_content_type == "application/json" or text.lstrip().startswith(("{", "[")):
        try:
            return {
                "bytes": len(body),
                "truncated": truncated,
                "json": _redact_payload(json.loads(text)),
            }
        except json.JSONDecodeError:
            pass
    if base_content_type == "application/x-www-form-urlencoded":
        return {
            "bytes": len(body),
            "truncated": truncated,
            "form": {
                key: _redact_value(key, value)
                for key, value in parse_qsl(text, keep_blank_values=True)
            },
        }
    return {"bytes": len(body), "truncated": truncated, "body": text}


def _wire_headers(headers: Headers) -> dict[str, str]:
    return {
        name.lower(): _redact_header_value(name, value)
        for name, value in headers.items()
        if name.lower()
        not in {
            "accept-encoding",
            "connection",
            "content-length",
        }
    }


def _redacted_query_string(request: fastapi.Request) -> str:
    redacted = [
        (key, str(_redact_value(key, value)))
        for key, value in request.query_params.multi_items()
    ]
    return urlencode(redacted)


def _redact_url_query(value: str) -> str:
    if "?" not in value:
        return value
    base, query = value.split("?", 1)
    fragment = ""
    if "#" in query:
        query, fragment = query.split("#", 1)
        fragment = f"#{fragment}"
    redacted = [
        (key, str(_redact_value(key, item)))
        for key, item in parse_qsl(query, keep_blank_values=True)
    ]
    return f"{base}?{urlencode(redacted)}{fragment}"


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


def _database_health_error_payload(*, backend: str) -> dict[str, Any]:
    return {
        "status": "error",
        "service": "jurisdigta-mcp-server",
        "error": "database_unavailable",
        "message": f'Database health check failed for backend "{backend}".',
        "database": {
            "status": "error",
            "backend": backend,
        },
    }


def _public_base_url(request: fastapi.Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_proto and forwarded_host:
        proto = forwarded_proto.split(",")[0].strip()
        host = forwarded_host.split(",")[0].strip()
        return f"{proto}://{host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _mcp_page_locale(request: fastapi.Request) -> str:
    header = request.headers.get("accept-language", "")
    for item in header.split(","):
        language = item.split(";", 1)[0].strip().lower()
        primary = language.split("-", 1)[0]
        if primary in _SUPPORTED_MCP_PAGE_LOCALES:
            return primary
    return "en"


def _mcp_page_text(locale: str, key: str, **values: str) -> str:
    text = _MCP_PAGE_TEXT.get(locale, _MCP_PAGE_TEXT["en"]).get(key, _MCP_PAGE_TEXT["en"][key])
    return text.format(**values)


def _mcp_instructions_html(*, base_url: str, locale: str = "en") -> str:
    mcp_url = f"{base_url}/MCP"
    protected_resource_url = f"{base_url}/.well-known/oauth-protected-resource/MCP"
    authorization_server_url = f"{base_url}/.well-known/oauth-authorization-server"
    login_url = f"{base_url}/MCP/login"
    sign_up_url = f"{base_url}/MCP/sign-up"
    version_url = f"{base_url}/version"
    return f"""<!doctype html>
<html lang="{locale}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_mcp_page_text(locale, "title")}</title>
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
    <h1>{_mcp_page_text(locale, "title")}</h1>
    <p>
      {_mcp_page_text(locale, "intro")}
      {_mcp_page_text(locale, "endpoint")} <code>{mcp_url}</code>.
    </p>

    <section>
      <h2>{_mcp_page_text(locale, "registration")}</h2>
      <ol>
        <li>{_mcp_page_text(locale, "registration_open")} <a href="{sign_up_url}">{sign_up_url}</a>.</li>
        <li>{_mcp_page_text(locale, "registration_profile")}</li>
        <li>{_mcp_page_text(locale, "registration_otp")}</li>
        <li>{_mcp_page_text(locale, "registration_login", login_url=f'<a href="{login_url}">{login_url}</a>')}</li>
      </ol>
      <p>
        {_mcp_page_text(locale, "keys")}
      </p>
    </section>

    <section>
      <h2>{_mcp_page_text(locale, "setup")}</h2>
      <ul>
        <li><strong>ChatGPT custom connector:</strong> {_mcp_page_text(locale, "chatgpt", mcp_url=f'<code>{mcp_url}</code>')}</li>
        <li><strong>Claude:</strong> {_mcp_page_text(locale, "claude", mcp_url=f'<code>{mcp_url}</code>')}</li>
        <li><strong>VS Code:</strong> {_mcp_page_text(locale, "vscode", mcp_url=f'<code>{mcp_url}</code>')}</li>
        <li><strong>{_mcp_page_text(locale, "perplexity")}:</strong> {_mcp_page_text(locale, "other_clients")}</li>
      </ul>
    </section>

    <section>
      <h2>{_mcp_page_text(locale, "discovery")}</h2>
      <ul>
        <li>{_mcp_page_text(locale, "mcp_endpoint")}: <code>{mcp_url}</code></li>
        <li>{_mcp_page_text(locale, "protected_resource")}: <a href="{protected_resource_url}">{protected_resource_url}</a></li>
        <li>{_mcp_page_text(locale, "authorization_server")}: <a href="{authorization_server_url}">{authorization_server_url}</a></li>
        <li>{_mcp_page_text(locale, "version")}: <a href="{version_url}">{version_url}</a></li>
      </ul>
    </section>

    <section>
      <h2>{_mcp_page_text(locale, "docs")}</h2>
      <ul>
        <li><a href="https://developers.openai.com/api/docs/mcp">OpenAI remote MCP documentation</a></li>
        <li><a href="https://platform.claude.com/docs/en/agents-and-tools/mcp-connector">Claude MCP connector documentation</a></li>
        <li><a href="https://code.visualstudio.com/docs/agent-customization/mcp-servers">VS Code MCP server documentation</a></li>
      </ul>
    </section>

    <section>
      <h2>{_mcp_page_text(locale, "manual")}</h2>
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
      <h2>{_mcp_page_text(locale, "compliance")}</h2>
      <p>
        {_mcp_page_text(locale, "compliance_text")}
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
app.include_router(mcp_compat_router)
app.include_router(mcp_lowercase_compat_router)
instrument_fastapi(app)


@app.get("/", response_class=HTMLResponse)
def mcp_instructions(request: fastapi.Request) -> HTMLResponse:
    return HTMLResponse(
        _mcp_instructions_html(base_url=_public_base_url(request), locale=_mcp_page_locale(request))
    )


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
    wire_logging_enabled = _mcp_wire_logging_enabled()
    max_wire_bytes = _mcp_wire_log_max_bytes()
    if wire_logging_enabled:
        request_body = await request.body()
        logger.info(
            "mcp_wire_request request_id=%s correlation_id=%s payload=%s",
            request_id,
            correlation_id,
            json.dumps(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "query": _redacted_query_string(request),
                    "client": request.client.host if request.client else None,
                    "headers": _wire_headers(request.headers),
                    "body": _decode_body_preview(
                        body=request_body,
                        content_type=request.headers.get("content-type", ""),
                        max_bytes=max_wire_bytes,
                    ),
                },
                sort_keys=True,
            ),
        )
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - started) * 1000)
    response.headers["x-request-id"] = request_id
    response.headers["x-correlation-id"] = correlation_id
    if wire_logging_enabled:
        response_body = b""
        body_iterator: Any = getattr(response, "body_iterator", None)
        if body_iterator is not None:
            async for chunk in body_iterator:
                response_body += chunk
        else:
            response_body = getattr(response, "body", b"")
        logger.info(
            "mcp_wire_response request_id=%s correlation_id=%s payload=%s",
            request_id,
            correlation_id,
            json.dumps(
                {
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "headers": _wire_headers(response.headers),
                    "body": _decode_body_preview(
                        body=response_body,
                        content_type=response.headers.get("content-type", ""),
                        max_bytes=max_wire_bytes,
                    ),
                },
                sort_keys=True,
            ),
        )
        response_headers = {
            name: value
            for name, value in response.headers.items()
            if name.lower() != "content-length"
        }
        response = Response(
            content=response_body,
            status_code=response.status_code,
            headers=response_headers,
            media_type=response.media_type,
            background=response.background,
        )
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
        logger.warning(
            'MCP database health check failed for backend "%s": %s',
            database_backend,
            exc.__class__.__name__,
        )
        return JSONResponse(
            status_code=503,
            content=_database_health_error_payload(backend=database_backend),
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
