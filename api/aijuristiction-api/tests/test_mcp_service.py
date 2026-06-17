from fastapi.testclient import TestClient
from types import SimpleNamespace

import app.mcp_main as mcp_main
from app.mcp_main import app


client = TestClient(app)


class _HealthyStore:
    db_option = "local"

    def check_connection(self) -> None:
        return None


class _UnhealthyStore:
    db_option = "postgres"

    def check_connection(self) -> None:
        raise RuntimeError("connection refused")


def test_mcp_health_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("app.mcp_main.ApiDatabaseStore.from_env", lambda: _HealthyStore())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "jurisdigta-mcp-server",
        "database": {
            "status": "ok",
            "backend": "local",
        },
    }


def test_mcp_health_endpoint_reports_database_failure(monkeypatch) -> None:
    monkeypatch.setattr("app.mcp_main.ApiDatabaseStore.from_env", lambda: _UnhealthyStore())
    response = client.get("/health")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"] == "database_unavailable"
    assert "connection refused" in payload["message"]
    assert payload["database"] == {
        "status": "error",
        "backend": "postgres",
    }


def test_mcp_version_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_main,
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
    assert payload["service"] == "jurisdigta-mcp-server"
    assert payload["version"] == payload["api_version"]
    assert payload["mcp_server_version"] == payload["version"]
    assert payload["api_version"] != "unknown"
    assert payload["last_law_update_date"] == "2026-03-20T00:00:00Z"
    assert payload["laws_by_country"]["sk"]["last_law_update_date"] == "2026-03-21T00:00:00Z"


def test_mcp_request_and_correlation_ids_are_echoed(monkeypatch) -> None:
    monkeypatch.setattr("app.mcp_main.ApiDatabaseStore.from_env", lambda: _HealthyStore())
    response = client.get(
        "/health",
        headers={
            "x-request-id": "mcp-req-123",
            "x-correlation-id": "mcp-corr-456",
        },
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "mcp-req-123"
    assert response.headers["x-correlation-id"] == "mcp-corr-456"


def test_mcp_root_shows_assistant_setup_and_registration_steps() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "JurisDigta MCP server" in response.text
    assert "Registration" in response.text
    assert "/MCP/sign-up" in response.text
    assert "/MCP/login" in response.text
    assert "ChatGPT custom connector" in response.text
    assert "Claude" in response.text
    assert "VS Code" in response.text
    assert "Perplexity" in response.text
    assert "/.well-known/oauth-protected-resource/MCP" in response.text
    assert "Authorization: Bearer" in response.text


def test_mcp_root_localizes_for_slovak_browser() -> None:
    response = client.get("/", headers={"accept-language": "sk-SK,sk;q=0.9,en;q=0.8"})
    assert response.status_code == 200
    assert '<html lang="sk">' in response.text
    assert "Registracia" in response.text
    assert "Nastavenie asistenta" in response.text
    assert "Metadata autorizacneho servera" in response.text
    assert "/MCP/sign-up" in response.text
    assert "Authorization: Bearer" in response.text


def test_mcp_root_uses_forwarded_public_origin() -> None:
    response = client.get(
        "/",
        headers={
            "x-forwarded-proto": "https",
            "x-forwarded-host": "mcp.jurisdigta.eu",
        },
    )
    assert response.status_code == 200
    assert "https://mcp.jurisdigta.eu/MCP" in response.text
    assert "https://mcp.jurisdigta.eu/.well-known/oauth-authorization-server" in response.text
