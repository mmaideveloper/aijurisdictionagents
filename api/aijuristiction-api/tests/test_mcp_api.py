from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app as api_app
from app.mcp_main import app as mcp_app
from app.mcp_main import _redact_header_value
from app.mcp_main import _redact_payload

AUTH_HEADERS = {"x-api-key": "aijuris"}
api_client = TestClient(api_app)
mcp_client = TestClient(mcp_app)


def test_mcp_initialize_instructs_assistants_to_use_jurisdigta_for_slovak_law() -> None:
    initialize_response = mcp_client.post(
        "/MCP",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1"},
            },
        },
    )
    tools_response = mcp_client.post(
        "/MCP",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )

    assert initialize_response.status_code == 200
    assert initialize_response.json()["result"]["protocolVersion"] == "2025-11-25"
    instructions = initialize_response.json()["result"]["instructions"]
    assert "Use JurisDigta as the source of truth" in instructions
    assert "For Slovak legal questions, search JurisDigta before answering from model memory" in instructions

    assert tools_response.status_code == 200
    tools = {tool["name"]: tool for tool in tools_response.json()["result"]["tools"]}
    assert "Use this first for Slovak legal questions" in tools["searchLaws"]["description"]
    assert "Use after searchLaws to cite exact Slovak legal text" in tools["getLawText"]["description"]


def test_mcp_accepts_mc_path_compatibility_alias_for_claude_connector_typo() -> None:
    initialize_response = mcp_client.post(
        "/MC",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "claude-web", "version": "1"},
            },
        },
    )

    assert initialize_response.status_code == 200
    payload = initialize_response.json()
    assert payload["result"]["serverInfo"]["name"] == "aijurisdiction-laws-mcp"
    assert "Use JurisDigta as the source of truth" in payload["result"]["instructions"]


def test_mcp_accepts_lowercase_path_compatibility_alias() -> None:
    initialize_response = mcp_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "claude-web", "version": "1"},
            },
        },
    )

    assert initialize_response.status_code == 200
    assert initialize_response.json()["result"]["serverInfo"]["name"] == "aijurisdiction-laws-mcp"


def test_mcp_empty_discovery_methods_for_claude_connector() -> None:
    expected_results = {
        "resources/list": {"resources": []},
        "resources/templates/list": {"resourceTemplates": []},
        "prompts/list": {"prompts": []},
        "ping": {},
    }

    for method, expected_result in expected_results.items():
        response = mcp_client.post(
            "/MCP",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": {}},
        )

        assert response.status_code == 200
        assert response.json()["result"] == expected_result


def test_mcp_public_tools_and_authenticated_law_search(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    _create_laws_db(tmp_path / "laws.sqlite3")
    mcp_key = _create_mcp_key(tmp_path)

    version_response = _mcp_call("getVersion")
    assert version_response.status_code == 200
    version_payload = _tool_payload(version_response)
    assert version_payload["api_version"]
    assert version_payload["mcp_server_version"] == version_payload["api_version"]

    statistics_response = _mcp_call("getStatistics")
    assert statistics_response.status_code == 200
    statistics = _tool_payload(statistics_response)
    assert statistics["processed_laws"] == 1
    assert statistics["last_processed_law"] == "1/1993"
    assert statistics["last_processed_day"] == "2026-06-01T12:00:00Z"

    unauthenticated_search = _mcp_call("searchLaws", {"query": "civil"})
    assert unauthenticated_search.status_code == 401
    assert "WWW-Authenticate" in unauthenticated_search.headers
    assert unauthenticated_search.json()["error"]["code"] == 401

    authenticated_search = _mcp_call(
        "searchLaws",
        {"query": "civil"},
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    assert authenticated_search.status_code == 200
    results = _tool_payload(authenticated_search)["results"]
    assert results[0]["document_id"] == "doc-1"
    assert results[0]["law_identifier_text"] == "1/1993 Z. z."

    text_response = _mcp_call(
        "getLawText",
        {"document_id": "doc-1"},
        headers={"x-mcp-api-key": mcp_key},
    )
    assert text_response.status_code == 200
    assert _tool_payload(text_response)["content_text"] == "Civil code full text."


def test_mcp_logs_tool_events_without_sensitive_payloads(monkeypatch, tmp_path: Path, caplog) -> None:
    _configure_env(monkeypatch, tmp_path)
    _create_laws_db(tmp_path / "laws.sqlite3")
    mcp_key = _create_mcp_key(tmp_path)

    caplog.set_level(logging.INFO, logger="aijuristiction-api.mcp")
    secret_query = "civil-sensitive-query"
    text_response = _mcp_call(
        "getLawText",
        {"document_id": "doc-1"},
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    search_response = _mcp_call(
        "searchLaws",
        {"query": secret_query, "limit": 5},
        headers={"x-mcp-api-key": mcp_key},
    )

    assert text_response.status_code == 200
    assert search_response.status_code == 200
    mcp_log_messages = [
        record.getMessage() for record in caplog.records if record.name == "aijuristiction-api.mcp"
    ]
    assert any("mcp_tool_completed tool=getLawText" in message for message in mcp_log_messages)
    assert any("mcp_tool_completed tool=searchLaws" in message for message in mcp_log_messages)
    joined_logs = "\n".join(mcp_log_messages)
    assert secret_query not in joined_logs
    assert "Civil code full text." not in joined_logs
    assert "doc-1" not in joined_logs
    assert mcp_key not in joined_logs
    assert "secret-pass" not in joined_logs
    assert "mcp-search@example.com" not in joined_logs


def test_mcp_wire_logging_records_redacted_request_and_response(monkeypatch, tmp_path: Path, caplog) -> None:
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("MCP_WIRE_LOGGING_ENABLED", "true")
    caplog.set_level(logging.INFO, logger="jurisdigta-mcp-server.http")

    response = mcp_client.post(
        "/MCP?code=secret-code&state=public-state",
        headers={
            "authorization": "Bearer secret-bearer-token",
            "x-mcp-api-key": "secret-api-key",
            "x-request-id": "wire-test-request",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1"},
                "password": "secret-pass",
                "email": "mcp-search@example.com",
                "token_type": "Bearer",
                "access_token": "secret-access-token",
                "nested": {"verification_code": "123456"},
            },
        },
    )

    assert response.status_code == 200
    http_logs = [
        record.getMessage()
        for record in caplog.records
        if record.name == "jurisdigta-mcp-server.http"
    ]
    joined_logs = "\n".join(http_logs)
    assert "mcp_wire_request request_id=wire-test-request" in joined_logs
    assert "mcp_wire_response request_id=wire-test-request" in joined_logs
    assert '"authorization": "[redacted]"' in joined_logs
    assert '"x-mcp-api-key": "[redacted]"' in joined_logs
    assert "secret-bearer-token" not in joined_logs
    assert "secret-api-key" not in joined_logs
    assert "secret-code" not in joined_logs
    assert "secret-pass" not in joined_logs
    assert "secret-access-token" not in joined_logs
    assert "123456" not in joined_logs
    assert "mcp-search@example.com" not in joined_logs
    assert '"token_type": "Bearer"' in joined_logs
    assert "public-state" in joined_logs


def test_mcp_wire_logging_redacts_oauth_codes_in_redirect_headers() -> None:
    location = (
        "https://claude.ai/api/mcp/auth_callback?"
        "code=secret-code&state=public-state&iss=https%3A%2F%2Fmcp.jurisdigta.eu"
    )

    redacted = _redact_header_value("Location", location)

    assert "secret-code" not in redacted
    assert "code=%5Bredacted%5D" in redacted
    assert "state=public-state" in redacted
    assert "iss=https%3A%2F%2Fmcp.jurisdigta.eu" in redacted


def test_mcp_wire_logging_preserves_oauth_token_type_while_redacting_values() -> None:
    redacted = _redact_payload(
        {
            "token_type": "Bearer",
            "access_token": "secret-access-token",
            "refresh_token": "secret-refresh-token",
            "email": "mcp-search@example.com",
        }
    )

    assert redacted["token_type"] == "Bearer"
    assert redacted["access_token"] == "[redacted]"
    assert redacted["refresh_token"] == "[redacted]"
    assert redacted["email"] == "[redacted]"


def test_user_mcp_api_key_defaults_to_one_day(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)

    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421 900 111 226",
            "email": "mcp-default@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201
    before = datetime.now(timezone.utc)

    create_key_response = api_client.post(
        f"/v1/users/{sign_up_response.json()['user_id']}/mcp-api-key",
        headers=AUTH_HEADERS,
        json={},
    )

    assert create_key_response.status_code == 200
    token = create_key_response.json()["mcp_api_key"]
    claims = _jwt_claims(token)
    assert claims["sub"] == sign_up_response.json()["user_id"]
    assert claims["aud"] == "https://mcp.jurisdigta.eu/MCP"
    assert claims["scope"] == "mcp:laws"
    assert "email" not in claims
    assert "first_name" not in claims
    assert "last_name" not in claims
    expires_at = datetime.fromisoformat(create_key_response.json()["mcp_api_key_expires_at"])
    delta = expires_at - before
    assert 0.9 < delta.total_seconds() / 86400 < 1.1


def test_mcp_login_page_can_generate_key(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "true")
    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421 900 111 227",
            "email": "mcp-login@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201

    page_response = mcp_client.get("/MCP/login")
    assert page_response.status_code == 200
    assert "JurisDigta MCP" in page_response.text
    assert "auth-shell" in page_response.text
    assert "Send OTP code" in page_response.text
    assert "AIJurisdiction MCP Login" not in page_response.text

    login_response = mcp_client.post(
        "/MCP/login",
        data={"email": "mcp-login@example.com", "password": "secret-pass"},
    )
    assert login_response.status_code == 200
    assert "Verify MCP login" in login_response.text

    verify_response = mcp_client.post(
        "/MCP/login/verify",
        data={
            "email": "mcp-login@example.com",
            "verification_code": "123456",
            "expires_in_days": "1",
        },
    )
    assert verify_response.status_code == 200
    assert "MCP API key created" in verify_response.text

    with sqlite3.connect(tmp_path / "email.sqlite3") as conn:
        rows = conn.execute(
            "SELECT recipient, subject FROM email_outbox WHERE subject = ?",
            ("Your MCP login code",),
        ).fetchall()
    assert rows == [("mcp-login@example.com", "Your MCP login code")]


def test_mcp_login_invalid_otp_returns_localized_html_warning(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421 900 111 231",
            "email": "mcp-login-warning@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201

    login_response = mcp_client.post(
        "/MCP/login",
        data={"email": "mcp-login-warning@example.com", "password": "secret-pass"},
        headers={"accept-language": "sk-SK,sk;q=0.9,en;q=0.8"},
    )
    assert login_response.status_code == 200
    assert '<html lang="sk">' in login_response.text
    assert "Overenie MCP prihlasenia" in login_response.text

    verify_response = mcp_client.post(
        "/MCP/login/verify",
        data={
            "email": "mcp-login-warning@example.com",
            "verification_code": "000000",
            "expires_in_days": "7",
        },
        headers={"accept-language": "sk-SK,sk;q=0.9,en;q=0.8"},
    )

    assert verify_response.status_code == 400
    assert "text/html" in verify_response.headers["content-type"]
    assert "application/json" not in verify_response.headers["content-type"]
    assert "Overovaci kod je neplatny alebo expiroval" in verify_response.text
    assert 'name="email" type="hidden" value="mcp-login-warning@example.com"' in verify_response.text
    assert 'name="expires_in_days" type="hidden" value="7"' in verify_response.text


def test_mcp_sign_up_requires_email_otp_and_profile_fields(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "true")

    page_response = mcp_client.get("/MCP/sign-up")
    assert page_response.status_code == 200
    assert "JurisDigta MCP" in page_response.text
    assert "auth-shell" in page_response.text
    assert "ID card number" in page_response.text
    assert "AIJurisdiction MCP Sign up" not in page_response.text

    send_code_response = mcp_client.post(
        "/MCP/sign-up",
        data={
            "email": "mcp-new@example.com",
            "phone_number": "+421 900 111 229",
            "password": "secret-pass",
            "first_name": "Mcp",
            "last_name": "User",
            "address": "Main 1",
            "identity_card_number": "AB123456",
            "city": "Bratislava",
            "country": "SK",
            "zip_code": "81101",
            "data_processing_consent_accepted": "true",
        },
    )
    assert send_code_response.status_code == 200
    assert "Verify MCP sign up" in send_code_response.text
    assert "secret-pass" not in send_code_response.text
    assert "AB123456" not in send_code_response.text

    verify_response = mcp_client.post(
        "/MCP/sign-up/verify",
        data={
            "pending_id": _extract_hidden_value(send_code_response.text, "pending_id"),
            "verification_code": "123456",
        },
    )
    assert verify_response.status_code == 200
    assert "MCP account created" in verify_response.text

    profile_response = api_client.post(
        "/v1/users/sign-in",
        headers=AUTH_HEADERS,
        json={"email": "mcp-new@example.com", "password": "secret-pass"},
    )
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["phone_number"] == "+421900111229"
    assert profile["first_name"] == "Mcp"
    assert profile["last_name"] == "User"
    assert profile["address"] == "Main 1"
    assert profile["identity_card_number"] == "AB123456"
    assert profile["data_processing_consent_at"]

    with sqlite3.connect(tmp_path / "email.sqlite3") as conn:
        rows = conn.execute(
            "SELECT recipient, subject FROM email_outbox ORDER BY created_at ASC",
        ).fetchall()
    assert ("mcp-new@example.com", "Your MCP sign-up code") in rows
    assert ("mcp-new@example.com", "Welcome to AI Jurisdiction") in rows


def test_mcp_sign_up_invalid_otp_returns_localized_html_warning(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)

    page_response = mcp_client.get("/MCP/sign-up", headers={"accept-language": "sk"})
    assert page_response.status_code == 200
    assert '<html lang="sk">' in page_response.text
    assert "Cislo obcianskeho preukazu" in page_response.text

    send_code_response = mcp_client.post(
        "/MCP/sign-up",
        data={
            "email": "mcp-new-warning@example.com",
            "phone_number": "+421 900 111 232",
            "password": "secret-pass",
            "first_name": "Mcp",
            "last_name": "User",
            "address": "Main 1",
            "identity_card_number": "CD123456",
            "city": "Bratislava",
            "country": "SK",
            "zip_code": "81101",
            "data_processing_consent_accepted": "true",
        },
        headers={"accept-language": "sk"},
    )
    assert send_code_response.status_code == 200
    assert "Overenie MCP registracie" in send_code_response.text

    verify_response = mcp_client.post(
        "/MCP/sign-up/verify",
        data={
            "pending_id": _extract_hidden_value(send_code_response.text, "pending_id"),
            "email": _extract_hidden_value(send_code_response.text, "email"),
            "verification_code": "000000",
        },
        headers={"accept-language": "sk"},
    )

    assert verify_response.status_code == 400
    assert "text/html" in verify_response.headers["content-type"]
    assert "Overovaci kod je neplatny alebo expiroval" in verify_response.text
    assert 'name="pending_id" type="hidden"' in verify_response.text
    assert 'name="email" type="hidden" value="mcp-new-warning@example.com"' in verify_response.text


def test_oauth_discovery_and_authorization_code_flow(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    _create_laws_db(tmp_path / "laws.sqlite3")
    monkeypatch.setenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "true")
    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421 900 111 230",
            "email": "mcp-oauth@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201

    protected_metadata = mcp_client.get("/.well-known/oauth-protected-resource/MCP")
    assert protected_metadata.status_code == 200
    assert protected_metadata.json()["resource"].endswith("/MCP")
    assert protected_metadata.json()["resource_name"] == "JurisDigta MCP"
    assert protected_metadata.json()["scopes_supported"] == ["mcp:laws"]

    authorization_metadata = mcp_client.get("/.well-known/oauth-authorization-server")
    assert authorization_metadata.status_code == 200
    assert authorization_metadata.json()["code_challenge_methods_supported"] == ["S256"]
    assert authorization_metadata.json()["grant_types_supported"] == ["authorization_code", "refresh_token"]
    assert authorization_metadata.json()["scopes_supported"] == ["mcp:laws", "offline_access"]
    assert authorization_metadata.json()["registration_endpoint"].endswith("/oauth/register")
    assert authorization_metadata.json()["authorization_response_iss_parameter_supported"] is True
    assert authorization_metadata.json()["protected_resources"] == ["https://mcp.jurisdigta.eu/MCP"]

    registration_response = mcp_client.post(
        "/oauth/register",
        json={
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp:laws",
        },
    )
    assert registration_response.status_code == 201
    registration_payload = registration_response.json()
    assert registration_payload["client_id"].startswith("jurisdigta-")
    assert registration_payload["redirect_uris"] == ["https://claude.ai/api/mcp/auth_callback"]
    assert registration_payload["token_endpoint_auth_method"] == "none"

    claude_variant_registration = mcp_client.post(
        "/oauth/register",
        json={
            "client_name": "Claude Connector",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
            "scope": "mcp:laws offline_access",
        },
    )
    assert claude_variant_registration.status_code == 201
    claude_variant_payload = claude_variant_registration.json()
    assert claude_variant_payload["client_id"].startswith("jurisdigta-")
    assert claude_variant_payload["grant_types"] == ["authorization_code", "refresh_token"]
    assert claude_variant_payload["token_endpoint_auth_method"] == "none"
    assert claude_variant_payload["scope"] == "mcp:laws offline_access"

    code_verifier = "test-code-verifier-1234567890"
    code_challenge = _pkce_challenge(code_verifier)
    resource = "https://mcp.jurisdigta.eu/MCP"
    authorize_page = mcp_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "chatgpt",
            "redirect_uri": "https://client.example/callback",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "abc",
            "resource": resource,
        },
    )
    assert authorize_page.status_code == 200
    assert "Authorize MCP access" in authorize_page.text

    login_response = mcp_client.post(
        "/oauth/authorize/login",
        data={
            "response_type": "code",
            "client_id": "chatgpt",
            "redirect_uri": "https://client.example/callback",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "abc",
            "resource": resource,
            "email": "mcp-oauth@example.com",
            "password": "secret-pass",
        },
    )
    assert login_response.status_code == 200
    assert "Verify MCP OAuth login" in login_response.text

    verify_response = mcp_client.post(
        "/oauth/authorize/verify",
        data={
            "response_type": "code",
            "client_id": "chatgpt",
            "redirect_uri": "https://client.example/callback",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "abc",
            "resource": resource,
            "email": "mcp-oauth@example.com",
            "verification_code": "123456",
        },
        follow_redirects=False,
    )
    assert verify_response.status_code == 303
    location = verify_response.headers["location"]
    assert location.startswith("https://client.example/callback?")
    callback_query = parse_qs(urlparse(location).query)
    assert callback_query["state"] == ["abc"]
    assert callback_query["iss"] == ["https://mcp.jurisdigta.eu"]
    authorization_code = callback_query["code"][0]

    token_response = mcp_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": "https://client.example/callback",
            "client_id": "chatgpt",
            "code_verifier": code_verifier,
            "resource": resource,
        },
    )
    assert token_response.status_code == 200
    assert token_response.headers["cache-control"] == "no-store"
    assert token_response.headers["pragma"] == "no-cache"
    token_payload = token_response.json()
    assert token_payload["token_type"] == "Bearer"
    assert token_payload["scope"] == "mcp:laws offline_access"
    assert token_payload["refresh_token"]
    claims = _jwt_claims(token_payload["access_token"])
    assert claims["sub"] == sign_up_response.json()["user_id"]
    assert claims["aud"] == resource
    assert claims["scope"] == "mcp:laws"
    assert "email" not in claims
    refresh_claims = _jwt_claims(token_payload["refresh_token"])
    assert refresh_claims["sub"] == sign_up_response.json()["user_id"]
    assert refresh_claims["aud"] == resource
    assert refresh_claims["scope"] == "offline_access"
    assert refresh_claims["token_use"] == "refresh"
    assert "email" not in refresh_claims

    oauth_search = _mcp_call(
        "searchLaws",
        {"query": "civil"},
        headers={"authorization": f"Bearer {token_payload['access_token']}"},
    )
    assert oauth_search.status_code == 200
    assert _tool_payload(oauth_search)["results"][0]["document_id"] == "doc-1"

    refresh_as_access_search = _mcp_call(
        "searchLaws",
        {"query": "civil"},
        headers={"authorization": f"Bearer {token_payload['refresh_token']}"},
    )
    assert refresh_as_access_search.status_code == 200
    assert refresh_as_access_search.json()["error"]["code"] == 401

    refresh_response = mcp_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": token_payload["refresh_token"],
            "client_id": "chatgpt",
            "resource": resource,
        },
    )
    assert refresh_response.status_code == 200
    assert refresh_response.headers["cache-control"] == "no-store"
    assert refresh_response.headers["pragma"] == "no-cache"
    refreshed_payload = refresh_response.json()
    assert refreshed_payload["token_type"] == "Bearer"
    assert refreshed_payload["scope"] == "mcp:laws offline_access"
    assert refreshed_payload["access_token"] != token_payload["access_token"]
    assert refreshed_payload["refresh_token"] != token_payload["refresh_token"]
    refreshed_claims = _jwt_claims(refreshed_payload["access_token"])
    assert refreshed_claims["sub"] == sign_up_response.json()["user_id"]
    assert refreshed_claims["aud"] == resource
    assert refreshed_claims["scope"] == "mcp:laws"

    replacement_key_response = api_client.post(
        f"/v1/users/{sign_up_response.json()['user_id']}/mcp-api-key",
        headers=AUTH_HEADERS,
        json={"expires_in_days": 1},
    )
    assert replacement_key_response.status_code == 200
    assert replacement_key_response.json()["mcp_api_key"] != token_payload["access_token"]

    existing_oauth_search = _mcp_call(
        "searchLaws",
        {"query": "civil"},
        headers={"authorization": f"Bearer {token_payload['access_token']}"},
    )
    assert existing_oauth_search.status_code == 200
    assert _tool_payload(existing_oauth_search)["results"][0]["document_id"] == "doc-1"


def test_oauth_login_reuses_recent_mcp_otp_verification(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "true")
    monkeypatch.setenv("MCP_OTP_REUSE_WINDOW_HOURS", "24")
    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421 900 111 233",
            "email": "mcp-oauth-reuse@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201

    code_verifier = "test-code-verifier-reuse-1234567890"
    code_challenge = _pkce_challenge(code_verifier)
    resource = "https://mcp.jurisdigta.eu/MCP"
    authorize_data = {
        "response_type": "code",
        "client_id": "claude",
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": "claude-state",
        "resource": resource,
        "email": "mcp-oauth-reuse@example.com",
        "password": "secret-pass",
    }

    first_login_response = mcp_client.post("/oauth/authorize/login", data=authorize_data)
    assert first_login_response.status_code == 200
    assert "Verify MCP OAuth login" in first_login_response.text

    verify_response = mcp_client.post(
        "/oauth/authorize/verify",
        data={
            **{key: value for key, value in authorize_data.items() if key != "password"},
            "verification_code": "123456",
        },
        follow_redirects=False,
    )
    assert verify_response.status_code == 303

    reuse_response = mcp_client.post(
        "/oauth/authorize/login",
        data=authorize_data,
        follow_redirects=False,
    )

    assert reuse_response.status_code == 303
    assert reuse_response.headers["location"].startswith("https://claude.ai/api/mcp/auth_callback?")
    assert "state=claude-state" in reuse_response.headers["location"]
    with sqlite3.connect(tmp_path / "email.sqlite3") as conn:
        rows = conn.execute(
            "SELECT subject FROM email_outbox WHERE recipient = ? AND subject = ?",
            ("mcp-oauth-reuse@example.com", "Your MCP OAuth login code"),
        ).fetchall()
    assert rows == [("Your MCP OAuth login code",)]


def test_mcp_otp_reuse_can_be_disabled(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "true")
    monkeypatch.setenv("MCP_OTP_REUSE_WINDOW_HOURS", "0")
    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421 900 111 234",
            "email": "mcp-oauth-no-reuse@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201

    code_challenge = _pkce_challenge("test-code-verifier-no-reuse-1234567890")
    authorize_data = {
        "response_type": "code",
        "client_id": "claude",
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": "claude-state",
        "resource": "https://mcp.jurisdigta.eu/MCP",
        "email": "mcp-oauth-no-reuse@example.com",
        "password": "secret-pass",
    }

    first_login_response = mcp_client.post("/oauth/authorize/login", data=authorize_data)
    assert first_login_response.status_code == 200
    verify_response = mcp_client.post(
        "/oauth/authorize/verify",
        data={
            **{key: value for key, value in authorize_data.items() if key != "password"},
            "verification_code": "123456",
        },
        follow_redirects=False,
    )
    assert verify_response.status_code == 303

    second_login_response = mcp_client.post("/oauth/authorize/login", data=authorize_data)
    assert second_login_response.status_code == 200
    assert "Verify MCP OAuth login" in second_login_response.text


def test_oauth_discovery_uses_public_base_url(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "https://mcp.jurisdigta.eu")

    protected_metadata = mcp_client.get(
        "/.well-known/oauth-protected-resource/MCP",
        headers={"x-forwarded-proto": "http", "x-forwarded-host": "internal.local"},
    )
    authorization_metadata = mcp_client.get(
        "/.well-known/oauth-authorization-server",
        headers={"x-forwarded-proto": "http", "x-forwarded-host": "internal.local"},
    )
    mcp_path_authorization_metadata = mcp_client.get(
        "/.well-known/oauth-authorization-server/MCP",
        headers={"x-forwarded-proto": "http", "x-forwarded-host": "internal.local"},
    )

    assert protected_metadata.status_code == 200
    assert protected_metadata.json()["resource"] == "https://mcp.jurisdigta.eu/MCP"
    assert protected_metadata.json()["authorization_servers"] == ["https://mcp.jurisdigta.eu"]
    assert authorization_metadata.status_code == 200
    assert authorization_metadata.json()["issuer"] == "https://mcp.jurisdigta.eu"
    assert authorization_metadata.json()["token_endpoint"] == "https://mcp.jurisdigta.eu/oauth/token"
    assert authorization_metadata.json()["registration_endpoint"] == "https://mcp.jurisdigta.eu/oauth/register"
    assert mcp_path_authorization_metadata.status_code == 200
    assert mcp_path_authorization_metadata.json() == authorization_metadata.json()


def test_oauth_registration_rejects_unregistered_redirect_host(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)

    registration_response = mcp_client.post(
        "/oauth/register",
        json={
            "client_name": "Unknown client",
            "redirect_uris": ["https://evil.example/callback"],
            "token_endpoint_auth_method": "none",
        },
    )

    assert registration_response.status_code == 400
    assert registration_response.json()["detail"] == "Unregistered redirect_uri host"


def _configure_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "blob"))
    monkeypatch.setenv("EMAIL_DB_OPTION", "local")
    monkeypatch.setenv("EMAIL_DB_LOCAL", str(tmp_path / "email.sqlite3"))
    monkeypatch.setenv("EMAIL_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "laws.sqlite3"))
    monkeypatch.setenv("MCP_API_JWT_SECRET", "test-mcp-secret")
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "https://mcp.jurisdigta.eu")
    monkeypatch.setenv("MCP_OAUTH_ALLOWED_REDIRECT_HOSTS", "client.example,chatgpt.com,claude.ai")


def _create_mcp_key(tmp_path: Path) -> str:
    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421 900 111 228",
            "email": "mcp-search@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201
    create_key_response = api_client.post(
        f"/v1/users/{sign_up_response.json()['user_id']}/mcp-api-key",
        headers=AUTH_HEADERS,
        json={"expires_in_days": 1},
    )
    assert create_key_response.status_code == 200
    assert (tmp_path / "api.sqlite3").exists()
    return str(create_key_response.json()["mcp_api_key"])


def _mcp_call(
    name: str,
    arguments: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }
    return mcp_client.post("/MCP", json=payload, headers=headers or {})


def _tool_payload(response) -> dict[str, object]:
    text = response.json()["result"]["content"][0]["text"]
    return json.loads(text)


def _jwt_claims(token: str) -> dict[str, object]:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    assert isinstance(decoded, dict)
    return decoded


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _extract_hidden_value(html: str, name: str) -> str:
    marker = f'name="{name}" type="hidden" value="'
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    return html[start:end]


def _create_laws_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE law_documents (
                document_id TEXT PRIMARY KEY,
                country_code TEXT NOT NULL,
                collection_code TEXT NOT NULL,
                law_year INTEGER NOT NULL,
                law_number INTEGER NOT NULL,
                official_name TEXT NOT NULL,
                lawyer_title TEXT NOT NULL,
                source_url TEXT NOT NULL,
                current_status TEXT NOT NULL,
                last_stored_at TEXT NOT NULL
            );
            CREATE TABLE law_versions (
                version_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_token TEXT NOT NULL,
                effective_from TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_dimensions INTEGER NOT NULL,
                embedding_vector TEXT NOT NULL
            );
            CREATE TABLE law_metadata (
                law_metadata_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_id TEXT NOT NULL,
                law_identifier_text TEXT NOT NULL,
                title TEXT NOT NULL,
                law_type TEXT NOT NULL
            );
            CREATE TABLE source_artifacts (
                artifact_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_id TEXT NOT NULL,
                artifact_kind TEXT NOT NULL,
                source_url TEXT NOT NULL,
                storage_backend TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                content_text TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE collector_progress (
                country_code TEXT PRIMARY KEY,
                source_system TEXT NOT NULL,
                last_collector_run_at TEXT,
                last_processed_at TEXT,
                last_processed_law_year INTEGER,
                last_processed_law_number INTEGER,
                next_probe_law_year INTEGER NOT NULL,
                next_probe_law_number INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE collector_import_state (
                country_code TEXT NOT NULL,
                import_key TEXT NOT NULL,
                import_label TEXT NOT NULL,
                status TEXT NOT NULL,
                last_processed_at TEXT,
                last_processed_law_year INTEGER,
                last_processed_law_number INTEGER,
                completed_at TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE archive_import_assets (
                country_code TEXT NOT NULL,
                processing_status TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO law_documents(
                document_id, country_code, collection_code, law_year, law_number,
                official_name, lawyer_title, source_url, current_status, last_stored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-1",
                "SK",
                "ZZ",
                1993,
                1,
                "Civil Code",
                "Civil rights law",
                "https://example.test/laws/1",
                "published",
                "2026-06-01T12:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO law_versions(
                version_id, document_id, version_token, effective_from,
                embedding_model, embedding_dimensions, embedding_vector
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("ver-1", "doc-1", "19930101", "1993-01-01", "test-model", 8, "[0.1]"),
        )
        conn.execute(
            """
            INSERT INTO law_metadata(
                law_metadata_id, document_id, version_id, law_identifier_text, title, law_type
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("meta-1", "doc-1", "ver-1", "1/1993 Z. z.", "Civil Code", "act"),
        )
        conn.execute(
            """
            INSERT INTO source_artifacts(
                artifact_id, document_id, version_id, artifact_kind, source_url,
                storage_backend, storage_path, content_text, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "artifact-1",
                "doc-1",
                "ver-1",
                "html",
                "https://example.test/laws/1",
                "local_file",
                "ignored",
                "Civil code full text.",
                "2026-06-01T12:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO collector_progress(
                country_code, source_system, last_collector_run_at, last_processed_at,
                last_processed_law_year, last_processed_law_number,
                next_probe_law_year, next_probe_law_number, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SK",
                "slov-lex",
                "2026-06-01T12:01:00Z",
                "2026-06-01T12:00:00Z",
                1993,
                1,
                1993,
                2,
                "2026-06-01T12:01:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO collector_import_state(
                country_code, import_key, import_label, status, last_processed_at,
                last_processed_law_year, last_processed_law_number, completed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SK",
                "slov-lex:zip:test",
                "test import",
                "completed",
                "2026-06-01T12:00:00Z",
                1993,
                1,
                "2026-06-01T12:00:00Z",
                "2026-06-01T12:00:00Z",
            ),
        )
        conn.execute(
            "INSERT INTO archive_import_assets(country_code, processing_status) VALUES (?, ?)",
            ("SK", "processed"),
        )
        conn.commit()
