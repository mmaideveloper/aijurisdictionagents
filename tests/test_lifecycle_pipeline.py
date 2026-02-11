from __future__ import annotations

from aijurisdictionagents.lifecycle import (
    LifecycleAutomationConfig,
    LifecycleProject,
    build_default_pipeline,
)


def _default_project() -> LifecycleProject:
    return LifecycleProject(
        name="Lifecycle MVP",
        idea="Build a fullstack portal with API, worker, and data store.",
        project_type="fullstack",
        preferred_stack=("python", "react"),
        business_requirements=("API access for partners", "Data storage for user profiles"),
        technical_requirements=("CI pipeline", "deployment rollback"),
        deployment_targets=("dev", "staging", "production"),
        ci_cd_platforms=("github_actions", "azure_devops"),
    )


def test_lifecycle_pipeline_default_flow() -> None:
    pipeline = build_default_pipeline()
    result = pipeline.run(_default_project())

    assert result.succeeded
    assert [stage.stage for stage in result.stage_results] == [
        "solution",
        "requirements",
        "developer",
        "testing",
        "review",
        "deployment",
    ]
    deployment = result.stage_results[-1].artifacts["pipelines"]
    assert "github_actions" in deployment
    assert "azure_devops" in deployment


def test_lifecycle_pipeline_stage_filtering() -> None:
    config = LifecycleAutomationConfig(
        enabled_stages=("solution", "developer", "testing", "deployment"),
        stop_on_failure=True,
    )
    pipeline = build_default_pipeline(config)
    result = pipeline.run(_default_project())

    assert result.succeeded
    assert [stage.stage for stage in result.stage_results] == [
        "solution",
        "developer",
        "testing",
        "deployment",
    ]


def test_lifecycle_pipeline_fails_when_requirement_is_missing() -> None:
    project = LifecycleProject(
        name="Gap project",
        idea="Build a small backend API.",
        project_type="backend",
        preferred_stack=("python",),
        technical_requirements=("quantum-resistant ledger mesh",),
    )
    pipeline = build_default_pipeline()
    result = pipeline.run(project)

    assert not result.succeeded
    assert result.stage_results[-1].stage == "requirements"
    assert not result.stage_results[-1].passed
    missing = result.stage_results[-1].artifacts["missing_requirements"]
    assert "quantum-resistant ledger mesh" in missing


def test_lifecycle_pipeline_single_cicd_platform() -> None:
    project = LifecycleProject(
        name="Single pipeline project",
        idea="Frontend portal for customer requests.",
        project_type="frontend",
        preferred_stack=("react",),
        ci_cd_platforms=("github_actions",),
    )
    pipeline = build_default_pipeline()
    result = pipeline.run(project)

    assert result.succeeded
    deployment = result.stage_results[-1].artifacts["pipelines"]
    assert "github_actions" in deployment
    assert "azure_devops" not in deployment
