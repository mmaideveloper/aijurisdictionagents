from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import json
import logging
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app as api_app
from app.mcp_main import app as mcp_app

AUTH_HEADERS = {"x-api-key": "aijuris"}
api_client = TestClient(api_app)
mcp_client = TestClient(mcp_app)


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
    assert unauthenticated_search.status_code == 200
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
    assert claims["email"] == "mcp-default@example.com"
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
    assert "Send OTP code" in page_response.text

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


def test_mcp_sign_up_requires_email_otp_and_profile_fields(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "true")

    page_response = mcp_client.get("/MCP/sign-up")
    assert page_response.status_code == 200
    assert "ID card number" in page_response.text

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


def test_oauth_discovery_and_authorization_code_flow(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
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

    authorization_metadata = mcp_client.get("/.well-known/oauth-authorization-server")
    assert authorization_metadata.status_code == 200
    assert authorization_metadata.json()["code_challenge_methods_supported"] == ["S256"]

    code_verifier = "test-code-verifier-1234567890"
    code_challenge = _pkce_challenge(code_verifier)
    authorize_page = mcp_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "chatgpt",
            "redirect_uri": "https://client.example/callback",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "abc",
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
            "email": "mcp-oauth@example.com",
            "verification_code": "123456",
        },
        follow_redirects=False,
    )
    assert verify_response.status_code == 303
    location = verify_response.headers["location"]
    assert location.startswith("https://client.example/callback?")
    authorization_code = location.split("code=", 1)[1].split("&", 1)[0]

    token_response = mcp_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": "https://client.example/callback",
            "client_id": "chatgpt",
            "code_verifier": code_verifier,
        },
    )
    assert token_response.status_code == 200
    token_payload = token_response.json()
    assert token_payload["token_type"] == "Bearer"
    claims = _jwt_claims(token_payload["access_token"])
    assert claims["email"] == "mcp-oauth@example.com"


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
