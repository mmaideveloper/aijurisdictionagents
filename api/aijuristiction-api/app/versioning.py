from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

API_PACKAGE_NAME = "aijuristiction-api"
CORE_PACKAGE_NAME = "aijurisdictionagents"
UNKNOWN_VERSION = "unknown"


def get_api_version() -> str:
    installed = _get_installed_package_version(API_PACKAGE_NAME)
    if installed != UNKNOWN_VERSION:
        return installed

    source_version = _get_api_project_version()
    if source_version is not None:
        return source_version
    return UNKNOWN_VERSION


def get_core_version() -> str:
    installed = _get_installed_package_version(CORE_PACKAGE_NAME)
    if installed != UNKNOWN_VERSION:
        return installed

    source_version = _get_core_source_version()
    if source_version is not None:
        return source_version
    return UNKNOWN_VERSION


def _get_installed_package_version(package_name: str) -> str:
    try:
        return package_version(package_name)
    except PackageNotFoundError:
        return UNKNOWN_VERSION


def _get_core_source_version() -> str | None:
    init_file = (
        Path(__file__).resolve().parents[3] / "src" / "aijurisdictionagents" / "__init__.py"
    )
    if not init_file.exists():
        return None

    content = init_file.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    if match is None:
        return None
    return match.group(1)


def _get_api_project_version() -> str | None:
    pyproject_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if not pyproject_file.exists():
        return None

    content = pyproject_file.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', content)
    if match is None:
        return None
    return match.group(1)
