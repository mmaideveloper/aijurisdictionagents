from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_endpoint() -> None:
    response = client.get("/version")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "aijuristiction-api"
    assert payload["version"] == payload["api_version"]
    assert payload["api_version"] != "unknown"
    assert isinstance(payload["core_version"], str)


def test_swagger_docs_available() -> None:
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_contains_api_key_security_scheme() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    components = response.json().get("components", {})
    security_schemes = components.get("securitySchemes", {})
    assert "APIKeyHeader" in security_schemes


def test_request_and_correlation_ids_are_echoed() -> None:
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


def test_request_id_is_used_as_correlation_id_fallback() -> None:
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
