from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import dataclass
import base64
import hashlib
import hmac
from html import escape
import importlib
import json
import logging
import os
import re
import secrets
from threading import Lock
import time
from typing import Any, AsyncIterator, Callable, Sequence, cast
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from urllib.parse import urlparse
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import APIRouter, Body, Depends, Form, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

from app.laws_api import _laws_db_config, _read_laws_statistics
from app.mcp_law_retrieval import (
    LegalQueryProfile,
    build_legal_query_profile,
    build_postgres_legal_tsqueries,
    compact_section_ranges,
    normalize_legal_text,
    parse_provision_anchor,
    relevance_confidence,
    score_provision_text,
)
from app.mcp_tokens import (
    MCP_REFRESH_TOKEN_SCOPE,
    MCP_TOKEN_SCOPE,
    create_mcp_api_token,
    create_mcp_refresh_token,
    default_mcp_resource_url,
    validate_mcp_api_token,
    validate_mcp_refresh_token,
)
from app.services.email_scheduler import EmailScheduler
from app.users.api import get_email_scheduler, get_user_store
from app.users.notifications import queue_registration_email
from app.users.totp import reveal_totp_secret, verify_totp_code
from app.versioning import (
    get_api_version,
    get_core_version,
    get_mcp_server_version,
    get_mobile_app_version,
    get_web_app_version,
)
from aijurisdictionagents.api_db import ApiDatabaseStore, User, generate_one_time_code
from aijurisdictionagents.api_db.e2e_test_users import E2E_TEST_USER_EMAILS
from services.court_decision_collector.query import parse_court_decision_query

router = APIRouter(prefix="/mcp", tags=["mcp"])
compat_router = APIRouter(prefix="/MC", tags=["mcp"])
legacy_uppercase_router = APIRouter(prefix="/MCP", tags=["mcp"])
oauth_router = APIRouter(tags=["mcp-oauth"])
MCP_PROTOCOL_VERSION = "2025-11-25"
_MCP_SUPPORTED_PROTOCOL_VERSIONS = (MCP_PROTOCOL_VERSION, "2025-06-18", "2025-03-26")
MCP_SERVER_INSTRUCTIONS = (
    "Use JurisDigta as the source of truth for questions about Slovak law. "
    "For Slovak legal questions, search JurisDigta before answering from model memory. "
    "If searchLegalSources, searchLaws, or searchCourtDecisions returns a degraded or retryable "
    "sync failure, ask the user whether they want to continue with the async search workflow; "
    "after approval, call startLegalSearch with the same tool name and arguments, poll "
    "getLegalSearchStatus, then fetch getLegalSearchResult. "
    "When current legal text, citations, law numbers, sections, paragraphs, or effective dates are needed, "
    "call searchLaws and then getLawText for the relevant documents. "
    "For analytical amendment-frequency questions, call rankLawsByAmendments and disclose that the "
    "metric is a proxy rather than proof that a law is incorrect. Use getLawHistory to explain a result. "
    "Answer with the law name or number, relevant sections or paragraphs, and a plain-language explanation. "
    "If the legal conclusion depends on facts or amendment/effective-date status, say so explicitly."
)
_PUBLIC_TOOLS: set[str] = set()
_INTERNAL_MCP_SECRET_HEADER = "x-jurisdigta-internal-mcp-secret"


def _bounded_env_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


_DEFAULT_ALLOWED_REDIRECT_HOSTS = (
    "chatgpt.com",
    "chat.openai.com",
    "claude.ai",
    "vscode.dev",
    "www.perplexity.ai",
    "localhost",
    "127.0.0.1",
    "::1",
)
_MCP_OTP_VERIFICATION_PURPOSE = "mcp_access"
_DEFAULT_LAW_TEXT_MAX_CHARS = 20_000
_MAX_LAW_TEXT_CHARS = 100_000
_LEGAL_SEARCH_TIMEOUT_SECONDS = _bounded_env_int("MCP_LEGAL_SEARCH_TIMEOUT_SECONDS", default=30, minimum=1, maximum=300)
_LEGAL_SEARCH_TIMEOUT_MS = _LEGAL_SEARCH_TIMEOUT_SECONDS * 1000
_PROVISION_FTS_SCAN_MULTIPLIER = 1
_PROVISION_FTS_SCAN_MINIMUM = 600
_PROVISION_FTS_SCAN_MAXIMUM = 20_000
_COURT_DECISION_MCP_SEARCH_TIMEOUT_MS = _bounded_env_int(
    "COURT_DECISION_MCP_SEARCH_TIMEOUT_MS",
    default=600_000,
    minimum=1_000,
    maximum=600_000,
)
_COURT_DECISION_MCP_CONNECT_TIMEOUT_SECONDS = _bounded_env_int(
    "COURT_DECISION_MCP_CONNECT_TIMEOUT_SECONDS",
    default=3,
    minimum=1,
    maximum=30,
)
_MCP_ASYNC_SEARCH_RETENTION_SECONDS = _bounded_env_int(
    "MCP_ASYNC_SEARCH_RETENTION_SECONDS",
    default=900,
    minimum=60,
    maximum=86_400,
)
_OAUTH_PUBLIC_CLIENT_GRANT_TYPES = ("authorization_code", "refresh_token")
_OAUTH_TOLERATED_DCR_GRANT_TYPES = {"authorization_code", "refresh_token", "client_credentials"}
_OAUTH_PROTECTED_RESOURCE_SCOPES = (MCP_TOKEN_SCOPE,)
_OAUTH_AUTHORIZATION_SERVER_SCOPES = (MCP_TOKEN_SCOPE, "offline_access")
_OAUTH_GRANTED_SCOPE = MCP_TOKEN_SCOPE
_CLAUDE_CLIENT_ID_METADATA_URL = "https://claude.ai/oauth/mcp-oauth-client-metadata"
logger = logging.getLogger("aijuristiction-api.mcp")
_CURRENT_MCP_REQUEST_ID: ContextVar[str | None] = ContextVar("current_mcp_request_id", default=None)
_CURRENT_MCP_CORRELATION_ID: ContextVar[str | None] = ContextVar("current_mcp_correlation_id", default=None)
_MCP_SUPPORTED_LOCALES = {"en", "sk"}


@dataclass
class _AsyncSearchJob:
    search_id: str
    user_id: str
    tool_name: str
    arguments: dict[str, Any]
    created_at: float
    expires_at: float
    future: Future[dict[str, Any]]


_ASYNC_SEARCH_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mcp-legal-search")
_ASYNC_SEARCH_JOBS: dict[str, _AsyncSearchJob] = {}
_ASYNC_SEARCH_LOCK = Lock()
_MCP_TEXT: dict[str, dict[str, str]] = {
    "en": {
        "security_label": "Security and privacy",
        "trust_otp": "One-time email verification protects account and API key access.",
        "trust_scope": "Legal assistant access is scoped to the MCP server and expires by default.",
        "trust_profile": "Profile data is used only for account creation and required access controls.",
        "login_title": "Log in",
        "login_subtitle": "Generate a short-lived MCP API key for your legal assistant connection.",
        "login_note": "Use your JurisDigta account email and password. We will send an OTP code before creating a key.",
        "email": "Email",
        "password": "Password",
        "expiry_days": "API key expiry days",
        "send_otp": "Send OTP code",
        "choose_mfa_title": "Choose MFA method",
        "choose_mfa_subtitle": "Your account has authenticator-app MFA enabled. Choose how to verify this login.",
        "mfa_method": "MFA method",
        "mfa_email": "Email OTP",
        "mfa_totp": "Authenticator app",
        "continue": "Continue",
        "totp_code": "Authenticator code",
        "totp_note": "Open Google Authenticator or a compatible app and enter the current six-digit code.",
        "need_account": "Need an account?",
        "sign_up_link": "Sign up",
        "already_registered": "Already registered?",
        "log_in_link": "Log in",
        "oauth_title": "Authorize MCP access",
        "oauth_subtitle": "Confirm your account before authorizing this MCP client.",
        "oauth_note": "We will send an OTP code before completing authorization.",
        "oauth_verify_title": "Verify MCP OAuth login",
        "oauth_verify_subtitle": "Enter the one-time code from your email to authorize MCP access.",
        "otp_sent": "An OTP code was sent to {email}.",
        "otp_code": "OTP code",
        "authorize": "Authorize",
        "verify_login_title": "Verify MCP login",
        "verify_login_subtitle": "Enter the one-time code from your email to generate the API key.",
        "generate_key": "Generate MCP API key",
        "create_account_title": "Create account",
        "create_account_subtitle": "Register for JurisDigta MCP access with email verification and explicit data-processing consent.",
        "create_account_note": "Enter the details needed to create your account. We will email a verification code before saving the account.",
        "phone": "Phone number",
        "first_name": "First name",
        "last_name": "Last name",
        "address": "Address",
        "city": "City",
        "country": "Country",
        "zip_code": "ZIP code",
        "id_card": "ID card number",
        "consent": "I agree to data processing for account creation and MCP access.",
        "send_verification": "Send verification code",
        "verify_signup_title": "Verify MCP sign up",
        "verify_signup_subtitle": "Enter the one-time code from your email to create the account.",
        "create_account": "Create account",
        "account_created_title": "MCP account created",
        "account_created_subtitle": "Your JurisDigta MCP account is verified.",
        "account_created": "Account {email} is verified. You can now log in and generate an MCP API key.",
        "key_created_title": "MCP API key created",
        "key_created_subtitle": "Copy the key now. It is shown once and expires at the configured time.",
        "key_expires": "This key expires at {expires_at}.",
        "key_note": "Use it as a Bearer token or as the x-mcp-api-key header when connecting your AI assistant to /mcp.",
        "invalid_code": "The verification code is invalid or has expired. Check the code and try again.",
        "expired_code": "This sign-up request expired. Start sign-up again to receive a new code.",
    },
    "sk": {
        "security_label": "Bezpecnost a sukromie",
        "trust_otp": "Jednorazove overenie e-mailom chrani pristup k uctu a API klucu.",
        "trust_scope": "Pristup pravneho asistenta je obmedzeny na MCP server a predvolene expiruje.",
        "trust_profile": "Profilove udaje sa pouzivaju iba na vytvorenie uctu a potrebne riadenie pristupu.",
        "login_title": "Prihlasenie",
        "login_subtitle": "Vygenerujte kratkodoby MCP API kluc pre pripojenie pravneho asistenta.",
        "login_note": "Pouzite e-mail a heslo uctu JurisDigta. Pred vytvorenim kluca posleme OTP kod.",
        "email": "E-mail",
        "password": "Heslo",
        "expiry_days": "Platnost API kluca v dnoch",
        "send_otp": "Poslat OTP kod",
        "choose_mfa_title": "Vyber MFA metodu",
        "choose_mfa_subtitle": "Vas ucet ma zapnute MFA cez autentifikacnu aplikaciu. Vyberte sposob overenia prihlasenia.",
        "mfa_method": "MFA metoda",
        "mfa_email": "Email OTP",
        "mfa_totp": "Autentifikacna aplikacia",
        "continue": "Pokracovat",
        "totp_code": "Kod z autentifikacnej aplikacie",
        "totp_note": "Otvorte Google Authenticator alebo kompatibilnu aplikaciu a zadajte aktualny sestmiestny kod.",
        "need_account": "Potrebujete ucet?",
        "sign_up_link": "Registrovat sa",
        "already_registered": "Uz mate ucet?",
        "log_in_link": "Prihlasit sa",
        "oauth_title": "Autorizacia MCP pristupu",
        "oauth_subtitle": "Pred autorizaciou MCP klienta potvrďte svoj ucet.",
        "oauth_note": "Pred dokoncenim autorizacie posleme OTP kod.",
        "oauth_verify_title": "Overenie MCP OAuth prihlasenia",
        "oauth_verify_subtitle": "Zadajte jednorazovy kod z e-mailu na autorizaciu MCP pristupu.",
        "otp_sent": "OTP kod bol odoslany na {email}.",
        "otp_code": "OTP kod",
        "authorize": "Autorizovat",
        "verify_login_title": "Overenie MCP prihlasenia",
        "verify_login_subtitle": "Zadajte jednorazovy kod z e-mailu na vygenerovanie API kluca.",
        "generate_key": "Vygenerovat MCP API kluc",
        "create_account_title": "Vytvorenie uctu",
        "create_account_subtitle": "Registracia pristupu JurisDigta MCP s overenim e-mailu a vyslovnym suhlasom so spracovanim udajov.",
        "create_account_note": "Zadajte udaje potrebne na vytvorenie uctu. Pred ulozenim uctu posleme overovaci kod e-mailom.",
        "phone": "Telefonne cislo",
        "first_name": "Meno",
        "last_name": "Priezvisko",
        "address": "Adresa",
        "city": "Mesto",
        "country": "Krajina",
        "zip_code": "PSC",
        "id_card": "Cislo obcianskeho preukazu",
        "consent": "Suhlasim so spracovanim udajov na vytvorenie uctu a MCP pristup.",
        "send_verification": "Poslat overovaci kod",
        "verify_signup_title": "Overenie MCP registracie",
        "verify_signup_subtitle": "Zadajte jednorazovy kod z e-mailu na vytvorenie uctu.",
        "create_account": "Vytvorit ucet",
        "account_created_title": "MCP ucet bol vytvoreny",
        "account_created_subtitle": "Vas ucet JurisDigta MCP je overeny.",
        "account_created": "Ucet {email} je overeny. Teraz sa mozete prihlasit a vygenerovat MCP API kluc.",
        "key_created_title": "MCP API kluc bol vytvoreny",
        "key_created_subtitle": "Skopirujte si kluc teraz. Zobrazi sa iba raz a expiruje v nastavenom case.",
        "key_expires": "Tento kluc expiruje {expires_at}.",
        "key_note": "Pouzite ho ako Bearer token alebo hlavicku x-mcp-api-key pri pripajani AI asistenta k /mcp.",
        "invalid_code": "Overovaci kod je neplatny alebo expiroval. Skontrolujte kod a skuste to znova.",
        "expired_code": "Tato registracna poziadavka expirovala. Spustite registraciu znova a dostanete novy kod.",
    },
}


def _requested_mcp_protocol_version(message: dict[str, Any]) -> str | None:
    params = message.get("params")
    if not isinstance(params, dict):
        return None
    requested_protocol_version = params.get("protocolVersion")
    if not isinstance(requested_protocol_version, str):
        return None
    requested_protocol_version = requested_protocol_version.strip()
    return requested_protocol_version or None


def _negotiate_mcp_protocol_version(message: dict[str, Any]) -> tuple[str | None, str]:
    requested_protocol_version = _requested_mcp_protocol_version(message)
    if requested_protocol_version in _MCP_SUPPORTED_PROTOCOL_VERSIONS:
        return requested_protocol_version, requested_protocol_version
    return requested_protocol_version, MCP_PROTOCOL_VERSION


@dataclass(frozen=True)
class _LawsQueryConfig:
    backend: str
    query_all: Callable[[str, Sequence[Any]], list[Sequence[Any]]]
    param: str


def require_mcp_api_key(
    authorization: str | None = Header(default=None),
    x_mcp_api_key: str | None = Header(default=None),
    store: ApiDatabaseStore = Depends(get_user_store),
) -> str:
    api_key = _extract_mcp_api_key(authorization=authorization, x_mcp_api_key=x_mcp_api_key)
    if not api_key:
        logger.warning("mcp_auth_failed reason=missing_api_key")
        raise HTTPException(status_code=401, detail="Missing MCP API key")
    user = _authenticate_mcp_api_token(api_key=api_key, store=store)
    logger.info("mcp_auth_succeeded user_id=%s", user.user_id)
    return str(user.user_id)


@router.get("")
@compat_router.get("")
@legacy_uppercase_router.get("")
async def mcp_status(request: Request) -> Response:
    accept = request.headers.get("accept", "").lower()
    if "text/event-stream" not in accept:
        return JSONResponse(
            status_code=405,
            content={"detail": "Use POST /mcp for Streamable HTTP JSON-RPC."},
            headers={"Allow": "GET, POST"},
        )

    request_id = getattr(request.state, "request_id", None)
    correlation_id = getattr(request.state, "correlation_id", None)
    logger.info(
        "mcp_sse_stream_opened request_path=%s request_id=%s correlation_id=%s user_agent=%s",
        request.url.path,
        request_id,
        correlation_id,
        _oauth_user_agent_family(request),
    )

    async def events() -> AsyncIterator[str]:
        yield ": jurisdigta-mcp-ready\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status", response_class=JSONResponse)
@legacy_uppercase_router.get("/status", response_class=JSONResponse)
def mcp_authenticated_status(user_id: str = Depends(require_mcp_api_key)) -> dict[str, str]:
    logger.info("mcp_status_checked user_id=%s", user_id)
    return {
        "status": "ok",
        "transport": "streamable-http-json-rpc",
        "protocol_version": MCP_PROTOCOL_VERSION,
        "user_id": user_id,
    }


@router.post("", response_class=JSONResponse)
@compat_router.post("", response_class=JSONResponse)
@legacy_uppercase_router.post("", response_class=JSONResponse)
async def mcp_json_rpc(
    request: Request,
    authorization: str | None = Header(default=None),
    x_mcp_api_key: str | None = Header(default=None),
) -> JSONResponse:
    started_at = time.perf_counter()
    payload = await _read_json_rpc_payload(request)
    request_id = getattr(request.state, "request_id", None)
    correlation_id = getattr(request.state, "correlation_id", None)
    logger.info(
        "mcp_endpoint_called request_path=%s canonical_resource=%s user_agent=%s",
        request.url.path,
        _resource_url(request),
        _oauth_user_agent_family(request),
    )
    logger.info(
        "mcp_json_rpc_received request_id=%s correlation_id=%s batch=%s message_count=%d methods=%s",
        request_id,
        correlation_id,
        isinstance(payload, list),
        _payload_message_count(payload),
        ",".join(_payload_methods(payload)),
    )
    logger.info(
        "mcp_json_rpc_auth_state has_authorization=%s has_x_mcp_api_key=%s methods=%s",
        bool(authorization and authorization.strip()),
        bool(x_mcp_api_key and x_mcp_api_key.strip()),
        ",".join(_payload_methods(payload)),
    )
    public_tools = _public_tools_for_request(request)
    payload_requires_auth = _payload_requires_auth(
        request=request,
        payload=payload,
        public_tools=public_tools,
    )
    api_key = _extract_mcp_api_key(
        authorization=authorization,
        x_mcp_api_key=x_mcp_api_key,
    )
    if not api_key and payload_requires_auth:
        logger.warning(
            "mcp_json_rpc_auth_challenge reason=missing_bearer_token methods=%s",
            ",".join(_payload_methods(payload)),
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=_json_rpc_error(_first_payload_id(payload), 401, "Tool requires OAuth authorization"),
            headers={"WWW-Authenticate": _www_authenticate_header(request)},
        )
    store = get_user_store() if payload_requires_auth else None
    if api_key and store is not None and _payload_requires_discovery_auth(payload=payload):
        try:
            _authenticate_mcp_api_token(api_key=api_key, store=store)
        except HTTPException as exc:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=_json_rpc_error(_first_payload_id(payload), exc.status_code, str(exc.detail)),
                headers={"WWW-Authenticate": _www_authenticate_header(request)},
            )
    request_id_token = _CURRENT_MCP_REQUEST_ID.set(str(request_id) if request_id else None)
    correlation_id_token = _CURRENT_MCP_CORRELATION_ID.set(str(correlation_id) if correlation_id else None)
    try:
        response = _handle_json_rpc(
            payload=payload,
            authorization=authorization,
            x_mcp_api_key=x_mcp_api_key,
            store=store,
            public_tools=public_tools,
        )
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "mcp_json_rpc_completed request_id=%s correlation_id=%s status_code=%d duration_ms=%d",
            request_id,
            correlation_id,
            response.status_code,
            duration_ms,
        )
        return response
    finally:
        _CURRENT_MCP_REQUEST_ID.reset(request_id_token)
        _CURRENT_MCP_CORRELATION_ID.reset(correlation_id_token)


@router.get("/login", response_class=HTMLResponse)
@legacy_uppercase_router.get("/login", response_class=HTMLResponse)
def mcp_login_page(request: Request) -> HTMLResponse:
    locale = _mcp_locale(request)
    return HTMLResponse(_login_form_html(locale=locale))


@router.get("/sign-up", response_class=HTMLResponse)
@legacy_uppercase_router.get("/sign-up", response_class=HTMLResponse)
def mcp_sign_up_page(request: Request) -> HTMLResponse:
    locale = _mcp_locale(request)
    return HTMLResponse(_sign_up_form_html(locale=locale))


@oauth_router.get("/.well-known/oauth-protected-resource")
def oauth_protected_resource_metadata(request: Request) -> Any:
    base_url = _base_url(request)
    resource = _metadata_resource_url(request)
    logger.info(
        "mcp_oauth_protected_resource_metadata_served request_path=%s resource=%s authorization_server=%s user_agent=%s",
        request.url.path,
        resource,
        base_url,
        _oauth_user_agent_family(request),
    )
    return {
        "resource": resource,
        "resource_name": "JurisDigta MCP",
        "authorization_servers": [base_url],
        "bearer_methods_supported": ["header"],
        "scopes_supported": list(_OAUTH_PROTECTED_RESOURCE_SCOPES),
        "resource_documentation": f"{base_url}/mcp/login",
    }


@oauth_router.get("/.well-known/oauth-protected-resource/mcp")
def oauth_mcp_protected_resource_metadata(request: Request) -> Any:
    return oauth_protected_resource_metadata(request)


@oauth_router.get("/.well-known/oauth-protected-resource/MCP")
def oauth_legacy_public_mcp_protected_resource_metadata(request: Request) -> Any:
    return oauth_protected_resource_metadata(request)


@oauth_router.get("/.well-known/oauth-authorization-server")
@oauth_router.get("/.well-known/oauth-authorization-server/MCP")
@oauth_router.get("/.well-known/oauth-authorization-server/mcp")
def oauth_authorization_server_metadata(request: Request) -> Any:
    base_url = _base_url(request)
    protected_resources = _all_mcp_resource_urls(request)
    logger.info(
        "mcp_oauth_authorization_server_metadata_served request_path=%s issuer=%s protected_resources=%s user_agent=%s",
        request.url.path,
        base_url,
        ",".join(protected_resources),
        _oauth_user_agent_family(request),
    )
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "registration_endpoint": f"{base_url}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": list(_OAUTH_PUBLIC_CLIENT_GRANT_TYPES),
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": list(_OAUTH_AUTHORIZATION_SERVER_SCOPES),
        "authorization_response_iss_parameter_supported": _oauth_authorization_response_iss_enabled(),
        "protected_resources": protected_resources,
    }


@oauth_router.post("/oauth/register", status_code=status.HTTP_201_CREATED)
def oauth_dynamic_client_registration(
    request: Request,
    metadata: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    redirect_uris = _registration_string_list(metadata.get("redirect_uris"))
    if not redirect_uris:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_uris is required")
    for redirect_uri in redirect_uris:
        _validate_oauth_redirect_uri(redirect_uri)

    requested_auth_method = str(metadata.get("token_endpoint_auth_method") or "none").strip()
    allowed_auth_methods = {"none", "client_secret_post", "client_secret_basic"}
    if requested_auth_method not in allowed_auth_methods:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported token_endpoint_auth_method",
        )

    requested_grant_types = _registration_string_list(metadata.get("grant_types")) or ["authorization_code"]
    if any(grant_type not in _OAUTH_TOLERATED_DCR_GRANT_TYPES for grant_type in requested_grant_types):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported grant_types")
    if "authorization_code" not in requested_grant_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="authorization_code grant is required")
    ignored_client_credentials = "client_credentials" in requested_grant_types
    returned_grant_types = ["authorization_code"]
    if "refresh_token" in requested_grant_types:
        returned_grant_types.append("refresh_token")

    response_types = _registration_string_list(metadata.get("response_types")) or ["code"]
    if any(response_type != "code" for response_type in response_types):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported response_types")

    scope = str(metadata.get("scope") or MCP_TOKEN_SCOPE).strip()
    requested_scopes = {item for item in scope.split() if item}
    allowed_scopes = {MCP_TOKEN_SCOPE, "offline_access"}
    if requested_scopes and any(item not in allowed_scopes for item in requested_scopes):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported scope")

    client_id = f"jurisdigta-{secrets.token_urlsafe(18)}"
    logger.info(
        "mcp_oauth_client_registered client_id=%s redirect_count=%d request_host=%s "
        "requested_grants=%s returned_grants=%s ignored_client_credentials=%s",
        client_id,
        len(redirect_uris),
        request.headers.get("host", ""),
        ",".join(requested_grant_types),
        ",".join(returned_grant_types),
        ignored_client_credentials,
    )
    return {
        "client_id": client_id,
        "client_id_issued_at": int(time.time()),
        "client_name": str(metadata.get("client_name") or "MCP client").strip()[:100],
        "redirect_uris": redirect_uris,
        "grant_types": returned_grant_types,
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": _normalize_oauth_scope(scope),
    }


@oauth_router.get("/authorize", response_class=HTMLResponse)
@oauth_router.get("/oauth/authorize", response_class=HTMLResponse)
def oauth_authorize_page(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str = "",
    resource: str = "",
    scope: str = "",
    prompt: str = "",
) -> HTMLResponse:
    resolved_resource = _resolve_oauth_resource(
        request=request,
        resource=resource,
        client_id=client_id,
        redirect_uri=redirect_uri,
    )
    normalized_scope = _normalize_oauth_scope(scope)
    expected_resource = _resource_url(request)
    logger.info(
        "mcp_oauth_authorize_started response_type=%s client_id_hash=%s client_id_host=%s client_id_path=%s "
        "redirect_host=%s redirect_path=%s requested_scope=%s prompt=%s resource_supplied=%s "
        "resolved_resource=%s expected_resource=%s user_agent=%s",
        response_type,
        _stable_hash(client_id),
        _url_host(client_id),
        _url_path(client_id),
        _url_host(redirect_uri),
        _url_path(redirect_uri),
        _oauth_scope_summary(scope),
        prompt,
        bool(resource.strip()),
        resolved_resource,
        expected_resource,
        _oauth_user_agent_family(request),
    )
    try:
        _validate_oauth_authorize_request(
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            resource=resolved_resource,
            expected_resource=expected_resource,
        )
    except HTTPException as exc:
        logger.warning(
            "mcp_oauth_authorize_failed reason=validation_error detail=%s client_id_hash=%s "
            "redirect_host=%s redirect_path=%s resolved_resource=%s expected_resource=%s user_agent=%s",
            _http_exception_detail(exc),
            _stable_hash(client_id),
            _url_host(redirect_uri),
            _url_path(redirect_uri),
            resolved_resource,
            expected_resource,
            _oauth_user_agent_family(request),
        )
        raise
    logger.info(
        "mcp_oauth_authorize_succeeded client_id_hash=%s redirect_host=%s redirect_path=%s "
        "resolved_resource=%s user_agent=%s",
        _stable_hash(client_id),
        _url_host(redirect_uri),
        _url_path(redirect_uri),
        resolved_resource,
        _oauth_user_agent_family(request),
    )
    return HTMLResponse(
        _oauth_login_form_html(
            locale=_mcp_locale(request),
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            state=state,
            resource=resolved_resource,
            scope=normalized_scope,
        )
    )


@oauth_router.post("/oauth/authorize/login", response_class=HTMLResponse)
def oauth_authorize_login(
    request: Request,
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form(...),
    resource: str = Form(""),
    state: str = Form(""),
    scope: str = Form(MCP_TOKEN_SCOPE),
    email: str = Form(...),
    password: str = Form(...),
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> Response:
    resolved_resource = _resolve_oauth_resource(
        request=request,
        resource=resource,
        client_id=client_id,
        redirect_uri=redirect_uri,
    )
    _validate_oauth_authorize_request(
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        resource=resolved_resource,
        expected_resource=_resource_url(request),
    )
    normalized_scope = _normalize_oauth_scope(scope)
    user = store.authenticate_user(email=email, password=password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if _mcp_oauth_test_mfa_bypass_allowed(user=user):
        logger.warning(
            "mcp_oauth_test_mfa_bypass_used user_id=%s email_hash=%s client_id_hash=%s "
            "redirect_host=%s redirect_path=%s expires_at=%s",
            user.user_id,
            _stable_hash(user.email),
            _stable_hash(client_id),
            _url_host(redirect_uri),
            _url_path(redirect_uri),
            _mcp_oauth_test_mfa_bypass_expires_at_raw(),
        )
        return _redirect_with_oauth_authorization_code(
            store=store,
            user=user,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            resource=resolved_resource,
            state=state,
            scope=normalized_scope,
        )
    if _has_recent_mcp_otp_verification(store=store, user=user):
        logger.info("mcp_oauth_otp_reuse user_id=%s client_id=%s", user.user_id, client_id)
        return _redirect_with_oauth_authorization_code(
            store=store,
            user=user,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            resource=resolved_resource,
            state=state,
            scope=normalized_scope,
        )
    if _user_has_totp_enabled(store=store, user=user):
        return HTMLResponse(
            _oauth_mfa_method_form_html(
                locale=_mcp_locale(request),
                email=user.email,
                response_type=response_type,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                state=state,
                resource=resolved_resource,
                scope=normalized_scope,
            )
        )
    _send_oauth_login_code(store=store, scheduler=scheduler, user=user, client_id=client_id)
    return HTMLResponse(
        _oauth_otp_form_html(
            locale=_mcp_locale(request),
            email=user.email,
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            state=state,
            resource=resolved_resource,
            scope=normalized_scope,
        )
    )


@oauth_router.post("/oauth/authorize/mfa", response_class=HTMLResponse)
def oauth_authorize_mfa_method(
    request: Request,
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form(...),
    resource: str = Form(""),
    email: str = Form(...),
    mfa_method: str = Form(...),
    state: str = Form(""),
    scope: str = Form(MCP_TOKEN_SCOPE),
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> HTMLResponse:
    resolved_resource = _resolve_oauth_resource(
        request=request,
        resource=resource,
        client_id=client_id,
        redirect_uri=redirect_uri,
    )
    _validate_oauth_authorize_request(
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        resource=resolved_resource,
        expected_resource=_resource_url(request),
    )
    normalized_scope = _normalize_oauth_scope(scope)
    user = store.find_user_by_email(email=email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    method = mfa_method.strip().lower()
    if method == "totp":
        return HTMLResponse(
            _oauth_totp_form_html(
                locale=_mcp_locale(request),
                email=user.email,
                response_type=response_type,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                state=state,
                resource=resolved_resource,
                scope=normalized_scope,
            )
        )
    _send_oauth_login_code(store=store, scheduler=scheduler, user=user, client_id=client_id)
    return HTMLResponse(
        _oauth_otp_form_html(
            locale=_mcp_locale(request),
            email=user.email,
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            state=state,
            resource=resolved_resource,
            scope=normalized_scope,
        )
    )


@oauth_router.post("/oauth/authorize/verify")
def oauth_authorize_verify(
    request: Request,
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form(...),
    resource: str = Form(""),
    email: str = Form(...),
    verification_code: str = Form(...),
    mfa_method: str = Form("email"),
    state: str = Form(""),
    scope: str = Form(MCP_TOKEN_SCOPE),
    store: ApiDatabaseStore = Depends(get_user_store),
) -> Response:
    resolved_resource = _resolve_oauth_resource(
        request=request,
        resource=resource,
        client_id=client_id,
        redirect_uri=redirect_uri,
    )
    _validate_oauth_authorize_request(
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        resource=resolved_resource,
        expected_resource=_resource_url(request),
    )
    normalized_scope = _normalize_oauth_scope(scope)
    user = store.find_user_by_email(email=email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not _verify_mcp_mfa_code(
        store=store,
        user=user,
        method=mfa_method,
        code=verification_code,
        email_code_key=_oauth_login_code_key(email=email),
    ):
        locale = _mcp_locale(request)
        form_html = _oauth_totp_form_html if mfa_method.strip().lower() == "totp" else _oauth_otp_form_html
        return HTMLResponse(
            form_html(
                locale=locale,
                email=email,
                response_type=response_type,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                state=state,
                resource=resolved_resource,
                scope=normalized_scope,
                warning_key="invalid_code",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    _save_mcp_otp_verification(store=store, user=user)
    return _redirect_with_oauth_authorization_code(
        store=store,
        user=user,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        resource=resolved_resource,
        state=state,
        scope=normalized_scope,
    )


@oauth_router.post("/oauth/token")
def oauth_token(
    request: Request,
    grant_type: str = Form(...),
    code: str = Form(""),
    redirect_uri: str = Form(""),
    client_id: str = Form(...),
    code_verifier: str = Form(""),
    resource: str = Form(""),
    refresh_token: str = Form(""),
    store: ApiDatabaseStore = Depends(get_user_store),
) -> JSONResponse:
    logger.info(
        "mcp_oauth_token_started grant_type=%s client_id_hash=%s client_id_host=%s client_id_path=%s "
        "redirect_host=%s redirect_path=%s resource_supplied=%s requested_resource=%s user_agent=%s",
        grant_type,
        _stable_hash(client_id),
        _url_host(client_id),
        _url_path(client_id),
        _url_host(redirect_uri),
        _url_path(redirect_uri),
        bool(resource.strip()),
        _redacted_if_blank(resource),
        _oauth_user_agent_family(request),
    )
    if grant_type == "refresh_token":
        return _oauth_refresh_token_response(
            request=request,
            refresh_token=refresh_token,
            client_id=client_id,
            resource=resource,
            store=store,
        )
    if grant_type != "authorization_code":
        _log_oauth_token_failed(
            reason="unsupported_grant_type",
            grant_type=grant_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            resource=resource,
            request=request,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported grant_type")
    if not code or not redirect_uri or not code_verifier:
        _log_oauth_token_failed(
            reason="missing_authorization_code_parameters",
            grant_type=grant_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            resource=resource,
            request=request,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing authorization code parameters")
    record = store.consume_mcp_oauth_authorization_code(code=code)
    if record is None:
        _log_oauth_token_failed(
            reason="invalid_authorization_code",
            grant_type=grant_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            resource=resource,
            request=request,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid authorization code")
    if record["client_id"] != client_id or record["redirect_uri"] != redirect_uri:
        _log_oauth_token_failed(
            reason="authorization_code_context_mismatch",
            grant_type=grant_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            resource=resource,
            request=request,
            record_resource=str(record["resource"]),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Authorization code context mismatch")
    resolved_resource = _resolve_oauth_resource(
        request=request,
        resource=resource,
        client_id=client_id,
        redirect_uri=redirect_uri,
    )
    if not _is_mcp_resource_match(request=request, resource=record["resource"]) or not _is_mcp_resource_match(
        request=request,
        resource=resolved_resource,
    ):
        _log_oauth_token_failed(
            reason="resource_mismatch",
            grant_type=grant_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            resource=resolved_resource,
            request=request,
            record_resource=str(record["resource"]),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth resource mismatch")
    token_audience = _canonicalize_mcp_resource(
        request=request,
        resource=resolved_resource if resource.strip() else str(record["resource"]),
    )
    if _pkce_s256_challenge(code_verifier) != record["code_challenge"]:
        _log_oauth_token_failed(
            reason="invalid_pkce_verifier",
            grant_type=grant_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            resource=resolved_resource,
            request=request,
            record_resource=str(record["resource"]),
            token_audience=token_audience,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid PKCE code verifier")
    user = store.get_user(user_id=record["user_id"])
    token, expires_at = _issue_mcp_api_key(
        store=store,
        user=user,
        expires_in_days=1,
        audience=token_audience,
    )
    expires_in = max(1, int((datetime.fromisoformat(expires_at) - datetime.now(timezone.utc)).total_seconds()))
    granted_scope = _normalize_oauth_scope(str(record.get("scope") or _OAUTH_GRANTED_SCOPE))
    issue_refresh_token = _oauth_scope_includes_offline_access(granted_scope)
    token_payload: dict[str, Any] = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": _OAUTH_GRANTED_SCOPE,
    }
    if issue_refresh_token:
        refresh_token_value, _ = _issue_mcp_refresh_token(user=user, audience=token_audience)
        token_payload["refresh_token"] = refresh_token_value
    logger.info(
        "mcp_oauth_token_succeeded grant_type=%s client_id_hash=%s redirect_host=%s redirect_path=%s "
        "resource_supplied=%s record_resource=%s token_audience=%s access_scope=%s refresh_scope=%s "
        "expires_in=%d user_id=%s user_agent=%s",
        grant_type,
        _stable_hash(client_id),
        _url_host(redirect_uri),
        _url_path(redirect_uri),
        bool(resource.strip()),
        str(record["resource"]),
        token_audience,
        MCP_TOKEN_SCOPE,
        MCP_REFRESH_TOKEN_SCOPE if issue_refresh_token else "not_issued",
        expires_in,
        user.user_id,
        _oauth_user_agent_family(request),
    )
    return _oauth_token_json_response(token_payload)


def _oauth_refresh_token_response(
    *,
    request: Request,
    refresh_token: str,
    client_id: str,
    resource: str,
    store: ApiDatabaseStore,
) -> JSONResponse:
    if not refresh_token:
        _log_oauth_token_failed(
            reason="missing_refresh_token",
            grant_type="refresh_token",
            client_id=client_id,
            resource=resource,
            request=request,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing refresh_token")
    resolved_resource = _resolve_oauth_resource(
        request=request,
        resource=resource,
        client_id=client_id,
    )
    if not _is_mcp_resource_match(request=request, resource=resolved_resource):
        _log_oauth_token_failed(
            reason="refresh_resource_mismatch",
            grant_type="refresh_token",
            client_id=client_id,
            resource=resolved_resource,
            request=request,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth resource mismatch")
    matched_audience = resolved_resource
    payload = None
    for audience in _mcp_resource_audience_candidates(request=request, preferred=resolved_resource):
        payload = validate_mcp_refresh_token(refresh_token, audience=audience)
        if payload is not None:
            matched_audience = audience
            break
    if payload is None:
        _log_oauth_token_failed(
            reason="invalid_refresh_token",
            grant_type="refresh_token",
            client_id=client_id,
            resource=resolved_resource,
            request=request,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid refresh_token")
    user = store.find_user_by_id(user_id=str(payload["sub"]))
    if user is None or not user.mcp_api_key_hash:
        _log_oauth_token_failed(
            reason="mcp_access_revoked",
            grant_type="refresh_token",
            client_id=client_id,
            resource=resolved_resource,
            request=request,
            token_audience=str(payload.get("aud") or ""),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MCP access revoked")
    token, expires_at = _issue_mcp_api_key(
        store=store,
        user=user,
        expires_in_days=1,
        audience=matched_audience,
    )
    refresh_token_value, _ = _issue_mcp_refresh_token(user=user, audience=matched_audience)
    expires_in = max(1, int((datetime.fromisoformat(expires_at) - datetime.now(timezone.utc)).total_seconds()))
    logger.info(
        "mcp_oauth_token_succeeded grant_type=refresh_token client_id_hash=%s resource_supplied=%s "
        "token_audience=%s access_scope=%s refresh_scope=%s expires_in=%d user_id=%s user_agent=%s",
        _stable_hash(client_id),
        bool(resource.strip()),
        matched_audience,
        MCP_TOKEN_SCOPE,
        MCP_REFRESH_TOKEN_SCOPE,
        expires_in,
        user.user_id,
        _oauth_user_agent_family(request),
    )
    return _oauth_token_json_response(
        {
            "access_token": token,
            "refresh_token": refresh_token_value,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "scope": _OAUTH_GRANTED_SCOPE,
        }
    )


def _oauth_token_json_response(content: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        content=content,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )


def _redirect_with_oauth_authorization_code(
    *,
    store: ApiDatabaseStore,
    user: User,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    resource: str,
    state: str,
    scope: str,
) -> RedirectResponse:
    authorization_code = secrets.token_urlsafe(32)
    store.save_mcp_oauth_authorization_code(
        code=authorization_code,
        user_id=user.user_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        resource=resource,
        scope=_normalize_oauth_scope(scope),
    )
    query = {"code": authorization_code}
    if state:
        query["state"] = state
    if _oauth_authorization_response_iss_enabled():
        query["iss"] = _base_url_from_resource(resource)
    return RedirectResponse(url=f"{redirect_uri}?{urlencode(query)}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/login", response_class=HTMLResponse)
@legacy_uppercase_router.post("/login", response_class=HTMLResponse)
def mcp_login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    expires_in_days: int = Form(1),
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> HTMLResponse:
    if expires_in_days < 1 or expires_in_days > 365:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expiry must be 1-365 days")
    user = store.authenticate_user(email=email, password=password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if _has_recent_mcp_otp_verification(store=store, user=user):
        raw_key, expires_at = _issue_mcp_api_key(store=store, user=user, expires_in_days=expires_in_days)
        logger.info("mcp_login_otp_reuse user_id=%s", user.user_id)
        return HTMLResponse(
            _key_created_html(locale=_mcp_locale(request), api_key=raw_key, expires_at=expires_at)
        )
    if _user_has_totp_enabled(store=store, user=user):
        return HTMLResponse(
            _mfa_method_form_html(
                locale=_mcp_locale(request),
                email=user.email,
                expires_in_days=expires_in_days,
            )
        )
    _send_mcp_login_code(store=store, scheduler=scheduler, user=user)
    return HTMLResponse(
        _otp_form_html(locale=_mcp_locale(request), email=user.email, expires_in_days=expires_in_days)
    )


@router.post("/login/mfa", response_class=HTMLResponse)
@legacy_uppercase_router.post("/login/mfa", response_class=HTMLResponse)
def mcp_login_mfa_method(
    request: Request,
    email: str = Form(...),
    mfa_method: str = Form(...),
    expires_in_days: int = Form(1),
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> HTMLResponse:
    if expires_in_days < 1 or expires_in_days > 365:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expiry must be 1-365 days")
    user = store.find_user_by_email(email=email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    method = mfa_method.strip().lower()
    if method == "totp":
        return HTMLResponse(
            _totp_form_html(locale=_mcp_locale(request), email=user.email, expires_in_days=expires_in_days)
        )
    _send_mcp_login_code(store=store, scheduler=scheduler, user=user)
    return HTMLResponse(
        _otp_form_html(locale=_mcp_locale(request), email=user.email, expires_in_days=expires_in_days)
    )


@router.post("/login/verify", response_class=HTMLResponse)
@legacy_uppercase_router.post("/login/verify", response_class=HTMLResponse)
def mcp_login_verify(
    request: Request,
    email: str = Form(...),
    verification_code: str = Form(...),
    mfa_method: str = Form("email"),
    expires_in_days: int = Form(1),
    store: ApiDatabaseStore = Depends(get_user_store),
) -> HTMLResponse:
    if expires_in_days < 1 or expires_in_days > 365:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expiry must be 1-365 days")
    user = store.find_user_by_email(email=email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not _verify_mcp_mfa_code(
        store=store,
        user=user,
        method=mfa_method,
        code=verification_code,
        email_code_key=_mcp_login_code_key(email=email),
    ):
        form_html = _totp_form_html if mfa_method.strip().lower() == "totp" else _otp_form_html
        return HTMLResponse(
            form_html(
                locale=_mcp_locale(request),
                email=email,
                expires_in_days=expires_in_days,
                warning_key="invalid_code",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    _save_mcp_otp_verification(store=store, user=user)
    raw_key, expires_at = _issue_mcp_api_key(store=store, user=user, expires_in_days=expires_in_days)
    return HTMLResponse(_key_created_html(locale=_mcp_locale(request), api_key=raw_key, expires_at=expires_at))


@router.post("/sign-up", response_class=HTMLResponse)
@legacy_uppercase_router.post("/sign-up", response_class=HTMLResponse)
def mcp_sign_up_submit(
    request: Request,
    email: str = Form(...),
    phone_number: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    address: str = Form(...),
    identity_card_number: str = Form(...),
    city: str = Form(""),
    country: str = Form(""),
    zip_code: str = Form(""),
    data_processing_consent_accepted: bool = Form(False),
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> HTMLResponse:
    _require_sign_up_consent(data_processing_consent_accepted)
    _require_sign_up_profile(
        email=email,
        phone_number=phone_number,
        password=password,
        first_name=first_name,
        last_name=last_name,
        address=address,
        identity_card_number=identity_card_number,
    )
    if store.find_user_by_email(email=email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    if store.find_user_by_phone(phone_number=phone_number) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone number is already registered")
    code = generate_one_time_code()
    pending_id = secrets.token_urlsafe(24)
    pending_payload = {
        "email": email.strip().lower(),
        "phone_number": phone_number,
        "password": password,
        "first_name": first_name,
        "last_name": last_name,
        "address": address,
        "identity_card_number": identity_card_number,
        "city": city,
        "country": country,
        "zip_code": zip_code,
    }
    store.save_mcp_pending_signup(
        pending_id=pending_id,
        email=email,
        payload_json=json.dumps(pending_payload, ensure_ascii=True, sort_keys=True),
    )
    store.save_registration_code(email=_mcp_sign_up_code_key(pending_id=pending_id), code=code)
    scheduler.enqueue(
        recipient=email.strip().lower(),
        subject="Your MCP sign-up code",
        body=(
            "Hello,\n\n"
            f"your one time MCP sign-up code is: {code}\n"
            "The code expires in 30 minutes.\n"
        ),
        metadata={"event": "mcp_sign_up_code", "pending_id": pending_id},
    )
    return HTMLResponse(
        _sign_up_otp_form_html(
            locale=_mcp_locale(request),
            pending_id=pending_id,
            email=email,
        )
    )


@router.post("/sign-up/verify", response_class=HTMLResponse)
@legacy_uppercase_router.post("/sign-up/verify", response_class=HTMLResponse)
def mcp_sign_up_verify(
    request: Request,
    pending_id: str = Form(...),
    verification_code: str = Form(...),
    email: str = Form(""),
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> HTMLResponse:
    if not _accepts_any_local_auth_code() and not store.verify_registration_code(
        email=_mcp_sign_up_code_key(pending_id=pending_id),
        code=verification_code,
    ):
        return HTMLResponse(
            _sign_up_otp_form_html(
                locale=_mcp_locale(request),
                pending_id=pending_id,
                email=email,
                warning_key="invalid_code",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    pending_json = store.consume_mcp_pending_signup(pending_id=pending_id)
    if pending_json is None:
        return HTMLResponse(
            _sign_up_otp_form_html(
                locale=_mcp_locale(request),
                pending_id=pending_id,
                email=email,
                warning_key="expired_code",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    pending = json.loads(pending_json)
    try:
        user = store.create_user(
            phone_number=str(pending["phone_number"]),
            email=str(pending["email"]),
            password=str(pending["password"]),
            first_name=str(pending["first_name"]),
            last_name=str(pending["last_name"]),
            address=str(pending["address"]),
            city=str(pending.get("city", "")),
            country=str(pending.get("country", "")),
            zip_code=str(pending.get("zip_code", "")),
            identity_card_number=str(pending["identity_card_number"]),
            data_processing_consent_at=_now_iso(),
            data_processing_consent_version="mcp-sign-up-v1",
        )
    except Exception as exc:
        message = str(exc).lower()
        if "unique" not in message and "duplicate" not in message:
            raise
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists") from exc
    queue_registration_email(scheduler=scheduler, user=user)
    return HTMLResponse(_sign_up_complete_html(locale=_mcp_locale(request), email=user.email))


async def _read_json_rpc_payload(request: Request) -> Any:
    try:
        return await request.json()
    except Exception as exc:
        logger.warning(
            "mcp_json_rpc_invalid_payload request_id=%s correlation_id=%s reason=invalid_json",
            getattr(request.state, "request_id", None),
            getattr(request.state, "correlation_id", None),
        )
        raise HTTPException(status_code=400, detail="Invalid JSON-RPC payload") from exc


def _handle_json_rpc(
    *,
    payload: Any,
    authorization: str | None,
    x_mcp_api_key: str | None,
    store: ApiDatabaseStore | None,
    public_tools: set[str],
) -> JSONResponse:
    if isinstance(payload, list):
        logger.info("mcp_json_rpc_batch_started message_count=%d", len(payload))
        responses = [
            _handle_json_rpc_message(
                message=item,
                authorization=authorization,
                x_mcp_api_key=x_mcp_api_key,
                store=store,
                public_tools=public_tools,
            )
            for item in payload
        ]
        content = [item for item in responses if item is not None]
        logger.info("mcp_json_rpc_batch_completed response_count=%d", len(content))
        return JSONResponse(content)

    response = _handle_json_rpc_message(
        message=payload,
        authorization=authorization,
        x_mcp_api_key=x_mcp_api_key,
        store=store,
        public_tools=public_tools,
    )
    if response is None:
        return JSONResponse(status_code=202, content={})
    return JSONResponse(response)


def _handle_json_rpc_message(
    *,
    message: Any,
    authorization: str | None,
    x_mcp_api_key: str | None,
    store: ApiDatabaseStore | None,
    public_tools: set[str],
) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        logger.warning("mcp_json_rpc_invalid_message reason=non_object")
        return _json_rpc_error(None, -32600, "Invalid Request")
    request_id = message.get("id")
    method = message.get("method")
    if not isinstance(method, str):
        logger.warning("mcp_json_rpc_invalid_message reason=missing_method request_id_type=%s", _value_type(request_id))
        return _json_rpc_error(request_id, -32600, "Invalid Request")

    try:
        logger.info("mcp_json_rpc_method_started method=%s request_id_type=%s", method, _value_type(request_id))
        if method == "initialize":
            requested_protocol_version, selected_protocol_version = _negotiate_mcp_protocol_version(message)
            logger.info(
                "mcp_initialize_completed requested_protocol_version=%s selected_protocol_version=%s",
                requested_protocol_version or "missing",
                selected_protocol_version,
            )
            return _json_rpc_result(
                request_id,
                {
                    "protocolVersion": selected_protocol_version,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "aijurisdiction-laws-mcp", "version": get_api_version()},
                    "instructions": MCP_SERVER_INSTRUCTIONS,
                },
            )
        if method == "notifications/initialized":
            logger.info("mcp_notification_received method=%s", method)
            return None
        if method == "tools/list":
            logger.info("mcp_tools_list_completed tool_count=%d", len(_mcp_tools()))
            return _json_rpc_result(request_id, {"tools": _mcp_tools()})
        if method == "resources/list":
            logger.info("mcp_resources_list_completed resource_count=0")
            return _json_rpc_result(request_id, {"resources": []})
        if method == "resources/templates/list":
            logger.info("mcp_resource_templates_list_completed resource_template_count=0")
            return _json_rpc_result(request_id, {"resourceTemplates": []})
        if method == "prompts/list":
            logger.info("mcp_prompts_list_completed prompt_count=0")
            return _json_rpc_result(request_id, {"prompts": []})
        if method == "ping":
            logger.info("mcp_ping_completed")
            return _json_rpc_result(request_id, {})
        if method == "tools/call":
            raw_params = message.get("params")
            params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
            tool_name = params.get("name")
            raw_arguments = params.get("arguments")
            arguments: dict[str, Any] = raw_arguments if isinstance(raw_arguments, dict) else {}
            if not isinstance(tool_name, str):
                logger.warning("mcp_tool_invalid_request reason=missing_tool_name")
                return _json_rpc_error(request_id, -32602, "Missing tool name")
            started_at = time.perf_counter()
            logger.info(
                "mcp_tool_started tool=%s argument_keys=%s auth_required=%s",
                tool_name,
                ",".join(sorted(str(key) for key in arguments.keys())),
                tool_name not in public_tools,
            )
            if tool_name in public_tools:
                user_id = "internal"
            else:
                user_id = _require_auth_for_tool(
                    tool_name=tool_name,
                    authorization=authorization,
                    x_mcp_api_key=x_mcp_api_key,
                    store=store,
                )
            result = _call_tool(tool_name, arguments, user_id=user_id)
            logger.info(
                "mcp_tool_completed tool=%s duration_ms=%d result_summary=%s",
                tool_name,
                int((time.perf_counter() - started_at) * 1000),
                _tool_result_summary(tool_name=tool_name, result=result),
            )
            return _json_rpc_result(request_id, {"content": [{"type": "text", "text": _json_text(result)}]})
        logger.warning("mcp_json_rpc_unknown_method method=%s", method)
        return _json_rpc_error(request_id, -32601, f"Method not found: {method}")
    except HTTPException as exc:
        logger.warning(
            "mcp_json_rpc_error method=%s status_code=%d detail=%s",
            method,
            exc.status_code,
            exc.detail,
        )
        return _json_rpc_error(request_id, exc.status_code, str(exc.detail))
    except Exception as exc:
        logger.exception("mcp_json_rpc_unhandled_error method=%s", method)
        return _json_rpc_error(request_id, -32000, str(exc))


def _require_auth_for_tool(
    *,
    tool_name: str,
    authorization: str | None,
    x_mcp_api_key: str | None,
    store: ApiDatabaseStore | None,
) -> str:
    api_key = _extract_mcp_api_key(authorization=authorization, x_mcp_api_key=x_mcp_api_key)
    if not api_key:
        logger.warning("mcp_tool_auth_failed tool=%s reason=missing_api_key", tool_name)
        raise HTTPException(status_code=401, detail="Tool requires a valid MCP API key")
    if store is None:
        logger.error("mcp_tool_auth_failed tool=%s reason=missing_user_store", tool_name)
        raise HTTPException(status_code=500, detail="MCP user store is unavailable")
    user = _authenticate_mcp_api_token(api_key=api_key, store=store)
    logger.info("mcp_tool_auth_succeeded tool=%s user_id=%s", tool_name, user.user_id)
    return str(user.user_id)


def _call_tool(name: str, arguments: dict[str, Any], *, user_id: str = "internal") -> Any:
    handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
        "getVersion": _tool_get_version,
        "getStatistics": _tool_get_statistics,
        "searchLegalSources": _tool_search_legal_sources,
        "searchLaws": _tool_search_laws,
        "rankLawsByAmendments": _tool_rank_laws_by_amendments,
        "getLawHistory": _tool_get_law_history,
        "getLawText": _tool_get_law_text,
        "searchCourtDecisions": _tool_search_court_decisions,
        "getCourtDecision": _tool_get_court_decision,
        "startLegalSearch": lambda args: _tool_start_legal_search(args, user_id=user_id),
        "getLegalSearchStatus": lambda args: _tool_get_legal_search_status(args, user_id=user_id),
        "getLegalSearchResult": lambda args: _tool_get_legal_search_result(args, user_id=user_id),
    }
    handler = handlers.get(name)
    if handler is None:
        logger.warning("mcp_tool_unknown tool=%s", name)
        raise HTTPException(status_code=404, detail=f"Unknown MCP tool: {name}")
    return handler(arguments)


def _tool_rank_laws_by_amendments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Rank published laws by distinct amending acts recorded by the collector."""
    country_code = str(arguments.get("country_code", "SK")).strip().upper() or "SK"
    published_year = _bounded_int(
        arguments.get("published_year"), default=datetime.now(timezone.utc).year, minimum=1900, maximum=9999
    )
    amendment_year = _bounded_int(
        arguments.get("amendment_year"), default=published_year, minimum=1900, maximum=9999
    )
    limit = _bounded_int(arguments.get("limit"), default=5, minimum=1, maximum=20)
    with _LawsQuerySession(statement_timeout_ms=_LEGAL_SEARCH_TIMEOUT_MS) as laws:
        rows = laws.query_all(
            f"""
            WITH latest_metadata AS (
                SELECT law_metadata_id, document_id, version_id, law_identifier_text,
                       title, publication_date, effective_from
                FROM (
                    SELECT m.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY m.document_id
                               ORDER BY m.effective_from DESC, m.version_id DESC
                           ) AS row_number
                    FROM law_metadata AS m
                ) AS ranked
                WHERE row_number = 1
            )
            SELECT d.document_id, d.law_year, d.law_number,
                   m.law_identifier_text, m.title, d.source_url,
                   m.publication_date, m.effective_from,
                   COUNT(DISTINCT source_d.document_id) AS amendment_count,
                   (SELECT COUNT(*) FROM law_versions AS versions
                    WHERE versions.document_id = d.document_id) AS version_count,
                   MAX(CASE WHEN source_d.document_id IS NOT NULL
                            THEN source_m.publication_date END) AS latest_amendment_date
            FROM law_documents AS d
            JOIN latest_metadata AS m ON m.document_id = d.document_id
            LEFT JOIN law_metadata_relations AS relation
              ON relation.relation_type = 'amends'
             AND UPPER(relation.target_country_code) = UPPER(d.country_code)
             AND relation.target_collection_code = d.collection_code
             AND relation.target_law_year = d.law_year
             AND relation.target_law_number = d.law_number
            LEFT JOIN law_metadata AS source_m
              ON source_m.law_metadata_id = relation.law_metadata_id
            LEFT JOIN law_documents AS source_d
              ON source_d.document_id = source_m.document_id
             AND source_d.law_year = {laws.param}
            WHERE UPPER(d.country_code) = {laws.param}
              AND d.law_year = {laws.param}
            GROUP BY d.document_id, d.law_year, d.law_number,
                     m.law_identifier_text, m.title, d.source_url,
                     m.publication_date, m.effective_from
            ORDER BY amendment_count DESC, d.law_number DESC
            LIMIT {laws.param}
            """,
            (amendment_year, country_code, published_year, limit),
        )
    results = [
        {
            "rank": index,
            "document_id": str(row[0]),
            "law_year": int(row[1]),
            "law_number": int(row[2]),
            "law_identifier_text": str(row[3]),
            "title": str(row[4]),
            "source_url": str(row[5]),
            "publication_date": str(row[6]),
            "effective_from": str(row[7]),
            "amendment_count": int(row[8]),
            "version_count": int(row[9]),
            "latest_amendment_date": str(row[10]) if row[10] is not None else None,
        }
        for index, row in enumerate(rows, start=1)
    ]
    return {
        "status": "ok",
        "country_code": country_code,
        "metric": "distinct_amending_acts",
        "published_year": published_year,
        "amendment_year": amendment_year,
        "population": "laws_published_in_year",
        "proxy_disclosure": (
            "Amendment frequency is a user-selected analytical proxy and does not prove that a law is incorrect."
        ),
        "human_review_required": True,
        "coverage": {
            "source": "JurisDigta imported Slov-Lex metadata relations",
            "complete": False,
            "limitation": "Counts include only imported relations classified as amends.",
        },
        "results": results,
    }


def _tool_get_law_history(arguments: dict[str, Any]) -> dict[str, Any]:
    document_id = str(arguments.get("document_id") or "").strip()
    if not document_id:
        raise HTTPException(status_code=400, detail="document_id is required")
    with _LawsQuerySession(statement_timeout_ms=_LEGAL_SEARCH_TIMEOUT_MS) as laws:
        versions = laws.query_all(
            f"""
            SELECT v.version_id, v.version_token, v.effective_from,
                   m.publication_date, COALESCE(m.law_identifier_text, ''),
                   COALESCE(m.title, d.official_name), d.source_url
            FROM law_documents AS d
            JOIN law_versions AS v ON v.document_id = d.document_id
            LEFT JOIN law_metadata AS m ON m.version_id = v.version_id
            WHERE d.document_id = {laws.param}
            ORDER BY v.effective_from, v.version_token
            """,
            (document_id,),
        )
        relations = laws.query_all(
            f"""
            SELECT relation.relation_type, relation.target_law_identifier_text,
                   relation.target_title, relation.target_url,
                   source_m.publication_date
            FROM law_metadata AS source_m
            JOIN law_metadata_relations AS relation
              ON relation.law_metadata_id = source_m.law_metadata_id
            WHERE source_m.document_id = {laws.param}
            ORDER BY source_m.publication_date, relation.ordinal
            """,
            (document_id,),
        )
    return {
        "status": "ok",
        "document_id": document_id,
        "version_count": len(versions),
        "versions": [
            {
                "version_id": str(row[0]),
                "version_token": str(row[1]),
                "effective_from": str(row[2]),
                "publication_date": str(row[3]) if row[3] is not None else None,
                "law_identifier_text": str(row[4]),
                "title": str(row[5]),
                "source_url": str(row[6]),
            }
            for row in versions
        ],
        "relations": [
            {
                "relation_type": str(row[0]),
                "target_law_identifier_text": str(row[1]),
                "target_title": str(row[2]),
                "target_url": str(row[3]),
                "publication_date": str(row[4]) if row[4] is not None else None,
            }
            for row in relations
        ],
        "human_review_required": True,
        "coverage": {
            "complete": False,
            "limitation": "History includes only versions and relations imported by JurisDigta.",
        },
    }


def _tool_start_legal_search(arguments: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    tool_name = str(arguments.get("tool_name") or arguments.get("tool") or "searchLegalSources").strip()
    if tool_name not in {"searchLegalSources", "searchLaws", "searchCourtDecisions"}:
        raise HTTPException(
            status_code=400,
            detail="tool_name must be searchLegalSources, searchLaws, or searchCourtDecisions",
        )
    raw_tool_arguments = arguments.get("arguments")
    if isinstance(raw_tool_arguments, dict):
        tool_arguments = dict(raw_tool_arguments)
    else:
        tool_arguments = {
            key: value
            for key, value in arguments.items()
            if key not in {"tool", "tool_name", "arguments"}
        }
    tool_arguments = _normalized_async_search_arguments(tool_name=tool_name, arguments=tool_arguments)
    search_id = secrets.token_urlsafe(24)
    created_at = time.time()
    expires_at = created_at + _MCP_ASYNC_SEARCH_RETENTION_SECONDS
    future = _ASYNC_SEARCH_EXECUTOR.submit(_run_async_legal_search, tool_name, tool_arguments)
    job = _AsyncSearchJob(
        search_id=search_id,
        user_id=user_id,
        tool_name=tool_name,
        arguments=tool_arguments,
        created_at=created_at,
        expires_at=expires_at,
        future=future,
    )
    with _ASYNC_SEARCH_LOCK:
        _purge_expired_async_search_jobs(now=created_at)
        _ASYNC_SEARCH_JOBS[search_id] = job
    logger.info(
        "mcp_async_legal_search_started search_id_hash=%s tool=%s user_id=%s retention_seconds=%d",
        _stable_hash(search_id),
        tool_name,
        user_id,
        _MCP_ASYNC_SEARCH_RETENTION_SECONDS,
    )
    return {
        "search_id": search_id,
        "status": "running",
        "tool_name": tool_name,
        "created_at": _iso_from_epoch(created_at),
        "expires_at": _iso_from_epoch(expires_at),
        "retention_seconds": _MCP_ASYNC_SEARCH_RETENTION_SECONDS,
        "timeout_ms": _LEGAL_SEARCH_TIMEOUT_MS,
    }


def _tool_get_legal_search_status(arguments: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    search_id = _required_search_id(arguments)
    job = _async_search_job_for_user(search_id=search_id, user_id=user_id)
    return {
        "search_id": search_id,
        "status": _async_search_job_status(job),
        "tool_name": job.tool_name,
        "created_at": _iso_from_epoch(job.created_at),
        "expires_at": _iso_from_epoch(job.expires_at),
        "done": job.future.done(),
        "retention_seconds": _MCP_ASYNC_SEARCH_RETENTION_SECONDS,
    }


def _tool_get_legal_search_result(arguments: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    search_id = _required_search_id(arguments)
    job = _async_search_job_for_user(search_id=search_id, user_id=user_id)
    if not job.future.done():
        return {
            "search_id": search_id,
            "status": "running",
            "tool_name": job.tool_name,
            "created_at": _iso_from_epoch(job.created_at),
            "expires_at": _iso_from_epoch(job.expires_at),
            "result": None,
        }
    try:
        result = job.future.result()
    except Exception as exc:
        logger.warning(
            "mcp_async_legal_search_failed search_id_hash=%s tool=%s error_kind=%s exception=%s",
            _stable_hash(search_id),
            job.tool_name,
            _legal_search_error_kind(exc),
            exc.__class__.__name__,
        )
        result = _async_legal_search_degraded_result(
            tool_name=job.tool_name,
            arguments=job.arguments,
            duration_ms=0,
            error_kind=_legal_search_error_kind(exc),
        )
    result_status = str(result.get("status", "ok"))
    return {
        "search_id": search_id,
        "status": "completed" if result_status == "ok" else result_status,
        "tool_name": job.tool_name,
        "created_at": _iso_from_epoch(job.created_at),
        "expires_at": _iso_from_epoch(job.expires_at),
        "result": result,
    }


def _run_async_legal_search(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "searchLegalSources":
        return _tool_search_legal_sources(arguments)
    if tool_name == "searchLaws":
        return _tool_search_laws(arguments)
    if tool_name == "searchCourtDecisions":
        return _tool_search_court_decisions(arguments)
    raise ValueError(f"Unsupported async legal search tool: {tool_name}")


def _normalized_async_search_arguments(*, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(arguments)
    if tool_name in {"searchLegalSources", "searchLaws", "searchCourtDecisions"} and "sort" in normalized:
        normalized["sort"] = _search_sort(normalized.get("sort"))
    return normalized


def _required_search_id(arguments: dict[str, Any]) -> str:
    search_id = str(arguments.get("search_id", "")).strip()
    if not search_id:
        raise HTTPException(status_code=400, detail="search_id is required")
    return search_id


def _async_search_job_for_user(*, search_id: str, user_id: str) -> _AsyncSearchJob:
    now = time.time()
    with _ASYNC_SEARCH_LOCK:
        _purge_expired_async_search_jobs(now=now)
        job = _ASYNC_SEARCH_JOBS.get(search_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Legal search job not found or expired")
    if job.user_id != user_id:
        logger.warning("mcp_async_legal_search_access_denied search_id_hash=%s", _stable_hash(search_id))
        raise HTTPException(status_code=404, detail="Legal search job not found or expired")
    return job


def _purge_expired_async_search_jobs(*, now: float) -> None:
    expired = [search_id for search_id, job in _ASYNC_SEARCH_JOBS.items() if job.expires_at <= now]
    for search_id in expired:
        _ASYNC_SEARCH_JOBS.pop(search_id, None)


def _async_search_job_status(job: _AsyncSearchJob) -> str:
    if not job.future.done():
        return "running"
    if job.future.exception() is not None:
        return "degraded"
    result = job.future.result()
    status = str(result.get("status", "ok"))
    return "completed" if status == "ok" else status


def _iso_from_epoch(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat()


def _tool_get_version(_arguments: dict[str, Any]) -> dict[str, Any]:
    court_decisions = _court_decision_statistics()
    court_decision_collector_version = get_core_version()
    return {
        "api_version": get_api_version(),
        "mcp_server_version": get_mcp_server_version(),
        "system_version": get_core_version(),
        "mobile_app_version": get_mobile_app_version(),
        "web_app_version": get_web_app_version(),
        "court_decision_collector_version": court_decision_collector_version,
        "court_decision_collector": {
            "version": court_decision_collector_version,
            "status": court_decisions.get("collector_status"),
            "last_imported_decision": court_decisions.get("last_imported_decision"),
            "last_imported_at": court_decisions.get("last_imported_at"),
        },
    }


def _tool_get_statistics(arguments: dict[str, Any]) -> dict[str, Any]:
    country_code = str(arguments.get("country_code", "SK")).strip().upper() or "SK"
    logger.info("mcp_tool_get_statistics_query country_code=%s", country_code)
    payload = _read_laws_statistics(config=_laws_db_config(), country_code=country_code)
    collector = payload.get("collector", {})
    court_decisions = _court_decision_statistics()
    result = {
        "country_code": payload.get("country_code"),
        "processed_laws": payload.get("totals", {}).get("laws_imported", 0),
        "last_processed_law": collector.get("last_processed_law"),
        "last_processed_day": collector.get("last_processed_at"),
        "court_decision_collector_version": get_core_version(),
        "total_court_decisions": court_decisions.get("total_decisions", 0),
        "last_imported_decision": court_decisions.get("last_imported_decision"),
        "last_imported_decision_at": court_decisions.get("last_imported_at"),
        "court_decisions": court_decisions,
        "details": payload,
    }
    logger.info(
        (
            "mcp_tool_get_statistics_result country_code=%s processed_laws=%s "
            "last_processed_law=%s total_court_decisions=%s last_imported_decision=%s"
        ),
        result["country_code"],
        result["processed_laws"],
        result["last_processed_law"],
        result["total_court_decisions"],
        result["last_imported_decision"],
    )
    return result


def _tool_search_legal_sources(arguments: dict[str, Any]) -> dict[str, Any]:
    query = _required_search_query(arguments)
    country_code = str(arguments.get("country_code", "SK")).strip().upper() or "SK"
    source_types = _requested_source_types(arguments.get("source_types"))
    limit_per_source = _bounded_int(arguments.get("limit_per_source"), default=10, minimum=1, maximum=50)
    offset = _bounded_int(arguments.get("offset"), default=0, minimum=0, maximum=10_000)
    published_year = _optional_positive_int(arguments.get("published_year"))
    year_filter_mode = _year_filter_mode(arguments.get("year_filter_mode"))
    sort = _search_sort(arguments.get("sort"))
    logger.info(
        (
            "mcp_tool_search_legal_sources_query country_code=%s source_types=%s "
            "published_year=%s year_filter_mode=%s sort=%s limit_per_source=%d offset=%d query_length=%d"
        ),
        country_code,
        ",".join(source_types),
        published_year,
        year_filter_mode,
        sort,
        limit_per_source,
        offset,
        len(query),
    )
    laws_payload: dict[str, Any] | None = None
    court_decisions_payload: dict[str, Any] | None = None
    if "laws" in source_types:
        laws_payload = _search_laws(
            query=query,
            country_code=country_code,
            limit=limit_per_source,
            offset=offset,
            published_year=published_year,
            year_filter_mode=year_filter_mode,
            law_year=None,
            law_number=None,
            metadata_only=True,
            sort=sort,
            include_summaries=False,
        )
    if "court_decisions" in source_types:
        court_decisions_payload = _search_court_decisions(
            query=query,
            limit=limit_per_source,
            offset=offset,
            published_year=published_year,
            year_filter_mode=year_filter_mode,
            court_type=str(arguments.get("court_type", "")).strip(),
            court_name=str(arguments.get("court_name", "")).strip(),
            include_snippets=False,
            include_summaries=False,
            sort=sort,
        )
    result: dict[str, Any] = {
        "query": query,
        "country_code": country_code,
        "source_types": source_types,
        "year_filter_mode": year_filter_mode,
        "sort": sort,
        "published_year": published_year,
        "limit_per_source": limit_per_source,
        "offset": offset,
        "laws": laws_payload["results"] if laws_payload else [],
        "court_decisions": court_decisions_payload["results"] if court_decisions_payload else [],
        "court_decision_data_quality": (
            court_decisions_payload.get("data_quality") if court_decisions_payload else None
        ),
        "status": "ok",
        "warnings": [],
        "timeout_ms": _LEGAL_SEARCH_TIMEOUT_MS,
    }
    if laws_payload and laws_payload.get("status") == "degraded":
        result["status"] = "degraded"
        result["warnings"].append(laws_payload["error"])
    if court_decisions_payload and court_decisions_payload.get("status") == "degraded":
        result["status"] = "degraded"
        result["warnings"].append(court_decisions_payload["error"])
    if result["status"] == "degraded":
        async_fallback = _async_search_fallback(
            tool_name="searchLegalSources",
            arguments={
                "query": query,
                "country_code": country_code,
                "source_types": source_types,
                "published_year": published_year,
                "year_filter_mode": year_filter_mode,
                "court_type": str(arguments.get("court_type", "")).strip(),
                "court_name": str(arguments.get("court_name", "")).strip(),
                "sort": sort,
                "limit_per_source": limit_per_source,
                "offset": offset,
            },
        )
        result["async_fallback"] = async_fallback
    logger.info(
        "mcp_tool_search_legal_sources_result laws=%d court_decisions=%d status=%s",
        len(result["laws"]),
        len(result["court_decisions"]),
        result["status"],
    )
    return result


def _tool_search_laws(arguments: dict[str, Any]) -> dict[str, Any]:
    query = _required_search_query(arguments)
    country_code = str(arguments.get("country_code", "SK")).strip().upper() or "SK"
    limit = _bounded_int(arguments.get("limit"), default=10, minimum=1, maximum=50)
    offset = _bounded_int(arguments.get("offset"), default=0, minimum=0, maximum=10_000)
    published_year = _optional_positive_int(arguments.get("published_year"))
    year_filter_mode = _year_filter_mode(arguments.get("year_filter_mode"))
    sort = _search_sort(arguments.get("sort"))
    include_summaries = _bool_argument(arguments.get("include_summaries"), default=False)
    requested_law_year = _optional_positive_int(arguments.get("law_year"))
    requested_law_number = _optional_positive_int(arguments.get("law_number"))
    parsed_identifier = _parse_law_identifier(query)
    if requested_law_year is None and parsed_identifier is not None:
        requested_law_year = parsed_identifier[0]
    if requested_law_number is None and parsed_identifier is not None:
        requested_law_number = parsed_identifier[1]
    return _search_laws(
        query=query,
        country_code=country_code,
        limit=limit,
        offset=offset,
        published_year=published_year,
        year_filter_mode=year_filter_mode,
        law_year=requested_law_year,
        law_number=requested_law_number,
        metadata_only=True,
        sort=sort,
        include_summaries=include_summaries,
    )


def _search_laws(
    *,
    query: str,
    country_code: str,
    limit: int,
    offset: int,
    published_year: int | None,
    year_filter_mode: str,
    law_year: int | None,
    law_number: int | None,
    metadata_only: bool,
    sort: str,
    include_summaries: bool,
) -> dict[str, Any]:
    if year_filter_mode != "published_in":
        raise HTTPException(status_code=400, detail="Only year_filter_mode=published_in is supported")
    broad_latest_request = _is_broad_latest_law_request(
        query=query,
        sort=sort,
        published_year=published_year,
        law_year=law_year,
        law_number=law_number,
    )
    pattern = "%" if broad_latest_request else f"%{query.lower()}%"
    exact = query.lower()
    provision_profile = (
        build_legal_query_profile(query)
        if sort == "relevance" and law_year is None and law_number is None
        else None
    )
    logger.info(
        (
            "mcp_tool_search_laws_query country_code=%s limit=%d offset=%d "
            "published_year=%s year_filter_mode=%s sort=%s timeout_ms=%d query_length=%d"
        ),
        country_code,
        limit,
        offset,
        published_year,
        year_filter_mode,
        sort,
        _LEGAL_SEARCH_TIMEOUT_MS,
        len(query),
    )

    started_at = time.perf_counter()
    try:
        with _LawsQuerySession(statement_timeout_ms=_LEGAL_SEARCH_TIMEOUT_MS) as laws:
            law_year_filter = ""
            law_number_filter = ""
            published_year_filter = ""
            query_params: list[Any] = [
                country_code,
                pattern,
                pattern,
                pattern,
                pattern,
            ]
            if law_year is not None:
                law_year_filter = f" AND d.law_year = {laws.param}"
                query_params.append(law_year)
            if law_number is not None:
                law_number_filter = f" AND d.law_number = {laws.param}"
                query_params.append(law_number)
            if published_year is not None:
                published_year_filter = f" AND d.law_year = {laws.param}"
                query_params.append(published_year)
            order_by = (
                "d.law_year DESC, d.law_number DESC, v.effective_from DESC"
                if sort == "latest"
                else """
                CASE
                    WHEN LOWER(COALESCE(m.law_identifier_text, '')) = {param} THEN 0
                    WHEN LOWER(COALESCE(m.title, d.official_name)) = {param} THEN 1
                    WHEN LOWER(d.lawyer_title) = {param} THEN 2
                    WHEN COALESCE(m.law_identifier_text, '') LIKE {param} THEN 3
                    ELSE 10
                END,
                d.law_year DESC,
                d.law_number DESC,
                v.effective_from DESC
                """.format(param=laws.param)
            )
            if sort == "relevance":
                query_params.extend(
                    [
                        exact,
                        exact,
                        exact,
                        f"{law_number}/{law_year}%" if law_year and law_number else "",
                    ]
                )
            query_params.extend([limit, offset])
            rows = laws.query_all(
                f"""
                WITH latest_versions AS (
                    SELECT version_id, document_id, version_token, effective_from
                    FROM (
                        SELECT
                            v.version_id,
                            v.document_id,
                            v.version_token,
                            v.effective_from,
                            ROW_NUMBER() OVER (
                                PARTITION BY v.document_id
                                ORDER BY v.effective_from DESC, v.version_token DESC
                            ) AS row_number
                    FROM law_versions AS v
                    WHERE v.effective_from <= CURRENT_DATE
                    ) AS ranked_versions
                    WHERE row_number = 1
                )
                SELECT
                    d.document_id,
                    d.country_code,
                    d.collection_code,
                    d.law_year,
                    d.law_number,
                    d.official_name,
                    d.lawyer_title,
                    d.source_url,
                    v.version_id,
                    v.version_token,
                    v.effective_from,
                    COALESCE(m.law_identifier_text, '') AS law_identifier_text,
                    COALESCE(m.title, d.official_name) AS title,
                    COALESCE(m.law_type, '') AS law_type
                FROM law_documents AS d
                JOIN latest_versions AS v ON v.document_id = d.document_id
                LEFT JOIN law_metadata AS m ON m.version_id = v.version_id
                WHERE UPPER(d.country_code) = {laws.param}
                  AND (
                      LOWER(d.official_name) LIKE {laws.param}
                      OR LOWER(d.lawyer_title) LIKE {laws.param}
                      OR LOWER(COALESCE(m.title, '')) LIKE {laws.param}
                      OR LOWER(COALESCE(m.law_identifier_text, '')) LIKE {laws.param}
                  )
                  {law_year_filter}
                  {law_number_filter}
                  {published_year_filter}
                ORDER BY {order_by}
                LIMIT {laws.param}
                OFFSET {laws.param}
                """,
                tuple(query_params),
            )
            provision_rows = (
                _query_provision_candidates(
                    laws=laws,
                    profile=provision_profile,
                    country_code=country_code,
                    published_year=published_year,
                    law_year=law_year,
                    law_number=law_number,
                    candidate_limit=max(300, min(2_000, (limit + offset) * 60)),
                )
                if provision_profile is not None and provision_profile.search_terms
                else []
            )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        error_kind = _legal_search_error_kind(exc)
        logger.warning(
            (
                "mcp_tool_search_laws_degraded country_code=%s query_length=%d limit=%d "
                "duration_ms=%d error_kind=%s exception=%s request_id=%s correlation_id=%s"
            ),
            country_code,
            len(query),
            limit,
            duration_ms,
            error_kind,
            exc.__class__.__name__,
            _CURRENT_MCP_REQUEST_ID.get(),
            _CURRENT_MCP_CORRELATION_ID.get(),
        )
        return _legal_search_degraded_result(
            query=query,
            country_code=country_code,
            limit=limit,
            offset=offset,
            published_year=published_year,
            year_filter_mode=year_filter_mode,
            sort=sort,
            duration_ms=duration_ms,
            error_kind=error_kind,
        )
    metadata_results = [
        _search_result_from_row(row, include_summary=include_summaries) for row in rows
    ]
    provision_results = (
        _rank_provision_candidates(rows=provision_rows, profile=provision_profile)
        if provision_profile is not None
        else []
    )
    results = _merge_law_search_results(
        provision_results=provision_results,
        metadata_results=metadata_results,
        offset=offset,
        limit=limit,
    )
    logger.info("mcp_tool_search_laws_result country_code=%s result_count=%d", country_code, len(results))
    return {
        "query": query,
        "country_code": country_code,
        "year_filter_mode": year_filter_mode,
        "published_year": published_year,
        "sort": sort,
        "query_scope": "all_latest" if broad_latest_request else "matching",
        "include_summaries": include_summaries,
        "metadata_only": metadata_only and not provision_results,
        "retrieval_mode": "provision_aware" if provision_results else "metadata",
        "query_concepts": list(provision_profile.concepts) if provision_profile is not None else [],
        "human_review_required": True,
        "limitations": _law_search_limitations(provision_profile),
        "limit": limit,
        "offset": offset,
        "status": "ok",
        "timeout_ms": _LEGAL_SEARCH_TIMEOUT_MS,
        "results": results,
    }


def _query_provision_candidates(
    *,
    laws: _LawsQueryConfig,
    profile: LegalQueryProfile,
    country_code: str,
    published_year: int | None,
    law_year: int | None,
    law_number: int | None,
    candidate_limit: int,
) -> list[Sequence[Any]]:
    filters: list[str] = []
    filter_params: list[Any] = []
    if law_year is not None:
        filters.append(f"d.law_year = {laws.param}")
        filter_params.append(law_year)
    if law_number is not None:
        filters.append(f"d.law_number = {laws.param}")
        filter_params.append(law_number)
    if published_year is not None:
        filters.append(f"d.law_year = {laws.param}")
        filter_params.append(published_year)
    extra_filter = "" if not filters else " AND " + " AND ".join(filters)
    if laws.backend == "postgres":
        tsqueries = build_postgres_legal_tsqueries(profile)
        fts_scan_limit = max(
            _PROVISION_FTS_SCAN_MINIMUM,
            min(_PROVISION_FTS_SCAN_MAXIMUM, candidate_limit * _PROVISION_FTS_SCAN_MULTIPLIER),
        )
        per_query_limit = max(
            100,
            (fts_scan_limit + max(len(tsqueries), 1) - 1) // max(len(tsqueries), 1),
        )
        candidate_queries = []
        candidate_params: list[Any] = []
        for relation_index, tsquery in enumerate(tsqueries, start=1):
            candidate_queries.append(
                f"""
                (
                    SELECT
                        p.provision_id,
                        p.version_id,
                        p.anchor,
                        p.heading,
                        p.body_text,
                        p.ordinal,
                        {relation_index} AS relation_index,
                        ts_rank_cd(
                            to_tsvector('simple', LOWER(p.body_text)),
                            to_tsquery('simple', {laws.param})
                    ) AS database_rank
                    FROM law_provisions AS p
                    JOIN law_versions AS candidate_version
                        ON candidate_version.version_id = p.version_id
                    WHERE to_tsvector('simple', LOWER(p.body_text))
                        @@ to_tsquery('simple', {laws.param})
                      AND candidate_version.effective_from <= CURRENT_DATE
                      AND NOT EXISTS (
                          SELECT 1
                          FROM law_versions AS candidate_newer
                          WHERE candidate_newer.document_id = candidate_version.document_id
                            AND candidate_newer.effective_from <= CURRENT_DATE
                            AND (
                                candidate_newer.effective_from
                                    > candidate_version.effective_from
                                OR (
                                    candidate_newer.effective_from
                                        = candidate_version.effective_from
                                    AND candidate_newer.version_token
                                        > candidate_version.version_token
                                )
                            )
                      )
                    ORDER BY database_rank DESC, p.provision_id
                    LIMIT {laws.param}
                )
                """
            )
            candidate_params.extend((tsquery, tsquery, per_query_limit))
        laws.query_all("SELECT set_config('enable_seqscan', 'off', true)", ())
        return laws.query_all(
            f"""
            WITH fts_candidates AS MATERIALIZED (
                {' UNION ALL '.join(candidate_queries)}
            )
            SELECT
                d.document_id,
                d.country_code,
                d.collection_code,
                d.law_year,
                d.law_number,
                d.official_name,
                d.lawyer_title,
                d.source_url,
                v.version_id,
                v.version_token,
                v.effective_from,
                COALESCE(m.law_identifier_text, ''),
                COALESCE(m.title, d.official_name),
                COALESCE(m.law_type, ''),
                p.anchor,
                p.heading,
                p.body_text,
                p.ordinal,
                p.database_rank,
                p.relation_index
            FROM fts_candidates AS p
            JOIN law_versions AS v ON v.version_id = p.version_id
            JOIN law_documents AS d ON d.document_id = v.document_id
            LEFT JOIN law_metadata AS m ON m.version_id = v.version_id
            WHERE UPPER(d.country_code) = {laws.param}
              {extra_filter}
            ORDER BY database_rank DESC, d.law_year DESC, p.ordinal
            """,
            tuple(
                [
                    *candidate_params,
                    country_code,
                    *filter_params,
                ]
            ),
        )

    term_clauses = [
        f"LOWER(COALESCE(m.title, d.official_name) || ' ' || p.heading || ' ' || p.body_text) LIKE {laws.param}"
        for _term in profile.search_terms
    ]
    return laws.query_all(
        f"""
        WITH latest_versions AS (
            SELECT version_id, document_id, version_token, effective_from
            FROM (
                SELECT
                    v.version_id,
                    v.document_id,
                    v.version_token,
                    v.effective_from,
                    ROW_NUMBER() OVER (
                        PARTITION BY v.document_id
                        ORDER BY v.effective_from DESC, v.version_token DESC
                    ) AS row_number
            FROM law_versions AS v
            WHERE v.effective_from <= CURRENT_DATE
            ) AS ranked_versions
            WHERE row_number = 1
        )
        SELECT
            d.document_id,
            d.country_code,
            d.collection_code,
            d.law_year,
            d.law_number,
            d.official_name,
            d.lawyer_title,
            d.source_url,
            v.version_id,
            v.version_token,
            v.effective_from,
            COALESCE(m.law_identifier_text, ''),
            COALESCE(m.title, d.official_name),
            COALESCE(m.law_type, ''),
            p.anchor,
            p.heading,
            p.body_text,
            p.ordinal,
            0.0 AS database_rank
        FROM law_documents AS d
        JOIN latest_versions AS v ON v.document_id = d.document_id
        JOIN law_provisions AS p ON p.version_id = v.version_id
        LEFT JOIN law_metadata AS m ON m.version_id = v.version_id
        WHERE UPPER(d.country_code) = {laws.param}
          AND ({' OR '.join(term_clauses)})
          {extra_filter}
        ORDER BY d.law_year DESC, p.ordinal
        LIMIT {laws.param}
        """,
        tuple(
            [
                country_code,
                *(f"%{term.lower()}%" for term in profile.search_terms),
                *filter_params,
                candidate_limit,
            ]
        ),
    )


def _rank_provision_candidates(
    *,
    rows: list[Sequence[Any]],
    profile: LegalQueryProfile,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        parsed_anchor = parse_provision_anchor(str(row[14]))
        if parsed_anchor is None:
            continue
        relevance = score_provision_text(
            profile=profile,
            title=f"{row[5]} {row[6]} {row[12]}",
            heading=str(row[15]),
            body_text=str(row[16]),
            database_rank=float(row[18]),
        )
        if relevance_confidence(relevance.score) == "low":
            continue
        document_id = str(row[0])
        record = grouped.setdefault(
            document_id,
            {
                **_search_result_from_row(row),
                "matched_provisions": [],
                "_score": 0.0,
                "_sections": set(),
                "_relations": set(),
            },
        )
        provisions = cast(list[dict[str, Any]], record["matched_provisions"])
        if len(provisions) >= 24:
            continue
        provisions.append(
            {
                "anchor": str(row[14]),
                "section_number": parsed_anchor.section_number,
                "paragraph_number": parsed_anchor.paragraph_number,
                "heading": str(row[15]),
                "snippet": _bounded_law_snippet(str(row[16])),
                "matched_terms": list(relevance.matched_terms),
                "relevance_score": _normalized_law_relevance_score(relevance.score),
            }
        )
        record["_score"] = max(float(record["_score"]), relevance.score)
        cast(set[int], record["_sections"]).add(parsed_anchor.section_number)
        if len(row) > 19:
            cast(set[int], record["_relations"]).add(int(row[19]))

    results: list[dict[str, Any]] = []
    for record in grouped.values():
        sections = cast(set[int], record.pop("_sections"))
        relations = cast(set[int], record.pop("_relations"))
        aggregate_score = (
            float(record.pop("_score"))
            + min(len(sections), 8) * 0.75
            + min(len(relations), 6) * 4.0
            + _law_candidate_ranking_adjustment(
                profile=profile,
                law_type=str(record["law_type"]),
                title=f"{record['official_name']} {record['lawyer_title']} {record['title']}",
            )
        )
        provisions = cast(list[dict[str, Any]], record["matched_provisions"])
        provisions.sort(
            key=lambda provision: (
                -float(provision["relevance_score"]),
                int(provision["section_number"]),
                int(provision["paragraph_number"] or 0),
            )
        )
        record["relevant_sections"] = sorted(sections)
        record["relevant_section_ranges"] = [
            {"section_start": start, "section_end": end}
            for start, end in compact_section_ranges(sections, maximum_gap=3)
        ]
        record["retrieval_basis"] = "law_provisions"
        record["matched_relation_count"] = len(relations)
        record["_sort_score"] = aggregate_score
        record["relevance_score"] = _normalized_law_relevance_score(aggregate_score)
        record["confidence"] = relevance_confidence(aggregate_score)
        results.append(record)
    results.sort(
        key=lambda record: (
            -float(record["_sort_score"]),
            -int(record["law_year"]),
            -int(record["law_number"]),
        )
    )
    for record in results:
        record.pop("_sort_score", None)
    return results


def _normalized_law_relevance_score(score: float) -> float:
    bounded_score = max(score, 0.0)
    return round(bounded_score / (bounded_score + 40.0), 4)


def _law_candidate_ranking_adjustment(
    *, profile: LegalQueryProfile, law_type: str, title: str
) -> float:
    normalized_type = normalize_legal_text(law_type)
    normalized_title = normalize_legal_text(title)
    adjustment = 10.0 if normalized_type == "zakon" else 0.0
    if "real_estate" in profile.concepts and "katastr" in normalized_title:
        adjustment += 16.0
    if "ktorym sa meni" in normalized_title or "uplne znenie" in normalized_title:
        adjustment -= 12.0
    return adjustment


def _merge_law_search_results(
    *,
    provision_results: list[dict[str, Any]],
    metadata_results: list[dict[str, Any]],
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    if not provision_results:
        return metadata_results
    combined = list(provision_results)
    seen = {str(result["document_id"]) for result in combined}
    for result in metadata_results:
        if str(result["document_id"]) in seen:
            continue
        result["retrieval_basis"] = "metadata"
        result["confidence"] = "high" if not provision_results else "medium"
        result["relevance_score"] = 1.0 if not provision_results else 0.5
        result["matched_provisions"] = []
        result["relevant_sections"] = []
        result["relevant_section_ranges"] = []
        combined.append(result)
    return combined[offset : offset + limit]


def _bounded_law_snippet(body_text: str, *, max_chars: int = 600) -> str:
    normalized = " ".join(body_text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def _law_search_limitations(profile: LegalQueryProfile | None) -> list[str]:
    limitations = [
        "Results identify potentially applicable sources and require human legal review before use."
    ]
    if profile is not None and "real_estate" not in profile.concepts:
        limitations.append(
            "No explicit real-estate context was detected; cadastral or land-specific applicability was not assumed."
        )
    if profile is not None and not profile.concepts:
        limitations.append(
            "The query did not match a supported legal concept confidently; verify relevance from the cited source text."
        )
    return limitations


def _tool_get_law_text(arguments: dict[str, Any]) -> dict[str, Any]:
    document_id = str(arguments.get("document_id", "")).strip()
    if not document_id:
        raise HTTPException(status_code=400, detail="document_id is required")
    offset = _bounded_int(arguments.get("offset"), default=0, minimum=0, maximum=10_000_000)
    max_chars = _bounded_int(
        arguments.get("max_chars"),
        default=_DEFAULT_LAW_TEXT_MAX_CHARS,
        minimum=1,
        maximum=_MAX_LAW_TEXT_CHARS,
    )
    section_start, section_end = _requested_section_range(arguments)
    paragraph_number = _optional_positive_int(arguments.get("paragraph_number"))
    if paragraph_number is not None and section_start is None:
        raise HTTPException(status_code=400, detail="paragraph_number requires a section selection")
    if paragraph_number is not None and section_start != section_end:
        raise HTTPException(status_code=400, detail="paragraph_number requires one selected section")
    logger.info(
        "mcp_tool_get_law_text_query document_id_hash=%s offset=%d max_chars=%d section_start=%s section_end=%s",
        _stable_hash(document_id),
        offset,
        max_chars,
        section_start,
        section_end,
    )
    with _LawsQuerySession() as laws:
        rows = laws.query_all(
            f"""
            SELECT
                d.document_id,
                d.country_code,
                d.collection_code,
                d.law_year,
                d.law_number,
                d.official_name,
                v.version_id,
                v.version_token,
                v.effective_from,
                d.source_url,
                COALESCE(s.content_text, '') AS content_text
            FROM law_documents AS d
            JOIN law_versions AS v ON v.document_id = d.document_id
            LEFT JOIN source_artifacts AS s ON s.version_id = v.version_id AND s.artifact_kind = 'html'
            WHERE d.document_id = {laws.param}
            ORDER BY v.effective_from DESC
            LIMIT 1
            """,
            (document_id,),
        )
        provision_rows = (
            laws.query_all(
                f"""
                SELECT anchor, heading, body_text, ordinal
                FROM law_provisions
                WHERE version_id = {laws.param}
                ORDER BY ordinal
                """,
                (str(rows[0][6]),),
            )
            if rows and section_start is not None
            else []
        )
    if not rows:
        logger.warning("mcp_tool_get_law_text_not_found document_id_hash=%s", _stable_hash(document_id))
        raise HTTPException(status_code=404, detail="Law document not found")
    row = rows[0]
    result_document_id = str(row[0])
    result_country_code = str(row[1])
    result_content_text = str(row[10])
    content_scope = "full"
    requested_sections: list[int] = []
    section_found = True
    source_offset = offset
    total_content_length = len(result_content_text)
    scoped_text = result_content_text
    section_source = "source_artifact"
    matched_provision_anchors: list[str] = []
    if section_start is not None:
        assert section_end is not None
        content_scope = "sections"
        requested_sections = list(range(section_start, section_end + 1))
        structured_extract = _extract_structured_provision_range(
            rows=provision_rows,
            section_start=section_start,
            section_end=section_end,
            paragraph_number=paragraph_number,
        )
        section_extract = (
            (structured_extract[0], 0)
            if structured_extract is not None
            else _extract_section_range(result_content_text, section_start, section_end)
        )
        section_found = section_extract is not None
        if section_extract is None:
            scoped_text = ""
            source_offset = 0
            total_content_length = 0
        else:
            scoped_text, source_offset = section_extract
            if structured_extract is not None:
                section_source = "law_provisions"
                matched_provision_anchors = structured_extract[1]
            total_content_length = len(scoped_text)
            offset = 0
    content_text = scoped_text[offset : offset + max_chars]
    next_offset = offset + len(content_text)
    content_truncated = next_offset < len(scoped_text)
    result = {
        "document_id": result_document_id,
        "country_code": result_country_code,
        "collection_code": str(row[2]),
        "law_year": int(row[3]),
        "law_number": int(row[4]),
        "official_name": str(row[5]),
        "version_id": str(row[6]),
        "version_token": str(row[7]),
        "effective_from": str(row[8]),
        "source_url": str(row[9]),
        "content_text": content_text,
        "content_scope": content_scope,
        "section_source": section_source,
        "requested_sections": requested_sections,
        "requested_paragraph_number": paragraph_number,
        "matched_provision_anchors": matched_provision_anchors,
        "section_found": section_found,
        "source_offset": source_offset,
        "offset": offset,
        "max_chars": max_chars,
        "content_length": len(content_text),
        "total_content_length": total_content_length,
        "content_truncated": content_truncated,
        "next_offset": next_offset if content_truncated else None,
    }
    logger.info(
        (
            "mcp_tool_get_law_text_result document_id_hash=%s country_code=%s "
            "content_scope=%s content_length=%d total_content_length=%d truncated=%s"
        ),
        _stable_hash(result_document_id),
        result_country_code,
        content_scope,
        len(content_text),
        total_content_length,
        content_truncated,
    )
    return result


def _extract_structured_provision_range(
    *,
    rows: list[Sequence[Any]],
    section_start: int,
    section_end: int,
    paragraph_number: int | None,
) -> tuple[str, list[str]] | None:
    selected: list[tuple[str, str, str, int, int | None]] = []
    for row in rows:
        anchor = str(row[0])
        parsed = parse_provision_anchor(anchor)
        if parsed is None or not section_start <= parsed.section_number <= section_end:
            continue
        if paragraph_number is not None and parsed.paragraph_number != paragraph_number:
            continue
        selected.append(
            (
                anchor,
                str(row[1]).strip(),
                str(row[2]).strip(),
                parsed.section_number,
                parsed.paragraph_number,
            )
        )
    if not selected:
        return None

    rendered: list[str] = []
    anchors: list[str] = []
    previous_section: int | None = None
    for anchor, heading, body_text, section_number, selected_paragraph in selected:
        anchors.append(anchor)
        if section_number != previous_section:
            rendered.append(f"§ {section_number}")
            previous_section = section_number
        if heading:
            rendered.append(heading)
        paragraph_label = f"({selected_paragraph}) " if selected_paragraph is not None else ""
        rendered.append(f"{paragraph_label}{body_text}".strip())
    return "\n".join(part for part in rendered if part).strip(), anchors


def _tool_search_court_decisions(arguments: dict[str, Any]) -> dict[str, Any]:
    query = _required_search_query(arguments)
    query_profile = parse_court_decision_query(query)
    limit = _bounded_int(
        arguments.get("limit"),
        default=query_profile.requested_limit or 10,
        minimum=1,
        maximum=50,
    )
    offset = _bounded_int(arguments.get("offset"), default=0, minimum=0, maximum=10_000)
    published_year = _optional_positive_int(arguments.get("published_year"))
    year_filter_mode = _year_filter_mode(arguments.get("year_filter_mode"))
    court_type = str(arguments.get("court_type", "")).strip()
    court_name = str(arguments.get("court_name", "")).strip()
    include_snippets = _bool_argument(arguments.get("include_snippets"), default=False)
    include_summaries = _bool_argument(arguments.get("include_summaries"), default=False)
    sort = _search_sort(arguments.get("sort"))
    return _search_court_decisions(
        query=query,
        limit=limit,
        offset=offset,
        published_year=published_year,
        year_filter_mode=year_filter_mode,
        court_type=court_type,
        court_name=court_name,
        include_snippets=include_snippets,
        include_summaries=include_summaries,
        sort=sort,
    )


def _search_court_decisions(
    *,
    query: str,
    limit: int,
    offset: int,
    published_year: int | None,
    year_filter_mode: str,
    court_type: str,
    court_name: str,
    include_snippets: bool,
    include_summaries: bool,
    sort: str,
) -> dict[str, Any]:
    if year_filter_mode != "published_in":
        raise HTTPException(status_code=400, detail="Only year_filter_mode=published_in is supported")
    started_at = time.perf_counter()
    logger.info(
        (
            "mcp_tool_search_court_decisions_query query_length=%d limit=%d offset=%d "
            "published_year=%s year_filter_mode=%s court_type_supplied=%s court_name_supplied=%s "
            "include_snippets=%s include_summaries=%s sort=%s timeout_ms=%d"
        ),
        len(query),
        limit,
        offset,
        published_year,
        year_filter_mode,
        bool(court_type),
        bool(court_name),
        include_snippets,
        include_summaries,
        sort,
        _COURT_DECISION_MCP_SEARCH_TIMEOUT_MS,
    )
    try:
        store = _court_decision_store(
            initialize=False,
            connect_timeout_seconds=_COURT_DECISION_MCP_CONNECT_TIMEOUT_SECONDS,
            statement_timeout_ms=_COURT_DECISION_MCP_SEARCH_TIMEOUT_MS,
        )
        results = [
            {
                "decision_id": item.decision_id,
                "version_id": item.version_id,
                "source_guid": item.source_guid,
                "court_name": item.court_name,
                "court_type": item.court_type,
                "file_number": item.file_number,
                "case_number": item.case_number,
                "ecli": item.ecli,
                "issue_date": item.issue_date,
                "issue_date_status": item.issue_date_status,
                "source_url": item.source_url,
                "score": item.score,
                "output_mode": "public",
            }
            | ({"snippet": item.snippet} if include_snippets else {})
            | ({
                "summary": item.summary,
                "summary_status": "available" if item.summary else "not_enriched",
                "enrichment_status": item.enrichment_status,
                "content_source": item.content_source,
            } if include_summaries else {})
            for item in store.search(
                query=query,
                limit=limit,
                offset=offset,
                published_year=published_year,
                year_filter_mode=year_filter_mode,
                court_type=court_type,
                court_name=court_name,
                sort=sort,
            )
        ]
        coverage_method = getattr(store, "search_coverage", None)
        coverage = coverage_method() if callable(coverage_method) else {}
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        error_kind = _court_decision_search_error_kind(exc)
        logger.warning(
            (
                "mcp_tool_search_court_decisions_degraded query_length=%d limit=%d "
                "duration_ms=%d error_kind=%s exception=%s request_id=%s correlation_id=%s"
            ),
            len(query),
            limit,
            duration_ms,
            error_kind,
            exc.__class__.__name__,
            _CURRENT_MCP_REQUEST_ID.get(),
            _CURRENT_MCP_CORRELATION_ID.get(),
        )
        return _court_decision_search_degraded_result(
            query=query,
            limit=limit,
            offset=offset,
            published_year=published_year,
            year_filter_mode=year_filter_mode,
            sort=sort,
            court_type=court_type,
            court_name=court_name,
            include_snippets=include_snippets,
            include_summaries=include_summaries,
            duration_ms=duration_ms,
            error_kind=error_kind,
        )
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "mcp_tool_search_court_decisions_result result_count=%d duration_ms=%d",
        len(results),
        duration_ms,
    )
    return {
        "query": query,
        "results": results,
        "output_mode": "public",
        "metadata_only": not include_snippets and not include_summaries,
        "include_snippets": include_snippets,
        "include_summaries": include_summaries,
        "year_filter_mode": year_filter_mode,
        "published_year": published_year,
        "court_name": court_name or None,
        "sort": sort,
        "limit": limit,
        "offset": offset,
        "status": "ok",
        "coverage": coverage,
        "coverage_notice": (
            "Results are the latest matching decisions available in the JurisDigta corpus, "
            "not a guarantee of complete national case-law coverage."
        ),
        "data_quality": {
            "issue_date_ordering": "calendar",
            "invalid_or_missing_issue_date_results": sum(
                item["issue_date_status"] != "valid" for item in results
            ),
            "latest_label_safe": bool(results)
            and all(item["issue_date_status"] == "valid" for item in results),
            "exact_court_filter_applied": bool(court_name),
        },
        "duration_ms": duration_ms,
        "timeout_ms": _COURT_DECISION_MCP_SEARCH_TIMEOUT_MS,
    }


def _tool_get_court_decision(arguments: dict[str, Any]) -> dict[str, Any]:
    decision_id = str(arguments.get("decision_id", "")).strip()
    if not decision_id:
        raise HTTPException(status_code=400, detail="decision_id is required")
    output_mode = str(arguments.get("outputMode", arguments.get("output_mode", "public"))).strip()
    raw = output_mode == "internal_raw"
    if raw and os.getenv("COURT_DECISIONS_ALLOW_INTERNAL_RAW_MCP", "").strip().lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=403, detail="internal_raw court-decision output is not enabled")
    full_version = _bool_argument(
        arguments.get("full_version", arguments.get("fullVersion", arguments.get("fullversion"))),
        default=False,
    )
    max_chars = _bounded_int(arguments.get("max_chars"), default=12_000, minimum=1, maximum=50_000)
    logger.info(
        "mcp_tool_get_court_decision_query decision_id_hash=%s output_mode=%s full_version=%s max_chars=%d",
        _stable_hash(decision_id),
        "internal_raw" if raw else "public",
        full_version,
        max_chars,
    )
    store = _court_decision_store()
    record = store.get_decision(decision_id=decision_id, raw=raw)
    if record is None:
        raise HTTPException(status_code=404, detail="Court decision not found")
    enrich_if_missing = _bool_argument(arguments.get("enrich_if_missing"), default=True)
    if enrich_if_missing and record.get("enrichment_status", "ready") != "ready":
        from services.court_decision_collector.config import CourtDecisionCollectorConfig
        from services.court_decision_collector.enrichment import OnDemandCourtDecisionEnricher
        from services.court_decision_collector.infosud_source import InfoSudSourceClient

        config = CourtDecisionCollectorConfig.from_env()
        source = InfoSudSourceClient(
            base_url=config.source_base_url,
            timeout_seconds=config.source_timeout_seconds,
            retry_attempts=config.source_retry_attempts,
            retry_backoff_seconds=config.source_retry_backoff_seconds,
        )
        enriched = OnDemandCourtDecisionEnricher(
            store=store, source=source, storage_root=config.storage_root,
            max_pdf_bytes=config.max_pdf_bytes,
        ).enrich_source_url(str(record["source_url"]))
        record = store.get_decision(decision_id=decision_id, raw=raw)
        if record is None:
            raise HTTPException(status_code=404, detail="Court decision disappeared after enrichment")
        record["cache_hit"] = enriched.cache_hit
    text = str(record["text"])
    if full_version:
        record["text"] = text[:max_chars]
        record["content_truncated"] = len(text) > max_chars
    else:
        record.pop("text", None)
        record["content_truncated"] = False
    record["full_version"] = full_version
    record["metadata_only"] = not full_version
    logger.info(
        (
            "mcp_tool_get_court_decision_result decision_id_hash=%s output_mode=%s "
            "full_version=%s content_length=%d truncated=%s"
        ),
        _stable_hash(decision_id),
        record["output_mode"],
        full_version,
        len(str(record.get("text", ""))),
        record["content_truncated"],
    )
    return cast(dict[str, Any], record)


def _requested_section_range(arguments: dict[str, Any]) -> tuple[int | None, int | None]:
    section_start = _optional_positive_int(arguments.get("section_start"))
    section_end = _optional_positive_int(arguments.get("section_end"))
    section_number = _optional_positive_int(arguments.get("section_number"))
    section_numbers = arguments.get("section_numbers")
    if section_number is not None:
        section_start = section_number if section_start is None else section_start
        section_end = section_number if section_end is None else section_end
    if isinstance(section_numbers, list) and section_numbers:
        parsed_sections = sorted(
            section
            for section in (_optional_positive_int(value) for value in section_numbers)
            if section is not None
        )
        if parsed_sections:
            section_start = parsed_sections[0] if section_start is None else section_start
            section_end = parsed_sections[-1] if section_end is None else section_end
    if section_start is None and section_end is None:
        return None, None
    if section_start is None or section_end is None:
        selected = section_start if section_start is not None else section_end
        return selected, selected
    if section_end < section_start:
        raise HTTPException(status_code=400, detail="section_end must be greater than or equal to section_start")
    return section_start, section_end


def _extract_section_range(content_text: str, section_start: int, section_end: int) -> tuple[str, int] | None:
    section_matches = [
        (match.start(), int(match.group(1)))
        for match in re.finditer(r"(?<!\d)§\s*(\d+)\b", content_text)
    ]
    if not section_matches:
        return None

    start_index: int | None = None
    end_index = len(content_text)
    for index, (position, section_number) in enumerate(section_matches):
        if start_index is None and section_number >= section_start:
            if section_number > section_start:
                return None
            start_index = position
            continue
        if start_index is not None and section_number > section_end:
            end_index = position
            break
        if start_index is not None and index == len(section_matches) - 1:
            end_index = len(content_text)

    if start_index is None:
        return None
    return content_text[start_index:end_index].strip(), start_index


class _LawsQuerySession:
    def __init__(self, *, statement_timeout_ms: int | None = None) -> None:
        self._connection: Any = None
        self._statement_timeout_ms = statement_timeout_ms

    def __enter__(self) -> _LawsQueryConfig:
        config = _laws_db_config()
        logger.info("mcp_laws_db_session_opening backend=%s", config.backend)
        if config.backend == "sqlite":
            import sqlite3

            if not config.local_path.exists():
                logger.error("mcp_laws_db_session_failed backend=sqlite reason=missing_local_database")
                raise FileNotFoundError(f"Laws SQLite database not found: {config.local_path}")
            self._connection = sqlite3.connect(config.local_path)
            logger.info("mcp_laws_db_session_opened backend=sqlite")

            def query_all(query: str, params: Sequence[Any]) -> list[Sequence[Any]]:
                return cast(list[Sequence[Any]], self._connection.execute(query, params).fetchall())

            return _LawsQueryConfig(
                backend="sqlite",
                query_all=query_all,
                param="?",
            )
        if config.backend == "postgres":
            if not config.cloud_uri:
                logger.error("mcp_laws_db_session_failed backend=postgres reason=missing_cloud_uri")
                raise ValueError("LAWS_DB_CLOUD must be set when LAWS_DB_BACKEND=postgres")
            psycopg = importlib.import_module("psycopg")
            self._connection = psycopg.connect(config.cloud_uri)
            if self._statement_timeout_ms is not None:
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('statement_timeout', %s, true)",
                        (f"{self._statement_timeout_ms}ms",),
                    )
            logger.info("mcp_laws_db_session_opened backend=postgres")

            def query_all(query: str, params: Sequence[Any]) -> list[Sequence[Any]]:
                return cast(list[Sequence[Any]], self._connection.execute(query, params).fetchall())

            return _LawsQueryConfig(
                backend="postgres",
                query_all=query_all,
                param="%s",
            )
        logger.error("mcp_laws_db_session_failed backend=%s reason=unsupported_backend", config.backend)
        raise ValueError("LAWS_DB_BACKEND must be one of: sqlite, postgres")

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        if self._connection is not None:
            self._connection.close()
            logger.info("mcp_laws_db_session_closed")


def _court_decision_store(
    *,
    initialize: bool = False,
    connect_timeout_seconds: int | None = None,
    statement_timeout_ms: int | None = None,
) -> Any:
    from services.court_decision_collector.config import CourtDecisionCollectorConfig
    from services.court_decision_collector.postgres_store import PostgresCourtDecisionStore

    config = CourtDecisionCollectorConfig.from_env()
    config.validate()
    store = PostgresCourtDecisionStore(
        connection_uri=config.db_cloud,
        embedding_dimensions=config.embedding_dimensions,
        connect_timeout_seconds=connect_timeout_seconds,
        statement_timeout_ms=statement_timeout_ms,
    )
    if initialize:
        store.initialize()
    return store


def _court_decision_statistics() -> dict[str, Any]:
    try:
        stats = _court_decision_store().statistics()
    except Exception as exc:
        logger.warning("mcp_court_decision_statistics_unavailable reason=%s", exc.__class__.__name__)
        return {
            "status": "unavailable",
            "collector_status": "unavailable",
            "total_decisions": 0,
            "published_decisions": 0,
            "total_versions": 0,
            "last_imported_decision": None,
            "last_imported_decision_id": None,
            "last_imported_source_guid": None,
            "last_imported_at": None,
            "last_imported_court_name": None,
            "last_imported_court_type": None,
            "last_imported_issue_date": None,
            "last_imported_ecli": None,
            "last_imported_file_number": None,
            "collector_last_processed_at": None,
            "collector_last_source_guid": None,
        }
    return {
        "status": "ok",
        "collector_status": stats.collector_status,
        "total_decisions": stats.total_decisions,
        "published_decisions": stats.published_decisions,
        "total_versions": stats.total_versions,
        "last_imported_decision": stats.last_imported_source_guid or stats.last_imported_decision_id or None,
        "last_imported_decision_id": stats.last_imported_decision_id or None,
        "last_imported_source_guid": stats.last_imported_source_guid or None,
        "last_imported_at": stats.last_imported_at or None,
        "last_imported_court_name": stats.last_imported_court_name or None,
        "last_imported_court_type": stats.last_imported_court_type or None,
        "last_imported_issue_date": stats.last_imported_issue_date or None,
        "last_imported_ecli": stats.last_imported_ecli or None,
        "last_imported_file_number": stats.last_imported_file_number or None,
        "collector_last_processed_at": stats.collector_last_processed_at or None,
        "collector_last_source_guid": stats.collector_last_source_guid or None,
    }


def _court_decision_search_degraded_result(
    *,
    query: str,
    limit: int,
    offset: int,
    published_year: int | None,
    year_filter_mode: str,
    sort: str,
    court_type: str,
    court_name: str,
    include_snippets: bool,
    include_summaries: bool,
    duration_ms: int,
    error_kind: str,
) -> dict[str, Any]:
    message = (
        "Court-decision search is temporarily unavailable or exceeded the server search budget. "
        "Retry metadata for an authenticated async search is available in async_fallback."
    )
    fallback_arguments: dict[str, Any] = {
        "query": query,
        "limit": limit,
        "offset": offset,
        "published_year": published_year,
        "year_filter_mode": year_filter_mode,
        "court_type": court_type,
        "court_name": court_name,
        "include_snippets": include_snippets,
        "sort": sort,
    }
    if include_summaries:
        fallback_arguments["include_summaries"] = True
    async_fallback = _async_search_fallback(
        tool_name="searchCourtDecisions",
        arguments=fallback_arguments,
    )
    return {
        "query": query,
        "results": [],
        "output_mode": "public",
        "status": "degraded",
        "retryable": True,
        "error": {
            "code": "court_decision_search_timeout"
            if error_kind == "timeout"
            else "court_decision_search_unavailable",
            "message": message,
            "kind": error_kind,
            "correlation_id": _CURRENT_MCP_CORRELATION_ID.get(),
            "request_id": _CURRENT_MCP_REQUEST_ID.get(),
        },
        "async_fallback": async_fallback,
        "limit": limit,
        "offset": offset,
        "published_year": published_year,
        "year_filter_mode": year_filter_mode,
        "court_type": court_type,
        "court_name": court_name or None,
        "include_snippets": include_snippets,
        "include_summaries": include_summaries,
        "sort": sort,
        "duration_ms": duration_ms,
        "timeout_ms": _COURT_DECISION_MCP_SEARCH_TIMEOUT_MS,
    }


def _court_decision_search_error_kind(exc: Exception) -> str:
    return _legal_search_error_kind(exc)


def _legal_search_error_kind(exc: Exception) -> str:
    exception_name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in exception_name or "timeout" in message:
        return "timeout"
    return "unavailable"


def _legal_search_degraded_result(
    *,
    query: str,
    country_code: str,
    limit: int,
    offset: int,
    published_year: int | None,
    year_filter_mode: str,
    sort: str,
    duration_ms: int,
    error_kind: str,
    tool_name: str = "searchLaws",
) -> dict[str, Any]:
    message = (
        "Legal-source search is temporarily unavailable or exceeded the server search budget. "
        "Retry metadata for an authenticated async search is available in async_fallback."
    )
    async_fallback = _async_search_fallback(
        tool_name=tool_name,
        arguments={
            "query": query,
            "country_code": country_code,
            "limit": limit,
            "offset": offset,
            "published_year": published_year,
            "year_filter_mode": year_filter_mode,
            "sort": sort,
        },
    )
    return {
        "query": query,
        "country_code": country_code,
        "results": [],
        "status": "degraded",
        "retryable": True,
        "error": {
            "code": "legal_search_timeout" if error_kind == "timeout" else "legal_search_unavailable",
            "message": message,
            "kind": error_kind,
            "correlation_id": _CURRENT_MCP_CORRELATION_ID.get(),
            "request_id": _CURRENT_MCP_REQUEST_ID.get(),
        },
        "async_fallback": async_fallback,
        "metadata_only": True,
        "limit": limit,
        "offset": offset,
        "published_year": published_year,
        "year_filter_mode": year_filter_mode,
        "sort": sort,
        "duration_ms": duration_ms,
        "timeout_ms": _LEGAL_SEARCH_TIMEOUT_MS,
    }


def _async_legal_search_degraded_result(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    duration_ms: int,
    error_kind: str,
) -> dict[str, Any]:
    async_fallback = _async_search_fallback(tool_name=tool_name, arguments=arguments)
    return {
        "tool_name": tool_name,
        "query": str(arguments.get("query", "")),
        "results": [],
        "status": "degraded",
        "retryable": True,
        "error": {
            "code": "legal_search_timeout" if error_kind == "timeout" else "legal_search_unavailable",
            "message": (
                "Async legal search failed or exceeded the server search budget. "
                "Retry metadata is available in async_fallback."
            ),
            "kind": error_kind,
            "correlation_id": _CURRENT_MCP_CORRELATION_ID.get(),
            "request_id": _CURRENT_MCP_REQUEST_ID.get(),
        },
        "async_fallback": async_fallback,
        "duration_ms": duration_ms,
        "timeout_ms": _LEGAL_SEARCH_TIMEOUT_MS,
    }


def _async_search_fallback(*, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    sanitized_arguments = {
        key: value for key, value in arguments.items() if value is not None and value != ""
    }
    return {
        "available": True,
        "requires_user_confirmation": True,
        "start_tool": "startLegalSearch",
        "start_arguments": {
            "tool_name": tool_name,
            "arguments": sanitized_arguments,
        },
        "poll_tool": "getLegalSearchStatus",
        "result_tool": "getLegalSearchResult",
    }


def _search_sort(value: object) -> str:
    sort = str(value or "relevance").strip().lower()
    if sort in {"date", "date_desc", "newest", "newest_first", "latest_first"}:
        return "latest"
    if sort not in {"relevance", "latest"}:
        raise HTTPException(status_code=400, detail="sort must be relevance or latest")
    return sort


def _mcp_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "getVersion",
            "description": (
                "Authenticated version information for the mobile, system, API, and web apps, "
                "plus court-decision collector status and latest imported decision metadata."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "getStatistics",
            "description": (
                "Authenticated laws collector and court-decision collector processing statistics, including "
                "totals and latest imported source identifiers."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"country_code": {"type": "string", "default": "SK"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "searchLegalSources",
            "description": (
                "Protected combined metadata search for Slovak legal sources. Use this for user questions "
                "that ask for both laws and court decisions. The MCP server is model-free: clients parse "
                "natural-language questions and pass structured filters such as published_year, court_name, and sort. "
                "Use sort=latest for newest results by publication/effective metadata or court issue_date. "
                "Results are grouped into laws and court_decisions and return metadata only by default. "
                "If this sync tool returns status=degraded or retryable=true, ask the user for approval "
                "to continue asynchronously, then call startLegalSearch with tool_name=searchLegalSources "
                "and the same arguments."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "minLength": 2},
                    "country_code": {"type": "string", "default": "SK"},
                    "source_types": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["laws", "court_decisions"]},
                        "default": ["laws", "court_decisions"],
                    },
                    "published_year": {"type": "integer", "minimum": 1},
                    "year_filter_mode": {
                        "type": "string",
                        "enum": ["published_in"],
                        "default": "published_in",
                    },
                    "court_type": {"type": "string"},
                    "court_name": {"type": "string"},
                    "sort": {
                        "type": "string",
                        "enum": ["relevance", "latest"],
                        "default": "relevance",
                    },
                    "limit_per_source": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                    "offset": {"type": "integer", "minimum": 0, "default": 0},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "searchLaws",
            "description": (
                "Search JurisDigta imported Slovak laws by title, identifier, and relevant provision text. "
                "Natural-language legal scenarios return structured matched provisions, confidence, source URLs, "
                "and a human-review limitation; exact identifier searches remain metadata-first. "
                "Use sort=latest to order by latest law publication/effective metadata. "
                "Use exact law_number and law_year when the user cites a legal identifier such as 40/1964; "
                "otherwise prefer exact title matches over amendment acts. Use this first for Slovak legal "
                "questions instead of relying on model memory. If this sync tool returns status=degraded "
                "or retryable=true, ask the user for approval to continue asynchronously, then call "
                "startLegalSearch with tool_name=searchLaws and the same arguments."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "minLength": 2},
                    "country_code": {"type": "string", "default": "SK"},
                    "law_year": {"type": "integer", "minimum": 1},
                    "law_number": {"type": "integer", "minimum": 1},
                    "published_year": {"type": "integer", "minimum": 1},
                    "year_filter_mode": {
                        "type": "string",
                        "enum": ["published_in"],
                        "default": "published_in",
                    },
                    "sort": {
                        "type": "string",
                        "enum": ["relevance", "latest"],
                        "default": "relevance",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                    "offset": {"type": "integer", "minimum": 0, "default": 0},
                    "include_summaries": {"type": "boolean", "default": False},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "rankLawsByAmendments",
            "description": (
                "Deterministically rank Slovak laws published in a selected year by the number of "
                "distinct amending acts recorded for a selected amendment year. Amendment frequency "
                "is an analytical proxy, not a finding that a law is legally incorrect."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["published_year"],
                "properties": {
                    "country_code": {"type": "string", "default": "SK"},
                    "published_year": {"type": "integer", "minimum": 1900, "maximum": 9999},
                    "amendment_year": {"type": "integer", "minimum": 1900, "maximum": 9999},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "getLawHistory",
            "description": (
                "Return imported versions and legal relations for one law document. Use it to explain "
                "an analytical ranking; the result is evidence metadata and requires human review."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["document_id"],
                "properties": {"document_id": {"type": "string", "minLength": 1}},
                "additionalProperties": False,
            },
        },
        {
            "name": "getLawText",
            "description": (
                "Return bounded latest imported legal text for a JurisDigta law document id. "
                "Use after searchLaws to cite exact Slovak legal text, sections, paragraphs, and effective wording. "
                "For large codes, request section_number or section_start/section_end instead of the full law."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["document_id"],
                "properties": {
                    "document_id": {"type": "string", "minLength": 1},
                    "section_number": {"type": "integer", "minimum": 1},
                    "section_numbers": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 1},
                        "minItems": 1,
                    },
                    "section_start": {"type": "integer", "minimum": 1},
                    "section_end": {"type": "integer", "minimum": 1},
                    "paragraph_number": {"type": "integer", "minimum": 1},
                    "offset": {"type": "integer", "minimum": 0, "default": 0},
                    "max_chars": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": _MAX_LAW_TEXT_CHARS,
                        "default": _DEFAULT_LAW_TEXT_MAX_CHARS,
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "searchCourtDecisions",
            "description": (
                "Search imported Slovak court decisions (sudne rozhodnutia / case law) by semantic "
                "and metadata relevance. For a named court such as Okresny sud Poprad, pass the full "
                "name in court_name; court_type is only for a generic category such as Okresny sud. "
                "Use sort=latest to order by the normalized calendar issue date. "
                "Returns metadata only by default; set include_snippets=true for pseudonymized "
                "public snippets or include_summaries=true for available pseudonymized summaries. "
                "Conversational Slovak requests are reduced to legal topic terms and a count such as "
                "'poslednych 5' is honored when limit is omitted. Use this to cite court, date, ECLI, "
                "file number, and source URL while distinguishing case-law support from binding "
                "statutory law. If this sync tool returns status=degraded or retryable=true, ask the "
                "user for approval to continue asynchronously, then call startLegalSearch with "
                "tool_name=searchCourtDecisions and the same arguments."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "minLength": 2},
                    "published_year": {"type": "integer", "minimum": 1},
                    "year_filter_mode": {
                        "type": "string",
                        "enum": ["published_in"],
                        "default": "published_in",
                    },
                    "court_type": {"type": "string"},
                    "court_name": {"type": "string"},
                    "sort": {
                        "type": "string",
                        "enum": ["relevance", "latest"],
                        "default": "relevance",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                    "offset": {"type": "integer", "minimum": 0, "default": 0},
                    "include_snippets": {"type": "boolean", "default": False},
                    "include_summaries": {"type": "boolean", "default": False},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "startLegalSearch",
            "description": (
                "Start a short-lived authenticated async legal search job without webhook callbacks. "
                "Use for broad latest-result queries that may exceed client time budgets, or after "
                "searchLegalSources, searchLaws, or searchCourtDecisions returns a degraded/retryable "
                "sync failure and the user approves async continuation. Results are metadata-first by "
                "default and scoped to the authenticated MCP user."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["arguments"],
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "enum": ["searchLegalSources", "searchLaws", "searchCourtDecisions"],
                        "default": "searchLegalSources",
                    },
                    "arguments": {"type": "object"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "getLegalSearchStatus",
            "description": "Poll the status of an authenticated async legal search job by search_id.",
            "inputSchema": {
                "type": "object",
                "required": ["search_id"],
                "properties": {"search_id": {"type": "string", "minLength": 1}},
                "additionalProperties": False,
            },
        },
        {
            "name": "getLegalSearchResult",
            "description": (
                "Fetch the completed result for an authenticated async legal search job. "
                "Returns running status until the job is complete; expired or cross-user IDs are not disclosed."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["search_id"],
                "properties": {"search_id": {"type": "string", "minLength": 1}},
                "additionalProperties": False,
            },
        },
        {
            "name": "getCourtDecision",
            "description": (
                "Return one imported Slovak court decision. Defaults to metadata only. Set "
                "full_version=true to return bounded pseudonymized public text. "
                "outputMode=internal_raw is restricted to controlled internal use and must not be used "
                "for normal external model prompts or UI display. Missing PDF content is enriched "
                "locally from the allowlisted InfoSud source and cached by default."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["decision_id"],
                "properties": {
                    "decision_id": {"type": "string", "minLength": 1},
                    "full_version": {"type": "boolean", "default": False},
                    "enrich_if_missing": {"type": "boolean", "default": True},
                    "outputMode": {
                        "type": "string",
                        "enum": ["public", "internal_raw"],
                        "default": "public",
                    },
                    "max_chars": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50_000,
                        "default": 12_000,
                    },
                },
                "additionalProperties": False,
            },
        },
    ]


def _issue_mcp_api_key(
    *,
    store: ApiDatabaseStore,
    user: User,
    expires_in_days: int,
    audience: str | None = None,
    opaque: bool = False,
) -> tuple[str, str]:
    expires_at_dt = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).replace(microsecond=0)
    raw_key = f"mcp_{secrets.token_urlsafe(32)}" if opaque else create_mcp_api_token(
        user=user,
        expires_at=expires_at_dt,
        audience=audience,
    )
    expires_at = expires_at_dt.isoformat()
    store.set_user_mcp_api_key(user_id=user.user_id, api_key=raw_key, expires_at=expires_at)
    return raw_key, expires_at


def _issue_mcp_refresh_token(*, user: User, audience: str) -> tuple[str, str]:
    expires_at_dt = (datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=0)
    raw_key = create_mcp_refresh_token(user=user, expires_at=expires_at_dt, audience=audience)
    return raw_key, expires_at_dt.isoformat()


def _extract_mcp_api_key(*, authorization: str | None, x_mcp_api_key: str | None) -> str | None:
    if x_mcp_api_key and x_mcp_api_key.strip():
        return x_mcp_api_key.strip()
    if authorization:
        scheme, _, value = authorization.strip().partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    return None


def _mcp_login_code_key(*, email: str) -> str:
    return f"mcp-login:{email.strip().lower()}"


def _mcp_sign_up_code_key(*, pending_id: str) -> str:
    return f"mcp-sign-up:{pending_id.strip()}"


def _oauth_login_code_key(*, email: str) -> str:
    return f"mcp-oauth-login:{email.strip().lower()}"


def _authenticate_mcp_api_token(*, api_key: str, store: ApiDatabaseStore) -> User:
    expected_audience = default_mcp_resource_url()
    payload = validate_mcp_api_token(
        api_key,
        audience=expected_audience,
        required_scope=MCP_TOKEN_SCOPE,
    )
    legacy_audience = ""
    if payload is None and expected_audience.lower().endswith("/mcp"):
        legacy_audience = f"{expected_audience[:-4]}/MCP"
        payload = validate_mcp_api_token(
            api_key,
            audience=legacy_audience,
            required_scope=MCP_TOKEN_SCOPE,
        )
    if payload is None:
        user = store.find_user_by_mcp_api_key(api_key=api_key)
        if user is None:
            logger.warning(
                "mcp_auth_failed reason=invalid_or_expired_token expected_audience=%s legacy_audience=%s",
                expected_audience,
                legacy_audience,
            )
            raise HTTPException(status_code=401, detail="Invalid or expired MCP API key")
        logger.info("mcp_auth_succeeded token_type=opaque user_id=%s", user.user_id)
        return user
    user = store.find_user_by_id(user_id=str(payload["sub"]))
    if user is None or user.user_id != payload.get("sub"):
        logger.warning(
            "mcp_auth_failed reason=token_user_mismatch subject_type=%s",
            _value_type(payload.get("sub")),
        )
        raise HTTPException(status_code=401, detail="Invalid or expired MCP API key")
    if not user.mcp_api_key_hash:
        logger.warning("mcp_auth_failed reason=mcp_access_revoked user_id=%s", user.user_id)
        raise HTTPException(status_code=401, detail="Invalid or expired MCP API key")
    logger.info(
        "mcp_auth_succeeded token_type=jwt user_id=%s token_audience=%s token_scope=%s",
        user.user_id,
        payload.get("aud"),
        payload.get("scope"),
    )
    return user


def _accepts_any_local_auth_code() -> bool:
    return os.getenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _mcp_otp_reuse_window_hours() -> int:
    raw_value = os.getenv("MCP_OTP_REUSE_WINDOW_HOURS", os.getenv("MFA_REUSE_WINDOW_HOURS", "24")).strip()
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("mcp_otp_reuse_window_invalid value_type=str")
        return 24
    return _bounded_int(value, default=24, minimum=0, maximum=168)


def _has_recent_mcp_otp_verification(*, store: ApiDatabaseStore, user: User) -> bool:
    if _mcp_otp_reuse_window_hours() < 1:
        return False
    return bool(
        store.has_valid_mcp_otp_verification(
            user_id=user.user_id,
            purpose=_MCP_OTP_VERIFICATION_PURPOSE,
        )
    )


def _save_mcp_otp_verification(*, store: ApiDatabaseStore, user: User) -> None:
    reuse_window_hours = _mcp_otp_reuse_window_hours()
    if reuse_window_hours < 1:
        return
    store.save_mcp_otp_verification(
        user_id=user.user_id,
        purpose=_MCP_OTP_VERIFICATION_PURPOSE,
        expires_in_hours=reuse_window_hours,
    )


def _user_has_totp_enabled(*, store: ApiDatabaseStore, user: User) -> bool:
    return bool(store.get_user_mfa_settings(user_id=user.user_id).totp_enabled)


def _send_mcp_login_code(*, store: ApiDatabaseStore, scheduler: EmailScheduler, user: User) -> None:
    code = generate_one_time_code()
    store.save_registration_code(email=_mcp_login_code_key(email=user.email), code=code)
    scheduler.enqueue(
        recipient=user.email,
        subject="Your MCP login code",
        body=(
            f"Hello {user.full_name},\n\n"
            f"your one time MCP login code is: {code}\n"
            "The code expires in 30 minutes.\n"
        ),
        metadata={"event": "mcp_login_code", "user_id": user.user_id},
    )


def _send_oauth_login_code(
    *,
    store: ApiDatabaseStore,
    scheduler: EmailScheduler,
    user: User,
    client_id: str,
) -> None:
    code = generate_one_time_code()
    store.save_registration_code(email=_oauth_login_code_key(email=user.email), code=code)
    scheduler.enqueue(
        recipient=user.email,
        subject="Your MCP OAuth login code",
        body=(
            f"Hello {user.full_name},\n\n"
            f"your one time MCP OAuth login code is: {code}\n"
            "The code expires in 30 minutes.\n"
        ),
        metadata={"event": "mcp_oauth_login_code", "user_id": user.user_id, "client_id": client_id},
    )


def _verify_mcp_mfa_code(
    *,
    store: ApiDatabaseStore,
    user: User,
    method: str,
    code: str,
    email_code_key: str,
) -> bool:
    normalized_method = method.strip().lower()
    if normalized_method == "totp":
        settings = store.get_user_mfa_settings(user_id=user.user_id)
        secret = reveal_totp_secret(settings.totp_secret_protected or "")
        return bool(secret and verify_totp_code(secret=secret, code=code))
    return _accepts_any_local_auth_code() or store.verify_registration_code(email=email_code_key, code=code)


def _require_sign_up_consent(accepted: bool) -> None:
    if not accepted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Data processing consent is required")


def _require_sign_up_profile(**values: str) -> None:
    missing = [name for name, value in values.items() if not value.strip()]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required sign-up fields: {', '.join(missing)}",
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_url(request: Request) -> str:
    configured = os.getenv("MCP_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_proto and forwarded_host:
        proto = forwarded_proto.split(",")[0].strip()
        host = forwarded_host.split(",")[0].strip()
        return f"{proto}://{host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _resource_url(request: Request) -> str:
    return _uppercase_resource_url(request)


def _uppercase_resource_url(request: Request) -> str:
    return f"{_base_url(request)}/MCP"


def _all_mcp_resource_urls(request: Request) -> list[str]:
    return [_uppercase_resource_url(request)]


def _metadata_resource_url(request: Request) -> str:
    return _uppercase_resource_url(request)


def _base_url_from_resource(resource: str) -> str:
    parsed = urlparse(resource)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return resource.rstrip("/")


def _resolve_oauth_resource(
    *,
    request: Request,
    resource: str,
    client_id: str = "",
    redirect_uri: str = "",
) -> str:
    if resource.strip():
        return resource.strip()
    if _is_uppercase_mcp_oauth_client(client_id=client_id, redirect_uri=redirect_uri):
        return _uppercase_resource_url(request)
    return _resource_url(request)


def _is_uppercase_mcp_oauth_client(*, client_id: str, redirect_uri: str = "") -> bool:
    return _is_claude_oauth_client(client_id=client_id, redirect_uri=redirect_uri) or _is_vscode_oauth_client(
        client_id=client_id,
        redirect_uri=redirect_uri,
    )


def _is_claude_oauth_client(*, client_id: str, redirect_uri: str = "") -> bool:
    return _url_host(client_id) == "claude.ai" or _url_host(redirect_uri) == "claude.ai"


def _is_vscode_oauth_client(*, client_id: str, redirect_uri: str = "") -> bool:
    client_id_parts = urlparse(client_id)
    redirect_parts = urlparse(redirect_uri)
    vscode_schemes = {"vscode", "vscode-insiders"}
    vscode_hosts = {"vscode.dev", "insiders.vscode.dev"}
    return (
        client_id_parts.scheme.lower() in vscode_schemes
        or redirect_parts.scheme.lower() in vscode_schemes
        or (client_id_parts.hostname or "").lower() in vscode_hosts
        or (redirect_parts.hostname or "").lower() in vscode_hosts
    )


def _mcp_resource_audience_candidates(*, request: Request, preferred: str) -> list[str]:
    candidates = [preferred, _canonicalize_mcp_resource(request=request, resource=preferred)]
    candidates.extend(_all_mcp_resource_urls(request))
    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def _canonicalize_mcp_resource(*, request: Request, resource: str) -> str:
    expected = _resource_url(request)
    parsed = urlparse(resource)
    expected_parsed = urlparse(expected)
    if (
        parsed.scheme.lower() == expected_parsed.scheme.lower()
        and parsed.netloc.lower() == expected_parsed.netloc.lower()
        and parsed.path.lower() == "/mcp"
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    ):
        return expected
    return resource


def _is_mcp_resource_match(*, request: Request, resource: str) -> bool:
    return _canonicalize_mcp_resource(request=request, resource=resource) == _resource_url(request)


def _allowed_oauth_redirect_hosts() -> set[str]:
    configured = os.getenv("MCP_OAUTH_ALLOWED_REDIRECT_HOSTS", "").strip()
    if configured:
        return {host.strip().lower() for host in configured.split(",") if host.strip()}
    return set(_DEFAULT_ALLOWED_REDIRECT_HOSTS)


def _public_tools_for_request(request: Request) -> set[str]:
    if _is_internal_mcp_request(request):
        return {str(tool["name"]) for tool in _mcp_tools()}
    return _PUBLIC_TOOLS


def _is_internal_mcp_request(request: Request) -> bool:
    expected_secret = _internal_mcp_shared_secret()
    if not expected_secret:
        return False
    provided_secret = request.headers.get(_INTERNAL_MCP_SECRET_HEADER, "").strip()
    return bool(provided_secret) and hmac.compare_digest(provided_secret, expected_secret)


def _internal_mcp_shared_secret() -> str:
    raw_value = os.getenv("INTERNAL_MCP_SHARED_SECRET", "").strip()
    if raw_value in {"", "unknown-variable"}:
        raw_value = os.getenv("MCP_API_JWT_SECRET", "").strip()
    return "" if raw_value in {"", "unknown-variable"} else raw_value


def _payload_requires_auth(*, request: Request, payload: Any, public_tools: set[str]) -> bool:
    if _payload_requires_discovery_auth(payload=payload):
        return True
    messages = payload if isinstance(payload, list) else [payload]
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("method") != "tools/call":
            continue
        raw_params = message.get("params")
        params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
        tool_name = params.get("name")
        if isinstance(tool_name, str) and tool_name not in public_tools:
            return True
    return False


def _payload_requires_discovery_auth(*, payload: Any) -> bool:
    methods = set(_payload_methods(payload))
    return bool(methods & {"initialize", "tools/list"})


def _is_vscode_mcp_client(*, request: Request, payload: Any) -> bool:
    user_agent = request.headers.get("user-agent", "").lower()
    if "vscode" in user_agent or "visual studio code" in user_agent:
        return True
    messages = payload if isinstance(payload, list) else [payload]
    for message in messages:
        if not isinstance(message, dict) or message.get("method") != "initialize":
            continue
        raw_params = message.get("params")
        params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
        raw_client_info = params.get("clientInfo")
        client_info: dict[str, Any] = raw_client_info if isinstance(raw_client_info, dict) else {}
        client_name = str(client_info.get("name", "")).lower()
        if "vscode" in client_name or "visual studio code" in client_name:
            return True
    return False


def _oauth_authorization_response_iss_enabled() -> bool:
    raw_value = os.getenv("MCP_OAUTH_AUTHORIZATION_RESPONSE_ISS", "true").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _mcp_oauth_test_mfa_bypass_allowed(*, user: User) -> bool:
    if os.getenv("MCP_OAUTH_TEST_MFA_BYPASS_ENABLED", "false").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False
    normalized_email = user.email.strip().lower()
    allowed_emails = {
        email.strip().lower()
        for email in os.getenv("MCP_OAUTH_TEST_MFA_BYPASS_EMAILS", "").split(",")
        if email.strip() and email.strip().lower() != "unknown-variable"
    }
    if normalized_email not in E2E_TEST_USER_EMAILS or normalized_email not in allowed_emails:
        return False
    expires_at = _mcp_oauth_test_mfa_bypass_expires_at()
    if expires_at is None:
        return False
    return datetime.now(timezone.utc) < expires_at


def _mcp_oauth_test_mfa_bypass_expires_at_raw() -> str:
    return os.getenv("MCP_OAUTH_TEST_MFA_BYPASS_EXPIRES_AT", "").strip()


def _mcp_oauth_test_mfa_bypass_expires_at() -> datetime | None:
    raw_value = _mcp_oauth_test_mfa_bypass_expires_at_raw()
    if not raw_value or raw_value == "unknown-variable":
        return None
    try:
        expires_at = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at.astimezone(timezone.utc)


def _first_payload_id(payload: Any) -> Any:
    if isinstance(payload, list):
        for message in payload:
            if isinstance(message, dict):
                return message.get("id")
        return None
    if isinstance(payload, dict):
        return payload.get("id")
    return None


def _www_authenticate_header(request: Request) -> str:
    resource_path = "MCP" if request.url.path.rstrip("/").endswith("/MCP") else "mcp"
    metadata_url = f"{_base_url(request)}/.well-known/oauth-protected-resource/{resource_path}"
    return f'Bearer resource_metadata="{metadata_url}", scope="{MCP_TOKEN_SCOPE}"'


def _validate_oauth_authorize_request(
    *,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    resource: str,
    expected_resource: str,
) -> None:
    if response_type != "code":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only response_type=code is supported")
    if not client_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="client_id is required")
    _validate_client_id_metadata_document(client_id=client_id, redirect_uri=redirect_uri)
    _validate_oauth_redirect_uri(redirect_uri)
    if code_challenge_method != "S256":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PKCE S256 is supported")
    if not code_challenge.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_challenge is required")
    if _canonicalize_mcp_resource_for_expected(resource=resource, expected_resource=expected_resource) != expected_resource:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth resource mismatch")


def _canonicalize_mcp_resource_for_expected(*, resource: str, expected_resource: str) -> str:
    parsed = urlparse(resource)
    expected_parsed = urlparse(expected_resource)
    if (
        parsed.scheme.lower() == expected_parsed.scheme.lower()
        and parsed.netloc.lower() == expected_parsed.netloc.lower()
        and parsed.path.lower() == "/mcp"
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    ):
        return expected_resource
    return resource


def _registration_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expected a JSON array")
    return [str(item).strip() for item in value if str(item).strip()]


def _validate_oauth_redirect_uri(redirect_uri: str) -> None:
    parsed_redirect = urlparse(redirect_uri)
    scheme = parsed_redirect.scheme.lower()
    if scheme not in {"http", "https", "vscode", "vscode-insiders"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported redirect_uri")
    if scheme == "http":
        if not _is_loopback_host(parsed_redirect.hostname):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unregistered redirect_uri host")
    if scheme == "https":
        hostname = (parsed_redirect.hostname or "").lower()
        allowed_hosts = _allowed_oauth_redirect_hosts()
        if not hostname or hostname not in allowed_hosts:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unregistered redirect_uri host")


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    normalized = hostname.strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validate_client_id_metadata_document(*, client_id: str, redirect_uri: str) -> None:
    parsed_client_id = urlparse(client_id)
    if not parsed_client_id.scheme and not parsed_client_id.netloc:
        return
    if parsed_client_id.scheme.lower() != "https" or not parsed_client_id.netloc or not parsed_client_id.path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid client_id metadata document URL")
    if _is_loopback_host(parsed_client_id.hostname):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid client_id metadata document URL")
    metadata = _fetch_client_id_metadata_document(client_id)
    if str(metadata.get("client_id") or "").strip() != client_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="client_id metadata mismatch")
    redirect_uris = _registration_string_list(metadata.get("redirect_uris"))
    if redirect_uri not in redirect_uris:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_uri is not registered for client_id")


def _fetch_client_id_metadata_document(client_id: str) -> dict[str, Any]:
    if client_id == _CLAUDE_CLIENT_ID_METADATA_URL:
        return {
            "client_id": _CLAUDE_CLIENT_ID_METADATA_URL,
            "client_name": "Claude",
            "client_uri": "https://claude.ai",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "grant_types": [
                "authorization_code",
                "refresh_token",
                "urn:ietf:params:oauth:grant-type:jwt-bearer",
            ],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
    request = UrlRequest(
        client_id,
        headers={"Accept": "application/json", "User-Agent": "JurisDigta-MCP-OAuth/1.0"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=2) as response:
            body = response.read(65537)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to fetch client_id metadata document",
        ) from exc
    if len(body) > 65536:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="client_id metadata document is too large")
    try:
        metadata = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid client_id metadata document") from exc
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid client_id metadata document")
    return metadata


def _pkce_s256_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _search_result_from_row(
    row: Sequence[Any], *, include_summary: bool = False
) -> dict[str, Any]:
    result = {
        "document_id": str(row[0]),
        "country_code": str(row[1]),
        "collection_code": str(row[2]),
        "law_year": int(row[3]),
        "law_number": int(row[4]),
        "official_name": str(row[5]),
        "lawyer_title": str(row[6]),
        "source_url": str(row[7]),
        "version_id": str(row[8]),
        "version_token": str(row[9]),
        "effective_from": str(row[10]),
        "law_identifier_text": str(row[11]),
        "title": str(row[12]),
        "law_type": str(row[13]),
    }
    if include_summary:
        subject = str(row[12] or row[6] or row[5]).strip()
        result["summary"] = f"Predpis sa podľa importovaných verejných metadát týka témy: {subject}."
        result["summary_status"] = "metadata_derived"
    return result


def _is_broad_latest_law_request(
    *,
    query: str,
    sort: str,
    published_year: int | None,
    law_year: int | None,
    law_number: int | None,
) -> bool:
    if sort != "latest" or any(
        value is not None for value in (published_year, law_year, law_number)
    ):
        return False
    tokens = re.findall(r"[a-z0-9]+", normalize_legal_text(query))
    if not any(token.startswith(("posledn", "najnovs", "nov")) for token in tokens):
        return False
    if not any(token.startswith(("zakon", "predpis")) or token in {"law", "laws"} for token in tokens):
        return False
    generic_tokens = {
        "a",
        "aj",
        "and",
        "co",
        "coho",
        "cover",
        "daj",
        "chcem",
        "include",
        "je",
        "ktory",
        "last",
        "me",
        "mi",
        "na",
        "new",
        "newest",
        "of",
        "please",
        "prosim",
        "sa",
        "schvaleny",
        "show",
        "so",
        "slovensku",
        "the",
        "they",
        "tyka",
        "tykaju",
        "vediet",
        "what",
        "with",
        "zobraz",
    }
    generic_prefixes = (
        "posledn",
        "najnovs",
        "nov",
        "zakon",
        "predpis",
        "sumar",
        "zhrnut",
    )
    return all(
        token.isdigit()
        or token in generic_tokens
        or token in {"law", "laws", "latest", "summary", "summaries"}
        or token.startswith(generic_prefixes)
        for token in tokens
    )


def _optional_positive_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    parsed = _bounded_int(value, default=0, minimum=1, maximum=999999)
    return parsed


def _parse_law_identifier(query: str) -> tuple[int, int] | None:
    match = re.search(r"\b(?P<number>\d{1,6})\s*/\s*(?P<year>\d{4})\b", query)
    if match is None:
        return None
    return int(match.group("year")), int(match.group("number"))


def _payload_message_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    return 1


def _payload_methods(payload: Any) -> list[str]:
    messages = payload if isinstance(payload, list) else [payload]
    methods: list[str] = []
    for message in messages[:10]:
        if not isinstance(message, dict):
            methods.append("<invalid>")
            continue
        method = message.get("method")
        methods.append(method if isinstance(method, str) else "<missing>")
    if len(messages) > 10:
        methods.append("<truncated>")
    return methods


def _value_type(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, str):
        return "str"
    return type(value).__name__


def _url_host(value: str) -> str:
    parsed = urlparse(value)
    return (parsed.hostname or "").lower()


def _url_path(value: str) -> str:
    return urlparse(value).path or ""


def _oauth_scope_summary(scope: str) -> str:
    values = sorted({item for item in scope.split() if item})
    return ",".join(values)


def _normalize_oauth_scope(scope: str) -> str:
    requested = {item for item in scope.split() if item}
    granted = [MCP_TOKEN_SCOPE]
    if "offline_access" in requested:
        granted.append("offline_access")
    return " ".join(granted)


def _oauth_scope_includes_offline_access(scope: str) -> bool:
    return "offline_access" in {item for item in scope.split() if item}


def _oauth_user_agent_family(request: Request) -> str:
    user_agent = request.headers.get("user-agent", "").lower()
    if "python-httpx" in user_agent:
        return "python-httpx"
    if "claude" in user_agent:
        return "claude"
    if "mozilla" in user_agent or "chrome" in user_agent or "safari" in user_agent:
        return "browser"
    return "unknown"


def _http_exception_detail(exc: HTTPException) -> str:
    if isinstance(exc.detail, str):
        return exc.detail
    return _value_type(exc.detail)


def _redacted_if_blank(value: str) -> str:
    return value.strip() or "<not_supplied>"


def _log_oauth_token_failed(
    *,
    reason: str,
    grant_type: str,
    client_id: str,
    request: Request,
    redirect_uri: str = "",
    resource: str = "",
    record_resource: str = "",
    token_audience: str = "",
) -> None:
    logger.warning(
        "mcp_oauth_token_failed reason=%s grant_type=%s client_id_hash=%s client_id_host=%s client_id_path=%s "
        "redirect_host=%s redirect_path=%s resource_supplied=%s requested_resource=%s record_resource=%s "
        "token_audience=%s user_agent=%s",
        reason,
        grant_type,
        _stable_hash(client_id),
        _url_host(client_id),
        _url_path(client_id),
        _url_host(redirect_uri),
        _url_path(redirect_uri),
        bool(resource.strip()),
        _redacted_if_blank(resource),
        _redacted_if_blank(record_resource),
        _redacted_if_blank(token_audience),
        _oauth_user_agent_family(request),
    )


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _tool_result_summary(*, tool_name: str, result: Any) -> str:
    if not isinstance(result, dict):
        return f"type={type(result).__name__}"
    if tool_name == "getVersion":
        court_decisions = result.get("court_decision_collector")
        court_status = court_decisions.get("status") if isinstance(court_decisions, dict) else "missing"
        return f"fields=api_version,system_version,mobile_app_version,web_app_version court_status={court_status}"
    if tool_name == "getStatistics":
        return (
            f"country_code={result.get('country_code')} "
            f"processed_laws={result.get('processed_laws')} "
            f"last_processed_law={result.get('last_processed_law')} "
            f"total_court_decisions={result.get('total_court_decisions')}"
        )
    if tool_name == "searchLaws":
        results = result.get("results")
        result_count = len(results) if isinstance(results, list) else 0
        return f"country_code={result.get('country_code')} result_count={result_count}"
    if tool_name == "searchLegalSources":
        laws = result.get("laws")
        court_decisions = result.get("court_decisions")
        laws_count = len(laws) if isinstance(laws, list) else 0
        court_count = len(court_decisions) if isinstance(court_decisions, list) else 0
        return f"country_code={result.get('country_code')} laws={laws_count} court_decisions={court_count}"
    if tool_name == "getLawText":
        content_text = result.get("content_text")
        content_length = len(content_text) if isinstance(content_text, str) else 0
        document_id = result.get("document_id")
        document_hash = _stable_hash(document_id) if isinstance(document_id, str) else "missing"
        return (
            f"document_id_hash={document_hash} "
            f"country_code={result.get('country_code')} "
            f"content_length={content_length}"
        )
    if tool_name == "searchCourtDecisions":
        results = result.get("results")
        result_count = len(results) if isinstance(results, list) else 0
        return f"result_count={result_count} output_mode={result.get('output_mode')}"
    if tool_name == "getCourtDecision":
        text = result.get("text")
        content_length = len(text) if isinstance(text, str) else 0
        decision_id = result.get("decision_id")
        decision_hash = _stable_hash(decision_id) if isinstance(decision_id, str) else "missing"
        return (
            f"decision_id_hash={decision_hash} "
            f"output_mode={result.get('output_mode')} "
            f"content_length={content_length}"
        )
    return f"keys={','.join(sorted(str(key) for key in result.keys()))}"


def _json_rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _json_text(payload: Any) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    resolved = int(value)
    if resolved < minimum:
        return minimum
    if resolved > maximum:
        return maximum
    return resolved


def _required_search_query(arguments: dict[str, Any]) -> str:
    query = str(arguments.get("query", "")).strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="query must contain at least 2 characters")
    return query


def _year_filter_mode(value: Any) -> str:
    mode = str(value or "published_in").strip() or "published_in"
    if mode != "published_in":
        raise HTTPException(status_code=400, detail="Only year_filter_mode=published_in is supported")
    return mode


def _bool_argument(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise HTTPException(status_code=400, detail="Expected a boolean value")


def _requested_source_types(value: Any) -> list[str]:
    if value is None:
        return ["laws", "court_decisions"]
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="source_types must be an array")
    requested = [str(item).strip() for item in value if str(item).strip()]
    allowed = {"laws", "court_decisions"}
    if not requested or any(item not in allowed for item in requested):
        raise HTTPException(status_code=400, detail="source_types must contain laws and/or court_decisions")
    return list(dict.fromkeys(requested))


def _mcp_locale(request: Request) -> str:
    header = request.headers.get("accept-language", "")
    for item in header.split(","):
        language = item.split(";", 1)[0].strip().lower()
        primary = language.split("-", 1)[0]
        if primary in _MCP_SUPPORTED_LOCALES:
            return primary
    return "en"


def _mcp_t(locale: str, key: str, **values: str) -> str:
    text = _MCP_TEXT.get(locale, _MCP_TEXT["en"]).get(key, _MCP_TEXT["en"][key])
    return text.format(**values)


def _warning_html(*, locale: str, warning_key: str | None) -> str:
    if not warning_key:
        return ""
    return f'    <div class="alert" role="alert">{escape(_mcp_t(locale, warning_key), quote=False)}</div>\n'


def _mcp_auth_page_html(
    *,
    locale: str,
    title: str,
    subtitle: str,
    body_html: str,
    footer_html: str = "",
) -> str:
    return f"""<!doctype html>
<html lang="{escape(locale, quote=True)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title, quote=False)} - JurisDigta MCP</title>
  <style>
    :root {{
      color-scheme: light;
      --background: #f5f0ea;
      --background-end: #e8dfd4;
      --surface: #ffffff;
      --surface-muted: #f0e9e2;
      --surface-contrast: #251c13;
      --text: #1f1b16;
      --muted: #5f564b;
      --line: rgba(31, 27, 22, 0.12);
      --primary: #d0632c;
      --primary-dark: #8d3510;
      --accent: #d0632c;
      --accent-soft: #f5c7a6;
      --focus: #d0632c;
      --shadow: 0 24px 60px rgba(31, 27, 22, 0.12);
      --radius: 24px;
      --font-display: "Fraunces", "Times New Roman", serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: radial-gradient(circle at top, #fdf7f1 0%, var(--background) 45%, var(--background-end) 100%);
      color: var(--text);
      font-family: "Space Grotesk", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    a {{ color: var(--accent); font-weight: 700; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .auth-shell {{
      width: min(1120px, calc(100% - 32px));
      min-height: 100vh;
      margin: 0 auto;
      display: grid;
      grid-template-columns: minmax(280px, 0.9fr) minmax(320px, 1.1fr);
      gap: 32px;
      align-items: center;
      padding: 48px 0;
    }}
    .brand-panel {{
      padding: 8px;
    }}
    .brand-mark {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      font-size: 0.9rem;
      font-weight: 800;
      letter-spacing: 0;
      color: var(--text);
    }}
    .brand-mark::before {{
      content: "AJ";
      display: inline-flex;
      width: 44px;
      height: 44px;
      align-items: center;
      justify-content: center;
      border-radius: 50%;
      background: var(--accent);
      color: #fff;
      box-shadow: var(--shadow);
      font-weight: 800;
    }}
    h1 {{
      font-family: var(--font-display);
      margin: 24px 0 14px;
      font-size: clamp(2.15rem, 6vw, 4.25rem);
      line-height: 1;
      letter-spacing: 0;
      font-weight: 600;
    }}
    .subtitle {{
      max-width: 580px;
      color: var(--muted);
      font-size: 1.05rem;
    }}
    .trust-list {{
      display: grid;
      gap: 10px;
      margin: 28px 0 0;
      padding: 0;
      list-style: none;
      color: var(--muted);
    }}
    .trust-list li {{
      display: flex;
      gap: 10px;
      align-items: flex-start;
    }}
    .trust-list li::before {{
      content: "";
      flex: 0 0 auto;
      width: 9px;
      height: 9px;
      margin-top: 8px;
      border-radius: 999px;
      background: var(--accent);
    }}
    .auth-card {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
      box-shadow: var(--shadow);
      padding: 2rem;
    }}
    .form-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .form-grid .wide, .field.wide {{ grid-column: 1 / -1; }}
    .field {{
      display: grid;
      gap: 7px;
      color: var(--text);
      font-weight: 700;
      font-size: 0.92rem;
    }}
    .hint, .form-note, .email-note {{
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .alert {{
      margin: 0 0 18px;
      border: 1px solid var(--accent-soft);
      border-radius: 12px;
      background: #fff7ed;
      color: #8d2b2b;
      padding: 12px 14px;
      font-weight: 700;
    }}
    input {{
      width: 100%;
      min-height: 46px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fff;
      color: var(--text);
      font: inherit;
      padding: 0.8rem 1rem;
    }}
    input:focus {{
      border-color: var(--focus);
      box-shadow: 0 0 0 3px rgba(208, 99, 44, 0.16);
      outline: none;
    }}
    .checkbox-field {{
      grid-column: 1 / -1;
      display: flex;
      gap: 10px;
      align-items: flex-start;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--surface-muted);
      color: var(--muted);
      font-weight: 600;
    }}
    .checkbox-field input {{
      width: 18px;
      min-width: 18px;
      height: 18px;
      min-height: 18px;
      margin-top: 2px;
      accent-color: var(--primary);
    }}
    .primary-button {{
      width: 100%;
      min-height: 48px;
      border: 0;
      border-radius: 999px;
      background: var(--primary);
      color: #fff;
      cursor: pointer;
      font: inherit;
      font-weight: 600;
      margin-top: 18px;
      padding: 0.7rem 1.4rem;
      box-shadow: var(--shadow);
    }}
    .primary-button:hover {{ background: var(--primary-dark); }}
    .auth-footer {{
      margin: 18px 0 0;
      color: var(--muted);
      text-align: center;
    }}
    .key-output {{
      overflow-wrap: anywhere;
      white-space: pre-wrap;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--surface-contrast);
      color: #fff;
      padding: 16px;
    }}
    @media (max-width: 820px) {{
      .auth-shell {{
        grid-template-columns: 1fr;
        gap: 20px;
        padding: 28px 0;
      }}
      .brand-panel {{ padding: 0; }}
      .auth-card {{ padding: 22px; }}
      .form-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (prefers-color-scheme: dark) {{
      .alert {{
        border-color: #f59e0b;
        background: #2b1d0d;
        color: #fed7aa;
      }}
    }}
  </style>
</head>
<body>
  <main class="auth-shell">
    <section class="brand-panel" aria-labelledby="mcp-auth-title">
      <div class="brand-mark">JurisDigta MCP</div>
      <h1 id="mcp-auth-title">{escape(title, quote=False)}</h1>
      <p class="subtitle">{escape(subtitle, quote=False)}</p>
      <ul class="trust-list" aria-label="{escape(_mcp_t(locale, "security_label"), quote=True)}">
        <li>{escape(_mcp_t(locale, "trust_otp"), quote=False)}</li>
        <li>{escape(_mcp_t(locale, "trust_scope"), quote=False)}</li>
        <li>{escape(_mcp_t(locale, "trust_profile"), quote=False)}</li>
      </ul>
    </section>
    <section class="auth-card" aria-label="{escape(title, quote=True)} form">
{body_html}
{footer_html}
    </section>
  </main>
</body>
</html>"""


def _login_form_html(*, locale: str) -> str:
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "login_title"),
        subtitle=_mcp_t(locale, "login_subtitle"),
        body_html=f"""    <p class="form-note">{escape(_mcp_t(locale, "login_note"), quote=False)}</p>
    <form method="post" action="/mcp/login">
      <div class="form-grid">
        <label class="field wide">{escape(_mcp_t(locale, "email"), quote=False)}
          <input name="email" type="email" autocomplete="username" required>
        </label>
        <label class="field wide">{escape(_mcp_t(locale, "password"), quote=False)}
          <input name="password" type="password" autocomplete="current-password" required>
        </label>
        <label class="field wide">{escape(_mcp_t(locale, "expiry_days"), quote=False)}
          <input name="expires_in_days" type="number" min="1" max="365" value="1">
        </label>
      </div>
      <button class="primary-button" type="submit">{escape(_mcp_t(locale, "send_otp"), quote=False)}</button>
    </form>
""",
        footer_html=(
            f'    <p class="auth-footer">{escape(_mcp_t(locale, "need_account"), quote=False)} '
            f'<a href="/mcp/sign-up">{escape(_mcp_t(locale, "sign_up_link"), quote=False)}</a></p>'
        ),
    )


def _oauth_login_form_html(
    *,
    locale: str,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
    resource: str,
    scope: str,
) -> str:
    hidden = _hidden_inputs(
        {
            "response_type": response_type,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "state": state,
            "resource": resource,
            "scope": scope,
        }
    )
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "oauth_title"),
        subtitle=_mcp_t(locale, "oauth_subtitle"),
        body_html=f"""    <p class="form-note">{escape(_mcp_t(locale, "oauth_note"), quote=False)}</p>
    <form method="post" action="/oauth/authorize/login">
{hidden}
      <div class="form-grid">
        <label class="field wide">{escape(_mcp_t(locale, "email"), quote=False)}
          <input name="email" type="email" autocomplete="username" required>
        </label>
        <label class="field wide">{escape(_mcp_t(locale, "password"), quote=False)}
          <input name="password" type="password" autocomplete="current-password" required>
        </label>
      </div>
      <button class="primary-button" type="submit">{escape(_mcp_t(locale, "send_otp"), quote=False)}</button>
    </form>
""",
        footer_html=(
            f'    <p class="auth-footer">{escape(_mcp_t(locale, "need_account"), quote=False)} '
            f'<a href="/mcp/sign-up">{escape(_mcp_t(locale, "sign_up_link"), quote=False)}</a></p>'
        ),
    )


def _oauth_otp_form_html(
    *,
    locale: str,
    email: str,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
    resource: str,
    scope: str,
    warning_key: str | None = None,
) -> str:
    hidden = _hidden_inputs(
        {
            "email": email,
            "response_type": response_type,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "state": state,
            "resource": resource,
            "scope": scope,
        }
    )
    escaped_email = escape(email, quote=False)
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "oauth_verify_title"),
        subtitle=_mcp_t(locale, "oauth_verify_subtitle"),
        body_html=f"""{_warning_html(locale=locale, warning_key=warning_key)}    <p class="email-note">{escape(_mcp_t(locale, "otp_sent", email=escaped_email), quote=False)}</p>
    <form method="post" action="/oauth/authorize/verify">
{hidden}
      <label class="field wide">{escape(_mcp_t(locale, "otp_code"), quote=False)}
        <input name="verification_code" type="text" inputmode="numeric" autocomplete="one-time-code" required>
      </label>
      <button class="primary-button" type="submit">{escape(_mcp_t(locale, "authorize"), quote=False)}</button>
    </form>
""",
    )


def _oauth_mfa_method_form_html(
    *,
    locale: str,
    email: str,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
    resource: str,
    scope: str,
) -> str:
    hidden = _hidden_inputs(
        {
            "email": email,
            "response_type": response_type,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "state": state,
            "resource": resource,
            "scope": scope,
        }
    )
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "choose_mfa_title"),
        subtitle=_mcp_t(locale, "choose_mfa_subtitle"),
        body_html=f"""    <form method="post" action="/oauth/authorize/mfa">
{hidden}
      <label class="field wide">{escape(_mcp_t(locale, "mfa_method"), quote=False)}
        <select name="mfa_method" required>
          <option value="email">{escape(_mcp_t(locale, "mfa_email"), quote=False)}</option>
          <option value="totp">{escape(_mcp_t(locale, "mfa_totp"), quote=False)}</option>
        </select>
      </label>
      <button class="primary-button" type="submit">{escape(_mcp_t(locale, "continue"), quote=False)}</button>
    </form>
""",
    )


def _oauth_totp_form_html(
    *,
    locale: str,
    email: str,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
    resource: str,
    scope: str,
    warning_key: str | None = None,
) -> str:
    hidden = _hidden_inputs(
        {
            "email": email,
            "mfa_method": "totp",
            "response_type": response_type,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "state": state,
            "resource": resource,
            "scope": scope,
        }
    )
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "oauth_verify_title"),
        subtitle=_mcp_t(locale, "oauth_verify_subtitle"),
        body_html=f"""{_warning_html(locale=locale, warning_key=warning_key)}    <p class="form-note">{escape(_mcp_t(locale, "totp_note"), quote=False)}</p>
    <form method="post" action="/oauth/authorize/verify">
{hidden}
      <label class="field wide">{escape(_mcp_t(locale, "totp_code"), quote=False)}
        <input name="verification_code" type="text" inputmode="numeric" autocomplete="one-time-code" required>
      </label>
      <button class="primary-button" type="submit">{escape(_mcp_t(locale, "authorize"), quote=False)}</button>
    </form>
""",
    )


def _otp_form_html(
    *,
    locale: str,
    email: str,
    expires_in_days: int,
    warning_key: str | None = None,
) -> str:
    escaped_email = escape(email, quote=True)
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "verify_login_title"),
        subtitle=_mcp_t(locale, "verify_login_subtitle"),
        body_html=f"""{_warning_html(locale=locale, warning_key=warning_key)}    <p class="email-note">{escape(_mcp_t(locale, "otp_sent", email=escaped_email), quote=False)}</p>
    <form method="post" action="/mcp/login/verify">
      <input name="email" type="hidden" value="{escaped_email}">
      <input name="expires_in_days" type="hidden" value="{expires_in_days}">
      <label class="field wide">{escape(_mcp_t(locale, "otp_code"), quote=False)}
        <input name="verification_code" type="text" inputmode="numeric" autocomplete="one-time-code" required>
      </label>
      <button class="primary-button" type="submit">{escape(_mcp_t(locale, "generate_key"), quote=False)}</button>
    </form>
""",
    )


def _mfa_method_form_html(*, locale: str, email: str, expires_in_days: int) -> str:
    escaped_email = escape(email, quote=True)
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "choose_mfa_title"),
        subtitle=_mcp_t(locale, "choose_mfa_subtitle"),
        body_html=f"""    <form method="post" action="/mcp/login/mfa">
      <input name="email" type="hidden" value="{escaped_email}">
      <input name="expires_in_days" type="hidden" value="{expires_in_days}">
      <label class="field wide">{escape(_mcp_t(locale, "mfa_method"), quote=False)}
        <select name="mfa_method" required>
          <option value="email">{escape(_mcp_t(locale, "mfa_email"), quote=False)}</option>
          <option value="totp">{escape(_mcp_t(locale, "mfa_totp"), quote=False)}</option>
        </select>
      </label>
      <button class="primary-button" type="submit">{escape(_mcp_t(locale, "continue"), quote=False)}</button>
    </form>
""",
    )


def _totp_form_html(
    *,
    locale: str,
    email: str,
    expires_in_days: int,
    warning_key: str | None = None,
) -> str:
    escaped_email = escape(email, quote=True)
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "verify_login_title"),
        subtitle=_mcp_t(locale, "verify_login_subtitle"),
        body_html=f"""{_warning_html(locale=locale, warning_key=warning_key)}    <p class="form-note">{escape(_mcp_t(locale, "totp_note"), quote=False)}</p>
    <form method="post" action="/mcp/login/verify">
      <input name="email" type="hidden" value="{escaped_email}">
      <input name="mfa_method" type="hidden" value="totp">
      <input name="expires_in_days" type="hidden" value="{expires_in_days}">
      <label class="field wide">{escape(_mcp_t(locale, "totp_code"), quote=False)}
        <input name="verification_code" type="text" inputmode="numeric" autocomplete="one-time-code" required>
      </label>
      <button class="primary-button" type="submit">{escape(_mcp_t(locale, "generate_key"), quote=False)}</button>
    </form>
""",
    )


def _sign_up_form_html(*, locale: str) -> str:
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "create_account_title"),
        subtitle=_mcp_t(locale, "create_account_subtitle"),
        body_html=f"""    <p class="form-note">{escape(_mcp_t(locale, "create_account_note"), quote=False)}</p>
    <form method="post" action="/mcp/sign-up">
      <div class="form-grid">
        <label class="field wide">{escape(_mcp_t(locale, "email"), quote=False)}
          <input name="email" type="email" autocomplete="username" required>
        </label>
        <label class="field">{escape(_mcp_t(locale, "phone"), quote=False)}
          <input name="phone_number" type="tel" autocomplete="tel" required>
        </label>
        <label class="field">{escape(_mcp_t(locale, "password"), quote=False)}
          <input name="password" type="password" autocomplete="new-password" required>
        </label>
        <label class="field">{escape(_mcp_t(locale, "first_name"), quote=False)}
          <input name="first_name" type="text" autocomplete="given-name" required>
        </label>
        <label class="field">{escape(_mcp_t(locale, "last_name"), quote=False)}
          <input name="last_name" type="text" autocomplete="family-name" required>
        </label>
        <label class="field wide">{escape(_mcp_t(locale, "address"), quote=False)}
          <input name="address" type="text" autocomplete="street-address" required>
        </label>
        <label class="field">{escape(_mcp_t(locale, "city"), quote=False)}
          <input name="city" type="text" autocomplete="address-level2">
        </label>
        <label class="field">{escape(_mcp_t(locale, "country"), quote=False)}
          <input name="country" type="text" autocomplete="country-name">
        </label>
        <label class="field">{escape(_mcp_t(locale, "zip_code"), quote=False)}
          <input name="zip_code" type="text" autocomplete="postal-code">
        </label>
        <label class="field">{escape(_mcp_t(locale, "id_card"), quote=False)}
          <input name="identity_card_number" type="text" required>
        </label>
        <label class="checkbox-field">
          <input name="data_processing_consent_accepted" type="checkbox" value="true" required>
          <span>{escape(_mcp_t(locale, "consent"), quote=False)}</span>
        </label>
      </div>
      <button class="primary-button" type="submit">{escape(_mcp_t(locale, "send_verification"), quote=False)}</button>
    </form>
""",
        footer_html=(
            f'    <p class="auth-footer">{escape(_mcp_t(locale, "already_registered"), quote=False)} '
            f'<a href="/mcp/login">{escape(_mcp_t(locale, "log_in_link"), quote=False)}</a></p>'
        ),
    )


def _sign_up_otp_form_html(
    *,
    locale: str,
    pending_id: str,
    email: str,
    warning_key: str | None = None,
) -> str:
    hidden_html = _hidden_inputs({"pending_id": pending_id, "email": email})
    escaped_email = escape(email, quote=False)
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "verify_signup_title"),
        subtitle=_mcp_t(locale, "verify_signup_subtitle"),
        body_html=f"""{_warning_html(locale=locale, warning_key=warning_key)}    <p class="email-note">{escape(_mcp_t(locale, "otp_sent", email=escaped_email), quote=False)}</p>
    <form method="post" action="/mcp/sign-up/verify">
{hidden_html}
      <label class="field wide">{escape(_mcp_t(locale, "otp_code"), quote=False)}
        <input name="verification_code" type="text" inputmode="numeric" autocomplete="one-time-code" required>
      </label>
      <button class="primary-button" type="submit">{escape(_mcp_t(locale, "create_account"), quote=False)}</button>
    </form>
""",
    )


def _hidden_inputs(values: dict[str, str]) -> str:
    return "\n".join(
        f'      <input name="{escape(name, quote=True)}" type="hidden" value="{escape(value, quote=True)}">'
        for name, value in values.items()
    )


def _sign_up_complete_html(*, locale: str, email: str) -> str:
    escaped_email = escape(email, quote=False)
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "account_created_title"),
        subtitle=_mcp_t(locale, "account_created_subtitle"),
        body_html=f"""    <p class="email-note">{escape(_mcp_t(locale, "account_created", email=escaped_email), quote=False)}</p>
    <p class="auth-footer"><a href="/mcp/login">{escape(_mcp_t(locale, "log_in_link"), quote=False)}</a></p>
""",
    )


def _key_created_html(*, locale: str, api_key: str, expires_at: str) -> str:
    escaped_api_key = escape(api_key, quote=False)
    escaped_expires_at = escape(expires_at, quote=False)
    return _mcp_auth_page_html(
        locale=locale,
        title=_mcp_t(locale, "key_created_title"),
        subtitle=_mcp_t(locale, "key_created_subtitle"),
        body_html=f"""    <p class="email-note">{escape(_mcp_t(locale, "key_expires", expires_at=escaped_expires_at), quote=False)}</p>
    <pre class="key-output">{escaped_api_key}</pre>
    <p class="form-note">{escape(_mcp_t(locale, "key_note"), quote=False)}</p>
""",
    )
