from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app as api_app
from app import mcp_api
from app.mcp_main import app as mcp_app
from app.mcp_main import _redact_header_value
from app.mcp_main import _redact_payload
from app.mcp_tokens import create_mcp_api_token
from app.users.totp import current_totp_code
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import (
    E2E_TEST_FREE_EMAIL,
    E2E_TEST_PAID_EMAIL,
    provision_e2e_test_users,
)
from services.court_decision_collector.domain import CourtDecisionSearchResult

AUTH_HEADERS = {"x-api-key": "aijuris"}
api_client = TestClient(api_app)
mcp_client = TestClient(mcp_app)


def test_postgres_laws_query_session_sets_parameterized_statement_timeout(monkeypatch) -> None:
    executed: list[tuple[str, tuple[object, ...]]] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb) -> None:
            return None

        def execute(self, query: str, params: tuple[object, ...]) -> None:
            if query.startswith("SET LOCAL statement_timeout"):
                raise SyntaxError('syntax error at or near "$1"')
            executed.append((query, params))

    class FakeResult:
        def fetchall(self) -> list[tuple[int]]:
            return [(1,)]

    class FakeConnection:
        closed = False

        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def execute(self, query: str, params: tuple[object, ...]) -> FakeResult:
            executed.append((query, params))
            return FakeResult()

        def close(self) -> None:
            self.closed = True

    connection = FakeConnection()
    fake_psycopg = SimpleNamespace(connect=lambda uri: connection)
    monkeypatch.setattr(
        mcp_api,
        "_laws_db_config",
        lambda: SimpleNamespace(backend="postgres", cloud_uri="postgresql://redacted"),
    )
    monkeypatch.setattr(mcp_api.importlib, "import_module", lambda name: fake_psycopg)

    with mcp_api._LawsQuerySession(statement_timeout_ms=30_000) as laws:
        assert laws.backend == "postgres"
        assert laws.param == "%s"
        assert laws.query_all("SELECT %s", (1,)) == [(1,)]

    assert executed == [
        ("SELECT set_config('statement_timeout', %s, true)", ("30000ms",)),
        ("SELECT %s", (1,)),
    ]
    assert connection.closed is True


def test_postgres_provision_search_uses_parameterized_full_text_query() -> None:
    captured: list[tuple[str, tuple[object, ...]]] = []

    def query_all(query: str, params: tuple[object, ...]) -> list[tuple[object, ...]]:
        captured.append((query, params))
        return []

    profile = mcp_api.build_legal_query_profile("kúpna zmluva na záhradu")
    laws = mcp_api._LawsQueryConfig(backend="postgres", query_all=query_all, param="%s")

    rows = mcp_api._query_provision_candidates(
        laws=laws,
        profile=profile,
        country_code="SK",
        published_year=None,
        law_year=None,
        law_number=None,
        candidate_limit=300,
    )

    assert rows == []
    assert len(captured) == 2
    assert captured[0] == ("SELECT set_config('enable_seqscan', 'off', true)", ())
    query, params = captured[1]
    assert query.count("to_tsquery('simple', %s)") == 10
    assert "fts_candidates AS MATERIALIZED" in query
    assert "FROM law_provisions AS p" in query
    assert "CROSS JOIN search_query" not in query
    assert "to_tsvector('simple', LOWER(p.body_text))" in query
    assert "@@ to_tsquery('simple', %s)" in query
    assert "JOIN law_versions AS v ON v.version_id = p.version_id" in query
    assert "AND NOT EXISTS" in query
    assert "ROW_NUMBER() OVER" not in query
    assert params[0] == params[1]
    assert params[2] == 120
    assert params[3] == params[4]
    assert params[5] == 120
    assert params[-1] == "SK"
    assert query.count("LIMIT %s") == 5
    assert query.count("effective_from <= CURRENT_DATE") == 10
    assert "JOIN law_versions AS candidate_version" in query
    assert "kúp:*" in str(params[0])
    assert "zmluv:*" in str(params[0])
    assert any("nehnuteľ:*" in str(value) for value in params)
    assert any("navrh:*" in str(value) for value in params)
    assert any("podpis:*" in str(value) for value in params)


def test_law_ranking_prefers_primary_cadastral_act_over_derivative_sources() -> None:
    profile = mcp_api.build_legal_query_profile("kupno predajna zmluva")

    cadastral_act = mcp_api._law_candidate_ranking_adjustment(
        profile=profile,
        law_type="Zákon",
        title="Zákon o katastri nehnuteľností (katastrálny zákon)",
    )
    implementing_regulation = mcp_api._law_candidate_ranking_adjustment(
        profile=profile,
        law_type="Vyhláška",
        title="Vyhláška, ktorou sa vykonáva katastrálny zákon",
    )
    amendment = mcp_api._law_candidate_ranking_adjustment(
        profile=profile,
        law_type="Zákon",
        title="Zákon, ktorým sa mení a dopĺňa katastrálny zákon",
    )

    assert cadastral_act > implementing_regulation
    assert cadastral_act > amendment


def test_mcp_initialize_instructs_assistants_to_use_jurisdigta_for_slovak_law(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)
    initialize_response = mcp_client.post(
        "/mcp",
        headers={"authorization": f"Bearer {mcp_key}"},
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
        "/mcp",
        headers={"authorization": f"Bearer {mcp_key}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )

    assert initialize_response.status_code == 200
    assert initialize_response.json()["result"]["protocolVersion"] == "2025-03-26"
    instructions = initialize_response.json()["result"]["instructions"]
    assert "Use JurisDigta as the source of truth" in instructions
    assert "For Slovak legal questions, search JurisDigta before answering from model memory" in instructions
    assert "ask the user whether they want to continue with the async search workflow" in instructions

    assert tools_response.status_code == 200
    tools = {tool["name"]: tool for tool in tools_response.json()["result"]["tools"]}
    assert "metadata search for Slovak legal sources" in tools["searchLegalSources"]["description"]
    assert "tool_name=searchLegalSources" in tools["searchLegalSources"]["description"]
    assert "Use this first for Slovak legal questions" in tools["searchLaws"]["description"]
    assert "tool_name=searchLaws" in tools["searchLaws"]["description"]
    assert "Use after searchLaws to cite exact Slovak legal text" in tools["getLawText"]["description"]
    assert "metadata only by default" in tools["searchCourtDecisions"]["description"]
    assert "tool_name=searchCourtDecisions" in tools["searchCourtDecisions"]["description"]
    assert tools["searchCourtDecisions"]["inputSchema"]["properties"]["sort"]["enum"] == ["relevance", "latest"]
    assert "court_name" in tools["searchCourtDecisions"]["inputSchema"]["properties"]
    assert "startLegalSearch" in tools
    assert "user approves async continuation" in tools["startLegalSearch"]["description"]
    assert "getLegalSearchStatus" in tools
    assert "getLegalSearchResult" in tools
    assert "full_version=true" in tools["getCourtDecision"]["description"]


def test_mcp_challenges_vscode_initialize_without_bearer() -> None:
    response = mcp_client.post(
        "/MCP",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "Visual Studio Code", "version": "1.102.0"},
            },
        },
    )

    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert "oauth-protected-resource/MCP" in response.headers["WWW-Authenticate"]
    assert response.json()["error"]["message"] == "Tool requires OAuth authorization"


def test_mcp_challenges_vscode_tools_list_without_bearer() -> None:
    response = mcp_client.post(
        "/MCP",
        headers={"user-agent": "Visual Studio Code/1.102.0"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert "oauth-protected-resource/MCP" in response.headers["WWW-Authenticate"]
    assert response.json()["error"]["message"] == "Tool requires OAuth authorization"


def test_mcp_accepts_authenticated_vscode_initialize(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)

    response = mcp_client.post(
        "/MCP",
        headers={"authorization": f"Bearer {mcp_key}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "Visual Studio Code", "version": "1.102.0"},
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["protocolVersion"] == "2025-11-25"


def test_mcp_challenges_mc_path_compatibility_alias_for_claude_connector_typo() -> None:
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

    assert initialize_response.status_code == 401
    assert "oauth-protected-resource/mcp" in initialize_response.headers["www-authenticate"]


def test_mcp_accepts_legacy_uppercase_path_compatibility_alias(monkeypatch, tmp_path: Path, caplog) -> None:
    _configure_env(monkeypatch, tmp_path)
    caplog.set_level(logging.INFO, logger="aijuristiction-api.mcp")
    initialize_response = mcp_client.post(
        "/MCP",
        headers={"authorization": f"Bearer {_create_mcp_key(tmp_path)}"},
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
    mcp_messages = [
        record.getMessage() for record in caplog.records if record.name == "aijuristiction-api.mcp"
    ]
    assert any(
        "mcp_endpoint_called request_path=/MCP canonical_resource=https://mcp.jurisdigta.eu/MCP" in message
        for message in mcp_messages
    )


def test_mcp_challenges_claude_backend_probe_without_bearer_token() -> None:
    initialize_response = mcp_client.post(
        "/mcp",
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

    assert initialize_response.status_code == 401
    assert "oauth-protected-resource/mcp" in initialize_response.headers["www-authenticate"]


def test_mcp_plain_get_keeps_method_guidance() -> None:
    response = mcp_client.get("/MCP")

    assert response.status_code == 405
    assert response.headers["allow"] == "GET, POST"
    assert response.json()["detail"] == "Use POST /mcp for Streamable HTTP JSON-RPC."


def test_mcp_accepts_sse_get_probe_for_streamable_http_clients(caplog) -> None:
    caplog.set_level(logging.INFO, logger="aijuristiction-api.mcp")

    response = mcp_client.get(
        "/MCP",
        headers={
            "accept": "text/event-stream",
            "user-agent": "python-httpx/0.28.1",
            "mcp-protocol-version": "2025-11-25",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == ": jurisdigta-mcp-ready\n\n"
    assert any("mcp_sse_stream_opened request_path=/MCP" in record.getMessage() for record in caplog.records)


def test_mcp_initialize_defaults_to_latest_for_unknown_protocol(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)
    initialize_response = mcp_client.post(
        "/mcp",
        headers={"authorization": f"Bearer {mcp_key}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2099-01-01",
                "capabilities": {},
                "clientInfo": {"name": "future-client", "version": "1"},
            },
        },
    )

    assert initialize_response.status_code == 200
    assert initialize_response.json()["result"]["protocolVersion"] == "2025-11-25"
    assert initialize_response.json()["result"]["serverInfo"]["name"] == "aijurisdiction-laws-mcp"


def test_legacy_uppercase_mcp_advertises_oauth_and_requires_auth_for_law_search(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _create_laws_db(tmp_path / "laws.sqlite3")

    legacy_protected_metadata = mcp_client.get(
        "/.well-known/oauth-protected-resource/MCP",
        headers={"user-agent": "python-httpx/0.28.1", "mcp-protocol-version": "2025-11-25"},
    )
    assert legacy_protected_metadata.status_code == 200
    assert legacy_protected_metadata.json()["resource"] == "https://mcp.jurisdigta.eu/MCP"
    assert legacy_protected_metadata.json()["authorization_servers"] == ["https://mcp.jurisdigta.eu"]

    lowercase_search = _mcp_call("searchLaws", {"query": "civil"})
    assert lowercase_search.status_code == 401
    assert "oauth-protected-resource" in lowercase_search.headers["www-authenticate"]

    claude_search = _mcp_call("searchLaws", {"query": "civil"}, path="/MCP")
    assert claude_search.status_code == 401
    assert "oauth-protected-resource/MCP" in claude_search.headers["www-authenticate"]

    raw_court_decision = _mcp_call(
        "getCourtDecision",
        {"decisionId": "decision-1", "outputMode": "internal_raw"},
        path="/MCP",
    )
    assert raw_court_decision.status_code == 401
    assert "oauth-protected-resource" in raw_court_decision.headers["www-authenticate"]


def test_mcp_empty_discovery_methods_for_claude_connector() -> None:
    expected_results = {
        "resources/list": {"resources": []},
        "resources/templates/list": {"resourceTemplates": []},
        "prompts/list": {"prompts": []},
        "ping": {},
    }

    for method, expected_result in expected_results.items():
        response = mcp_client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": {}},
        )

        assert response.status_code == 200
        assert response.json()["result"] == expected_result


def test_mcp_all_tools_require_auth_and_authenticated_calls_work(monkeypatch, tmp_path: Path) -> None:
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

    unauthenticated_version = _mcp_call("getVersion")
    assert unauthenticated_version.status_code == 401
    assert "oauth-protected-resource" in unauthenticated_version.headers["www-authenticate"]
    assert unauthenticated_version.json()["error"]["code"] == 401

    unauthenticated_statistics = _mcp_call("getStatistics")
    assert unauthenticated_statistics.status_code == 401
    assert "oauth-protected-resource" in unauthenticated_statistics.headers["www-authenticate"]
    assert unauthenticated_statistics.json()["error"]["code"] == 401

    version_response = _mcp_call("getVersion", headers={"authorization": f"Bearer {mcp_key}"})
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

    statistics_response = _mcp_call("getStatistics", headers={"authorization": f"Bearer {mcp_key}"})
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

    store = ApiDatabaseStore(db_path=tmp_path / "api.sqlite3", blob_root=tmp_path / "blob")
    legacy_user = store.find_user_by_email(email="mcp-search@example.com")
    assert legacy_user is not None
    legacy_mcp_key = create_mcp_api_token(
        user=legacy_user,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        audience="https://mcp.jurisdigta.eu/MCP",
    )
    legacy_authenticated_search = _mcp_call(
        "searchLaws",
        {"query": "civil"},
        headers={"authorization": f"Bearer {legacy_mcp_key}"},
    )
    assert legacy_authenticated_search.status_code == 200

    text_response = _mcp_call(
        "getLawText",
        {"document_id": "doc-1"},
        headers={"x-mcp-api-key": mcp_key},
    )
    assert text_response.status_code == 200
    assert _tool_payload(text_response)["content_text"] == "Civil code full text."


def test_mcp_internal_secret_allows_api_to_call_protected_tools(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    _create_laws_db(tmp_path / "laws.sqlite3")

    unauthenticated_response = _mcp_call("getStatistics")
    assert unauthenticated_response.status_code == 401

    internal_response = _mcp_call(
        "getStatistics",
        {"country_code": "SK"},
        headers={"X-JurisDigta-Internal-MCP-Secret": "test-mcp-secret"},
    )

    assert internal_response.status_code == 200
    payload = _tool_payload(internal_response)
    assert payload["processed_laws"] == 1
    assert payload["last_processed_law"] == "1/1993"


def test_mcp_court_decision_tools_require_auth() -> None:
    unauthenticated_legal_sources = _mcp_call(
        "searchLegalSources",
        {"query": "prenajom bytu", "published_year": 2026},
        path="/MCP",
    )
    assert unauthenticated_legal_sources.status_code == 401

    unauthenticated_search = _mcp_call("searchCourtDecisions", {"query": "najomna zmluva"})
    assert unauthenticated_search.status_code == 401

    unauthenticated_detail = _mcp_call("getCourtDecision", {"decision_id": "decision-1"})
    assert unauthenticated_detail.status_code == 401


def test_mcp_search_legal_sources_returns_grouped_metadata_only(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    db_path = tmp_path / "laws.sqlite3"
    _create_laws_db(db_path)
    mcp_key = _create_mcp_key(tmp_path)
    _insert_law_search_fixture(
        db_path,
        document_id="doc-10-2026",
        version_id="ver-10-2026",
        metadata_id="meta-10-2026",
        artifact_id="artifact-10-2026",
        law_year=2026,
        law_number=10,
        official_name="Zakon o prenajme bytu",
        lawyer_title="Prenajom bytu",
        law_identifier_text="10/2026 Z. z.",
        title="Zakon o prenajme bytu",
        content_text="Konsolidovane znenie o prenajme bytu.",
    )

    class FakeCourtDecisionStore:
        def search_coverage(self) -> dict[str, object]:
            return {
                "published_decisions": 2,
                "enriched_versions": 1,
                "enrichment": {"published": 2, "ready": 1, "queued": 1},
            }

        def search(
            self,
            *,
            query: str,
            limit: int,
            offset: int,
            published_year: int | None,
            year_filter_mode: str,
            court_type: str,
            court_name: str,
            sort: str = "relevance",
        ) -> list[CourtDecisionSearchResult]:
            assert query == "prenajom bytu"
            assert limit == 2
            assert offset == 0
            assert published_year == 2026
            assert year_filter_mode == "published_in"
            assert court_type == ""
            assert sort == "relevance"
            return [
                CourtDecisionSearchResult(
                    decision_id="decision-lease-2026",
                    version_id="version-lease-2026",
                    source_guid="infosud-lease-2026",
                    court_name="Okresny sud Bratislava I",
                    court_type="Okresny sud",
                    file_number="12C/10/2026",
                    case_number="12C/10/2026",
                    ecli="ECLI:SK:OSBA1:2026:10.1",
                    issue_date="2026-02-03",
                    source_url="https://example.test/decision/lease-2026",
                    snippet="Pseudonymizovany text o prenajme bytu.",
                    score=0.88,
                )
            ]

    monkeypatch.setattr(mcp_api, "_court_decision_store", lambda **_kwargs: FakeCourtDecisionStore())

    response = _mcp_call(
        "searchLegalSources",
        {"query": "prenajom bytu", "published_year": 2026, "limit_per_source": 2},
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert response.status_code == 200
    payload = _tool_payload(response)
    assert payload["status"] == "ok"
    assert payload["year_filter_mode"] == "published_in"
    assert payload["published_year"] == 2026
    assert payload["laws"][0]["document_id"] == "doc-10-2026"
    assert payload["laws"][0]["law_year"] == 2026
    assert payload["court_decisions"][0]["decision_id"] == "decision-lease-2026"
    assert "snippet" not in payload["court_decisions"][0]
    assert "content_text" not in payload["laws"][0]


def test_mcp_search_court_decisions_returns_bounded_results_and_privacy_safe_logs(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)

    class FakeCourtDecisionStore:
        def search_coverage(self) -> dict[str, object]:
            return {
                "published_decisions": 2,
                "enriched_versions": 1,
                "enrichment": {"published": 2, "ready": 1, "queued": 1},
            }

        def search(
            self,
            *,
            query: str,
            limit: int,
            offset: int,
            published_year: int | None,
            year_filter_mode: str,
            court_type: str,
            court_name: str,
            sort: str = "relevance",
        ) -> list[CourtDecisionSearchResult]:
            assert query == "zobraz mi posledne sudne rozhodnutie ktore sa tykalo rozdelenia pozemku podla podielu"
            assert limit == 1
            assert offset == 0
            assert published_year == 2026
            assert year_filter_mode == "published_in"
            assert court_type == "Okresny sud"
            assert sort == "relevance"
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
                    summary="Sud posudzoval sposob rozdelenia pozemku medzi spoluvlastnikov.",
                    enrichment_status="ready",
                    content_source="enrichment",
                )
            ]

    def fake_court_decision_store(**kwargs: object) -> FakeCourtDecisionStore:
        assert kwargs["initialize"] is False
        assert kwargs["connect_timeout_seconds"] == 3
        assert kwargs["statement_timeout_ms"] == 600000
        return FakeCourtDecisionStore()

    monkeypatch.setattr(mcp_api, "_court_decision_store", fake_court_decision_store)
    caplog.set_level(logging.INFO, logger="aijuristiction-api.mcp")
    secret_query = "zobraz mi posledne sudne rozhodnutie ktore sa tykalo rozdelenia pozemku podla podielu"

    response = _mcp_call(
        "searchCourtDecisions",
        {
            "query": secret_query,
            "limit": 1,
            "published_year": 2026,
            "court_type": "Okresny sud",
        },
        headers={"authorization": f"Bearer {mcp_key}", "x-request-id": "court-search-request"},
    )

    assert response.status_code == 200
    payload = _tool_payload(response)
    assert payload["status"] == "ok"
    assert payload["output_mode"] == "public"
    assert payload["metadata_only"] is True
    assert payload["timeout_ms"] == 600000
    assert payload["content_coverage_status"] == "partial"
    assert payload["content_unavailable"] is False
    assert "unenriched decisions may contain additional matches" in payload["coverage_notice"]
    assert payload["coverage"]["enrichment"]["ready"] == 1
    assert payload["results"][0]["decision_id"] == "decision-1"
    assert payload["results"][0]["issue_date"] == "2026-06-29"
    assert "snippet" not in payload["results"][0]
    snippet_response = _mcp_call(
        "searchCourtDecisions",
        {
            "query": secret_query,
            "limit": 1,
            "published_year": 2026,
            "court_type": "Okresny sud",
            "include_snippets": True,
        },
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    snippet_payload = _tool_payload(snippet_response)
    assert snippet_payload["metadata_only"] is False
    assert "Pseudonymizovane rozhodnutie" in snippet_payload["results"][0]["snippet"]
    summary_response = _mcp_call(
        "searchCourtDecisions",
        {
            "query": secret_query,
            "limit": 1,
            "published_year": 2026,
            "court_type": "Okresny sud",
            "include_summaries": True,
        },
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    summary_payload = _tool_payload(summary_response)
    assert summary_payload["metadata_only"] is False
    assert summary_payload["results"][0]["summary_status"] == "available"
    assert "spoluvlastnikov" in summary_payload["results"][0]["summary"]
    mcp_log_messages = [
        record.getMessage() for record in caplog.records if record.name == "aijuristiction-api.mcp"
    ]
    assert any("mcp_tool_search_court_decisions_result result_count=1" in message for message in mcp_log_messages)
    joined_logs = "\n".join(mcp_log_messages)
    assert secret_query not in joined_logs
    assert "Pseudonymizovane rozhodnutie" not in joined_logs
    assert mcp_key not in joined_logs


def test_mcp_search_court_decisions_latest_sort_passes_contract(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)

    class FakeCourtDecisionStore:
        def search(
            self,
            *,
            query: str,
            limit: int,
            offset: int,
            published_year: int | None,
            year_filter_mode: str,
            court_type: str,
            court_name: str,
            sort: str = "relevance",
        ) -> list[CourtDecisionSearchResult]:
            assert query == "podnajom"
            assert limit == 2
            assert offset == 0
            assert published_year is None
            assert year_filter_mode == "published_in"
            assert court_type == ""
            assert sort == "latest"
            return [
                CourtDecisionSearchResult(
                    decision_id="decision-newer",
                    version_id="version-newer",
                    source_guid="infosud-newer",
                    court_name="Krajsky sud Bratislava",
                    court_type="Krajsky sud",
                    file_number="8Co/10/2026",
                    case_number="8Co/10/2026",
                    ecli="ECLI:SK:KSBA:2026:10.1",
                    issue_date="2026-06-01",
                    source_url="https://example.test/decision/newer",
                    snippet="Pseudonymizovane rozhodnutie k podnajmu.",
                    score=0.7,
                ),
                CourtDecisionSearchResult(
                    decision_id="decision-older",
                    version_id="version-older",
                    source_guid="infosud-older",
                    court_name="Okresny sud Bratislava I",
                    court_type="Okresny sud",
                    file_number="12C/10/2025",
                    case_number="12C/10/2025",
                    ecli="ECLI:SK:OSBA1:2025:10.1",
                    issue_date="2025-05-01",
                    source_url="https://example.test/decision/older",
                    snippet="Pseudonymizovane rozhodnutie k podnajmu.",
                    score=0.9,
                ),
            ]

    monkeypatch.setattr(mcp_api, "_court_decision_store", lambda **_kwargs: FakeCourtDecisionStore())

    response = _mcp_call(
        "searchCourtDecisions",
        {"query": "podnajom", "limit": 2, "sort": "latest"},
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert response.status_code == 200
    payload = _tool_payload(response)
    assert payload["status"] == "ok"
    assert payload["sort"] == "latest"
    assert payload["timeout_ms"] == 600000
    assert [item["decision_id"] for item in payload["results"]] == ["decision-newer", "decision-older"]
    assert payload["data_quality"]["issue_date_ordering"] == "calendar"
    assert payload["data_quality"]["latest_label_safe"] is True


def test_mcp_search_court_decisions_passes_exact_court_name(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)

    class FakeCourtDecisionStore:
        def search(self, **arguments: object) -> list[CourtDecisionSearchResult]:
            assert arguments["court_name"] == "Okresny sud Poprad"
            assert arguments["sort"] == "latest"
            return [
                CourtDecisionSearchResult(
                    decision_id="poprad-1",
                    version_id="poprad-version-1",
                    source_guid="infosud-poprad-1",
                    court_name="Okresny sud Poprad",
                    court_type="Okresny sud",
                    file_number="20C/444/2012",
                    case_number="8712209850",
                    ecli="ECLI:SK:OSPP:2012:8712209850.3",
                    issue_date="31.12.2012",
                    source_url="https://example.test/decision/poprad-1",
                    snippet="",
                    score=0.8,
                )
            ]

    monkeypatch.setattr(mcp_api, "_court_decision_store", lambda **_kwargs: FakeCourtDecisionStore())
    response = _mcp_call(
        "searchCourtDecisions",
        {
            "query": "sudne rozhodnutia",
            "court_name": "Okresny sud Poprad",
            "sort": "latest",
            "limit": 5,
        },
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    payload = _tool_payload(response)
    assert payload["status"] == "ok"
    assert payload["court_name"] == "Okresny sud Poprad"
    assert [item["court_name"] for item in payload["results"]] == ["Okresny sud Poprad"]
    assert payload["data_quality"]["exact_court_filter_applied"] is True


def test_mcp_search_court_decisions_accepts_date_desc_sort_alias(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)

    class FakeCourtDecisionStore:
        def search(
            self,
            *,
            query: str,
            limit: int,
            offset: int,
            published_year: int | None,
            year_filter_mode: str,
            court_type: str,
            court_name: str,
            sort: str = "relevance",
        ) -> list[CourtDecisionSearchResult]:
            assert sort == "latest"
            return [
                CourtDecisionSearchResult(
                    decision_id="decision-latest",
                    version_id="version-latest",
                    source_guid="infosud-latest",
                    court_name="Najvyssi sud SR",
                    court_type="Najvyssi sud",
                    file_number="1Cdo/10/2026",
                    case_number="1Cdo/10/2026",
                    ecli="ECLI:SK:NSSR:2026:10.1",
                    issue_date="2026-06-30",
                    source_url="https://example.test/decision/latest",
                    snippet="Pseudonymizovane rozhodnutie k podnajmu.",
                    score=0.8,
                )
            ]

    monkeypatch.setattr(mcp_api, "_court_decision_store", lambda **_kwargs: FakeCourtDecisionStore())

    response = _mcp_call(
        "searchCourtDecisions",
        {"query": "podnajom", "limit": 1, "sort": "date_desc"},
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert response.status_code == 200
    payload = _tool_payload(response)
    assert payload["status"] == "ok"
    assert payload["sort"] == "latest"
    assert payload["results"][0]["decision_id"] == "decision-latest"


def test_mcp_search_legal_sources_passes_latest_sort_to_court_decisions(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)

    class FakeCourtDecisionStore:
        def search(
            self,
            *,
            query: str,
            limit: int,
            offset: int,
            published_year: int | None,
            year_filter_mode: str,
            court_type: str,
            court_name: str,
            sort: str = "relevance",
        ) -> list[CourtDecisionSearchResult]:
            assert query == "podnajom"
            assert limit == 1
            assert offset == 0
            assert published_year is None
            assert year_filter_mode == "published_in"
            assert court_type == ""
            assert sort == "latest"
            return [
                CourtDecisionSearchResult(
                    decision_id="decision-latest",
                    version_id="version-latest",
                    source_guid="infosud-latest",
                    court_name="Najvyssi sud SR",
                    court_type="Najvyssi sud",
                    file_number="1Cdo/10/2026",
                    case_number="1Cdo/10/2026",
                    ecli="ECLI:SK:NSSR:2026:10.1",
                    issue_date="2026-06-30",
                    source_url="https://example.test/decision/latest",
                    snippet="Pseudonymizovane rozhodnutie k podnajmu.",
                    score=0.8,
                )
            ]

    monkeypatch.setattr(mcp_api, "_court_decision_store", lambda **_kwargs: FakeCourtDecisionStore())

    response = _mcp_call(
        "searchLegalSources",
        {
            "query": "podnajom",
            "source_types": ["court_decisions"],
            "limit_per_source": 1,
            "sort": "latest",
        },
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert response.status_code == 200
    payload = _tool_payload(response)
    assert payload["status"] == "ok"
    assert payload["sort"] == "latest"
    assert payload["laws"] == []
    assert payload["court_decisions"][0]["decision_id"] == "decision-latest"


def test_mcp_async_legal_search_lifecycle_is_user_scoped(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    db_path = tmp_path / "laws.sqlite3"
    _create_laws_db(db_path)
    mcp_key = _create_mcp_key(tmp_path)
    other_key = _create_mcp_key(
        tmp_path,
        email="other-mcp-search@example.com",
        phone_number="+421 900 111 229",
    )

    start_response = _mcp_call(
        "startLegalSearch",
        {
            "tool_name": "searchLaws",
            "arguments": {"query": "civil", "limit": 1, "sort": "latest"},
        },
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert start_response.status_code == 200
    start_payload = _tool_payload(start_response)
    search_id = start_payload["search_id"]
    assert start_payload["status"] == "running"
    assert start_payload["timeout_ms"] == 30000

    status_response = _mcp_call(
        "getLegalSearchStatus",
        {"search_id": search_id},
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    result_response = None
    result_payload: dict[str, object] = {}
    for _ in range(20):
        result_response = _mcp_call(
            "getLegalSearchResult",
            {"search_id": search_id},
            headers={"authorization": f"Bearer {mcp_key}"},
        )
        result_payload = _tool_payload(result_response)
        if result_payload["status"] == "completed":
            break
        time.sleep(0.05)
    other_user_response = _mcp_call(
        "getLegalSearchResult",
        {"search_id": search_id},
        headers={"authorization": f"Bearer {other_key}"},
    )

    assert status_response.status_code == 200
    assert _tool_payload(status_response)["status"] in {"running", "completed"}
    assert result_response is not None
    assert result_response.status_code == 200
    assert result_payload["status"] == "completed"
    assert result_payload["result"]["results"][0]["document_id"] == "doc-1"
    assert result_payload["result"]["sort"] == "latest"
    assert other_user_response.status_code == 200
    assert other_user_response.json()["error"]["message"] == "Legal search job not found or expired"


def test_mcp_async_court_decision_failure_preserves_tool_and_arguments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)

    def fail_async_search(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        assert tool_name == "searchCourtDecisions"
        assert arguments == {"query": "podnajom", "limit": 1, "sort": "latest"}
        raise TimeoutError("statement timeout")

    monkeypatch.setattr(mcp_api, "_run_async_legal_search", fail_async_search)

    start_response = _mcp_call(
        "startLegalSearch",
        {
            "tool_name": "searchCourtDecisions",
            "arguments": {"query": "podnajom", "limit": 1, "sort": "date_desc"},
        },
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    assert start_response.status_code == 200
    search_id = _tool_payload(start_response)["search_id"]

    result_payload: dict[str, object] = {}
    for _ in range(20):
        result_response = _mcp_call(
            "getLegalSearchResult",
            {"search_id": search_id},
            headers={"authorization": f"Bearer {mcp_key}"},
        )
        assert result_response.status_code == 200
        result_payload = _tool_payload(result_response)
        if result_payload["status"] != "running":
            break
        time.sleep(0.05)

    result = result_payload["result"]
    assert isinstance(result, dict)
    assert result_payload["status"] == "degraded"
    assert result["tool_name"] == "searchCourtDecisions"
    assert result["query"] == "podnajom"
    assert "assistant_next_step" not in result
    async_fallback = result["async_fallback"]
    assert isinstance(async_fallback, dict)
    assert "assistant_instruction" not in async_fallback
    assert async_fallback["start_arguments"] == {
        "tool_name": "searchCourtDecisions",
        "arguments": {"query": "podnajom", "limit": 1, "sort": "latest"},
    }


def test_mcp_get_court_decision_defaults_to_metadata_only(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)

    class FakeCourtDecisionStore:
        def get_decision(self, *, decision_id: str, raw: bool = False) -> dict[str, object] | None:
            assert decision_id == "decision-1"
            assert raw is False
            return {
                "decision_id": "decision-1",
                "version_id": "version-1",
                "source_guid": "infosud-1",
                "court_name": "Okresny sud Bratislava I",
                "court_type": "Okresny sud",
                "file_number": "12C/34/2026",
                "case_number": "12C/34/2026",
                "ecli": "ECLI:SK:OSBA1:2026:1234567890.1",
                "issue_date": "2026-06-29",
                "source_url": "https://example.test/decision/1",
                "output_mode": "public",
                "text": "Pseudonymizovane plne znenie rozhodnutia o prenajme bytu.",
            }

    monkeypatch.setattr(mcp_api, "_court_decision_store", lambda **_kwargs: FakeCourtDecisionStore())

    metadata_response = _mcp_call(
        "getCourtDecision",
        {"decision_id": "decision-1"},
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    full_response = _mcp_call(
        "getCourtDecision",
        {"decision_id": "decision-1", "fullversion": True, "max_chars": 20},
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert metadata_response.status_code == 200
    metadata_payload = _tool_payload(metadata_response)
    assert metadata_payload["metadata_only"] is True
    assert metadata_payload["full_version"] is False
    assert "text" not in metadata_payload

    assert full_response.status_code == 200
    full_payload = _tool_payload(full_response)
    assert full_payload["metadata_only"] is False
    assert full_payload["full_version"] is True
    assert full_payload["text"] == "Pseudonymizovane pln"
    assert full_payload["content_truncated"] is True


def test_mcp_search_court_decisions_timeout_returns_structured_degraded_result(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    mcp_key = _create_mcp_key(tmp_path)

    class TimeoutCourtDecisionStore:
        def search(
            self,
            *,
            query: str,
            limit: int,
            offset: int,
            published_year: int | None,
            year_filter_mode: str,
            court_type: str,
            court_name: str,
            sort: str = "relevance",
        ) -> list[CourtDecisionSearchResult]:
            assert sort == "relevance"
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
    assert "assistant_next_step" not in payload
    assert payload["async_fallback"]["requires_user_confirmation"] is True
    assert "assistant_instruction" not in payload["async_fallback"]
    assert payload["async_fallback"]["start_tool"] == "startLegalSearch"
    assert payload["async_fallback"]["start_arguments"] == {
        "tool_name": "searchCourtDecisions",
        "arguments": {
            "query": "zobraz mi posledne sudne rozhodnutie ktore sa tykalo rozdelenia pozemku podla podielu",
            "limit": 5,
            "offset": 0,
            "year_filter_mode": "published_in",
            "sort": "relevance",
            "include_snippets": False,
        },
    }
    assert payload["async_fallback"]["poll_tool"] == "getLegalSearchStatus"
    assert payload["async_fallback"]["result_tool"] == "getLegalSearchResult"
    assert payload["timeout_ms"] == 600000
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


def test_mcp_search_laws_supports_published_year_metadata_filter(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    db_path = tmp_path / "laws.sqlite3"
    _create_laws_db(db_path)
    mcp_key = _create_mcp_key(tmp_path)
    _insert_law_search_fixture(
        db_path,
        document_id="doc-lease-2025",
        version_id="ver-lease-2025",
        metadata_id="meta-lease-2025",
        artifact_id="artifact-lease-2025",
        law_year=2025,
        law_number=30,
        official_name="Zakon o prenajme bytu 2025",
        lawyer_title="Prenajom bytu",
        law_identifier_text="30/2025 Z. z.",
        title="Prenajom bytu",
        content_text="Starsi zakon o prenajme bytu.",
    )
    _insert_law_search_fixture(
        db_path,
        document_id="doc-lease-2026",
        version_id="ver-lease-2026",
        metadata_id="meta-lease-2026",
        artifact_id="artifact-lease-2026",
        law_year=2026,
        law_number=11,
        official_name="Zakon o prenajme bytu 2026",
        lawyer_title="Prenajom bytu",
        law_identifier_text="11/2026 Z. z.",
        title="Prenajom bytu",
        content_text="Aktualne konsolidovane znenie o prenajme bytu.",
    )

    response = _mcp_call(
        "searchLaws",
        {"query": "prenajom bytu", "published_year": 2026},
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert response.status_code == 200
    payload = _tool_payload(response)
    assert payload["metadata_only"] is True
    assert payload["published_year"] == 2026
    assert [result["document_id"] for result in payload["results"]] == ["doc-lease-2026"]
    assert "content_text" not in payload["results"][0]


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


def test_mcp_search_laws_finds_legal_basis_from_natural_language_scenario(
    monkeypatch, tmp_path: Path
) -> None:
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
        official_name="Občiansky zákonník",
        lawyer_title="Občiansky zákonník",
        law_identifier_text="40/1964 Zb.",
        title="Občiansky zákonník",
        content_text="Flattened source without paragraph markers.",
        source_url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1964/40/",
        provisions=(
            (
                "paragraf-46.odsek-1.text",
                "Písomná forma",
                "Písomnú formu musia mať zmluvy o prevodoch nehnuteľností.",
            ),
            (
                "paragraf-133.odsek-2.text",
                "Nadobudnutie vlastníctva",
                "Ak sa prevádza nehnuteľná vec na základe zmluvy, vlastníctvo sa "
                "nadobúda vkladom do katastra nehnuteľností.",
            ),
            (
                "paragraf-588.odsek-1.text",
                "Kúpna zmluva",
                "Z kúpnej zmluvy vznikne predávajúcemu povinnosť predmet "
                "kupujúcemu odovzdať a kupujúcemu povinnosť zaplatiť cenu.",
            ),
            (
                "paragraf-600.odsek-1.text",
                "Vedľajšie dojednania",
                "Zmluvné strany môžu dohodnúť vedľajšie dojednania pri kúpe.",
            ),
        ),
    )
    _insert_law_search_fixture(
        db_path,
        document_id="doc-162-1995",
        version_id="ver-162-1995",
        metadata_id="meta-162-1995",
        artifact_id="artifact-162-1995",
        law_year=1995,
        law_number=162,
        official_name="Katastrálny zákon",
        lawyer_title="Zákon o katastri nehnuteľností",
        law_identifier_text="162/1995 Z. z.",
        title="Katastrálny zákon",
        content_text="Flattened source without paragraph markers.",
        source_url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1995/162/",
        provisions=(
            (
                "paragraf-28.odsek-1.text",
                "Vklad",
                "Práva k nehnuteľnostiam zo zmlúv sa zapisujú do katastra vkladom.",
            ),
            (
                "paragraf-31.odsek-1.text",
                "Konanie o návrhu na vklad",
                "Okresný úrad preskúma zmluvu z hľadiska oprávnenia previesť "
                "nehnuteľnosť a určitosti prejavov vôle.",
            ),
            (
                "paragraf-42.odsek-2.text",
                "Spôsobilosť listín",
                "Zmluva musí označiť účastníkov a nehnuteľnosť podľa katastrálneho územia a parcely.",
            ),
        ),
    )
    _insert_law_search_fixture(
        db_path,
        document_id="doc-89-2016",
        version_id="ver-89-2016",
        metadata_id="meta-89-2016",
        artifact_id="artifact-89-2016",
        law_year=2016,
        law_number=89,
        official_name="Zákon o výrobe a predaji tabakových výrobkov",
        lawyer_title="Tabakové výrobky",
        law_identifier_text="89/2016 Z. z.",
        title="Predaj tabakových výrobkov",
        content_text="Predaj tabakových výrobkov.",
        provisions=(("paragraf-10.odsek-1.text", "Predaj", "Predaj tabakových výrobkov."),),
    )

    payload = None
    for query in (
        "chcem kupno predajnu zmluvu na zahradu",
        "kúpna zmluva na záhradu",
        "kúpno-predajná zmluva na pozemok",
        "predaj záhrady",
        "kupna zmluva zahrada",
    ):
        response = _mcp_call(
            "searchLaws",
            {"query": query, "limit": 5},
            headers={"authorization": f"Bearer {mcp_key}"},
        )

        assert response.status_code == 200
        payload = _tool_payload(response)
        assert payload["retrieval_mode"] == "provision_aware"
        assert payload["metadata_only"] is False
        assert payload["query_concepts"] == ["purchase_contract", "real_estate"]
        assert payload["human_review_required"] is True
        assert {result["law_identifier_text"] for result in payload["results"][:2]} == {
            "40/1964 Zb.",
            "162/1995 Z. z.",
        }

    assert payload is not None
    results = payload["results"]
    civil_code = next(result for result in results if result["law_identifier_text"] == "40/1964 Zb.")
    cadastral_act = next(
        result for result in results if result["law_identifier_text"] == "162/1995 Z. z."
    )
    assert {46, 133, 588}.issubset(civil_code["relevant_sections"])
    assert {28, 31, 42}.issubset(cadastral_act["relevant_sections"])
    assert all(result["retrieval_basis"] == "law_provisions" for result in results[:2])
    assert civil_code["source_url"].endswith("/SK/ZZ/1964/40/")
    assert cadastral_act["source_url"].endswith("/SK/ZZ/1995/162/")
    exact_identifier = _mcp_call(
        "searchLaws",
        {"query": "162/1995", "law_year": 1995, "law_number": 162},
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    assert exact_identifier.status_code == 200
    assert [result["law_identifier_text"] for result in _tool_payload(exact_identifier)["results"]] == [
        "162/1995 Z. z."
    ]


def test_mcp_get_law_text_uses_structured_provisions_and_paragraph_filter(
    monkeypatch, tmp_path: Path
) -> None:
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
        official_name="Občiansky zákonník",
        lawyer_title="Občiansky zákonník",
        law_identifier_text="40/1964 Zb.",
        title="Občiansky zákonník",
        content_text="Flattened text has no section symbols.",
        provisions=(
            ("paragraf-46.odsek-1.text", "", "Zmluva o prevode nehnuteľnosti musí byť písomná."),
            ("paragraf-133.odsek-1.text", "Vlastníctvo", "Hnuteľná vec sa nadobúda prevzatím."),
            (
                "paragraf-133.odsek-2.text",
                "Vlastníctvo",
                "Vlastníctvo k nehnuteľnosti sa nadobúda vkladom do katastra.",
            ),
            ("paragraf-588.odsek-1.text", "Kúpna zmluva", "Kupujúci zaplatí dohodnutú cenu."),
            ("paragraf-600.odsek-1.text", "Dojednania", "Strany sa môžu dohodnúť."),
        ),
    )

    paragraph_response = _mcp_call(
        "getLawText",
        {"document_id": "doc-40-1964", "section_number": 133, "paragraph_number": 2},
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    range_response = _mcp_call(
        "getLawText",
        {"document_id": "doc-40-1964", "section_start": 588, "section_end": 600},
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    written_form_response = _mcp_call(
        "getLawText",
        {"document_id": "doc-40-1964", "section_number": 46},
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert paragraph_response.status_code == 200
    paragraph = _tool_payload(paragraph_response)
    assert paragraph["section_source"] == "law_provisions"
    assert paragraph["matched_provision_anchors"] == ["paragraf-133.odsek-2.text"]
    assert "(2) Vlastníctvo k nehnuteľnosti" in paragraph["content_text"]
    assert "Hnuteľná vec" not in paragraph["content_text"]
    assert range_response.status_code == 200
    section_range = _tool_payload(range_response)
    assert section_range["section_source"] == "law_provisions"
    assert "§ 588" in section_range["content_text"]
    assert "§ 600" in section_range["content_text"]
    assert written_form_response.status_code == 200
    written_form = _tool_payload(written_form_response)
    assert written_form["section_found"] is True
    assert "§ 46" in written_form["content_text"]


def test_mcp_get_law_text_returns_cadastral_section_ranges(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    db_path = tmp_path / "laws.sqlite3"
    _create_laws_db(db_path)
    mcp_key = _create_mcp_key(tmp_path)
    _insert_law_search_fixture(
        db_path,
        document_id="doc-162-1995",
        version_id="ver-162-1995",
        metadata_id="meta-162-1995",
        artifact_id="artifact-162-1995",
        law_year=1995,
        law_number=162,
        official_name="Katastrálny zákon",
        lawyer_title="Katastrálny zákon",
        law_identifier_text="162/1995 Z. z.",
        title="Katastrálny zákon",
        content_text="Flattened text has no section symbols.",
        provisions=(
            ("paragraf-28.odsek-1.text", "", "Práva sa zapisujú vkladom."),
            ("paragraf-29.odsek-1.text", "", "Vklad sa vykoná na základe rozhodnutia."),
            ("paragraf-30.odsek-1.text", "", "Konanie sa začína na návrh."),
            ("paragraf-31.odsek-1.text", "", "Okresný úrad preskúma zmluvu."),
            ("paragraf-42.odsek-1.text", "", "Listina musí byť písomne vyhotovená."),
        ),
    )

    registration = _mcp_call(
        "getLawText",
        {"document_id": "doc-162-1995", "section_start": 28, "section_end": 31},
        headers={"authorization": f"Bearer {mcp_key}"},
    )
    document_form = _mcp_call(
        "getLawText",
        {"document_id": "doc-162-1995", "section_number": 42},
        headers={"authorization": f"Bearer {mcp_key}"},
    )

    assert registration.status_code == 200
    registration_payload = _tool_payload(registration)
    assert registration_payload["section_found"] is True
    assert registration_payload["section_source"] == "law_provisions"
    assert all(f"§ {section}" in registration_payload["content_text"] for section in range(28, 32))
    assert document_form.status_code == 200
    document_payload = _tool_payload(document_form)
    assert document_payload["section_found"] is True
    assert "§ 42" in document_payload["content_text"]


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
        "/mcp?code=secret-code&state=public-state",
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

    assert response.status_code == 401
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


def test_mcp_wire_logging_redacts_legal_queries_and_tool_text() -> None:
    redacted = _redact_payload(
        {
            "params": {
                "arguments": {"query": "synthetic legal scenario", "document_id": "doc-public"}
            },
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '{"snippet":"public provision body","document_id":"doc-public"}',
                    }
                ]
            },
        }
    )

    assert redacted["params"]["arguments"]["query"] == "[redacted]"
    assert redacted["params"]["arguments"]["document_id"] == "[redacted]"
    assert redacted["result"]["content"][0]["text"] == "[redacted]"


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

    page_response = mcp_client.get("/mcp/login")
    assert page_response.status_code == 200
    assert "JurisDigta MCP" in page_response.text
    assert "auth-shell" in page_response.text
    assert "Send OTP code" in page_response.text
    assert "AIJurisdiction MCP Login" not in page_response.text

    login_response = mcp_client.post(
        "/mcp/login",
        data={"email": "mcp-login@example.com", "password": "secret-pass"},
    )
    assert login_response.status_code == 200
    assert "Verify MCP login" in login_response.text

    verify_response = mcp_client.post(
        "/mcp/login/verify",
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
        "/mcp/login",
        data={"email": "mcp-login-warning@example.com", "password": "secret-pass"},
        headers={"accept-language": "sk-SK,sk;q=0.9,en;q=0.8"},
    )
    assert login_response.status_code == 200
    assert '<html lang="sk">' in login_response.text
    assert "Overenie MCP prihlasenia" in login_response.text

    verify_response = mcp_client.post(
        "/mcp/login/verify",
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
        "/mcp/login",
        data={"email": "mcp-totp@example.com", "password": "secret-pass", "expires_in_days": "1"},
    )
    assert login_response.status_code == 200
    assert "Choose MFA method" in login_response.text
    assert 'option value="email"' in login_response.text
    assert 'option value="totp"' in login_response.text

    method_response = mcp_client.post(
        "/mcp/login/mfa",
        data={"email": "mcp-totp@example.com", "mfa_method": "totp", "expires_in_days": "1"},
    )
    assert method_response.status_code == 200
    assert "Authenticator code" in method_response.text

    verify_response = mcp_client.post(
        "/mcp/login/verify",
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

    page_response = mcp_client.get("/mcp/sign-up")
    assert page_response.status_code == 200
    assert "JurisDigta MCP" in page_response.text
    assert "auth-shell" in page_response.text
    assert "ID card number" in page_response.text
    assert "AIJurisdiction MCP Sign up" not in page_response.text

    send_code_response = mcp_client.post(
        "/mcp/sign-up",
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
        "/mcp/sign-up/verify",
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

    page_response = mcp_client.get("/mcp/sign-up", headers={"accept-language": "sk"})
    assert page_response.status_code == 200
    assert '<html lang="sk">' in page_response.text
    assert "Cislo obcianskeho preukazu" in page_response.text

    send_code_response = mcp_client.post(
        "/mcp/sign-up",
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
        "/mcp/sign-up/verify",
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


def test_oauth_discovery_and_authorization_code_flow(monkeypatch, tmp_path: Path, caplog) -> None:
    _configure_env(monkeypatch, tmp_path)
    _create_laws_db(tmp_path / "laws.sqlite3")
    caplog.set_level(logging.INFO, logger="aijuristiction-api.mcp")
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

    protected_metadata = mcp_client.get("/.well-known/oauth-protected-resource/mcp")
    assert protected_metadata.status_code == 200
    assert protected_metadata.json()["resource"].endswith("/MCP")
    assert protected_metadata.json()["resource_name"] == "JurisDigta MCP"
    assert protected_metadata.json()["scopes_supported"] == ["mcp:laws"]
    claude_web_protected_metadata = mcp_client.get(
        "/.well-known/oauth-protected-resource/mcp",
        headers={"user-agent": "python-httpx/0.28.1", "mcp-protocol-version": "2025-11-25"},
    )
    assert claude_web_protected_metadata.status_code == 200
    claude_web_root_protected_metadata = mcp_client.get(
        "/.well-known/oauth-protected-resource",
        headers={"user-agent": "python-httpx/0.28.1", "mcp-protocol-version": "2025-11-25"},
    )
    assert claude_web_root_protected_metadata.status_code == 200
    claude_web_root_authorization_metadata = mcp_client.get(
        "/.well-known/oauth-authorization-server",
        headers={"user-agent": "python-httpx/0.28.1", "mcp-protocol-version": "2025-11-25"},
    )
    assert claude_web_root_authorization_metadata.status_code == 200
    claude_web_authorization_metadata_without_protocol_header = mcp_client.get(
        "/.well-known/oauth-authorization-server",
        headers={"user-agent": "python-httpx/0.28.1"},
    )
    assert claude_web_authorization_metadata_without_protocol_header.status_code == 200
    assert claude_web_authorization_metadata_without_protocol_header.json()["registration_endpoint"].endswith(
        "/oauth/register"
    )
    assert (
        claude_web_authorization_metadata_without_protocol_header.json()[
            "authorization_response_iss_parameter_supported"
        ]
        is True
    )
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
    authorization_metadata = mcp_client.get("/.well-known/oauth-authorization-server")
    assert authorization_metadata.status_code == 200
    assert authorization_metadata.json()["code_challenge_methods_supported"] == ["S256"]
    assert authorization_metadata.json()["grant_types_supported"] == ["authorization_code", "refresh_token"]
    assert authorization_metadata.json()["scopes_supported"] == ["mcp:laws", "offline_access"]
    assert authorization_metadata.json()["registration_endpoint"].endswith("/oauth/register")
    assert "client_id_metadata_document_supported" not in authorization_metadata.json()
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

    smartidentity_style_registration = mcp_client.post(
        "/oauth/register",
        json={
            "client_name": "Claude SmartIdentity-style Connector",
            "redirect_uris": [
                "https://claude.ai/api/mcp/auth_callback",
                "https://vscode.dev/redirect",
                "https://www.perplexity.ai/rest/connections/oauth_callback",
                "http://localhost:5100/oauth/callback",
            ],
            "grant_types": ["authorization_code", "client_credentials"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp:laws offline_access",
        },
    )
    assert smartidentity_style_registration.status_code == 201
    smartidentity_style_payload = smartidentity_style_registration.json()
    assert smartidentity_style_payload["client_id"].startswith("jurisdigta-")
    assert smartidentity_style_payload["grant_types"] == ["authorization_code"]
    assert smartidentity_style_payload["redirect_uris"] == [
        "https://claude.ai/api/mcp/auth_callback",
        "https://vscode.dev/redirect",
        "https://www.perplexity.ai/rest/connections/oauth_callback",
        "http://localhost:5100/oauth/callback",
    ]

    client_credentials_only_registration = mcp_client.post(
        "/oauth/register",
        json={
            "client_name": "Machine-only client",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "grant_types": ["client_credentials"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    assert client_credentials_only_registration.status_code == 400
    assert client_credentials_only_registration.json()["detail"] == "authorization_code grant is required"

    client_credentials_token = mcp_client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": smartidentity_style_payload["client_id"],
        },
    )
    assert client_credentials_token.status_code == 400
    assert client_credentials_token.json()["detail"] == "Unsupported grant_type"

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

    vscode_challenge = _mcp_call(
        "searchLaws",
        {"query": "civil"},
        headers={"user-agent": "Visual Studio Code MCP client"},
    )
    assert vscode_challenge.status_code == 401
    assert (
        'resource_metadata="https://mcp.jurisdigta.eu/.well-known/oauth-protected-resource/mcp"'
        in vscode_challenge.headers["www-authenticate"]
    )

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
    resource = "https://mcp.jurisdigta.eu/mcp"
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

    claude_root_authorize_page = mcp_client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "pkce",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "claude-state",
        },
    )
    assert claude_root_authorize_page.status_code == 200
    assert "Authorize MCP access" in claude_root_authorize_page.text
    assert _extract_hidden_value(claude_root_authorize_page.text, "resource") == "https://mcp.jurisdigta.eu/MCP"

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
    assert token_payload["scope"] == "mcp:laws"
    assert "refresh_token" not in token_payload
    access_claims = _jwt_claims(token_payload["access_token"])
    assert access_claims["sub"] == sign_up_response.json()["user_id"]
    assert access_claims["aud"] == "https://mcp.jurisdigta.eu/MCP"
    assert access_claims["iss"] == "https://mcp.jurisdigta.eu"
    assert access_claims["scope"] == "mcp:laws"
    assert access_claims["token_use"] == "access"
    assert isinstance(access_claims["iat"], int)
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

    claude_code_verifier = "claude-code-verifier-1234567890"
    claude_code_challenge = _pkce_challenge(claude_code_verifier)
    claude_authorize_page = mcp_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "https://claude.ai/oauth/mcp-oauth-client-metadata",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "code_challenge": claude_code_challenge,
            "code_challenge_method": "S256",
            "state": "claude-refresh",
            "resource": "https://mcp.jurisdigta.eu/MCP",
            "scope": "mcp:laws offline_access",
        },
    )
    assert claude_authorize_page.status_code == 200
    assert _extract_hidden_value(claude_authorize_page.text, "scope") == "mcp:laws offline_access"
    claude_login_response = mcp_client.post(
        "/oauth/authorize/login",
        data={
            "response_type": "code",
            "client_id": "https://claude.ai/oauth/mcp-oauth-client-metadata",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "code_challenge": claude_code_challenge,
            "code_challenge_method": "S256",
            "state": "claude-refresh",
            "resource": "https://mcp.jurisdigta.eu/MCP",
            "scope": "mcp:laws offline_access",
            "email": "mcp-oauth@example.com",
            "password": "secret-pass",
        },
        follow_redirects=False,
    )
    assert claude_login_response.status_code == 303
    claude_callback_query = parse_qs(urlparse(claude_login_response.headers["location"]).query)
    assert claude_callback_query["state"] == ["claude-refresh"]
    claude_token_response = mcp_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": claude_callback_query["code"][0],
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": "https://claude.ai/oauth/mcp-oauth-client-metadata",
            "code_verifier": claude_code_verifier,
            "resource": "https://mcp.jurisdigta.eu/MCP",
        },
    )
    assert claude_token_response.status_code == 200
    claude_token_payload = claude_token_response.json()
    assert claude_token_payload["scope"] == "mcp:laws"
    assert claude_token_payload["token_type"] == "Bearer"
    assert "refresh_token" in claude_token_payload
    claude_access_claims = _jwt_claims(claude_token_payload["access_token"])
    assert claude_access_claims["aud"] == "https://mcp.jurisdigta.eu/MCP"
    assert claude_access_claims["scope"] == "mcp:laws"

    refresh_token_response = mcp_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": "https://claude.ai/oauth/mcp-oauth-client-metadata",
            "refresh_token": claude_token_payload["refresh_token"],
            "resource": "https://mcp.jurisdigta.eu/MCP",
        },
    )
    assert refresh_token_response.status_code == 200
    refresh_token_payload = refresh_token_response.json()
    assert refresh_token_payload["scope"] == "mcp:laws"
    assert "refresh_token" in refresh_token_payload
    refreshed_access_claims = _jwt_claims(refresh_token_payload["access_token"])
    assert refreshed_access_claims["aud"] == "https://mcp.jurisdigta.eu/MCP"
    assert refreshed_access_claims["scope"] == "mcp:laws"

    mcp_log_text = "\n".join(
        record.getMessage() for record in caplog.records if record.name == "aijuristiction-api.mcp"
    )
    assert "mcp_oauth_protected_resource_metadata_served" in mcp_log_text
    assert "mcp_oauth_authorization_server_metadata_served" in mcp_log_text
    assert "mcp_oauth_authorize_started" in mcp_log_text
    assert "mcp_oauth_authorize_succeeded" in mcp_log_text
    assert "mcp_oauth_token_started grant_type=authorization_code" in mcp_log_text
    assert "mcp_oauth_token_succeeded grant_type=authorization_code" in mcp_log_text
    assert "redirect_host=client.example redirect_path=/callback" in mcp_log_text
    assert "token_audience=https://mcp.jurisdigta.eu/MCP" in mcp_log_text
    assert "mcp_auth_succeeded token_type=jwt" in mcp_log_text
    assert "secret-pass" not in mcp_log_text
    assert "mcp-oauth@example.com" not in mcp_log_text
    assert code_verifier not in mcp_log_text
    assert authorization_code not in mcp_log_text
    assert token_payload["access_token"] not in mcp_log_text
    assert claude_token_payload["access_token"] not in mcp_log_text
    assert claude_token_payload["refresh_token"] not in mcp_log_text
    assert refresh_token_payload["access_token"] not in mcp_log_text
    assert refresh_token_payload["refresh_token"] not in mcp_log_text
    assert "refresh_token" not in token_payload


def test_vscode_mcp_json_uppercase_endpoint_can_complete_oauth_without_static_headers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _create_laws_db(tmp_path / "laws.sqlite3")
    monkeypatch.setenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "true")
    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421 900 111 231",
            "email": "mcp-vscode@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201

    initialize_response = mcp_client.post(
        "/MCP",
        headers={"user-agent": "Visual Studio Code MCP client"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "Visual Studio Code", "version": "1"},
            },
        },
    )
    assert initialize_response.status_code == 401
    assert (
        'resource_metadata="https://mcp.jurisdigta.eu/.well-known/oauth-protected-resource/MCP"'
        in initialize_response.headers["www-authenticate"]
    )

    protected_metadata = mcp_client.get(
        "/.well-known/oauth-protected-resource/MCP",
        headers={"user-agent": "Visual Studio Code MCP client"},
    )
    assert protected_metadata.status_code == 200
    assert protected_metadata.json()["resource"] == "https://mcp.jurisdigta.eu/MCP"
    assert protected_metadata.json()["authorization_servers"] == ["https://mcp.jurisdigta.eu"]

    registration_response = mcp_client.post(
        "/oauth/register",
        headers={"user-agent": "Visual Studio Code MCP client"},
        json={
            "client_name": "Visual Studio Code",
            "redirect_uris": [
                "vscode://vscode.github-authentication/did-authenticate",
                "vscode-insiders://vscode.github-authentication/did-authenticate",
                "https://vscode.dev/redirect",
                "http://127.0.0.1:6274/callback",
            ],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp:laws offline_access",
        },
    )
    assert registration_response.status_code == 201
    registration_payload = registration_response.json()
    assert registration_payload["client_id"].startswith("jurisdigta-")
    assert registration_payload["token_endpoint_auth_method"] == "none"

    code_verifier = "test-code-verifier-vscode-1234567890"
    code_challenge = _pkce_challenge(code_verifier)
    redirect_uri = "vscode://vscode.github-authentication/did-authenticate"
    authorize_page = mcp_client.get(
        "/oauth/authorize",
        headers={"user-agent": "Visual Studio Code MCP client"},
        params={
            "response_type": "code",
            "client_id": registration_payload["client_id"],
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "vscode-state",
        },
    )
    assert authorize_page.status_code == 200
    assert _extract_hidden_value(authorize_page.text, "resource") == "https://mcp.jurisdigta.eu/MCP"

    login_response = mcp_client.post(
        "/oauth/authorize/login",
        headers={"user-agent": "Visual Studio Code MCP client"},
        data={
            "response_type": "code",
            "client_id": registration_payload["client_id"],
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "vscode-state",
            "resource": "https://mcp.jurisdigta.eu/MCP",
            "email": "mcp-vscode@example.com",
            "password": "secret-pass",
        },
    )
    assert login_response.status_code == 200

    verify_response = mcp_client.post(
        "/oauth/authorize/verify",
        headers={"user-agent": "Visual Studio Code MCP client"},
        data={
            "response_type": "code",
            "client_id": registration_payload["client_id"],
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "vscode-state",
            "resource": "https://mcp.jurisdigta.eu/MCP",
            "email": "mcp-vscode@example.com",
            "verification_code": "123456",
        },
        follow_redirects=False,
    )
    assert verify_response.status_code == 303
    callback_query = parse_qs(urlparse(verify_response.headers["location"]).query)
    assert callback_query["state"] == ["vscode-state"]
    assert callback_query["iss"] == ["https://mcp.jurisdigta.eu"]

    token_response = mcp_client.post(
        "/oauth/token",
        headers={"user-agent": "Visual Studio Code MCP client"},
        data={
            "grant_type": "authorization_code",
            "code": callback_query["code"][0],
            "redirect_uri": redirect_uri,
            "client_id": registration_payload["client_id"],
            "code_verifier": code_verifier,
        },
    )
    assert token_response.status_code == 200
    token_payload = token_response.json()
    access_claims = _jwt_claims(token_payload["access_token"])
    assert access_claims["aud"] == "https://mcp.jurisdigta.eu/MCP"
    assert access_claims["scope"] == "mcp:laws"

    authenticated_initialize = mcp_client.post(
        "/MCP",
        headers={
            "authorization": f"Bearer {token_payload['access_token']}",
            "user-agent": "Visual Studio Code MCP client",
        },
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "Visual Studio Code", "version": "1"},
            },
        },
    )
    assert authenticated_initialize.status_code == 200
    assert authenticated_initialize.json()["result"]["protocolVersion"] == "2025-11-25"

    protected_search = _mcp_call(
        "searchLaws",
        {"query": "civil"},
        path="/MCP",
        headers={
            "authorization": f"Bearer {token_payload['access_token']}",
            "user-agent": "Visual Studio Code MCP client",
        },
    )
    assert protected_search.status_code == 200
    assert _tool_payload(protected_search)["results"][0]["document_id"] == "doc-1"


def test_oauth_mfa_bypass_is_limited_to_synthetic_e2e_users(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    caplog.set_level(logging.INFO, logger="aijuristiction-api.mcp")
    monkeypatch.setenv("MCP_OAUTH_TEST_MFA_BYPASS_ENABLED", "true")
    monkeypatch.setenv(
        "MCP_OAUTH_TEST_MFA_BYPASS_EMAILS",
        f"{E2E_TEST_FREE_EMAIL},{E2E_TEST_PAID_EMAIL},real-user@example.com",
    )
    monkeypatch.setenv("MCP_OAUTH_TEST_MFA_BYPASS_EXPIRES_AT", "2030-01-01T00:00:00Z")
    store = ApiDatabaseStore.from_env()
    store.initialize()
    provisioned = provision_e2e_test_users(store=store, password="test-secret-pass")
    assert [user.plan_code for user in provisioned] == ["free", "case"]
    real_user = store.create_user(
        email="real-user@example.com",
        password="test-secret-pass",
        full_name="Real User",
    )

    code_verifier = "test-code-verifier-bypass-1234567890"
    code_challenge = _pkce_challenge(code_verifier)
    bypass_response = mcp_client.post(
        "/oauth/authorize/login",
        data={
            "response_type": "code",
            "client_id": "claude",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "bypass-ok",
            "resource": "https://mcp.jurisdigta.eu/MCP",
            "email": E2E_TEST_FREE_EMAIL,
            "password": "test-secret-pass",
        },
        follow_redirects=False,
    )
    assert bypass_response.status_code == 303
    assert bypass_response.headers["location"].startswith("https://claude.ai/api/mcp/auth_callback?")
    assert "state=bypass-ok" in bypass_response.headers["location"]

    real_user_response = mcp_client.post(
        "/oauth/authorize/login",
        data={
            "response_type": "code",
            "client_id": "claude",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "bypass-deny",
            "resource": "https://mcp.jurisdigta.eu/MCP",
            "email": real_user.email,
            "password": "test-secret-pass",
        },
    )
    assert real_user_response.status_code == 200
    assert "Verify MCP OAuth login" in real_user_response.text

    mcp_log_text = "\n".join(
        record.getMessage() for record in caplog.records if record.name == "aijuristiction-api.mcp"
    )
    assert "mcp_oauth_test_mfa_bypass_used" in mcp_log_text
    assert E2E_TEST_FREE_EMAIL not in mcp_log_text
    assert "test-secret-pass" not in mcp_log_text


def test_claude_oauth_without_resource_uses_uppercase_mcp_audience(monkeypatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "true")
    client_id = "https://claude.ai/oauth/mcp-oauth-client-metadata"
    redirect_uri = "https://claude.ai/api/mcp/auth_callback"
    monkeypatch.setattr(
        "app.mcp_api._fetch_client_id_metadata_document",
        lambda fetched_client_id: {
            "client_id": fetched_client_id,
            "client_name": "Claude",
            "redirect_uris": [redirect_uri],
        },
    )
    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421 900 111 239",
            "email": "mcp-claude-oauth@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201

    code_verifier = "test-code-verifier-claude-1234567890"
    code_challenge = _pkce_challenge(code_verifier)
    authorize_page = mcp_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "claude-no-resource",
            "scope": "mcp:laws offline_access",
            "prompt": "consent",
        },
    )
    assert authorize_page.status_code == 200
    selected_resource = _extract_hidden_value(authorize_page.text, "resource")
    assert selected_resource == "https://mcp.jurisdigta.eu/MCP"

    verify_response = mcp_client.post(
        "/oauth/authorize/verify",
        data={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "claude-no-resource",
            "resource": selected_resource,
            "email": "mcp-claude-oauth@example.com",
            "verification_code": "123456",
        },
        follow_redirects=False,
    )
    assert verify_response.status_code == 303
    callback_query = parse_qs(urlparse(verify_response.headers["location"]).query)
    authorization_code = callback_query["code"][0]

    token_response = mcp_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
        },
    )
    assert token_response.status_code == 200
    token_payload = token_response.json()
    assert token_payload["scope"] == "mcp:laws"
    access_claims = _jwt_claims(token_payload["access_token"])
    assert access_claims["aud"] == "https://mcp.jurisdigta.eu/MCP"
    assert access_claims["scope"] == "mcp:laws"
    assert "refresh_token" not in token_payload


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
        "/.well-known/oauth-protected-resource/mcp",
        headers={"x-forwarded-proto": "http", "x-forwarded-host": "internal.local"},
    )
    authorization_metadata = mcp_client.get(
        "/.well-known/oauth-authorization-server",
        headers={"x-forwarded-proto": "http", "x-forwarded-host": "internal.local"},
    )
    mcp_path_authorization_metadata = mcp_client.get(
        "/.well-known/oauth-authorization-server/mcp",
        headers={"x-forwarded-proto": "http", "x-forwarded-host": "internal.local"},
    )
    legacy_mcp_protected_metadata = mcp_client.get(
        "/.well-known/oauth-protected-resource/MCP",
        headers={"x-forwarded-proto": "http", "x-forwarded-host": "internal.local"},
    )
    legacy_mcp_authorization_metadata = mcp_client.get(
        "/.well-known/oauth-authorization-server/MCP",
        headers={"x-forwarded-proto": "http", "x-forwarded-host": "internal.local"},
    )

    assert protected_metadata.status_code == 200
    assert protected_metadata.json()["resource"] == "https://mcp.jurisdigta.eu/MCP"
    assert protected_metadata.json()["authorization_servers"] == ["https://mcp.jurisdigta.eu"]
    assert legacy_mcp_protected_metadata.status_code == 200
    assert legacy_mcp_protected_metadata.json()["resource"] == "https://mcp.jurisdigta.eu/MCP"
    assert legacy_mcp_protected_metadata.json()["authorization_servers"] == ["https://mcp.jurisdigta.eu"]
    assert authorization_metadata.status_code == 200
    assert authorization_metadata.json()["issuer"] == "https://mcp.jurisdigta.eu"
    assert authorization_metadata.json()["token_endpoint"] == "https://mcp.jurisdigta.eu/oauth/token"
    assert authorization_metadata.json()["registration_endpoint"] == "https://mcp.jurisdigta.eu/oauth/register"
    assert "client_id_metadata_document_supported" not in authorization_metadata.json()
    assert authorization_metadata.json()["protected_resources"] == ["https://mcp.jurisdigta.eu/MCP"]
    assert mcp_path_authorization_metadata.status_code == 200
    assert mcp_path_authorization_metadata.json() == authorization_metadata.json()
    assert legacy_mcp_authorization_metadata.status_code == 200
    assert legacy_mcp_authorization_metadata.json() == authorization_metadata.json()


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
            "resource": "https://mcp.jurisdigta.eu/mcp",
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
            "resource": "https://mcp.jurisdigta.eu/mcp",
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
    monkeypatch.setenv("EMAIL_TRANSPORT", "log")
    monkeypatch.setenv("EMAIL_SENDER", "noreply@example.test")
    monkeypatch.setenv("EMAIL_SMTP_PORT", "587")
    monkeypatch.setenv("EMAIL_SMTP_USE_TLS", "true")
    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "laws.sqlite3"))
    monkeypatch.setenv("MCP_API_JWT_SECRET", "test-mcp-secret")
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "https://mcp.jurisdigta.eu")
    monkeypatch.setenv(
        "MCP_OAUTH_ALLOWED_REDIRECT_HOSTS",
        "client.example,chatgpt.com,claude.ai,vscode.dev,www.perplexity.ai,localhost,127.0.0.1,::1",
    )


def _create_mcp_key(
    tmp_path: Path,
    *,
    email: str = "mcp-search@example.com",
    phone_number: str = "+421 900 111 228",
) -> str:
    sign_up_response = api_client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": phone_number,
            "email": email,
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
    path: str = "/mcp",
):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }
    return mcp_client.post(path, json=payload, headers=headers or {})


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
            CREATE TABLE law_provisions (
                provision_id TEXT PRIMARY KEY,
                version_id TEXT NOT NULL,
                anchor TEXT NOT NULL,
                heading TEXT NOT NULL,
                body_text TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                created_at TEXT NOT NULL
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
    provisions: tuple[tuple[str, str, str], ...] = (),
    source_url: str | None = None,
) -> None:
    resolved_source_url = source_url or f"https://example.test/laws/{law_year}/{law_number}"
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
                resolved_source_url,
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
                resolved_source_url,
                "local_file",
                "ignored",
                content_text,
                "2026-06-01T12:00:00Z",
            ),
        )
        for ordinal, (anchor, heading, body_text) in enumerate(provisions):
            conn.execute(
                """
                INSERT INTO law_provisions(
                    provision_id, version_id, anchor, heading, body_text, ordinal, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{version_id}-provision-{ordinal}",
                    version_id,
                    anchor,
                    heading,
                    body_text,
                    ordinal,
                    "2026-06-01T12:00:00Z",
                ),
            )
        conn.commit()
