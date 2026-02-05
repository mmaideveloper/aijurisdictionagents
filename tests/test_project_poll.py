from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_project_poll_fixture_snapshot(tmp_path: Path) -> None:
    script = Path("scripts") / "project_poll.py"
    fixture = Path("examples") / "project_poll_fixture.json"
    output = tmp_path / "snapshots"

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
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["summary"]["total"] == 6
    assert summary["summary"]["by_status"]["In progress"] == 3
    assert summary["summary"]["by_status"]["Ready"] == 3

    for project_number in (5, 6, 7):
        payload = json.loads(
            (output / f"project_{project_number}.json").read_text(encoding="utf-8")
        )
        assert payload["summary"]["total"] == 2
        assert payload["summary"]["by_status"]["In progress"] == 1
        assert payload["summary"]["by_status"]["Ready"] == 1
