from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    skills_root = repo_root / "skills"
    skill_names = sorted(
        child.name for child in skills_root.iterdir() if child.is_dir() and (child / "SKILL.md").exists()
    )

    print("Repo-local Codex skills:")
    for name in skill_names:
        print(f"- {name}")

    print("\nDry-run sync preview:\n")
    sync_script = repo_root / "scripts" / "sync_codex_skills.py"
    result = subprocess.run(
        [sys.executable, str(sync_script), "--dry-run"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
