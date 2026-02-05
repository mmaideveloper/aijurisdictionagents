from __future__ import annotations

from pathlib import Path

from automation.github import GitHubClient, ProjectStatusUpdater
from automation.runner import DryRunRunner
from automation.tasks import create_ready_tasks, load_task_specs
from aijurisdictionagents.observability import create_run_dir, setup_logging


def main() -> None:
    tasks = load_task_specs(Path("examples/automation_tasks.json"))
    run_dir = create_run_dir(Path("runs") / "automation")
    logger = setup_logging(run_dir, log_level="INFO")

    github = GitHubClient(runner=DryRunRunner(), dry_run=True)
    status_updater = ProjectStatusUpdater(github, dry_run=True)

    created = create_ready_tasks(
        tasks=tasks,
        github=github,
        status_updater=status_updater,
        owner="example-owner",
        project_number=0,
        repo="example/repo",
        logger=logger,
    )

    print("Dry-run created tasks:")
    for issue in created:
        print(f"- #{issue.number} {issue.title} ({issue.url})")


if __name__ == "__main__":
    main()
