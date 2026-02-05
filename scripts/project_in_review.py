from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProjectConfig:
    owner: str
    repo: str
    project_number: int
    status_field: str = "Status"
    selection_strategy: str = "oldest_ready"
    labels: dict[str, str] = field(default_factory=dict)
    name: str | None = None


@dataclass(frozen=True)
class ProjectItem:
    item_id: str
    issue_number: int
    title: str
    url: str
    status: str


@dataclass(frozen=True)
class PullRequestInfo:
    number: int
    title: str
    url: str
    head_ref: str
    is_draft: bool
    closing_issues: tuple[int, ...]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config(path: Path) -> list[ProjectConfig]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "projects" in data:
        entries = data.get("projects", [])
    elif isinstance(data, list):
        entries = data
    else:
        entries = [data]

    if not isinstance(entries, list):
        raise ValueError("Config must contain a list of projects")

    projects: list[ProjectConfig] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each project config must be an object")
        owner = str(entry.get("owner", "")).strip()
        repo = str(entry.get("repo", "")).strip()
        project_number = int(entry.get("project_number", 0))
        if not owner or not repo or not project_number:
            raise ValueError("Each project requires owner, repo, and project_number")
        status_field = str(entry.get("status_field", "Status"))
        selection_strategy = str(entry.get("selection_strategy", "oldest_ready"))
        labels = entry.get("labels") or {}
        if not isinstance(labels, dict):
            raise ValueError("labels must be a JSON object")
        name = str(entry.get("name")).strip() if entry.get("name") else None
        projects.append(
            ProjectConfig(
                owner=owner,
                repo=repo,
                project_number=project_number,
                status_field=status_field,
                selection_strategy=selection_strategy,
                labels={str(k): str(v) for k, v in labels.items()},
                name=name,
            )
        )
    return projects


def _run_gh_json(args: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "gh command failed"
        raise RuntimeError(message)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Failed to parse gh JSON output") from exc


def _run_gh(args: list[str]) -> None:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "gh command failed"
        raise RuntimeError(message)


def _status_from_item(raw: dict[str, Any]) -> str:
    status = raw.get("status")
    if isinstance(status, dict):
        return str(status.get("name", ""))
    if status is None:
        return ""
    return str(status)


def _item_id_from_raw(raw: dict[str, Any], index: int, project_number: int) -> str:
    item_id = raw.get("id")
    if item_id:
        return str(item_id)
    return f"fixture-{project_number}-{index}"


def parse_items(raw_items: list[dict[str, Any]], project_number: int) -> list[ProjectItem]:
    items: list[ProjectItem] = []
    for index, raw in enumerate(raw_items):
        content = raw.get("content") or {}
        number = content.get("number")
        if number is None:
            continue
        items.append(
            ProjectItem(
                item_id=_item_id_from_raw(raw, index, project_number),
                issue_number=int(number),
                title=str(content.get("title", "")),
                url=str(content.get("url", "")),
                status=_status_from_item(raw),
            )
        )
    return items


def fetch_project_items(config: ProjectConfig, limit: int) -> list[ProjectItem]:
    payload = _run_gh_json(
        [
            "project",
            "item-list",
            str(config.project_number),
            "--owner",
            config.owner,
            "--format",
            "json",
            "--limit",
            str(limit),
        ]
    )
    raw_items = payload.get("items", payload)
    if not isinstance(raw_items, list):
        raise RuntimeError("Unexpected project item-list output")
    return parse_items(raw_items, config.project_number)


def load_fixture(path: Path, project_number: int) -> list[ProjectItem]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_items: Any
    if isinstance(payload, dict) and "projects" in payload:
        projects = payload.get("projects")
        if not isinstance(projects, dict):
            raise ValueError("Fixture projects must be an object")
        raw_items = projects.get(str(project_number)) or projects.get(project_number)
        if raw_items is None:
            raise ValueError(f"Fixture missing project {project_number}")
    else:
        raw_items = payload.get("items", payload)
    if not isinstance(raw_items, list):
        raise ValueError("Fixture must contain an items list")
    return parse_items(raw_items, project_number)


def _parse_pr_list(payload: Any) -> list[PullRequestInfo]:
    if isinstance(payload, dict) and "pull_requests" in payload:
        entries = payload.get("pull_requests")
    else:
        entries = payload
    if not isinstance(entries, list):
        raise ValueError("Pull request payload must be a list")

    prs: list[PullRequestInfo] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        closing = entry.get("closingIssuesReferences") or entry.get("closing_issues") or []
        closing_numbers = []
        for issue in closing:
            if isinstance(issue, dict) and "number" in issue:
                closing_numbers.append(int(issue["number"]))
            elif isinstance(issue, int):
                closing_numbers.append(issue)
            elif isinstance(issue, str) and issue.isdigit():
                closing_numbers.append(int(issue))
        prs.append(
            PullRequestInfo(
                number=int(entry.get("number", 0)),
                title=str(entry.get("title", "")),
                url=str(entry.get("url", "")),
                head_ref=str(entry.get("headRefName", "")),
                is_draft=bool(entry.get("isDraft", False)),
                closing_issues=tuple(closing_numbers),
            )
        )
    return prs


def fetch_pull_requests(repo: str) -> list[PullRequestInfo]:
    payload = _run_gh_json(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--json",
            "number,title,url,headRefName,isDraft,closingIssuesReferences",
        ]
    )
    return _parse_pr_list(payload)


def load_pr_fixture(path: Path) -> list[PullRequestInfo]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _parse_pr_list(payload)


def _extract_issue_numbers(text: str) -> set[int]:
    matches = set()
    for match in re.findall(r"(?:#|issue[-_ ]?)(\d+)", text, flags=re.IGNORECASE):
        if match.isdigit():
            matches.add(int(match))
    return matches


def _pr_matches_issue(pr: PullRequestInfo, issue_number: int) -> bool:
    if issue_number in pr.closing_issues:
        return True
    if issue_number in _extract_issue_numbers(pr.title):
        return True
    if issue_number in _extract_issue_numbers(pr.head_ref):
        return True
    return False


def build_pr_index(prs: list[PullRequestInfo]) -> dict[int, list[PullRequestInfo]]:
    index: dict[int, list[PullRequestInfo]] = {}
    for pr in prs:
        for issue_number in pr.closing_issues:
            index.setdefault(issue_number, []).append(pr)
        for issue_number in _extract_issue_numbers(pr.title):
            index.setdefault(issue_number, []).append(pr)
        for issue_number in _extract_issue_numbers(pr.head_ref):
            index.setdefault(issue_number, []).append(pr)
    return index


def get_project_status_field(project_number: int, owner: str, status_field: str) -> tuple[str, str]:
    project = _run_gh_json(
        ["project", "view", str(project_number), "--owner", owner, "--format", "json"]
    )
    fields = _run_gh_json(
        ["project", "field-list", str(project_number), "--owner", owner, "--format", "json"]
    )
    status = next((field for field in fields.get("fields", []) if field.get("name") == status_field), None)
    if not status:
        raise RuntimeError(f"Status field '{status_field}' not found")
    return str(project["id"]), str(status["id"])


def resolve_status_option(
    project_number: int,
    owner: str,
    status_field: str,
    status_value: str,
) -> str:
    fields = _run_gh_json(
        ["project", "field-list", str(project_number), "--owner", owner, "--format", "json"]
    )
    status = next((field for field in fields.get("fields", []) if field.get("name") == status_field), None)
    if not status:
        raise RuntimeError(f"Status field '{status_field}' not found")
    option = next((opt for opt in status.get("options", []) if opt.get("name") == status_value), None)
    if not option:
        raise RuntimeError(f"Status option '{status_value}' not found")
    return str(option["id"])


def update_project_status(
    project_id: str,
    field_id: str,
    option_id: str,
    item_id: str,
) -> None:
    _run_gh(
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


def issue_has_label(repo: str, issue_number: int, label: str) -> bool:
    payload = _run_gh_json(
        ["issue", "view", str(issue_number), "--repo", repo, "--json", "labels"]
    )
    labels = payload.get("labels", [])
    return any(str(item.get("name", "")) == label for item in labels if isinstance(item, dict))


def add_issue_label(repo: str, issue_number: int, label: str) -> None:
    _run_gh(["issue", "edit", str(issue_number), "--repo", repo, "--add-label", label])


def add_issue_comment(repo: str, issue_number: int, body: str) -> None:
    _run_gh(["issue", "comment", str(issue_number), "--repo", repo, "--body", body])


def select_ready_items(items: list[ProjectItem], ready_status: str) -> list[ProjectItem]:
    return [item for item in items if item.status.strip().lower() == ready_status.strip().lower()]


def build_plan(
    *,
    project: ProjectConfig,
    items: list[ProjectItem],
    prs: list[PullRequestInfo],
    ready_status: str,
    in_review_status: str,
) -> list[dict[str, Any]]:
    index = build_pr_index(prs)
    actions: list[dict[str, Any]] = []
    for item in select_ready_items(items, ready_status):
        candidates = index.get(item.issue_number, [])
        candidates = [pr for pr in candidates if not pr.is_draft]
        if not candidates:
            continue
        pr = sorted(candidates, key=lambda p: p.number)[0]
        actions.append(
            {
                "project_number": project.project_number,
                "project_name": project.name,
                "issue_number": item.issue_number,
                "item_id": item.item_id,
                "status_from": item.status,
                "status_to": in_review_status,
                "pr_number": pr.number,
                "pr_url": pr.url,
            }
        )
    return actions


def write_plan(path: Path, plan: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Move Ready project items with PRs to In review."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(".github/automation.yml"),
        help="Path to automation config (JSON content).",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Optional fixture JSON for project items.",
    )
    parser.add_argument(
        "--pr-fixture",
        type=Path,
        default=None,
        help="Optional fixture JSON for pull requests.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=200,
        help="Max project items to fetch.",
    )
    parser.add_argument(
        "--ready-status",
        type=str,
        default="Ready",
        help="Status name that indicates a task is Ready.",
    )
    parser.add_argument(
        "--in-review-status",
        type=str,
        default="In review",
        help="Status name to set when PRs are created.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without updating GitHub.",
    )
    parser.add_argument(
        "--plan-output",
        type=Path,
        default=None,
        help="Optional JSON output path for planned actions.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        projects = load_config(args.config)
        pr_cache: dict[str, list[PullRequestInfo]] = {}
        plan: dict[str, Any] = {"generated_at": _now_iso(), "projects": []}

        for project in projects:
            if args.fixture:
                items = load_fixture(args.fixture, project.project_number)
            else:
                items = fetch_project_items(project, args.max_items)

            if args.pr_fixture:
                prs = load_pr_fixture(args.pr_fixture)
            else:
                prs = pr_cache.get(project.repo)
                if prs is None:
                    prs = fetch_pull_requests(project.repo)
                    pr_cache[project.repo] = prs

            actions = build_plan(
                project=project,
                items=items,
                prs=prs,
                ready_status=args.ready_status,
                in_review_status=args.in_review_status,
            )

            plan["projects"].append(
                {
                    "project_number": project.project_number,
                    "project_name": project.name,
                    "actions": actions,
                }
            )

            if not actions:
                continue

            if args.dry_run:
                for action in actions:
                    print(
                        f"Would move issue #{action['issue_number']} to {args.in_review_status} "
                        f"(project {project.project_number})"
                    )
                continue

            project_id, field_id = get_project_status_field(
                project.project_number, project.owner, project.status_field
            )
            option_id = resolve_status_option(
                project.project_number, project.owner, project.status_field, args.in_review_status
            )
            label_name = project.labels.get("in_review", "auto:in-review")

            for action in actions:
                issue_number = action["issue_number"]
                pr_number = action["pr_number"]
                if label_name and issue_has_label(project.repo, issue_number, label_name):
                    continue
                comment = (
                    f"Implementation ready: PR #{pr_number} created. "
                    f"Moving task to {args.in_review_status}."
                )
                add_issue_comment(project.repo, issue_number, comment)
                if label_name:
                    try:
                        add_issue_label(project.repo, issue_number, label_name)
                    except RuntimeError as exc:
                        print(f"Warning: failed to add label '{label_name}' to #{issue_number}: {exc}")
                update_project_status(project_id, field_id, option_id, action["item_id"])

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.plan_output:
        write_plan(args.plan_output, plan)
        print(f"Plan saved: {args.plan_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
