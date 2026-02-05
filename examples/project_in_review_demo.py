from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    script = Path("scripts") / "project_in_review.py"
    fixture = Path("examples") / "project_poll_fixture.json"
    pr_fixture = Path("examples") / "project_pr_fixture.json"
    output = Path("runs") / "automation" / "example_in_review_plan.json"

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
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    print(f"Wrote in-review plan to {output}")


if __name__ == "__main__":
    main()
