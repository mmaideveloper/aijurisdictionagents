from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .models import LifecycleProject, LifecycleStageResult


class LifecycleAgent(Protocol):
    stage: str
    name: str

    def run(
        self,
        project: LifecycleProject,
        context: dict[str, dict[str, Any]],
    ) -> LifecycleStageResult:
        ...


def _project_type(value: str) -> str:
    return (value or "").strip().lower()


def _stack(project: LifecycleProject) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in project.preferred_stack if item.strip())


def _solution_modules(project: LifecycleProject) -> list[dict[str, str]]:
    kind = _project_type(project.project_type)
    if kind == "frontend":
        return [
            {"name": "web-ui", "responsibility": "Render UX and user interactions."},
            {"name": "ui-tests", "responsibility": "Validate browser behavior and regressions."},
        ]
    if kind == "backend":
        return [
            {"name": "api-service", "responsibility": "Serve API endpoints and orchestration hooks."},
            {"name": "worker", "responsibility": "Run asynchronous jobs and queue workloads."},
            {"name": "data-store", "responsibility": "Persist domain and audit data."},
        ]
    return [
        {"name": "web-ui", "responsibility": "Render UX and user interactions."},
        {"name": "api-service", "responsibility": "Serve API endpoints and orchestration hooks."},
        {"name": "worker", "responsibility": "Run asynchronous jobs and queue workloads."},
        {"name": "data-store", "responsibility": "Persist domain and audit data."},
    ]


def _pick_languages(project: LifecycleProject) -> tuple[str, str]:
    stack = _stack(project)
    frontend_language = "TypeScript"
    backend_language = "Python"

    if any(token in stack for token in ("react", "next.js", "nextjs", "vue", "angular")):
        frontend_language = "TypeScript"
    if any(token in stack for token in ("javascript", "node", "node.js", "express")):
        backend_language = "Node.js"
    if any(token in stack for token in ("c#", ".net", "dotnet")):
        backend_language = "C#"
    return frontend_language, backend_language


def _requirement_tokens(requirement: str) -> list[str]:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in requirement.lower())
    return [part for part in cleaned.split() if len(part) >= 3]


def _is_requirement_addressed(requirement: str, project: LifecycleProject, solution_text: str) -> bool:
    tokens = _requirement_tokens(requirement)
    if not tokens:
        return True

    haystack = f"{solution_text} {project.idea.lower()} {_project_type(project.project_type)}"
    if all(token in haystack for token in tokens):
        return True

    joined = " ".join(tokens)
    if "api" in tokens and "api-service" in haystack:
        return True
    if "frontend" in tokens and _project_type(project.project_type) in {"frontend", "fullstack"}:
        return True
    if "backend" in tokens and _project_type(project.project_type) in {"backend", "fullstack"}:
        return True
    if ("database" in tokens or "storage" in tokens or "data" in tokens) and "data-store" in haystack:
        return True
    if ("pipeline" in tokens or "ci" in tokens or "cd" in tokens) and project.ci_cd_platforms:
        return True
    if ("deploy" in joined or "rollback" in joined) and project.deployment_targets:
        return True
    return False


@dataclass(frozen=True)
class SolutionAgent:
    stage: str = "solution"
    name: str = "SolutionAgent"

    def run(
        self,
        project: LifecycleProject,
        context: dict[str, dict[str, Any]],
    ) -> LifecycleStageResult:
        del context
        modules = _solution_modules(project)
        kind = _project_type(project.project_type)
        architecture_style = "modular monolith"
        if kind in {"service", "microservice", "microservices"}:
            architecture_style = "microservices"
        elif kind == "frontend":
            architecture_style = "frontend app with edge APIs"

        artifacts = {
            "architecture_style": architecture_style,
            "modules": modules,
            "deliverables": [
                "technical-architecture.md",
                "component-diagram.mmd",
                "decision-log.md",
            ],
        }
        summary = (
            f"Created {architecture_style} solution with {len(modules)} modules for "
            f"{project.name}."
        )
        return LifecycleStageResult(
            stage=self.stage,
            agent_name=self.name,
            summary=summary,
            artifacts=artifacts,
        )


@dataclass(frozen=True)
class RequirementsAgent:
    stage: str = "requirements"
    name: str = "RequirementsAgent"

    def run(
        self,
        project: LifecycleProject,
        context: dict[str, dict[str, Any]],
    ) -> LifecycleStageResult:
        solution = context.get("solution", {})
        modules = solution.get("modules", [])
        module_names = " ".join(
            str(item.get("name", "")).lower() for item in modules if isinstance(item, dict)
        )
        solution_text = f"{solution.get('architecture_style', '')} {module_names}".lower()

        requirements = tuple(project.business_requirements) + tuple(project.technical_requirements)
        missing: list[str] = []
        for requirement in requirements:
            if not _is_requirement_addressed(requirement, project, solution_text):
                missing.append(requirement)

        passed = len(missing) == 0
        warnings: tuple[str, ...] = ()
        if not passed:
            warnings = ("Some requirements are not covered by the proposed solution.",)

        summary = "Validated proposed solution against project requirements."
        if not passed:
            summary = f"{summary} Missing: {len(missing)}."

        artifacts = {
            "validated_requirements": [req for req in requirements if req not in missing],
            "missing_requirements": missing,
            "total_requirements": len(requirements),
        }
        return LifecycleStageResult(
            stage=self.stage,
            agent_name=self.name,
            summary=summary,
            artifacts=artifacts,
            warnings=warnings,
            passed=passed,
        )


@dataclass(frozen=True)
class DeveloperAgent:
    stage: str = "developer"
    name: str = "DeveloperAgent"

    def run(
        self,
        project: LifecycleProject,
        context: dict[str, dict[str, Any]],
    ) -> LifecycleStageResult:
        solution = context.get("solution", {})
        modules = solution.get("modules", [])
        frontend_language, backend_language = _pick_languages(project)
        components: list[dict[str, str]] = []

        for module in modules:
            if not isinstance(module, dict):
                continue
            module_name = str(module.get("name", "component"))
            if module_name.startswith("web"):
                language = frontend_language
            elif "test" in module_name:
                language = frontend_language
            else:
                language = backend_language
            components.append(
                {
                    "module": module_name,
                    "language": language,
                    "status": "scaffolded",
                }
            )

        artifacts = {
            "components": components,
            "repository_layout": [
                "src/",
                "tests/",
                "docs/",
                ".github/workflows/",
                "azure-pipelines.yml",
            ],
        }
        summary = (
            f"Generated implementation scaffold for {len(components)} components using "
            f"{backend_language}/{frontend_language}."
        )
        return LifecycleStageResult(
            stage=self.stage,
            agent_name=self.name,
            summary=summary,
            artifacts=artifacts,
        )


@dataclass(frozen=True)
class TestAgent:
    stage: str = "testing"
    name: str = "TestAgent"

    def run(
        self,
        project: LifecycleProject,
        context: dict[str, dict[str, Any]],
    ) -> LifecycleStageResult:
        del project
        developer = context.get("developer", {})
        components = developer.get("components", [])
        component_count = len(components) if isinstance(components, list) else 0

        suites = [
            {"type": "unit", "estimated_cases": max(component_count * 3, 3)},
            {"type": "integration", "estimated_cases": max(component_count, 1)},
            {"type": "functional", "estimated_cases": max(component_count // 2, 1)},
        ]
        artifacts = {
            "test_suites": suites,
            "ci_triggers": ["pull_request", "push:main"],
            "feedback_target": "DeveloperAgent",
        }
        summary = f"Prepared test plan with {len(suites)} suites for CI execution."
        return LifecycleStageResult(
            stage=self.stage,
            agent_name=self.name,
            summary=summary,
            artifacts=artifacts,
            passed=component_count > 0,
        )


@dataclass(frozen=True)
class CodeReviewAgent:
    stage: str = "review"
    name: str = "CodeReviewAgent"

    def run(
        self,
        project: LifecycleProject,
        context: dict[str, dict[str, Any]],
    ) -> LifecycleStageResult:
        del project
        developer = context.get("developer", {})
        components = developer.get("components", [])
        component_count = len(components) if isinstance(components, list) else 0

        gates = ["lint", "type-check", "unit-tests", "security-scan", "performance-budget"]
        findings: list[str] = []
        if component_count == 0:
            findings.append("No components available for review.")

        artifacts = {
            "review_gates": gates,
            "pull_request_feedback_mode": "inline-comments",
            "findings": findings,
        }
        summary = "Generated automated review gates and PR feedback strategy."
        return LifecycleStageResult(
            stage=self.stage,
            agent_name=self.name,
            summary=summary,
            artifacts=artifacts,
            passed=component_count > 0,
        )


@dataclass(frozen=True)
class DeploymentAgent:
    stage: str = "deployment"
    name: str = "DeploymentAgent"

    def run(
        self,
        project: LifecycleProject,
        context: dict[str, dict[str, Any]],
    ) -> LifecycleStageResult:
        del context
        platforms = tuple(item.strip().lower() for item in project.ci_cd_platforms if item.strip())
        targets = list(project.deployment_targets)
        pipelines: dict[str, Any] = {}

        if "github_actions" in platforms:
            pipelines["github_actions"] = {
                "workflow": ".github/workflows/ci.yml",
                "stages": ["build", "test", *targets],
                "rollback": "re-deploy previous successful artifact",
            }
        if "azure_devops" in platforms:
            pipelines["azure_devops"] = {
                "pipeline": "azure-pipelines.yml",
                "stages": ["build", "validate", *targets],
                "rollback": "invoke rollback stage with last stable release",
            }

        summary = (
            f"Prepared deployment automation for {len(pipelines)} CI/CD platform(s) across "
            f"{len(targets)} environment(s)."
        )
        return LifecycleStageResult(
            stage=self.stage,
            agent_name=self.name,
            summary=summary,
            artifacts={
                "pipelines": pipelines,
                "targets": targets,
            },
            passed=len(pipelines) > 0,
            warnings=() if pipelines else ("No CI/CD platform selected for deployment.",),
        )
