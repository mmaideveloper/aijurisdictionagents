from fastapi.testclient import TestClient
from types import SimpleNamespace

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
        raise RuntimeError("password authentication failed")


def test_health_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("app.main.ApiDatabaseStore.from_env", lambda: _HealthyStore())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": {
            "status": "ok",
            "backend": "local",
        },
    }


def test_health_endpoint_reports_database_failure(monkeypatch) -> None:
    monkeypatch.setattr("app.main.ApiDatabaseStore.from_env", lambda: _UnhealthyStore())
    response = client.get("/health")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"] == "database_unavailable"
    assert "password authentication failed" in payload["message"]
    assert payload["database"] == {
        "status": "error",
        "backend": "azure",
    }


def test_version_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.get_law_knowledge_snapshot",
        lambda _country: SimpleNamespace(
            last_law_update_date="2026-03-20T00:00:00Z",
            last_law_update_source="law_documents_global",
            model_knowledge_cutoff_date="2020-12-31",
            model_knowledge_cutoff_source="model_knowledge_cutoff_cache",
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
    assert isinstance(payload["core_version"], str)
    assert payload["last_law_update_date"] == "2026-03-20T00:00:00Z"
    assert payload["last_law_update_source"] == "law_documents_global"
    assert payload["model_knowledge_cutoff_date"] == "2020-12-31"
    assert payload["model_knowledge_cutoff_source"] == "model_knowledge_cutoff_cache"
    assert payload["law_reference_links"] == [
        "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/"
    ]
    assert payload["mobile_app_version"] == get_mobile_app_version()
    assert payload["mobile_app_release_url"] == (
        "https://github.com/mmaideveloper/aijurisdictionagents/releases/latest"
    )
    assert payload["mobile_app_apk_download_url"] == (
        "https://github.com/mmaideveloper/aijurisdictionagents/releases/latest/download/app-release.apk"
    )


def test_swagger_docs_available() -> None:
    response = client.get("/docs")
    assert response.status_code == 200


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
