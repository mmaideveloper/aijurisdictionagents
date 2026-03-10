from __future__ import annotations

import importlib
import sys
from pathlib import Path

import dotenv


def test_api_import_loads_repo_dotenv(monkeypatch) -> None:
    calls: list[tuple[Path | None, bool]] = []

    def fake_load_dotenv(
        dotenv_path: str | Path | None = None, override: bool = False
    ) -> bool:
        path = Path(dotenv_path) if dotenv_path is not None else None
        calls.append((path, override))
        return True

    monkeypatch.setattr(dotenv, "load_dotenv", fake_load_dotenv)
    sys.modules.pop("app.main", None)

    importlib.import_module("app.main")

    assert calls
    dotenv_path, override = calls[0]
    assert dotenv_path is not None
    assert dotenv_path.name == ".env"
    assert dotenv_path.parent.name == "aijurisdictionagents"
    assert override is False
