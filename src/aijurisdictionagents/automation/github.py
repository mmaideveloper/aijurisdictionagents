from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .models import IssueRef, ProjectItem
from .runner import CommandRunner, CommandResult, SubprocessRunner


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectFieldOption:
    id: str
    name: str


@dataclass(frozen=True)
class ProjectField:
    id: str
    name: str
    options: tuple[ProjectFieldOption, ...]


@dataclass(frozen=True)
class ProjectInfo:
    id: str


class GitHubClient:
    def __init__(
        self,
        runner: Optional[CommandRunner] = None,
        dry_run: bool = False,
        dry_run_start: int = 9000,
    ) -> None:
        self._runner = runner or SubprocessRunner()
        self._dry_run = dry_run
        self._dry_run_counter = dry_run_start

    def create_issue(self, repo: str, title: str, body: str) -> IssueRef:
        if self._dry_run:
            return self._dry_run_issue(title, repo)

        result = self._run_gh(["issue", "create", "--repo", repo, "--title", title, "--body", body])
        issue_url = result.stdout.strip().splitlines()[-1]
        if not issue_url:
            raise GitHubError("gh issue create returned no URL")
        return self.issue_view(repo, issue_url)

    def issue_view(self, repo: str, issue: str | int) -> IssueRef:
        if self._dry_run:
            issue_number = int(str(issue).split("/")[-1]) if str(issue).isdigit() else 0
            return IssueRef(number=issue_number, title=f"dry-run-{issue}", url=str(issue))

        payload = self._run_gh_json(
            ["issue", "view", str(issue), "--repo", repo, "--json", "number,title,url,state"]
        )
        return IssueRef(
            number=int(payload["number"]),
            title=str(payload["title"]),
            url=str(payload["url"]),
            state=str(payload.get("state")) if payload.get("state") else None,
        )

    def add_issue_to_project(self, project_number: int, owner: str, issue_url: str) -> None:
        if self._dry_run:
            return
        self._run_gh(
            [
                "project",
                "item-add",
                str(project_number),
                "--owner",
                owner,
                "--url",
                issue_url,
            ]
        )

    def comment_issue(self, repo: str, issue_number: int, body: str) -> None:
        if self._dry_run:
            return
        self._run_gh(["issue", "comment", str(issue_number), "--repo", repo, "--body", body])

    def project_view(self, project_number: int, owner: str) -> ProjectInfo:
        payload = self._run_gh_json(
            ["project", "view", str(project_number), "--owner", owner, "--format", "json"]
        )
        return ProjectInfo(id=str(payload["id"]))

    def project_fields(self, project_number: int, owner: str) -> tuple[ProjectField, ...]:
        payload = self._run_gh_json(
            ["project", "field-list", str(project_number), "--owner", owner, "--format", "json"]
        )
        fields = []
        for field in payload.get("fields", []):
            options = tuple(
                ProjectFieldOption(id=str(option["id"]), name=str(option["name"]))
                for option in field.get("options", [])
            )
            fields.append(ProjectField(id=str(field["id"]), name=str(field["name"]), options=options))
        return tuple(fields)

    def project_items(self, project_number: int, owner: str, limit: int = 200) -> tuple[ProjectItem, ...]:
        payload = self._run_gh_json(
            [
                "project",
                "item-list",
                str(project_number),
                "--owner",
                owner,
                "--format",
                "json",
                "--limit",
                str(limit),
            ]
        )
        items = []
        for item in payload.get("items", []):
            content = item.get("content") or {}
            number = content.get("number")
            if number is None:
                continue
            items.append(
                ProjectItem(
                    issue_number=int(number),
                    title=str(content.get("title", "")),
                    url=str(content.get("url", "")),
                    status=str(item.get("status", "")),
                )
            )
        return tuple(items)

    def project_item_edit(
        self,
        project_id: str,
        item_id: str,
        field_id: str,
        option_id: str,
    ) -> None:
        if self._dry_run:
            return
        self._run_gh(
            [
                "project",
                "item-edit",
                "--id",
                item_id,
                "--project-id",
                project_id,
                "--field-id",
                field_id,
                "--single-select-option-id",
                option_id,
            ]
        )

    def update_project_status(
        self,
        *,
        issue_number: int,
        project_number: int,
        owner: str,
        status: str,
    ) -> None:
        project = self.project_view(project_number, owner)
        fields = self.project_fields(project_number, owner)
        status_field = next((field for field in fields if field.name == "Status"), None)
        if not status_field:
            raise GitHubError("Status field not found in project")
        option = next((opt for opt in status_field.options if opt.name == status), None)
        if not option:
            raise GitHubError(f"Status option '{status}' not found")
        items_payload = self._run_gh_json(
            [
                "project",
                "item-list",
                str(project_number),
                "--owner",
                owner,
                "--format",
                "json",
                "--limit",
                "200",
            ]
        )
        item = next(
            (
                candidate
                for candidate in items_payload.get("items", [])
                if (candidate.get("content") or {}).get("number") == issue_number
            ),
            None,
        )
        if not item:
            raise GitHubError(f"Issue #{issue_number} not found in project")
        self.project_item_edit(
            project_id=project.id,
            item_id=str(item["id"]),
            field_id=status_field.id,
            option_id=option.id,
        )

    def _run_gh(self, args: Iterable[str]) -> CommandResult:
        result = self._runner.run(["gh", *args])
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "Unknown gh error"
            raise GitHubError(message)
        return result

    def _run_gh_json(self, args: Iterable[str]) -> dict:
        result = self._run_gh(args)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise GitHubError("Failed to parse gh JSON output") from exc

    def _dry_run_issue(self, title: str, repo: str) -> IssueRef:
        self._dry_run_counter += 1
        number = self._dry_run_counter
        url = f"https://example.invalid/{repo}/issues/{number}"
        return IssueRef(number=number, title=title, url=url, state="OPEN")


class ProjectStatusUpdater:
    def __init__(
        self,
        github: GitHubClient,
        repo_root: Optional[Path] = None,
        use_script: bool = True,
        dry_run: bool = False,
    ) -> None:
        self._github = github
        self._dry_run = dry_run
        self._use_script = use_script
        root = repo_root or Path(__file__).resolve().parents[3]
        self._script_path = root / "scripts" / "project_status.ps1"

    def set_status(
        self,
        *,
        issue_number: int,
        status: str,
        owner: str,
        project_number: int,
        repo: str,
        comment: str | None = None,
    ) -> None:
        if self._dry_run:
            return
        if self._use_script and self._script_path.exists() and os.name == "nt":
            self._run_status_script(
                issue_number=issue_number,
                status=status,
                owner=owner,
                project_number=project_number,
                repo=repo,
                comment=comment,
            )
            return
        self._github.update_project_status(
            issue_number=issue_number,
            project_number=project_number,
            owner=owner,
            status=status,
        )
        if comment:
            self._github.comment_issue(repo, issue_number, comment)

    def _run_status_script(
        self,
        *,
        issue_number: int,
        status: str,
        owner: str,
        project_number: int,
        repo: str,
        comment: str | None = None,
    ) -> None:
        shell = "pwsh" if shutil.which("pwsh") else "powershell"
        args = [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self._script_path),
            "-IssueNumber",
            str(issue_number),
            "-Status",
            status,
            "-Owner",
            owner,
            "-ProjectNumber",
            str(project_number),
            "-Repo",
            repo,
        ]
        if comment:
            args.extend(["-Comment", comment])
        result = self._github._runner.run(args)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "Failed to run status script"
            raise GitHubError(message)
