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
class PollingConfig:
    owner: str
    repo: str
    project_number: int
    status_field: str = "Status"
    selection_strategy: str = "oldest_ready"
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectItem:
    issue_number: int
    title: str
    url: str
    status: str


def load_config(path: Path) -> PollingConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    owner = str(data.get("owner", "")).strip()
    repo = str(data.get("repo", "")).strip()
    project_number = int(data.get("project_number", 0))
    if not owner or not repo or not project_number:
        raise ValueError("Config requires owner, repo, and project_number")
    status_field = str(data.get("status_field", "Status"))
    selection_strategy = str(data.get("selection_strategy", "oldest_ready"))
    labels = data.get("labels") or {}
    if not isinstance(labels, dict):
        raise ValueError("labels must be a JSON object")
    return PollingConfig(
        owner=owner,
        repo=repo,
        project_number=project_number,
        status_field=status_field,
        selection_strategy=selection_strategy,
        labels={str(k): str(v) for k, v in labels.items()},
    )


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


def fetch_project_items(config: PollingConfig, limit: int) -> list[ProjectItem]:
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


def load_fixture(path: Path) -> list[ProjectItem]:
    payload = json.loads(path.read_text(encoding="utf-8"))
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


def build_snapshot(config: PollingConfig, items: list[ProjectItem]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
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


def write_snapshot(snapshot: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def _default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("runs") / "automation" / stamp / "project_snapshot.json"


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
        help="Output path for snapshot JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        if args.fixture:
            items = load_fixture(args.fixture)
        else:
            items = fetch_project_items(config, args.max_items)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    snapshot = build_snapshot(config, items)
    output_path = args.output or _default_output_path()
    write_snapshot(snapshot, output_path)

    print(f"Snapshot saved: {output_path}")
    for status, count in snapshot["summary"]["by_status"].items():
        print(f"- {status}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
