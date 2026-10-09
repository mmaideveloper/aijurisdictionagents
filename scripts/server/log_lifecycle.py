"""Atomic latest-log links and retention cleanup, confined to one log directory."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import time
import uuid


def publish_latest(log: Path, latest: Path) -> None:
    directory = latest.parent.resolve()
    target = log.resolve(strict=True)
    if target.parent != directory or not target.is_file() or log.is_symlink():
        raise ValueError("Latest target must be a regular file in the same log directory")
    if latest.exists() and not latest.is_symlink():
        raise ValueError("Refusing to replace a regular file with a latest alias")
    temporary = directory / f".{latest.name}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.symlink_to(target.name)
        os.replace(temporary, latest)
    finally:
        temporary.unlink(missing_ok=True)


def prune_logs(directory: Path, *, retention_days: int, now: float | None = None) -> int:
    if retention_days < 1:
        raise ValueError("retention_days must be positive")
    directory = directory.resolve(strict=True)
    cutoff = (time.time() if now is None else now) - retention_days * 86400
    files = [p for p in directory.glob("*.log") if not p.is_symlink() and p.is_file()]
    expired = {p for p in files if p.stat().st_mtime < cutoff}
    for alias in directory.glob("*-latest.log"):
        if not alias.is_symlink():
            continue
        target = alias.resolve()
        if target.parent == directory and target.is_file() and target not in expired:
            # Normalize legacy absolute links for the log-only container mount.
            publish_latest(target, alias)
            continue
        prefix = alias.name.removesuffix("latest.log")
        candidates = [p for p in files if p not in expired and p.name.startswith(prefix)]
        if candidates:
            publish_latest(max(candidates, key=lambda p: p.stat().st_mtime), alias)
        else:
            # Missing history is unavailable, never an empty placeholder success.
            alias.unlink()
    for path in expired:
        path.unlink(missing_ok=True)
    return len(expired)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    publish = actions.add_parser("publish")
    publish.add_argument("--log", type=Path, required=True)
    publish.add_argument("--latest", type=Path, required=True)
    prune = actions.add_parser("prune")
    prune.add_argument("--log-dir", type=Path, required=True)
    prune.add_argument("--retention-days", type=int, required=True)
    args = parser.parse_args()
    if args.action == "publish":
        publish_latest(args.log, args.latest)
    else:
        print(f"Expired logs removed: {prune_logs(args.log_dir, retention_days=args.retention_days)}")


if __name__ == "__main__":
    main()
