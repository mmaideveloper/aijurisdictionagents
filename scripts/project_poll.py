from __future__ import annotations

import argparse
import json
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
    issue_number: int
    title: str
    url: str
    status: str


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


def _run_gh(args: list[str]) -> dict[str, Any]:
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


def _status_from_item(raw: dict[str, Any]) -> str:
    status = raw.get("status")
    if isinstance(status, dict):
        return str(status.get("name", ""))
    if status is None:
        return ""
    return str(status)


def parse_items(raw_items: list[dict[str, Any]]) -> list[ProjectItem]:
    items: list[ProjectItem] = []
    for raw in raw_items:
        content = raw.get("content") or {}
        number = content.get("number")
        if number is None:
            continue
        items.append(
            ProjectItem(
                issue_number=int(number),
                title=str(content.get("title", "")),
                url=str(content.get("url", "")),
                status=_status_from_item(raw),
            )
        )
    return items


def fetch_project_items(config: ProjectConfig, limit: int) -> list[ProjectItem]:
    payload = _run_gh(
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
    return parse_items(raw_items)


def load_fixture(path: Path, project_number: int | None = None) -> list[ProjectItem]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_items: Any
    if isinstance(payload, dict) and "projects" in payload:
        projects = payload.get("projects")
        if not isinstance(projects, dict):
            raise ValueError("Fixture projects must be an object")
        if project_number is None:
            raise ValueError("Fixture requires project_number when using projects map")
        raw_items = projects.get(str(project_number)) or projects.get(project_number)
        if raw_items is None:
            raise ValueError(f"Fixture missing project {project_number}")
    else:
        raw_items = payload.get("items", payload)
    if not isinstance(raw_items, list):
        raise ValueError("Fixture must contain an items list")
    return parse_items(raw_items)


def summarize_items(items: list[ProjectItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = item.status or "(unset)"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[0]))


def build_project_snapshot(config: ProjectConfig, items: list[ProjectItem]) -> dict[str, Any]:
    snapshot = {
        "generated_at": _now_iso(),
        "project": {
            "owner": config.owner,
            "repo": config.repo,
            "project_number": config.project_number,
            "status_field": config.status_field,
            "selection_strategy": config.selection_strategy,
            "labels": config.labels,
        },
        "summary": {
            "total": len(items),
            "by_status": summarize_items(items),
        },
        "items": [
            {
                "issue_number": item.issue_number,
                "title": item.title,
                "url": item.url,
                "status": item.status,
            }
            for item in items
        ],
    }
    if config.name:
        snapshot["project"]["name"] = config.name
    return snapshot


def build_multi_summary(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    aggregated: dict[str, int] = {}
    projects: list[dict[str, Any]] = []

    for snapshot in snapshots:
        summary = snapshot.get("summary", {})
        total += int(summary.get("total", 0))
        for status, count in (summary.get("by_status") or {}).items():
            aggregated[status] = aggregated.get(status, 0) + int(count)
        project_info = snapshot.get("project", {})
        projects.append(
            {
                "project_number": project_info.get("project_number"),
                "name": project_info.get("name"),
                "summary": summary,
            }
        )

    return {
        "generated_at": _now_iso(),
        "summary": {
            "total": total,
            "by_status": dict(sorted(aggregated.items(), key=lambda kv: kv[0])),
        },
        "projects": projects,
    }


def write_snapshot(snapshot: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def _default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("runs") / "automation" / stamp / "project_snapshot.json"


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("runs") / "automation" / stamp


def _resolve_output_dir(output: Path | None) -> Path:
    if output is None:
        return _default_output_dir()
    if output.suffix:
        return output.with_suffix("")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Poll GitHub Project V2 items and write a snapshot for automation workflows."
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
        help="Optional fixture JSON for offline runs.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=200,
        help="Max project items to fetch.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file (single project) or directory (multi-project).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        projects = load_config(args.config)
        snapshots: list[dict[str, Any]] = []
        for project in projects:
            if args.fixture:
                items = load_fixture(args.fixture, project.project_number)
            else:
                items = fetch_project_items(project, args.max_items)
            snapshots.append(build_project_snapshot(project, items))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if len(snapshots) == 1:
        output_path = args.output or _default_output_path()
        write_snapshot(snapshots[0], output_path)
        print(f"Snapshot saved: {output_path}")
        for status, count in snapshots[0]["summary"]["by_status"].items():
            print(f"- {status}: {count}")
        return 0

    output_dir = _resolve_output_dir(args.output)
    for snapshot in snapshots:
        project_number = snapshot["project"]["project_number"]
        path = output_dir / f"project_{project_number}.json"
        write_snapshot(snapshot, path)
        project_name = snapshot["project"].get("name") or project_number
        print(f"Snapshot saved: {path} (project {project_name})")
        for status, count in snapshot["summary"]["by_status"].items():
            print(f"- {status}: {count}")

    summary = build_multi_summary(snapshots)
    summary_path = output_dir / "summary.json"
    write_snapshot(summary, summary_path)
    print(f"Summary saved: {summary_path}")
    for status, count in summary["summary"]["by_status"].items():
        print(f"- {status}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
