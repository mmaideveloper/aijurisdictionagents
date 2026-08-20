"""Install the AI Architect Toolkit skills pinned by architecture/toolkit.lock.json."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "architecture" / "toolkit.lock.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Existing aiarchitecttoolkit checkout")
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path.home() / ".codex" / "skills",
        help="Codex skill destination",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_lock() -> dict[str, object]:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def resolve_source(args: argparse.Namespace, lock: dict[str, object], temporary: Path) -> Path:
    if args.source:
        source = args.source.expanduser().resolve()
    else:
        source = temporary / "aiarchitecttoolkit"
        subprocess.run(
            ["git", "clone", "--quiet", str(lock["repository"]), str(source)],
            check=True,
        )
    expected = str(lock["resolved_commit"])
    actual = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != expected:
        if args.source:
            raise SystemExit(f"Toolkit source is {actual}; expected pinned commit {expected}")
        subprocess.run(["git", "-C", str(source), "checkout", "--quiet", expected], check=True)
    return source


def main() -> int:
    args = parse_args()
    lock = load_lock()
    destination = args.destination.expanduser().resolve()
    with tempfile.TemporaryDirectory() as temporary_directory:
        source = resolve_source(args, lock, Path(temporary_directory))
        for skill in lock["skills"]:
            source_skill = source / "skills" / str(skill)
            target_skill = destination / str(skill)
            if not (source_skill / "SKILL.md").exists():
                raise SystemExit(f"Pinned toolkit is missing skill: {skill}")
            print(f"{'DRY RUN ' if args.dry_run else ''}{source_skill} -> {target_skill}")
            if args.dry_run:
                continue
            if target_skill.exists():
                if not args.force:
                    raise SystemExit(f"Destination exists; use --force: {target_skill}")
                shutil.rmtree(target_skill)
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_skill, target_skill)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
