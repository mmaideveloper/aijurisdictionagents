from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
from html import escape
import importlib
import json
import logging
import os
import secrets
import time
from typing import Any, Callable, Sequence, cast
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.laws_api import _laws_db_config, _read_laws_statistics
from app.mcp_tokens import MCP_TOKEN_SCOPE, create_mcp_api_token, default_mcp_resource_url, validate_mcp_api_token
from app.services.email_scheduler import EmailScheduler
from app.users.api import get_email_scheduler, get_user_store
from app.users.notifications import queue_registration_email
from app.versioning import (
    get_api_version,
    get_core_version,
    get_mcp_server_version,
    get_mobile_app_version,
    get_web_app_version,
)
from aijurisdictionagents.api_db import ApiDatabaseStore, User, generate_one_time_code

router = APIRouter(prefix="/MCP", tags=["mcp"])
oauth_router = APIRouter(tags=["mcp-oauth"])
MCP_PROTOCOL_VERSION = "2025-03-26"
_PUBLIC_TOOLS = {"getVersion", "getStatistics"}
_DEFAULT_ALLOWED_REDIRECT_HOSTS = ("chatgpt.com", "chat.openai.com")
logger = logging.getLogger("aijuristiction-api.mcp")


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


@router.get("", response_class=JSONResponse)
def mcp_status() -> JSONResponse:
    return JSONResponse(status_code=405, content={"detail": "Use POST /MCP for Streamable HTTP JSON-RPC."})


@router.get("/status", response_class=JSONResponse)
def mcp_authenticated_status(user_id: str = Depends(require_mcp_api_key)) -> dict[str, str]:
    logger.info("mcp_status_checked user_id=%s", user_id)
    return {
        "status": "ok",
        "transport": "streamable-http-json-rpc",
        "protocol_version": MCP_PROTOCOL_VERSION,
        "user_id": user_id,
    }


@router.post("", response_class=JSONResponse)
async def mcp_json_rpc(
    request: Request,
    authorization: str | None = Header(default=None),
    x_mcp_api_key: str | None = Header(default=None),
    store: ApiDatabaseStore = Depends(get_user_store),
) -> JSONResponse:
    started_at = time.perf_counter()
    payload = await _read_json_rpc_payload(request)
    request_id = getattr(request.state, "request_id", None)
    correlation_id = getattr(request.state, "correlation_id", None)
    logger.info(
        "mcp_json_rpc_received request_id=%s correlation_id=%s batch=%s message_count=%d methods=%s",
        request_id,
        correlation_id,
        isinstance(payload, list),
        _payload_message_count(payload),
        ",".join(_payload_methods(payload)),
    )
    if _payload_requires_auth(payload) and not _extract_mcp_api_key(
        authorization=authorization,
        x_mcp_api_key=x_mcp_api_key,
    ):
        logger.warning("mcp_json_rpc_auth_challenge reason=missing_bearer_token")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=_json_rpc_error(_first_payload_id(payload), 401, "Tool requires OAuth authorization"),
            headers={"WWW-Authenticate": _www_authenticate_header(request)},
        )
    response = _handle_json_rpc(
        payload=payload,
        authorization=authorization,
        x_mcp_api_key=x_mcp_api_key,
        store=store,
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


@router.get("/login", response_class=HTMLResponse)
def mcp_login_page() -> HTMLResponse:
    return HTMLResponse(_login_form_html())


@router.get("/sign-up", response_class=HTMLResponse)
def mcp_sign_up_page() -> HTMLResponse:
    return HTMLResponse(_sign_up_form_html())


@oauth_router.get("/.well-known/oauth-protected-resource")
def oauth_protected_resource_metadata(request: Request) -> dict[str, Any]:
    base_url = _base_url(request)
    resource = _resource_url(request)
    return {
        "resource": resource,
        "authorization_servers": [base_url],
        "bearer_methods_supported": ["header"],
        "scopes_supported": [MCP_TOKEN_SCOPE],
        "resource_documentation": f"{base_url}/MCP/login",
    }


@oauth_router.get("/.well-known/oauth-protected-resource/MCP")
def oauth_mcp_protected_resource_metadata(request: Request) -> dict[str, Any]:
    return oauth_protected_resource_metadata(request)


@oauth_router.get("/.well-known/oauth-authorization-server")
def oauth_authorization_server_metadata(request: Request) -> dict[str, Any]:
    base_url = _base_url(request)
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": [MCP_TOKEN_SCOPE],
    }


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
) -> HTMLResponse:
    resolved_resource = _resolve_oauth_resource(request=request, resource=resource)
    _validate_oauth_authorize_request(
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        resource=resolved_resource,
        expected_resource=_resource_url(request),
    )
    return HTMLResponse(
        _oauth_login_form_html(
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            state=state,
            resource=resolved_resource,
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
    email: str = Form(...),
    password: str = Form(...),
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> HTMLResponse:
    resolved_resource = _resolve_oauth_resource(request=request, resource=resource)
    _validate_oauth_authorize_request(
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        resource=resolved_resource,
        expected_resource=_resource_url(request),
    )
    user = store.authenticate_user(email=email, password=password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
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
    return HTMLResponse(
        _oauth_otp_form_html(
            email=user.email,
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            state=state,
            resource=resolved_resource,
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
    state: str = Form(""),
    store: ApiDatabaseStore = Depends(get_user_store),
) -> RedirectResponse:
    resolved_resource = _resolve_oauth_resource(request=request, resource=resource)
    _validate_oauth_authorize_request(
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        resource=resolved_resource,
        expected_resource=_resource_url(request),
    )
    if not _accepts_any_local_auth_code() and not store.verify_registration_code(
        email=_oauth_login_code_key(email=email),
        code=verification_code,
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
    user = store.find_user_by_email(email=email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    authorization_code = secrets.token_urlsafe(32)
    store.save_mcp_oauth_authorization_code(
        code=authorization_code,
        user_id=user.user_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        resource=resolved_resource,
    )
    query = {"code": authorization_code}
    if state:
        query["state"] = state
    return RedirectResponse(url=f"{redirect_uri}?{urlencode(query)}", status_code=status.HTTP_303_SEE_OTHER)


@oauth_router.post("/oauth/token")
def oauth_token(
    request: Request,
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
    client_id: str = Form(...),
    code_verifier: str = Form(...),
    resource: str = Form(""),
    store: ApiDatabaseStore = Depends(get_user_store),
) -> dict[str, Any]:
    if grant_type != "authorization_code":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported grant_type")
    record = store.consume_mcp_oauth_authorization_code(code=code)
    if record is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid authorization code")
    if record["client_id"] != client_id or record["redirect_uri"] != redirect_uri:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Authorization code context mismatch")
    expected_resource = _resource_url(request)
    resolved_resource = _resolve_oauth_resource(request=request, resource=resource)
    if record["resource"] != expected_resource or resolved_resource != expected_resource:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth resource mismatch")
    if _pkce_s256_challenge(code_verifier) != record["code_challenge"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid PKCE code verifier")
    user = store.get_user(user_id=record["user_id"])
    token, expires_at = _issue_mcp_api_key(
        store=store,
        user=user,
        expires_in_days=1,
        audience=expected_resource,
    )
    expires_in = max(1, int((datetime.fromisoformat(expires_at) - datetime.now(timezone.utc)).total_seconds()))
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": MCP_TOKEN_SCOPE,
    }


@router.post("/login", response_class=HTMLResponse)
def mcp_login_submit(
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
    code = generate_one_time_code()
    code_key = _mcp_login_code_key(email=user.email)
    store.save_registration_code(email=code_key, code=code)
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
    return HTMLResponse(_otp_form_html(email=user.email, expires_in_days=expires_in_days))


@router.post("/login/verify", response_class=HTMLResponse)
def mcp_login_verify(
    email: str = Form(...),
    verification_code: str = Form(...),
    expires_in_days: int = Form(1),
    store: ApiDatabaseStore = Depends(get_user_store),
) -> HTMLResponse:
    if expires_in_days < 1 or expires_in_days > 365:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expiry must be 1-365 days")
    if not _accepts_any_local_auth_code() and not store.verify_registration_code(
        email=_mcp_login_code_key(email=email),
        code=verification_code,
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
    user = store.find_user_by_email(email=email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    raw_key, expires_at = _issue_mcp_api_key(store=store, user=user, expires_in_days=expires_in_days)
    return HTMLResponse(_key_created_html(api_key=raw_key, expires_at=expires_at))


@router.post("/sign-up", response_class=HTMLResponse)
def mcp_sign_up_submit(
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
            pending_id=pending_id,
            email=email,
        )
    )


@router.post("/sign-up/verify", response_class=HTMLResponse)
def mcp_sign_up_verify(
    pending_id: str = Form(...),
    verification_code: str = Form(...),
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> HTMLResponse:
    if not _accepts_any_local_auth_code() and not store.verify_registration_code(
        email=_mcp_sign_up_code_key(pending_id=pending_id),
        code=verification_code,
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
    pending_json = store.consume_mcp_pending_signup(pending_id=pending_id)
    if pending_json is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired sign-up request")
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
    return HTMLResponse(_sign_up_complete_html(email=user.email))


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
    store: ApiDatabaseStore,
) -> JSONResponse:
    if isinstance(payload, list):
        logger.info("mcp_json_rpc_batch_started message_count=%d", len(payload))
        responses = [
            _handle_json_rpc_message(
                message=item,
                authorization=authorization,
                x_mcp_api_key=x_mcp_api_key,
                store=store,
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
    )
    if response is None:
        return JSONResponse(status_code=202, content={})
    return JSONResponse(response)


def _handle_json_rpc_message(
    *,
    message: Any,
    authorization: str | None,
    x_mcp_api_key: str | None,
    store: ApiDatabaseStore,
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
            logger.info("mcp_initialize_completed")
            return _json_rpc_result(
                request_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "aijurisdiction-laws-mcp", "version": get_api_version()},
                },
            )
        if method == "notifications/initialized":
            logger.info("mcp_notification_received method=%s", method)
            return None
        if method == "tools/list":
            logger.info("mcp_tools_list_completed tool_count=%d", len(_mcp_tools()))
            return _json_rpc_result(request_id, {"tools": _mcp_tools()})
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
                tool_name not in _PUBLIC_TOOLS,
            )
            _require_auth_for_tool(
                tool_name=tool_name,
                authorization=authorization,
                x_mcp_api_key=x_mcp_api_key,
                store=store,
            )
            result = _call_tool(tool_name, arguments)
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
    store: ApiDatabaseStore,
) -> None:
    if tool_name in _PUBLIC_TOOLS:
        logger.info("mcp_tool_auth_skipped tool=%s reason=public_tool", tool_name)
        return
    api_key = _extract_mcp_api_key(authorization=authorization, x_mcp_api_key=x_mcp_api_key)
    if not api_key:
        logger.warning("mcp_tool_auth_failed tool=%s reason=missing_api_key", tool_name)
        raise HTTPException(status_code=401, detail="Tool requires a valid MCP API key")
    user = _authenticate_mcp_api_token(api_key=api_key, store=store)
    logger.info("mcp_tool_auth_succeeded tool=%s user_id=%s", tool_name, user.user_id)


def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
    handlers = {
        "getVersion": _tool_get_version,
        "getStatistics": _tool_get_statistics,
        "searchLaws": _tool_search_laws,
        "getLawText": _tool_get_law_text,
    }
    handler = handlers.get(name)
    if handler is None:
        logger.warning("mcp_tool_unknown tool=%s", name)
        raise HTTPException(status_code=404, detail=f"Unknown MCP tool: {name}")
    return handler(arguments)


def _tool_get_version(_arguments: dict[str, Any]) -> dict[str, str]:
    return {
        "api_version": get_api_version(),
        "mcp_server_version": get_mcp_server_version(),
        "system_version": get_core_version(),
        "mobile_app_version": get_mobile_app_version(),
        "web_app_version": get_web_app_version(),
    }


def _tool_get_statistics(arguments: dict[str, Any]) -> dict[str, Any]:
    country_code = str(arguments.get("country_code", "SK")).strip().upper() or "SK"
    logger.info("mcp_tool_get_statistics_query country_code=%s", country_code)
    payload = _read_laws_statistics(config=_laws_db_config(), country_code=country_code)
    collector = payload.get("collector", {})
    result = {
        "country_code": payload.get("country_code"),
        "processed_laws": payload.get("totals", {}).get("laws_imported", 0),
        "last_processed_law": collector.get("last_processed_law"),
        "last_processed_day": collector.get("last_processed_at"),
        "details": payload,
    }
    logger.info(
        "mcp_tool_get_statistics_result country_code=%s processed_laws=%s last_processed_law=%s",
        result["country_code"],
        result["processed_laws"],
        result["last_processed_law"],
    )
    return result


def _tool_search_laws(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="query must contain at least 2 characters")
    country_code = str(arguments.get("country_code", "SK")).strip().upper() or "SK"
    limit = _bounded_int(arguments.get("limit"), default=10, minimum=1, maximum=50)
    pattern = f"%{query.lower()}%"
    logger.info("mcp_tool_search_laws_query country_code=%s limit=%d query_length=%d", country_code, limit, len(query))

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
                d.lawyer_title,
                d.source_url,
                v.version_id,
                v.version_token,
                v.effective_from,
                COALESCE(m.law_identifier_text, '') AS law_identifier_text,
                COALESCE(m.title, d.official_name) AS title,
                COALESCE(m.law_type, '') AS law_type
            FROM law_documents AS d
            JOIN law_versions AS v ON v.document_id = d.document_id
            LEFT JOIN law_metadata AS m ON m.version_id = v.version_id
            WHERE UPPER(d.country_code) = {laws.param}
              AND (
                  LOWER(d.official_name) LIKE {laws.param}
                  OR LOWER(d.lawyer_title) LIKE {laws.param}
                  OR LOWER(COALESCE(m.title, '')) LIKE {laws.param}
                  OR LOWER(COALESCE(m.law_identifier_text, '')) LIKE {laws.param}
              )
            ORDER BY d.law_year DESC, d.law_number DESC, v.effective_from DESC
            LIMIT {laws.param}
            """,
            (country_code, pattern, pattern, pattern, pattern, limit),
        )
    results = [_search_result_from_row(row) for row in rows]
    logger.info("mcp_tool_search_laws_result country_code=%s result_count=%d", country_code, len(results))
    return {"query": query, "country_code": country_code, "results": results}


def _tool_get_law_text(arguments: dict[str, Any]) -> dict[str, Any]:
    document_id = str(arguments.get("document_id", "")).strip()
    if not document_id:
        raise HTTPException(status_code=400, detail="document_id is required")
    logger.info("mcp_tool_get_law_text_query document_id_hash=%s", _stable_hash(document_id))
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
    if not rows:
        logger.warning("mcp_tool_get_law_text_not_found document_id_hash=%s", _stable_hash(document_id))
        raise HTTPException(status_code=404, detail="Law document not found")
    row = rows[0]
    result_document_id = str(row[0])
    result_country_code = str(row[1])
    result_content_text = str(row[9])
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
        "content_text": result_content_text,
    }
    logger.info(
        "mcp_tool_get_law_text_result document_id_hash=%s country_code=%s content_length=%d",
        _stable_hash(result_document_id),
        result_country_code,
        len(result_content_text),
    )
    return result


class _LawsQuerySession:
    def __init__(self) -> None:
        self._connection: Any = None

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


def _mcp_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "getVersion",
            "description": "Public version information for the mobile, system, API, and web apps.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "getStatistics",
            "description": "Public laws collector processing statistics.",
            "inputSchema": {
                "type": "object",
                "properties": {"country_code": {"type": "string", "default": "SK"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "searchLaws",
            "description": "Search imported laws by title, identifier, and lawyer-facing title.",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "minLength": 2},
                    "country_code": {"type": "string", "default": "SK"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "getLawText",
            "description": "Return the latest imported HTML text for a law document id.",
            "inputSchema": {
                "type": "object",
                "required": ["document_id"],
                "properties": {"document_id": {"type": "string", "minLength": 1}},
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
) -> tuple[str, str]:
    expires_at_dt = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).replace(microsecond=0)
    raw_key = create_mcp_api_token(user=user, expires_at=expires_at_dt, audience=audience)
    expires_at = expires_at_dt.isoformat()
    store.set_user_mcp_api_key(user_id=user.user_id, api_key=raw_key, expires_at=expires_at)
    return raw_key, expires_at


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
    payload = validate_mcp_api_token(
        api_key,
        audience=default_mcp_resource_url(),
        required_scope=MCP_TOKEN_SCOPE,
    )
    if payload is None:
        logger.warning("mcp_auth_failed reason=invalid_or_expired_token")
        raise HTTPException(status_code=401, detail="Invalid or expired MCP API key")
    user = store.find_user_by_mcp_api_key(api_key=api_key)
    if user is None or user.user_id != payload.get("sub"):
        logger.warning(
            "mcp_auth_failed reason=token_user_mismatch subject_type=%s",
            _value_type(payload.get("sub")),
        )
        raise HTTPException(status_code=401, detail="Invalid or expired MCP API key")
    return user


def _accepts_any_local_auth_code() -> bool:
    return os.getenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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
    return f"{_base_url(request)}/MCP"


def _resolve_oauth_resource(*, request: Request, resource: str) -> str:
    return resource.strip() or _resource_url(request)


def _allowed_oauth_redirect_hosts() -> set[str]:
    configured = os.getenv("MCP_OAUTH_ALLOWED_REDIRECT_HOSTS", "").strip()
    if configured:
        return {host.strip().lower() for host in configured.split(",") if host.strip()}
    return set(_DEFAULT_ALLOWED_REDIRECT_HOSTS)


def _payload_requires_auth(payload: Any) -> bool:
    messages = payload if isinstance(payload, list) else [payload]
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("method") != "tools/call":
            continue
        raw_params = message.get("params")
        params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
        tool_name = params.get("name")
        if isinstance(tool_name, str) and tool_name not in _PUBLIC_TOOLS:
            return True
    return False


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
    metadata_url = f"{_base_url(request)}/.well-known/oauth-protected-resource/MCP"
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
    parsed_redirect = urlparse(redirect_uri)
    if parsed_redirect.scheme not in {"http", "https", "vscode", "vscode-insiders"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported redirect_uri")
    if parsed_redirect.scheme in {"http", "https"}:
        allowed_hosts = _allowed_oauth_redirect_hosts()
        if parsed_redirect.hostname is None or parsed_redirect.hostname.lower() not in allowed_hosts:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unregistered redirect_uri host")
    if code_challenge_method != "S256":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PKCE S256 is supported")
    if not code_challenge.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_challenge is required")
    if resource != expected_resource:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth resource mismatch")


def _pkce_s256_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _search_result_from_row(row: Sequence[Any]) -> dict[str, Any]:
    return {
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


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _tool_result_summary(*, tool_name: str, result: Any) -> str:
    if not isinstance(result, dict):
        return f"type={type(result).__name__}"
    if tool_name == "getVersion":
        return "fields=api_version,system_version,mobile_app_version,web_app_version"
    if tool_name == "getStatistics":
        return (
            f"country_code={result.get('country_code')} "
            f"processed_laws={result.get('processed_laws')} "
            f"last_processed_law={result.get('last_processed_law')}"
        )
    if tool_name == "searchLaws":
        results = result.get("results")
        result_count = len(results) if isinstance(results, list) else 0
        return f"country_code={result.get('country_code')} result_count={result_count}"
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


def _login_form_html() -> str:
    return """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>AIJurisdiction MCP Login</title></head>
<body>
  <main>
    <h1>AIJurisdiction MCP Login</h1>
    <form method="post" action="/MCP/login">
      <label>Username or email <input name="email" type="email" autocomplete="username" required></label><br>
      <label>Password <input name="password" type="password" autocomplete="current-password" required></label><br>
      <label>API key expiry days <input name="expires_in_days" type="number" min="1" max="365" value="1"></label><br>
      <button type="submit">Send OTP code</button>
    </form>
    <p><a href="/MCP/sign-up">Sign up</a></p>
  </main>
</body>
</html>"""


def _oauth_login_form_html(
    *,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
    resource: str,
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
        }
    )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Authorize MCP access</title></head>
<body>
  <main>
    <h1>Authorize MCP access</h1>
    <form method="post" action="/oauth/authorize/login">
{hidden}
      <label>Email <input name="email" type="email" autocomplete="username" required></label><br>
      <label>Password <input name="password" type="password" autocomplete="current-password" required></label><br>
      <button type="submit">Send OTP code</button>
    </form>
    <p><a href="/MCP/sign-up">Sign up</a></p>
  </main>
</body>
</html>"""


def _oauth_otp_form_html(
    *,
    email: str,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
    resource: str,
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
        }
    )
    escaped_email = escape(email, quote=False)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Verify MCP OAuth login</title></head>
<body>
  <main>
    <h1>Verify MCP OAuth login</h1>
    <p>An OTP code was sent to {escaped_email}.</p>
    <form method="post" action="/oauth/authorize/verify">
{hidden}
      <label>OTP code <input name="verification_code" type="text" inputmode="numeric" autocomplete="one-time-code" required></label><br>
      <button type="submit">Authorize</button>
    </form>
  </main>
</body>
</html>"""


def _otp_form_html(*, email: str, expires_in_days: int) -> str:
    escaped_email = escape(email, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Verify MCP login</title></head>
<body>
  <main>
    <h1>Verify MCP login</h1>
    <p>An OTP code was sent to {escaped_email}.</p>
    <form method="post" action="/MCP/login/verify">
      <input name="email" type="hidden" value="{escaped_email}">
      <input name="expires_in_days" type="hidden" value="{expires_in_days}">
      <label>OTP code <input name="verification_code" type="text" inputmode="numeric" autocomplete="one-time-code" required></label><br>
      <button type="submit">Generate MCP API key</button>
    </form>
  </main>
</body>
</html>"""


def _sign_up_form_html() -> str:
    return """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>AIJurisdiction MCP Sign up</title></head>
<body>
  <main>
    <h1>AIJurisdiction MCP Sign up</h1>
    <form method="post" action="/MCP/sign-up">
      <label>Email <input name="email" type="email" autocomplete="username" required></label><br>
      <label>Phone number <input name="phone_number" type="tel" autocomplete="tel" required></label><br>
      <label>Password <input name="password" type="password" autocomplete="new-password" required></label><br>
      <label>First name <input name="first_name" type="text" autocomplete="given-name" required></label><br>
      <label>Last name <input name="last_name" type="text" autocomplete="family-name" required></label><br>
      <label>Address <input name="address" type="text" autocomplete="street-address" required></label><br>
      <label>City <input name="city" type="text" autocomplete="address-level2"></label><br>
      <label>Country <input name="country" type="text" autocomplete="country-name"></label><br>
      <label>ZIP code <input name="zip_code" type="text" autocomplete="postal-code"></label><br>
      <label>ID card number <input name="identity_card_number" type="text" required></label><br>
      <label><input name="data_processing_consent_accepted" type="checkbox" value="true" required> I agree to data processing for account creation and MCP access.</label><br>
      <button type="submit">Send verification code</button>
    </form>
    <p><a href="/MCP/login">Back to login</a></p>
  </main>
</body>
</html>"""


def _sign_up_otp_form_html(
    *,
    pending_id: str,
    email: str,
) -> str:
    hidden_html = _hidden_inputs({"pending_id": pending_id})
    escaped_email = escape(email, quote=False)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Verify MCP sign up</title></head>
<body>
  <main>
    <h1>Verify MCP sign up</h1>
    <p>An OTP code was sent to {escaped_email}.</p>
    <form method="post" action="/MCP/sign-up/verify">
{hidden_html}
      <label>OTP code <input name="verification_code" type="text" inputmode="numeric" autocomplete="one-time-code" required></label><br>
      <button type="submit">Create account</button>
    </form>
  </main>
</body>
</html>"""


def _hidden_inputs(values: dict[str, str]) -> str:
    return "\n".join(
        f'      <input name="{escape(name, quote=True)}" type="hidden" value="{escape(value, quote=True)}">'
        for name, value in values.items()
    )


def _sign_up_complete_html(*, email: str) -> str:
    escaped_email = escape(email, quote=False)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>MCP account created</title></head>
<body>
  <main>
    <h1>MCP account created</h1>
    <p>Account {escaped_email} is verified. You can now log in and generate an MCP API key.</p>
    <p><a href="/MCP/login">Log in</a></p>
  </main>
</body>
</html>"""


def _key_created_html(*, api_key: str, expires_at: str) -> str:
    escaped_api_key = escape(api_key, quote=False)
    escaped_expires_at = escape(expires_at, quote=False)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>MCP API key created</title></head>
<body>
  <main>
    <h1>MCP API key created</h1>
    <p>This key is shown once and expires at {escaped_expires_at}.</p>
    <pre>{escaped_api_key}</pre>
    <p>Use it as a Bearer token or as the x-mcp-api-key header when connecting your AI assistant to /MCP.</p>
  </main>
</body>
</html>"""
