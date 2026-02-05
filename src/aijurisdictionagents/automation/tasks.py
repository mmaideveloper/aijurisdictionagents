from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from .github import GitHubClient, ProjectStatusUpdater
from .models import IssueRef, TaskSpec


def load_task_specs(path: Path) -> list[TaskSpec]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        entries = raw.get("tasks", [])
    elif isinstance(raw, list):
        entries = raw
    else:
        raise ValueError("Task spec must be a list or a dict with a 'tasks' key")

    tasks: list[TaskSpec] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each task must be an object with 'title' and 'body'")
        title = str(entry.get("title", "")).strip()
        body = str(entry.get("body", "")).strip()
        if not title:
            raise ValueError("Task title is required")
        tasks.append(TaskSpec(title=title, body=body))
    return tasks


def create_ready_tasks(
    *,
    tasks: Iterable[TaskSpec],
    github: GitHubClient,
    status_updater: ProjectStatusUpdater,
    owner: str,
    project_number: int,
    repo: str,
    logger: logging.Logger | None = None,
) -> list[IssueRef]:
    created: list[IssueRef] = []
    for task in tasks:
        if logger:
            logger.info("Creating issue: %s", task.title)
        issue = github.create_issue(repo, task.title, task.body)
        github.add_issue_to_project(project_number, owner, issue.url)
        status_updater.set_status(
            issue_number=issue.number,
            status="Ready",
            owner=owner,
            project_number=project_number,
            repo=repo,
        )
        if logger:
            logger.info("Added issue #%s to project %s as Ready", issue.number, project_number)
        created.append(issue)
    return created
