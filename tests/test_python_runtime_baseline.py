from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_PROJECTS = (
    REPO_ROOT / "pyproject.toml",
    REPO_ROOT / "api" / "aijuristiction-api" / "pyproject.toml",
    REPO_ROOT / "api" / "chat-simulator-app" / "pyproject.toml",
    REPO_ROOT / "services" / "document-engine-service" / "pyproject.toml",
)
PYTHON_DOCKERFILES = (
    REPO_ROOT / "api" / "aijuristiction-api" / "Dockerfile",
    REPO_ROOT / "src" / "services" / "laws_collector" / "Dockerfile",
    REPO_ROOT / "src" / "services" / "document_processor" / "Dockerfile",
    REPO_ROOT / "services" / "document-engine-service" / "Dockerfile",
)


def test_active_interpreter_meets_python_313_baseline() -> None:
    assert sys.version_info >= (3, 13)


def test_python_projects_require_python_313() -> None:
    for path in PYTHON_PROJECTS:
        with path.open("rb") as stream:
            metadata = tomllib.load(stream)
        assert metadata["project"]["requires-python"] == ">=3.13", path


def test_local_and_container_runtimes_use_python_313() -> None:
    assert (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.13"
    environment = (REPO_ROOT / "environment.yml").read_text(encoding="utf-8")
    assert "  - python=3.13\n" in environment.replace("\r\n", "\n")

    for path in PYTHON_DOCKERFILES:
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("FROM python:3.13-slim"), path

    monitoring = (REPO_ROOT / "Deployment" / "monitoring" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "python:3.10" not in monitoring
    assert "python:3.11" not in monitoring
    assert "python:3.12" not in monitoring


def test_api_container_pins_one_compatible_telemetry_family() -> None:
    dockerfile = (REPO_ROOT / "api" / "aijuristiction-api" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    expected_constraints = (
        "azure-monitor-opentelemetry==1.8.9",
        "azure-monitor-opentelemetry-exporter==1.0.0b56",
        "opentelemetry-api==1.43.0",
        "opentelemetry-sdk==1.43.0",
        "opentelemetry-exporter-otlp==1.43.0",
        "opentelemetry-instrumentation==0.64b0",
        "opentelemetry-instrumentation-fastapi==0.64b0",
        "opentelemetry-semantic-conventions==0.64b0",
    )

    for constraint in expected_constraints:
        assert constraint in dockerfile
    assert "opentelemetry-exporter-otlp==1.40.0" not in dockerfile


def test_github_workflows_use_python_313() -> None:
    workflow_dir = REPO_ROOT / ".github" / "workflows"
    declarations: list[tuple[Path, str]] = []
    for path in workflow_dir.glob("*.yml"):
        for version in re.findall(r"python-version:\s*[\"']?([^\"'\s]+)", path.read_text()):
            declarations.append((path, version))

    assert declarations
    assert all(version == "3.13" for _path, version in declarations), declarations
