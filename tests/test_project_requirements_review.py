from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_requirements_review_fixture_plan(tmp_path: Path) -> None:
    script = Path("scripts") / "project_requirements_review.py"
    fixture = Path("examples") / "project_requirements_review_fixture.json"
    output = tmp_path / "requirements_review_plan.json"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--config",
            ".github/automation.yml",
            "--fixture",
            str(fixture),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["projects"]) == 3

    core = next(project for project in payload["projects"] if project["project_number"] == 5)
    assert len(core["actions"]) == 1
    action = core["actions"][0]
    assert action["issue_number"] == 101
    assert action["missing_marker"] == "codex - business requirements reviewed"
    assert action["requirement_gaps"] == ["Missing acceptance criteria."]
    assert action["body_needs_update"] is True
    assert "Added Acceptance criteria section." in action["body_fixes"]
    assert "## Acceptance criteria" in action["fixed_body_preview"]
