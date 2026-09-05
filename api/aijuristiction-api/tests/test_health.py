import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

import app.main as app_main
from app.main import app
from app.versioning import get_mobile_app_version


client = TestClient(app)


class _HealthyStore:
    db_option = "local"

    def check_connection(self) -> None:
        return None


class _UnhealthyStore:
    db_option = "azure"

    def check_connection(self) -> None:
        raise RuntimeError(
            "password authentication failed for postgresql://user:secret-token@example/db"
        )


class _StartupStore:
    db_option = "local"
    db_cloud = ""
    uses_postgres = False

    def initialize(self) -> None:
        return None


class _StartupWorkflowStore:
    def purge_expired_debug_events(self) -> int:
        return 0


def _startup_workflow_service() -> SimpleNamespace:
    return SimpleNamespace(store=_StartupWorkflowStore())


def _startup_law_snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        last_law_update_date=None,
        last_law_update_source=None,
        last_collector_run_at=None,
        last_processed_law=None,
    )


def test_startup_runs_enabled_internal_mcp_probe_after_existing_initialization(monkeypatch) -> None:
    calls: list[tuple[str, int | None]] = []

    def load_workflow_service() -> SimpleNamespace:
        calls.append(("workflow", None))
        return _startup_workflow_service()

    monkeypatch.setattr(app_main.ApiDatabaseStore, "from_env", lambda: _StartupStore())
    monkeypatch.setattr(app_main, "get_case_workflow_service", load_workflow_service)
    monkeypatch.setattr(app_main, "get_law_knowledge_snapshot", lambda _country: _startup_law_snapshot())
    monkeypatch.setattr(
        "app.chat.mcp_law_context.probe_internal_mcp_readiness",
        lambda *, attempts=None: calls.append(("probe", attempts)),
    )
    monkeypatch.setenv("INTERNAL_MCP_STARTUP_PROBE_ENABLED", "true")
    monkeypatch.setenv("INTERNAL_MCP_STARTUP_PROBE_ATTEMPTS", "4")

    asyncio.run(app_main.startup_log())

    assert calls == [("workflow", None), ("probe", 4)]


def test_startup_fails_closed_when_internal_mcp_probe_fails(monkeypatch) -> None:
    from app.chat.mcp_law_context import InternalMcpUnavailableError

    monkeypatch.setattr(app_main.ApiDatabaseStore, "from_env", lambda: _StartupStore())
    monkeypatch.setattr(app_main, "get_case_workflow_service", _startup_workflow_service)
    monkeypatch.setattr(app_main, "get_law_knowledge_snapshot", lambda _country: _startup_law_snapshot())
    monkeypatch.setattr(
        "app.chat.mcp_law_context.probe_internal_mcp_readiness",
        lambda *, attempts=None: (_ for _ in ()).throw(
            InternalMcpUnavailableError(category="connectivity", attempts=attempts or 0)
        ),
    )
    monkeypatch.setenv("INTERNAL_MCP_STARTUP_PROBE_ENABLED", "true")
    monkeypatch.setenv("INTERNAL_MCP_STARTUP_PROBE_ATTEMPTS", "2")

    with pytest.raises(InternalMcpUnavailableError) as exc_info:
        asyncio.run(app_main.startup_log())

    assert exc_info.value.category == "connectivity"
    assert exc_info.value.attempts == 2


def test_health_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("app.main.ApiDatabaseStore.from_env", lambda: _HealthyStore())
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "aijuristiction-api",
        "llm": {
            "status": "ok",
            "provider": "mock",
        },
        "database": {
            "status": "ok",
            "backend": "local",
        },
    }


def test_health_endpoint_reports_model_routing_when_legacy_llm_provider_is_set(monkeypatch) -> None:
    monkeypatch.setattr("app.main.ApiDatabaseStore.from_env", lambda: _HealthyStore())
    monkeypatch.setenv("LLM_PROVIDER", "azure")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["llm"] == {
        "status": "ok",
        "provider": "model_routing",
    }


def test_health_endpoint_reports_database_failure(monkeypatch) -> None:
    monkeypatch.setattr("app.main.ApiDatabaseStore.from_env", lambda: _UnhealthyStore())
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    response = client.get("/health")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"] == "database_unavailable"
    assert payload["service"] == "aijuristiction-api"
    assert payload["message"] == 'Database health check failed for backend "azure".'
    assert "secret-token" not in response.text
    assert "postgresql://" not in response.text
    assert "password authentication failed" not in response.text
    assert payload["llm"] == {
        "status": "ok",
        "provider": "mock",
    }
    assert payload["database"] == {
        "status": "error",
        "backend": "azure",
    }


def test_health_endpoint_ignores_unsupported_legacy_llm_provider(monkeypatch) -> None:
    monkeypatch.setattr("app.main.ApiDatabaseStore.from_env", lambda: _HealthyStore())
    monkeypatch.setenv("LLM_PROVIDER", "custom-provider")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["llm"] == {
        "status": "ok",
        "provider": "model_routing",
    }


def test_version_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        app_main,
        "get_law_knowledge_snapshot",
        lambda country: SimpleNamespace(
            last_law_update_date="2026-03-21T00:00:00Z"
            if country == "SK"
            else "2026-03-20T00:00:00Z",
            last_law_update_source="law_documents_country"
            if country == "SK"
            else "law_documents_global",
            last_collector_run_at="2026-03-30T12:30:00Z (SK:slovlex)",
            last_processed_law="234/2026",
            model_knowledge_cutoff_date="2023-10-01",
            model_knowledge_cutoff_source="https://platform.openai.com/docs/models/gpt-4o-mini",
            reference_links=(
                "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/",
            ),
        ),
    )
    response = client.get("/version")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "aijuristiction-api"
    assert payload["version"] == payload["api_version"]
    assert payload["api_version"] != "unknown"
    assert payload["mcp_server_version"] == payload["api_version"]
    assert isinstance(payload["core_version"], str)
    assert payload["last_law_update_date"] == "2026-03-20T00:00:00Z"
    assert payload["last_law_update_source"] == "law_documents_global"
    assert payload["last_collector_run_at"] == "2026-03-30T12:30:00Z (SK:slovlex)"
    assert payload["last_processed_law"] == "234/2026"
    assert payload["model_knowledge_cutoff_date"] == "2023-10-01"
    assert (
        payload["model_knowledge_cutoff_source"]
        == "https://platform.openai.com/docs/models/gpt-4o-mini"
    )
    assert payload["law_reference_links"] == [
        "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/"
    ]
    assert payload["laws_by_country"]["sk"] == {
        "country_code": "SK",
        "last_law_update_date": "2026-03-21T00:00:00Z",
        "last_law_update_source": "law_documents_country",
        "last_collector_run_at": "2026-03-30T12:30:00Z (SK:slovlex)",
        "last_processed_law": "234/2026",
        "model_knowledge_cutoff_date": "2023-10-01",
        "model_knowledge_cutoff_source": "https://platform.openai.com/docs/models/gpt-4o-mini",
        "law_reference_links": [
            "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/"
        ],
    }
    assert payload["mobile_app_version"] == get_mobile_app_version()
    assert payload["mobile_app_release_url"] == (
        "https://github.com/mmaideveloper/aijurisdictionagents/releases/latest"
    )
    assert payload["mobile_app_apk_download_url"] == (
        "https://github.com/mmaideveloper/aijurisdictionagents/releases/latest/download/app-release.apk"
    )


def test_root_endpoint_renders_version_html(monkeypatch) -> None:
    monkeypatch.setattr(
        app_main,
        "get_law_knowledge_snapshot",
        lambda country: SimpleNamespace(
            last_law_update_date="2026-03-21T00:00:00Z"
            if country == "SK"
            else "2026-03-20T00:00:00Z",
            last_law_update_source="law_documents_country"
            if country == "SK"
            else "law_documents_global",
            last_collector_run_at="2026-03-30T12:30:00Z (SK:slovlex)",
            last_processed_law="234/2026",
            model_knowledge_cutoff_date="2023-10-01",
            model_knowledge_cutoff_source="https://platform.openai.com/docs/models/gpt-4o-mini",
            reference_links=(
                "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/",
            ),
        ),
    )
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "<h1>aijuristiction-api</h1>" in body
    assert f"API {app.version}" in body
    assert "JSON version output" in body
    assert "&quot;api_version&quot;" in body
    assert "&quot;last_law_update_date&quot;: &quot;2026-03-20T00:00:00Z&quot;" in body


def test_swagger_docs_available() -> None:
    response = client.get("/docs")
    assert response.status_code == 200


def test_public_api_does_not_mount_mcp() -> None:
    response = client.get("/mcp")
    assert response.status_code == 404


def test_openapi_contains_api_key_security_scheme() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    components = response.json().get("components", {})
    security_schemes = components.get("securitySchemes", {})
    assert "APIKeyHeader" in security_schemes


def test_request_and_correlation_ids_are_echoed(monkeypatch) -> None:
    monkeypatch.setattr("app.main.ApiDatabaseStore.from_env", lambda: _HealthyStore())
    response = client.get(
        "/health",
        headers={
            "x-request-id": "req-123",
            "x-correlation-id": "corr-456",
        },
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"
    assert response.headers["x-correlation-id"] == "corr-456"


def test_request_id_is_used_as_correlation_id_fallback(monkeypatch) -> None:
    monkeypatch.setattr("app.main.ApiDatabaseStore.from_env", lambda: _HealthyStore())
    response = client.get(
        "/health",
        headers={
            "x-request-id": "req-fallback-1",
        },
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-fallback-1"
    assert response.headers["x-correlation-id"] == "req-fallback-1"


def test_cors_preflight_allows_local_chat_simulator() -> None:
    response = client.options(
        "/v1/chat/sessions",
        headers={
            "Origin": "http://localhost:8090",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8090"


def test_cors_preflight_allows_production_agent_web() -> None:
    response = client.options(
        "/v1/users/sign-in",
        headers={
            "Origin": "https://agent.jurisdigta.eu",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key,content-type",
        },
    )
    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "https://agent.jurisdigta.eu"
    )


def test_cors_preflight_allows_flutter_web_localhost() -> None:
    response = client.options(
        "/v1/chat/sessions",
        headers={
            "Origin": "http://localhost:7357",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:7357"


def test_cors_preflight_allows_flutter_web_loopback_on_custom_port() -> None:
    response = client.options(
        "/v1/users/sign-in/phone",
        headers={
            "Origin": "http://127.0.0.1:7358",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:7358"


def test_cors_preflight_allows_loopback_ipv4_alias_on_custom_port() -> None:
    response = client.options(
        "/v1/users/sign-in/phone",
        headers={
            "Origin": "http://127.0.0.2:9001",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.2:9001"


def test_cors_preflight_allows_ipv6_loopback_on_custom_port() -> None:
    response = client.options(
        "/v1/users/sign-in/phone",
        headers={
            "Origin": "http://[::1]:7358",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://[::1]:7358"


def test_cors_preflight_allows_local_file_preview_contact_form() -> None:
    response = client.options(
        "/v1/contact",
        headers={
            "Origin": "null",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "null"
