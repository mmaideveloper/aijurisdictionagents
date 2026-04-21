from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    script = Path("scripts") / "project_requirements_review.py"
    fixture = Path("examples") / "project_requirements_review_fixture.json"
    output = Path("runs") / "automation" / "example_requirements_review_plan.json"

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
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    print(f"Wrote requirements-review plan to {output}")


if __name__ == "__main__":
    main()
