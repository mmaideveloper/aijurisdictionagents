from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .github import GitHubClient, ProjectStatusUpdater
from .runner import DryRunRunner, SubprocessRunner
from .tasks import create_ready_tasks, load_task_specs
from ..observability import create_run_dir, setup_logging


def _configure_logging(log_level: str) -> tuple[Path, logging.Logger]:
    run_dir = create_run_dir(Path("runs") / "automation")
    logger = setup_logging(run_dir, log_level=log_level)
    logger.info("Automation run directory: %s", run_dir)
    return run_dir, logger


def _create_ready_command(args: argparse.Namespace) -> int:
    _, logger = _configure_logging(args.log_level)
    tasks = load_task_specs(args.file)
    runner = DryRunRunner() if args.dry_run else SubprocessRunner()
    github = GitHubClient(runner=runner, dry_run=args.dry_run)
    status_updater = ProjectStatusUpdater(
        github,
        use_script=not args.no_status_script,
        dry_run=args.dry_run,
    )
    created = create_ready_tasks(
        tasks=tasks,
        github=github,
        status_updater=status_updater,
        owner=args.owner,
        project_number=args.project,
        repo=args.repo,
        logger=logger,
    )
    for issue in created:
        print(f"Created #{issue.number} - {issue.title}")
    if args.dry_run:
        print("Dry run complete. No changes were made.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automation utilities for GitHub project workflows.")
    parser.add_argument("--owner", type=str, default="mmaideveloper", help="GitHub owner/org.")
    parser.add_argument("--project", type=int, default=5, help="GitHub project number.")
    parser.add_argument(
        "--repo",
        type=str,
        default="mmaideveloper/aijurisdictionagents",
        help="GitHub repository (owner/name).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without calling GitHub.",
    )
    parser.add_argument(
        "--no-status-script",
        action="store_true",
        help="Disable scripts/project_status.ps1 even if available.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_ready = subparsers.add_parser(
        "create-ready",
        help="Create tasks as GitHub issues and set them to Ready in the project.",
    )
    create_ready.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to a JSON file describing tasks.",
    )
    create_ready.set_defaults(func=_create_ready_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
