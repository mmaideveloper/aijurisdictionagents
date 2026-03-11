from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def discover_skills(skills_root: Path) -> list[str]:
    names: list[str] = []
    for child in sorted(skills_root.iterdir()):
        if child.is_dir() and (child / "SKILL.md").exists():
            names.append(child.name)
    return names


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy repo-local Codex skills into the local ~/.codex/skills directory."
    )
    parser.add_argument(
        "--skills-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "skills",
        help="Path containing project skill folders.",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path.home() / ".codex" / "skills",
        help="Destination Codex skills directory.",
    )
    parser.add_argument(
        "--skill",
        action="append",
        dest="skills",
        help="Specific skill name to sync. Repeat for multiple skills.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing destination skill folders when present.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview copy operations without changing files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    skills_root = args.skills_root.resolve()
    destination = args.destination.expanduser().resolve()

    if not skills_root.exists():
        print(f"Skills root does not exist: {skills_root}", file=sys.stderr)
        return 1

    available = discover_skills(skills_root)
    requested = args.skills or available
    missing = [name for name in requested if name not in available]
    if missing:
        print(f"Unknown skills: {', '.join(missing)}", file=sys.stderr)
        print(f"Available skills: {', '.join(available)}", file=sys.stderr)
        return 1

    print(f"Source: {skills_root}")
    print(f"Destination: {destination}")
    print(f"Skills: {', '.join(requested)}")

    if args.dry_run:
        for name in requested:
            print(f"DRY RUN copy {skills_root / name} -> {destination / name}")
        return 0

    destination.mkdir(parents=True, exist_ok=True)

    for name in requested:
        source_dir = skills_root / name
        destination_dir = destination / name

        if destination_dir.exists():
            if not args.force:
                print(
                    f"Destination skill already exists, use --force to replace: {destination_dir}",
                    file=sys.stderr,
                )
                return 1
            shutil.rmtree(destination_dir)

        shutil.copytree(source_dir, destination_dir)
        print(f"Installed {name} -> {destination_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
