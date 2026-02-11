from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LifecycleProject:
    name: str
    idea: str
    project_type: str
    preferred_stack: tuple[str, ...] = ()
    business_requirements: tuple[str, ...] = ()
    technical_requirements: tuple[str, ...] = ()
    deployment_targets: tuple[str, ...] = ("dev", "staging", "production")
    ci_cd_platforms: tuple[str, ...] = ("github_actions", "azure_devops")


@dataclass(frozen=True)
class LifecycleStageResult:
    stage: str
    agent_name: str
    summary: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    passed: bool = True


@dataclass(frozen=True)
class LifecycleRunResult:
    project: LifecycleProject
    started_at: str
    completed_at: str
    succeeded: bool
    stage_results: tuple[LifecycleStageResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": {
                "name": self.project.name,
                "idea": self.project.idea,
                "project_type": self.project.project_type,
                "preferred_stack": list(self.project.preferred_stack),
                "business_requirements": list(self.project.business_requirements),
                "technical_requirements": list(self.project.technical_requirements),
                "deployment_targets": list(self.project.deployment_targets),
                "ci_cd_platforms": list(self.project.ci_cd_platforms),
            },
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "succeeded": self.succeeded,
            "stages": [
                {
                    "stage": item.stage,
                    "agent_name": item.agent_name,
                    "summary": item.summary,
                    "artifacts": item.artifacts,
                    "warnings": list(item.warnings),
                    "passed": item.passed,
                }
                for item in self.stage_results
            ],
        }
