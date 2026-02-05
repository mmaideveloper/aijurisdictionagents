from __future__ import annotations

import json
from pathlib import Path

import pytest

from automation.github import GitHubClient, ProjectStatusUpdater
from automation.models import TaskSpec
from automation.runner import DryRunRunner
from automation.tasks import create_ready_tasks, load_task_specs


def test_load_task_specs_accepts_list(tmp_path: Path) -> None:
    payload = [{"title": "Task A", "body": "Body"}]
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    tasks = load_task_specs(path)

    assert tasks == [TaskSpec(title="Task A", body="Body")]


def test_load_task_specs_accepts_dict(tmp_path: Path) -> None:
    payload = {"tasks": [{"title": "Task B", "body": "Details"}]}
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    tasks = load_task_specs(path)

    assert tasks == [TaskSpec(title="Task B", body="Details")]


def test_load_task_specs_requires_title(tmp_path: Path) -> None:
    payload = [{"body": "Missing title"}]
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Task title is required"):
        load_task_specs(path)


def test_create_ready_tasks_dry_run() -> None:
    tasks = [TaskSpec(title="One", body=""), TaskSpec(title="Two", body="")]
    github = GitHubClient(runner=DryRunRunner(), dry_run=True, dry_run_start=100)
    status_updater = ProjectStatusUpdater(github, dry_run=True)

    created = create_ready_tasks(
        tasks=tasks,
        github=github,
        status_updater=status_updater,
        owner="owner",
        project_number=1,
        repo="owner/repo",
        logger=None,
    )

    assert [issue.number for issue in created] == [101, 102]
    assert created[0].title == "One"
    assert created[1].title == "Two"
