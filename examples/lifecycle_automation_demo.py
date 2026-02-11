from __future__ import annotations

import sys
from pathlib import Path

# Allow running directly from repository root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aijurisdictionagents.lifecycle import LifecycleProject, build_default_pipeline


def main() -> None:
    project = LifecycleProject(
        name="Customer Support Platform",
        idea=(
            "Create a fullstack support platform with customer portal, API services, "
            "automated background processing, and production deployment."
        ),
        project_type="fullstack",
        preferred_stack=("python", "react", "postgres"),
        business_requirements=(
            "Frontend customer portal",
            "API for support ticket operations",
            "Data storage for tickets and audit logs",
        ),
        technical_requirements=(
            "CI pipeline",
            "deployment rollback",
        ),
        deployment_targets=("dev", "staging", "production"),
        ci_cd_platforms=("github_actions", "azure_devops"),
    )

    pipeline = build_default_pipeline()
    result = pipeline.run(project)

    print(f"Project: {project.name}")
    print(f"Succeeded: {result.succeeded}")
    print("Stages:")
    for stage in result.stage_results:
        print(f"- {stage.stage} ({stage.agent_name}): {stage.summary}")
        if stage.warnings:
            for warning in stage.warnings:
                print(f"  warning: {warning}")


if __name__ == "__main__":
    main()
