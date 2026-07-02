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
from app import mcp_api
from app.mcp_main import app as mcp_app
from app.mcp_main import _redact_header_value
from app.mcp_main import _redact_payload
from app.users.totp import current_totp_code
from services.court_decision_collector.domain import CourtDecisionSearchResult

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
    assert "pseudonymized public snippets" in tools["searchCourtDecisions"]["description"]
    assert "outputMode=public" in tools["getCourtDecision"]["description"]


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


def test_mcp_accepts_claude_backend_probe_without_bearer_token() -> None:
    initialize_response = mcp_client.post(
        "/MCP",
        headers={"user-agent": "python-httpx/0.28.1", "mcp-protocol-version": "2025-11-25"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "Anthropic", "version": "1.0.0"},
            },
        },
    )

    assert initialize_response.status_code == 200
    assert initialize_response.json()["result"]["protocolVersion"] == "2025-11-25"
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
    court_stats = {
        "status": "ok",
        "collector_status": "running",
        "total_decisions": 2,
        "published_decisions": 2,
        "total_versions": 3,
        "last_imported_decision": "fixture-sk-decision-2",
        "last_imported_decision_id": "decision-2",
        "last_imported_source_guid": "fixture-sk-decision-2",
        "last_imported_at": "2026-06-30T10:00:00+00:00",
        "last_imported_court_name": "Okresny sud Zilina",
        "last_imported_court_type": "Okresny sud",
        "last_imported_issue_date": "2026-06-29",
        "last_imported_ecli": "ECLI:SK:OSZA:2026:2",
        "last_imported_file_number": "12C/34/2026",
        "collector_last_processed_at": "2026-06-30T10:00:00+00:00",
        "collector_last_source_guid": "fixture-sk-decision-2",
    }
    monkeypatch.setattr(mcp_api, "_court_decision_statistics", lambda: court_stats)

    version_response = _mcp_call("getVersion")
    assert version_response.status_code == 200
    version_payload = _tool_payload(version_response)
    assert version_payload["api_version"]
    assert version_payload["mcp_server_version"] == version_payload["api_version"]
    assert version_payload["court_decision_collector_version"]
    assert version_payload["court_decision_collector"] == {
        "version": version_payload["court_decision_collector_version"],
        "status": "running",
        "last_imported_decision": "fixture-sk-decision-2",
        "last_imported_at": "2026-06-30T10:00:00+00:00",
    }

    statistics_response = _mcp_call("getStatistics")
    assert statistics_response.status_code == 200
    statistics = _tool_payload(statistics_response)
    assert statistics["processed_laws"] == 1
    assert statistics["last_processed_law"] == "1/1993"
    assert statistics["last_processed_day"] == "2026-06-01T12:00:00Z"
    assert statistics["court_decision_collector_version"] == version_payload["court_decision_collector_version"]
    assert statistics["total_court_decisions"] == 2
    assert statistics["last_imported_decision"] == "fixture-sk-decision-2"
    assert statistics["last_imported_decision_at"] == "2026-06-30T10:00:00+00:00"
    assert statistics["court_decisions"]["published_decisions"] == 2
    assert statistics["court_decisions"]["last_imported_file_number"] == "12C/34/2026"

    unauthenticated_search = _mcp_call("searchLaws", {"query": "civil"})
    assert unauthenticated_search.status_code == 401
    assert "oauth-protected-resource" in unauthenticated_search.headers["www-authenticate"]
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


def test_mcp_court_decision_tools_require_auth() -> None:
    unauthenticated_search = _mcp_call("searchCourtDecisions", {"query": "najomna zmluva"})
    assert unauthenticated_search.status_code == 401

    unauthenticated_detail = _mcp_call("getCourtDecision", {"decision_id": "decision-1"})
    assert unauthenticated_detail.status_code == 401


def test_mcp_search_court_decisions_returns_bounded_results_and_privacy_safe_logs(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)

    class FakeCourtDecisionStore:
        def search(self, *, query: str, limit: int) -> list[CourtDecisionSearchResult]:
            assert query == "zobraz mi posledne sudne rozhodnutie ktore sa tykalo rozdelenia pozemku podla podielu"
            assert limit == 1
            return [
                CourtDecisionSearchResult(
                    decision_id="decision-1",
                    version_id="version-1",
                    source_guid="infosud-1",
                    court_name="Okresny sud Bratislava I",
                    court_type="Okresny sud",
                    file_number="12C/34/2026",
                    case_number="12C/34/2026",
                    ecli="ECLI:SK:OSBA1:2026:1234567890.1",
                    issue_date="2026-06-29",
                    source_url="https://example.test/decision/1",
                    snippet="Pseudonymizovane rozhodnutie o rozdeleni pozemku podla podielu.",
                    score=0.91,
                )
            ]

    def fake_court_decision_store(**kwargs: object) -> FakeCourtDecisionStore:
        assert kwargs["initialize"] is False
        assert kwargs["connect_timeout_seconds"] == 3
        assert kwargs["statement_timeout_ms"] == 8000
        return FakeCourtDecisionStore()

    monkeypatch.setattr(mcp_api, "_court_decision_store", fake_court_decision_store)
    caplog.set_level(logging.INFO, logger="aijuristiction-api.mcp")
    secret_query = "zobraz mi posledne sudne rozhodnutie ktore sa tykalo rozdelenia pozemku podla podielu"

    response = _mcp_call(
        "searchCourtDecisions",
        {"query": secret_query, "limit": 1},
        headers={"authorization": f"Bearer {mcp_key}", "x-request-id": "court-search-request"},
    )

    assert response.status_code == 200
    payload = _tool_payload(response)
    assert payload["status"] == "ok"
    assert payload["output_mode"] == "public"
    assert payload["timeout_ms"] == 8000
    assert payload["results"][0]["decision_id"] == "decision-1"
    assert payload["results"][0]["issue_date"] == "2026-06-29"
    mcp_log_messages = [
        record.getMessage() for record in caplog.records if record.name == "aijuristiction-api.mcp"
    ]
    assert any("mcp_tool_search_court_decisions_result result_count=1" in message for message in mcp_log_messages)
    joined_logs = "\n".join(mcp_log_messages)
    assert secret_query not in joined_logs
    assert "Pseudonymizovane rozhodnutie" not in joined_logs
    assert mcp_key not in joined_logs


def test_mcp_search_court_decisions_timeout_returns_structured_degraded_result(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)

    class TimeoutCourtDecisionStore:
        def search(self, *, query: str, limit: int) -> list[CourtDecisionSearchResult]:
            raise TimeoutError("statement timeout")

    monkeypatch.setattr(mcp_api, "_court_decision_store", lambda **_kwargs: TimeoutCourtDecisionStore())
    caplog.set_level(logging.INFO, logger="aijuristiction-api.mcp")

    response = _mcp_call(
        "searchCourtDecisions",
        {
            "query": "zobraz mi posledne sudne rozhodnutie ktore sa tykalo rozdelenia pozemku podla podielu",
            "limit": 5,
        },
        headers={
            "authorization": f"Bearer {mcp_key}",
            "x-request-id": "court-timeout-request",
            "x-correlation-id": "court-timeout-correlation",
        },
    )

    assert response.status_code == 200
    payload = _tool_payload(response)
    assert payload["status"] == "degraded"
    assert payload["retryable"] is True
    assert payload["results"] == []
    assert payload["error"]["code"] == "court_decision_search_timeout"
    assert payload["error"]["kind"] == "timeout"
    assert payload["error"]["correlation_id"] == "court-timeout-correlation"
    assert payload["error"]["request_id"] == "court-timeout-request"
    assert payload["timeout_ms"] == 8000
    assert payload["limit"] == 5
    assert any(
        "mcp_tool_search_court_decisions_degraded" in record.getMessage()
        and "error_kind=timeout" in record.getMessage()
        for record in caplog.records
        if record.name == "aijuristiction-api.mcp"
    )


def test_mcp_search_prefers_base_law_over_newer_amendment(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    db_path = tmp_path / "laws.sqlite3"
    _create_laws_db(db_path)
    mcp_key = _create_mcp_key(tmp_path)
    _insert_law_search_fixture(
        db_path,
        document_id="doc-40-1964",
        version_id="ver-40-1964",
        metadata_id="meta-40-1964",
        artifact_id="artifact-40-1964",
        law_year=1964,
        law_number=40,
        official_name="Obciansky zakonnik",
        lawyer_title="Obciansky zakonnik",
        law_identifier_text="40/1964 Zb.",
        title="Obciansky zakonnik",
        content_text="Aktualne konsolidovane znenie Obcianskeho zakonnika.",
    )
    _insert_law_search_fixture(
        db_path,
        document_id="doc-254-2024",
        version_id="ver-254-2024",
        metadata_id="meta-254-2024",
        artifact_id="artifact-254-2024",
        law_year=2024,
        law_number=254,
        official_name="Zakon, ktorym sa meni a doplna zakon c. 40/1964 Zb. Obciansky zakonnik",
        lawyer_title="Novela Obcianskeho zakonnika",
        law_identifier_text="254/2024 Z. z.",
        title="Zakon, ktorym sa meni a doplna Obciansky zakonnik",
        content_text="Novelizacny zakon.",
    )

    title_search = _mcp_call(
        "searchLaws",
        {"query": "Obciansky zakonnik"},
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    identifier_search = _mcp_call(
        "searchLaws",
        {"query": "40/1964"},
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    explicit_identifier_search = _mcp_call(
        "searchLaws",
        {"query": "Obciansky zakonnik", "law_year": 1964, "law_number": 40},
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert title_search.status_code == 200
    assert identifier_search.status_code == 200
    assert explicit_identifier_search.status_code == 200
    assert _tool_payload(title_search)["results"][0]["document_id"] == "doc-40-1964"
    assert _tool_payload(identifier_search)["results"][0]["document_id"] == "doc-40-1964"
    explicit_results = _tool_payload(explicit_identifier_search)["results"]
    assert [result["document_id"] for result in explicit_results] == ["doc-40-1964"]


def test_mcp_get_law_text_caps_large_default_payload(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    db_path = tmp_path / "laws.sqlite3"
    _create_laws_db(db_path)
    mcp_key = _create_mcp_key(tmp_path)
    large_text = "Civil code full text.\n" + ("A" * 25_000)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE source_artifacts SET content_text = ? WHERE document_id = ?",
            (large_text, "doc-1"),
        )
        conn.commit()

    text_response = _mcp_call(
        "getLawText",
        {"document_id": "doc-1"},
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert text_response.status_code == 200
    payload = _tool_payload(text_response)
    assert len(payload["content_text"]) == 20_000
    assert payload["content_truncated"] is True
    assert payload["next_offset"] == 20_000
    assert payload["total_content_length"] == len(large_text)


def test_mcp_get_law_text_returns_requested_section_range(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    db_path = tmp_path / "laws.sqlite3"
    _create_laws_db(db_path)
    mcp_key = _create_mcp_key(tmp_path)
    civil_code_text = "\n".join(
        [
            "Prva cast",
            "§ 684 Predchadzajuce ustanovenie.",
            "§ 685 Najom bytu vznika najomnou zmluvou.",
            "§ 686 Najomna zmluva musi obsahovat oznacenie predmetu najmu.",
            "§ 716 Skoncenie najmu bytu.",
            "§ 717 Ubytovanie mimo najmu bytu.",
        ]
    )
    _insert_law_search_fixture(
        db_path,
        document_id="doc-40-1964",
        version_id="ver-40-1964",
        metadata_id="meta-40-1964",
        artifact_id="artifact-40-1964",
        law_year=1964,
        law_number=40,
        official_name="Obciansky zakonnik",
        lawyer_title="Obciansky zakonnik",
        law_identifier_text="40/1964 Zb.",
        title="Obciansky zakonnik",
        content_text=civil_code_text,
    )

    text_response = _mcp_call(
        "getLawText",
        {"document_id": "doc-40-1964", "section_start": 685, "section_end": 716},
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert text_response.status_code == 200
    payload = _tool_payload(text_response)
    assert payload["content_scope"] == "sections"
    assert payload["requested_sections"][0] == 685
    assert payload["requested_sections"][-1] == 716
    assert payload["section_found"] is True
    assert "§ 685 Najom bytu" in payload["content_text"]
    assert "§ 716 Skoncenie najmu" in payload["content_text"]
    assert "§ 684" not in payload["content_text"]
    assert "§ 717" not in payload["content_text"]


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
    assert claims["iss"] == "https://mcp.jurisdigta.eu"
    assert claims["scope"] == "mcp:laws"
    assert claims["token_use"] == "access"
    assert isinstance(claims["iat"], int)
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


def test_mcp_login_supports_totp_mfa_choice(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("MFA_REUSE_WINDOW_HOURS", "0")
    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900777222",
            "email": "mcp-totp@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201
    user_id = sign_up_response.json()["user_id"]
    start_response = api_client.post(f"/v1/users/{user_id}/mfa/totp/start", headers=AUTH_HEADERS)
    assert start_response.status_code == 200
    secret = start_response.json()["manual_setup_key"]
    confirm_response = api_client.post(
        f"/v1/users/{user_id}/mfa/totp/confirm",
        headers=AUTH_HEADERS,
        json={"verification_code": current_totp_code(secret=secret)},
    )
    assert confirm_response.status_code == 200

    login_response = mcp_client.post(
        "/MCP/login",
        data={"email": "mcp-totp@example.com", "password": "secret-pass", "expires_in_days": "1"},
    )
    assert login_response.status_code == 200
    assert "Choose MFA method" in login_response.text
    assert 'option value="email"' in login_response.text
    assert 'option value="totp"' in login_response.text

    method_response = mcp_client.post(
        "/MCP/login/mfa",
        data={"email": "mcp-totp@example.com", "mfa_method": "totp", "expires_in_days": "1"},
    )
    assert method_response.status_code == 200
    assert "Authenticator code" in method_response.text

    verify_response = mcp_client.post(
        "/MCP/login/verify",
        data={
            "email": "mcp-totp@example.com",
            "mfa_method": "totp",
            "verification_code": current_totp_code(secret=secret),
            "expires_in_days": "1",
        },
    )
    assert verify_response.status_code == 200
    assert "MCP API key created" in verify_response.text


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
    claude_web_protected_metadata = mcp_client.get(
        "/.well-known/oauth-protected-resource/MCP",
        headers={"user-agent": "python-httpx/0.28.1", "mcp-protocol-version": "2025-11-25"},
    )
    assert claude_web_protected_metadata.status_code == 200
    claude_web_authorization_metadata = mcp_client.get(
        "/.well-known/oauth-authorization-server",
        headers={"user-agent": "python-httpx/0.28.1"},
    )
    assert claude_web_authorization_metadata.status_code == 200
    assert claude_web_authorization_metadata.json()["registration_endpoint"].endswith("/oauth/register")
    assert claude_web_authorization_metadata.json()["authorization_response_iss_parameter_supported"] is True
    monkeypatch.setenv("MCP_CLAUDE_WEB_PUBLIC_DISCOVERY", "true")
    claude_web_authorization_metadata_with_legacy_flag = mcp_client.get(
        "/.well-known/oauth-authorization-server",
        headers={"user-agent": "python-httpx/0.28.1"},
    )
    assert claude_web_authorization_metadata_with_legacy_flag.status_code == 200
    claude_web_registration_with_legacy_flag = mcp_client.post(
        "/oauth/register",
        headers={"user-agent": "python-httpx/0.28.1"},
        json={
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
            "scope": "mcp:laws offline_access",
        },
    )
    assert claude_web_registration_with_legacy_flag.status_code == 201
    monkeypatch.delenv("MCP_CLAUDE_WEB_PUBLIC_DISCOVERY")
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

    additional_hosted_registration = mcp_client.post(
        "/oauth/register",
        json={
            "client_name": "Hosted OAuth clients",
            "redirect_uris": [
                "https://vscode.dev/redirect",
                "https://claude.ai/api/mcp/auth_callback",
                "https://www.perplexity.ai/rest/connections/oauth_callback",
            ],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp:laws offline_access",
        },
    )
    assert additional_hosted_registration.status_code == 201
    assert additional_hosted_registration.json()["redirect_uris"] == [
        "https://vscode.dev/redirect",
        "https://claude.ai/api/mcp/auth_callback",
        "https://www.perplexity.ai/rest/connections/oauth_callback",
    ]

    loopback_registration = mcp_client.post(
        "/oauth/register",
        json={
            "client_name": "Claude Desktop",
            "redirect_uris": [
                "http://127.0.0.1:6274/callback",
                "http://localhost:6274/callback",
                "http://[::1]:6274/callback",
            ],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp:laws offline_access",
        },
    )
    assert loopback_registration.status_code == 201
    assert loopback_registration.json()["redirect_uris"] == [
        "http://127.0.0.1:6274/callback",
        "http://localhost:6274/callback",
        "http://[::1]:6274/callback",
    ]

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
    access_claims = _jwt_claims(token_payload["access_token"])
    assert access_claims["sub"] == sign_up_response.json()["user_id"]
    assert access_claims["aud"] == resource
    assert access_claims["iss"] == "https://mcp.jurisdigta.eu"
    assert access_claims["scope"] == "mcp:laws"
    assert access_claims["token_use"] == "access"
    assert isinstance(access_claims["iat"], int)
    refresh_claims = _jwt_claims(token_payload["refresh_token"])
    assert refresh_claims["sub"] == sign_up_response.json()["user_id"]
    assert refresh_claims["aud"] == resource
    assert refresh_claims["iss"] == "https://mcp.jurisdigta.eu"
    assert refresh_claims["scope"] == "offline_access"
    assert refresh_claims["token_use"] == "refresh"
    assert isinstance(refresh_claims["iat"], int)
    assert "email" not in refresh_claims

    oauth_search = _mcp_call(
        "searchLaws",
        {"query": "civil"},
        headers={"authorization": f"Bearer {token_payload['access_token']}"},
    )
    assert oauth_search.status_code == 200
    assert _tool_payload(oauth_search)["results"][0]["document_id"] == "doc-1"

    unauthenticated_search = _mcp_call(
        "searchLaws",
        {"query": "civil"},
    )
    assert unauthenticated_search.status_code == 401
    assert "oauth-protected-resource" in unauthenticated_search.headers["www-authenticate"]
    assert unauthenticated_search.json()["error"]["code"] == 401

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
    refreshed_access_claims = _jwt_claims(refreshed_payload["access_token"])
    assert refreshed_access_claims["sub"] == sign_up_response.json()["user_id"]
    assert refreshed_access_claims["aud"] == resource
    assert refreshed_access_claims["scope"] == "mcp:laws"
    assert refreshed_access_claims["token_use"] == "access"

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


def test_oauth_authorization_response_issuer_can_be_enabled(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "true")
    monkeypatch.delenv("MCP_OAUTH_AUTHORIZATION_RESPONSE_ISS", raising=False)
    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421 900 111 235",
            "email": "mcp-oauth-iss@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201

    authorization_metadata = mcp_client.get("/.well-known/oauth-authorization-server")
    assert authorization_metadata.status_code == 200
    assert authorization_metadata.json()["authorization_response_iss_parameter_supported"] is True

    code_verifier = "test-code-verifier-issuer-1234567890"
    code_challenge = _pkce_challenge(code_verifier)
    resource = "https://mcp.jurisdigta.eu/mcp"
    verify_response = mcp_client.post(
        "/oauth/authorize/verify",
        data={
            "response_type": "code",
            "client_id": "chatgpt",
            "redirect_uri": "https://client.example/callback",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "with-issuer",
            "resource": resource,
            "email": "mcp-oauth-iss@example.com",
            "verification_code": "123456",
        },
        follow_redirects=False,
    )
    assert verify_response.status_code == 303
    callback_query = parse_qs(urlparse(verify_response.headers["location"]).query)
    assert callback_query["state"] == ["with-issuer"]
    assert callback_query["iss"] == ["https://mcp.jurisdigta.eu"]


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
    resource = "https://mcp.jurisdigta.eu/mcp"
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
        "resource": "https://mcp.jurisdigta.eu/mcp",
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
    lower_mcp_protected_metadata = mcp_client.get(
        "/.well-known/oauth-protected-resource/mcp",
        headers={"x-forwarded-proto": "http", "x-forwarded-host": "internal.local"},
    )
    lower_mcp_authorization_metadata = mcp_client.get(
        "/.well-known/oauth-authorization-server/mcp",
        headers={"x-forwarded-proto": "http", "x-forwarded-host": "internal.local"},
    )

    assert protected_metadata.status_code == 200
    assert protected_metadata.json()["resource"] == "https://mcp.jurisdigta.eu/MCP"
    assert protected_metadata.json()["authorization_servers"] == ["https://mcp.jurisdigta.eu"]
    assert lower_mcp_protected_metadata.status_code == 200
    assert lower_mcp_protected_metadata.json() == protected_metadata.json()
    assert authorization_metadata.status_code == 200
    assert authorization_metadata.json()["issuer"] == "https://mcp.jurisdigta.eu"
    assert authorization_metadata.json()["token_endpoint"] == "https://mcp.jurisdigta.eu/oauth/token"
    assert authorization_metadata.json()["registration_endpoint"] == "https://mcp.jurisdigta.eu/oauth/register"
    assert authorization_metadata.json()["client_id_metadata_document_supported"] is True
    assert mcp_path_authorization_metadata.status_code == 200
    assert mcp_path_authorization_metadata.json() == authorization_metadata.json()
    assert lower_mcp_authorization_metadata.status_code == 200
    assert lower_mcp_authorization_metadata.json() == authorization_metadata.json()


def test_oauth_registration_accepts_loopback_redirect_for_local_clients(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)

    registration_response = mcp_client.post(
        "/oauth/register",
        json={
            "client_name": "Claude Desktop mcp-remote",
            "redirect_uris": [
                "http://127.0.0.1:3334/callback",
                "http://localhost:3334/callback",
                "http://[::1]:3334/callback",
            ],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp:laws offline_access",
        },
    )

    assert registration_response.status_code == 201
    assert registration_response.json()["token_endpoint_auth_method"] == "none"
    assert registration_response.json()["redirect_uris"] == [
        "http://127.0.0.1:3334/callback",
        "http://localhost:3334/callback",
        "http://[::1]:3334/callback",
    ]


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


def test_oauth_authorize_accepts_client_id_metadata_document(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    client_id = "https://client.example/oauth/client-metadata.json"

    monkeypatch.setattr(
        "app.mcp_api._fetch_client_id_metadata_document",
        lambda client_id: {
            "client_id": client_id,
            "client_name": "Example MCP Client",
            "redirect_uris": ["http://127.0.0.1:3334/callback"],
        },
    )

    response = mcp_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "http://127.0.0.1:3334/callback",
            "code_challenge": "test-challenge",
            "code_challenge_method": "S256",
            "resource": "https://mcp.jurisdigta.eu/MCP",
            "state": "abc",
        },
    )

    assert response.status_code == 200
    assert "Authorize MCP access" in response.text


def test_oauth_authorize_rejects_unregistered_client_id_metadata_redirect(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    client_id = "https://client.example/oauth/client-metadata.json"

    monkeypatch.setattr(
        "app.mcp_api._fetch_client_id_metadata_document",
        lambda client_id: {
            "client_id": client_id,
            "client_name": "Example MCP Client",
            "redirect_uris": ["https://client.example/callback"],
        },
    )

    response = mcp_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "http://127.0.0.1:3334/callback",
            "code_challenge": "test-challenge",
            "code_challenge_method": "S256",
            "resource": "https://mcp.jurisdigta.eu/MCP",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "redirect_uri is not registered for client_id"


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
    monkeypatch.setenv(
        "MCP_OAUTH_ALLOWED_REDIRECT_HOSTS",
        "client.example,chatgpt.com,claude.ai,vscode.dev,www.perplexity.ai,localhost,127.0.0.1,::1",
    )


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


def _insert_law_search_fixture(
    path: Path,
    *,
    document_id: str,
    version_id: str,
    metadata_id: str,
    artifact_id: str,
    law_year: int,
    law_number: int,
    official_name: str,
    lawyer_title: str,
    law_identifier_text: str,
    title: str,
    content_text: str,
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO law_documents(
                document_id, country_code, collection_code, law_year, law_number,
                official_name, lawyer_title, source_url, current_status, last_stored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                "SK",
                "ZZ",
                law_year,
                law_number,
                official_name,
                lawyer_title,
                f"https://example.test/laws/{law_year}/{law_number}",
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
            (version_id, document_id, f"{law_year}0101", f"{law_year}-01-01", "test-model", 8, "[0.1]"),
        )
        conn.execute(
            """
            INSERT INTO law_metadata(
                law_metadata_id, document_id, version_id, law_identifier_text, title, law_type
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (metadata_id, document_id, version_id, law_identifier_text, title, "act"),
        )
        conn.execute(
            """
            INSERT INTO source_artifacts(
                artifact_id, document_id, version_id, artifact_kind, source_url,
                storage_backend, storage_path, content_text, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                document_id,
                version_id,
                "html",
                f"https://example.test/laws/{law_year}/{law_number}",
                "local_file",
                "ignored",
                content_text,
                "2026-06-01T12:00:00Z",
            ),
        )
        conn.commit()
