from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.databases.apply_api_db_schema import _redacted_target


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_schema_target_redacts_password_and_query_parameters() -> None:
    target = _redacted_target(
        "postgresql://juris:private%40value@127.0.0.1:5432/branch_e2e?sslmode=require"
    )

    assert target == "postgresql://juris:***@127.0.0.1:5432/branch_e2e"
    assert "private" not in target


def test_reused_container_preserves_explicit_database_and_redacts_password() -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for launcher regression coverage")

    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-File",
            str(REPO_ROOT / "tests" / "powershell" / "start_postgres_reuse_test.ps1"),
            "-ScriptPath",
            str(
                REPO_ROOT
                / "skills"
                / "start-postgres"
                / "scripts"
                / "start_postgres.ps1"
            ),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "start_postgres reuse regression passed" in result.stdout
