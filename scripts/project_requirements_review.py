from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEW_MARKER = "codex - business requirements reviewed"
DEFAULT_ACCEPTANCE_CRITERIA = (
    "When implementation is complete, the issue includes tests and documentation updates.",
    "The change is verified in a reproducible local run or CI check.",
)


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
    issue_number: int
    title: str
    url: str
    status: str


@dataclass(frozen=True)
class IssueSnapshot:
    number: int
    title: str
    url: str
    body: str
    comments: tuple[str, ...]


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
        projects.append(
            ProjectConfig(
                owner=owner,
                repo=repo,
                project_number=project_number,
                status_field=str(entry.get("status_field", "Status")),
                selection_strategy=str(entry.get("selection_strategy", "oldest_ready")),
                labels={str(k): str(v) for k, v in (entry.get("labels") or {}).items()},
                name=str(entry.get("name")).strip() if entry.get("name") else None,
            )
        )
    return projects


def _run_gh_json(args: list[str]) -> dict[str, Any]:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "gh command failed"
        raise RuntimeError(message)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Failed to parse gh JSON output") from exc


def _run_gh(args: list[str]) -> None:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "gh command failed"
        raise RuntimeError(message)


def parse_project_items(raw_items: list[dict[str, Any]]) -> list[ProjectItem]:
    items: list[ProjectItem] = []
    for raw in raw_items:
        content = raw.get("content") or {}
        number = content.get("number")
        if number is None:
            continue
        status = raw.get("status")
        if isinstance(status, dict):
            status = status.get("name", "")
        items.append(
            ProjectItem(
                issue_number=int(number),
                title=str(content.get("title", "")),
                url=str(content.get("url", "")),
                status=str(status or ""),
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
    return parse_project_items(raw_items)


def fetch_issue(repo: str, issue_number: int) -> IssueSnapshot:
    payload = _run_gh_json(
        [
            "issue",
            "view",
            str(issue_number),
            "--repo",
            repo,
            "--json",
            "number,title,url,body,comments",
        ]
    )
    raw_comments = payload.get("comments") or []
    comments = tuple(
        str(item.get("body", ""))
        for item in raw_comments
        if isinstance(item, dict)
    )
    return IssueSnapshot(
        number=int(payload.get("number", issue_number)),
        title=str(payload.get("title", "")),
        url=str(payload.get("url", "")),
        body=str(payload.get("body", "")),
        comments=comments,
    )


def load_fixture(path: Path, project_number: int) -> tuple[list[ProjectItem], dict[int, IssueSnapshot]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    projects = payload.get("projects") if isinstance(payload, dict) else None
    if not isinstance(projects, dict):
        raise ValueError("Fixture must include a projects object")

    raw_items = projects.get(str(project_number), [])
    if not isinstance(raw_items, list):
        raise ValueError("Fixture project items must be a list")

    raw_issues = payload.get("issues", {})
    if not isinstance(raw_issues, dict):
        raise ValueError("Fixture issues must be an object")

    issues: dict[int, IssueSnapshot] = {}
    for key, raw_issue in raw_issues.items():
        if not isinstance(raw_issue, dict):
            continue
        number = int(raw_issue.get("number", key))
        comments_raw = raw_issue.get("comments") or []
        comments = []
        for comment in comments_raw:
            if isinstance(comment, dict):
                comments.append(str(comment.get("body", "")))
            else:
                comments.append(str(comment))
        issues[number] = IssueSnapshot(
            number=number,
            title=str(raw_issue.get("title", "")),
            url=str(raw_issue.get("url", "")),
            body=str(raw_issue.get("body", "")),
            comments=tuple(comments),
        )

    return parse_project_items(raw_items), issues


def has_review_comment(comments: tuple[str, ...], marker: str = REVIEW_MARKER) -> bool:
    marker_folded = marker.casefold()
    return any(marker_folded in body.casefold() for body in comments)


def requirements_gaps(issue_body: str) -> list[str]:
    body = issue_body.casefold()
    gaps: list[str] = []

    if "business requirement" not in body and "requirements" not in body:
        gaps.append("Missing explicit business requirements section.")
    if "acceptance criteria" not in body and "done when" not in body:
        gaps.append("Missing acceptance criteria.")
    if len(issue_body.strip()) < 80:
        gaps.append("Issue description is too short; add clearer requirements context.")
    return gaps


def _collect_seed_requirements(issue_title: str, issue_body: str) -> list[str]:
    requirements: list[str] = []
    title = issue_title.strip()
    if title:
        requirements.append(f"Implement: {title}.")

    for line in issue_body.splitlines():
        text = line.strip().lstrip("-").strip()
        if not text:
            continue
        lowered = text.casefold()
        if lowered.startswith("##"):
            continue
        if any(token in lowered for token in ("require", "must", "should", "need")):
            requirements.append(text.rstrip(".") + ".")
        if len(requirements) >= 4:
            break

    if not requirements:
        requirements.append("Clarify expected business outcome and user impact.")
    return requirements


def build_fixed_issue_body(issue_title: str, issue_body: str) -> tuple[str, list[str]]:
    fixed = issue_body.rstrip()
    applied: list[str] = []
    body_folded = issue_body.casefold()

    if "business requirement" not in body_folded and "requirements" not in body_folded:
        applied.append("Added Business requirements section.")
        requirements = _collect_seed_requirements(issue_title, issue_body)
        bullets = "\n".join(f"- {item}" for item in requirements)
        fixed += f"\n\n## Business requirements\n{bullets}\n"

    if "acceptance criteria" not in body_folded and "done when" not in body_folded:
        applied.append("Added Acceptance criteria section.")
        criteria = "\n".join(f"- {item}" for item in DEFAULT_ACCEPTANCE_CRITERIA)
        fixed += f"\n\n## Acceptance criteria\n{criteria}\n"

    if len(issue_body.strip()) < 80:
        applied.append("Added Summary section for missing context.")
        fixed += (
            "\n\n## Summary\n"
            "Describe user problem, expected outcome, and constraints for implementation.\n"
        )

    return fixed.strip() + "\n", applied


def build_review_comment(gaps: list[str]) -> str:
    if not gaps:
        findings = "No requirement gaps detected from issue text."
    else:
        bullets = "\n".join(f"- {gap}" for gap in gaps)
        findings = f"Detected requirement gaps:\n{bullets}"
    return f"{REVIEW_MARKER}\n\n{findings}"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check project tasks for a requirements-review comment and generate/apply"
            " requirement review notes."
        )
    )
    parser.add_argument("--config", type=Path, default=Path(".github/automation.yml"))
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--max-items", type=int, default=200)
    parser.add_argument(
        "--statuses",
        type=str,
        default="Ready,In progress",
        help="Comma-separated task statuses to inspect.",
    )
    parser.add_argument("--marker", type=str, default=REVIEW_MARKER)
    parser.add_argument("--apply", action="store_true", help="Post missing review comments.")
    parser.add_argument(
        "--fix-body",
        action="store_true",
        help="When applying, also patch issue body with missing requirement sections.",
    )
    parser.add_argument("--output", type=Path, default=Path("runs/automation/requirements_review_plan.json"))
    return parser


def _matches_status(status: str, allowed: set[str]) -> bool:
    return status.strip().casefold() in allowed


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    allowed_statuses = {
        part.strip().casefold() for part in args.statuses.split(",") if part.strip()
    }

    try:
        projects = load_config(args.config)
        report: dict[str, Any] = {"generated_at": _now_iso(), "projects": []}

        for project in projects:
            if args.fixture:
                items, issues = load_fixture(args.fixture, project.project_number)
            else:
                items = fetch_project_items(project, args.max_items)
                issues = {}

            project_actions: list[dict[str, Any]] = []
            for item in items:
                if allowed_statuses and not _matches_status(item.status, allowed_statuses):
                    continue

                issue = issues.get(item.issue_number)
                if issue is None:
                    issue = fetch_issue(project.repo, item.issue_number)

                already_reviewed = has_review_comment(issue.comments, marker=args.marker)
                if already_reviewed:
                    continue

                gaps = requirements_gaps(issue.body)
                fixed_body, fixes_applied = build_fixed_issue_body(issue.title, issue.body)
                body_needs_update = fixed_body.strip() != issue.body.strip()
                comment_body = build_review_comment(gaps)
                action = {
                    "issue_number": issue.number,
                    "title": issue.title or item.title,
                    "url": issue.url or item.url,
                    "status": item.status,
                    "missing_marker": args.marker,
                    "requirement_gaps": gaps,
                    "body_fixes": fixes_applied,
                    "body_needs_update": body_needs_update,
                    "fixed_body_preview": fixed_body,
                    "comment_preview": comment_body,
                }
                project_actions.append(action)

                if args.apply and not args.fixture:
                    if args.fix_body and body_needs_update:
                        _run_gh(
                            [
                                "issue",
                                "edit",
                                str(issue.number),
                                "--repo",
                                project.repo,
                                "--body",
                                fixed_body,
                            ]
                        )
                    _run_gh(
                        [
                            "issue",
                            "comment",
                            str(issue.number),
                            "--repo",
                            project.repo,
                            "--body",
                            comment_body,
                        ]
                    )

            report["projects"].append(
                {
                    "project_number": project.project_number,
                    "project_name": project.name,
                    "repo": project.repo,
                    "actions": project_actions,
                }
            )

        write_json(args.output, report)

        missing_count = sum(len(project["actions"]) for project in report["projects"])
        print(f"Requirements review plan saved: {args.output}")
        print(f"Tasks missing marker '{args.marker}': {missing_count}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
