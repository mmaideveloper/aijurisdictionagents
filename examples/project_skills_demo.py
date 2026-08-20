from __future__ import annotations

import subprocess
import sys
import json
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
    if result.returncode:
        return result.returncode

    lock_path = repo_root / "architecture" / "toolkit.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    print("\nPinned AI Architect Toolkit:")
    print(f"- repository: {lock['repository']}")
    print(f"- commit: {lock['resolved_commit']}")
    for skill in lock["skills"]:
        print(f"- skill: {skill}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
