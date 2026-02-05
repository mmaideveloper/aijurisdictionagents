from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_project_in_review_plan(tmp_path: Path) -> None:
    script = Path("scripts") / "project_in_review.py"
    fixture = Path("examples") / "project_poll_fixture.json"
    pr_fixture = Path("examples") / "project_pr_fixture.json"
    output = tmp_path / "plan.json"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--config",
            ".github/automation.yml",
            "--fixture",
            str(fixture),
            "--pr-fixture",
            str(pr_fixture),
            "--dry-run",
            "--plan-output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert len(plan["projects"]) == 3
    for entry in plan["projects"]:
        actions = entry["actions"]
        assert len(actions) == 1
        assert actions[0]["issue_number"] == 55
        assert actions[0]["pr_number"] == 101
