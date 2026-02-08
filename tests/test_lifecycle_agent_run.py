from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_lifecycle_agent_run_solution_stage(tmp_path: Path) -> None:
    script = Path("scripts") / "lifecycle_agent_run.py"
    output = tmp_path / "solution.json"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--stage",
            "solution",
            "--project-name",
            "Demo",
            "--idea",
            "Build a fullstack support app.",
            "--project-type",
            "fullstack",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["succeeded"] is True
    assert payload["stages"][-1]["stage"] == "solution"
    assert payload["stages"][-1]["passed"] is True


def test_lifecycle_agent_run_requirements_failure(tmp_path: Path) -> None:
    script = Path("scripts") / "lifecycle_agent_run.py"
    output = tmp_path / "requirements.json"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--stage",
            "requirements",
            "--project-name",
            "Demo",
            "--idea",
            "Build a backend API.",
            "--project-type",
            "backend",
            "--technical-requirements",
            "quantum-resistant ledger mesh",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["succeeded"] is False
    assert payload["stages"][-1]["stage"] == "requirements"
    assert payload["stages"][-1]["passed"] is False
