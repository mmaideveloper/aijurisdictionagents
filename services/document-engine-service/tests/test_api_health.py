from fastapi.testclient import TestClient

from document_engine.api import app


client = TestClient(app)


class _BrokenEngine:
    def connect(self) -> "_BrokenEngine":
        raise RuntimeError("database password leaked in postgresql://user:secret@example/db")


def test_health_reports_database_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "document-engine-service",
        "database": {
            "status": "ok",
            "backend": "sqlite",
        },
    }


def test_health_sanitizes_database_failure(monkeypatch) -> None:
    monkeypatch.setattr("document_engine.api.engine", _BrokenEngine())

    response = client.get("/health")

    assert response.status_code == 503
    payload = response.json()
    assert payload == {
        "status": "error",
        "service": "document-engine-service",
        "error": "database_unavailable",
        "message": 'Database health check failed for backend "sqlite".',
        "database": {
            "status": "error",
            "backend": "sqlite",
        },
    }
    assert "secret" not in response.text
    assert "postgresql://" not in response.text
