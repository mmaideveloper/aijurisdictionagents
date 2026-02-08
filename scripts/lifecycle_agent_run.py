from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from aijurisdictionagents.lifecycle import (
    DEFAULT_STAGE_ORDER,
    LifecycleAutomationConfig,
    LifecycleProject,
    build_default_pipeline,
)


def _split_values(raw: str) -> tuple[str, ...]:
    text = (raw or "").strip()
    if not text:
        return ()
    parts = re.split(r"[,\n|;]", text)
    return tuple(item.strip() for item in parts if item.strip())


def _default_tuple(values: tuple[str, ...], fallback: tuple[str, ...]) -> tuple[str, ...]:
    if values:
        return values
    return fallback


def _stage_with_prerequisites(stage: str) -> tuple[str, ...]:
    index = DEFAULT_STAGE_ORDER.index(stage)
    return tuple(DEFAULT_STAGE_ORDER[: index + 1])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a single lifecycle automation agent stage and persist the result JSON."
    )
    parser.add_argument(
        "--stage",
        choices=list(DEFAULT_STAGE_ORDER),
        required=True,
        help="Lifecycle stage to run.",
    )
    parser.add_argument("--project-name", required=True, help="Project display name.")
    parser.add_argument("--idea", required=True, help="Project idea description.")
    parser.add_argument("--project-type", default="fullstack", help="Project type.")
    parser.add_argument(
        "--preferred-stack",
        default="python,react",
        help="Preferred stack tokens separated by comma/newline/|/;.",
    )
    parser.add_argument(
        "--business-requirements",
        default="",
        help="Business requirements separated by comma/newline/|/;.",
    )
    parser.add_argument(
        "--technical-requirements",
        default="",
        help="Technical requirements separated by comma/newline/|/;.",
    )
    parser.add_argument(
        "--deployment-targets",
        default="dev,staging,production",
        help="Deployment environments separated by comma/newline/|/;.",
    )
    parser.add_argument(
        "--ci-cd-platforms",
        default="github_actions,azure_devops",
        help="CI/CD platforms separated by comma/newline/|/;.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSON file path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    project = LifecycleProject(
        name=args.project_name,
        idea=args.idea,
        project_type=args.project_type,
        preferred_stack=_split_values(args.preferred_stack),
        business_requirements=_split_values(args.business_requirements),
        technical_requirements=_split_values(args.technical_requirements),
        deployment_targets=_default_tuple(
            _split_values(args.deployment_targets),
            ("dev", "staging", "production"),
        ),
        ci_cd_platforms=_default_tuple(
            _split_values(args.ci_cd_platforms),
            ("github_actions", "azure_devops"),
        ),
    )

    enabled_stages = _stage_with_prerequisites(args.stage)
    pipeline = build_default_pipeline(
        LifecycleAutomationConfig(enabled_stages=enabled_stages, stop_on_failure=True)
    )
    result = pipeline.run(project)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    if not result.stage_results:
        print(f"Error: stage '{args.stage}' produced no output.", file=sys.stderr)
        return 1

    stage_result = result.stage_results[-1]
    print(
        f"Lifecycle stage '{stage_result.stage}' "
        f"({stage_result.agent_name}) completed. passed={stage_result.passed}. "
        f"stages_run={len(result.stage_results)}"
    )
    print(f"Output saved: {args.output}")

    if not result.succeeded:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
