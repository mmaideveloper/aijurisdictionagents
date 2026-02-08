# Lifecycle Automation (Issue #69 MVP)

This module introduces a modular AI-agent pipeline that automates a software lifecycle from
solution design to deployment planning.

## What Is Included

- `SolutionAgent`: converts a project idea into architecture style and modules.
- `RequirementsAgent`: validates architecture against business/technical requirements.
- `DeveloperAgent`: generates implementation scaffold metadata and repository layout.
- `TestAgent`: generates test suites and CI trigger strategy.
- `CodeReviewAgent`: defines quality gates and PR review feedback mode.
- `DeploymentAgent`: prepares CI/CD deployment plans for GitHub Actions and Azure DevOps.

## Module Layout

- `src/aijurisdictionagents/lifecycle/models.py`
- `src/aijurisdictionagents/lifecycle/agents.py`
- `src/aijurisdictionagents/lifecycle/factory.py`
- `src/aijurisdictionagents/lifecycle/pipeline.py`
- `scripts/lifecycle_agent_run.py`

## GitHub Workflows (One Per Agent)

- `.github/workflows/lifecycle_solution_agent.yml`
- `.github/workflows/lifecycle_requirements_agent.yml`
- `.github/workflows/lifecycle_developer_agent.yml`
- `.github/workflows/lifecycle_testing_agent.yml`
- `.github/workflows/lifecycle_review_agent.yml`
- `.github/workflows/lifecycle_deployment_agent.yml`

Shared reusable workflow:

- `.github/workflows/lifecycle_agent_runner.yml`

Each workflow is manually triggerable (`workflow_dispatch`) and uploads a stage JSON artifact.
The selected stage runs with prerequisites (for example, `testing` runs `solution -> requirements ->
developer -> testing`) so agent context is available.

## Configuring Agents for New Projects

Use `LifecycleAutomationConfig` to choose the active stages:

```python
from aijurisdictionagents.lifecycle import LifecycleAutomationConfig, build_default_pipeline

config = LifecycleAutomationConfig(
    enabled_stages=("solution", "developer", "testing", "deployment"),
    stop_on_failure=True,
)
pipeline = build_default_pipeline(config)
```

## Minimal Runnable Example

```bash
python examples/lifecycle_automation_demo.py
```

Default project minimal example remains:

```bash
python examples/minimal_demo.py
```

Single-stage local run example:

```bash
python scripts/lifecycle_agent_run.py --stage solution --project-name "Demo" --idea "Build a fullstack app." --output runs/lifecycle/solution_agent_result.json
```
