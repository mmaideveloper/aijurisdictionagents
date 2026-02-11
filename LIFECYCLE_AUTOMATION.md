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

## Task Status Flow Per Agent

Project status values used in this repository:

- `Backlog`
- `Ready For Solution`
- `In progress`
- `In review`
- `Done`

Recommended status transition per lifecycle agent:

| Agent | Task status before agent runs | Final status after agent runs (success) | Final status after agent runs (issues found) |
| --- | --- | --- | --- |
| `SolutionAgent` | `Ready For Solution` | `In progress` | `Ready For Solution` |
| `RequirementsAgent` | `In progress` | `In progress` | `In progress` |
| `DeveloperAgent` | `In progress` | `In progress` | `In progress` |
| `TestAgent` | `In progress` | `In review` | `In progress` |
| `CodeReviewAgent` | `In review` | `In review` (approved and waiting merge/deploy) | `In progress` (changes requested) |
| `DeploymentAgent` | `In review` | `Done` | `In review` |

Notes:

- Status changes are policy guidance for task orchestration.
- Current lifecycle workflows generate stage artifacts and do not directly change GitHub Project status.
- Project status updates can be applied with `scripts/project_status.ps1`.
- `Backlog` is reserved for raw ideas and is not processed by `SolutionAgent`.
- `SolutionAgent` runs only when `task_status=Ready For Solution` (enforced in `scripts/lifecycle_agent_run.py` and `lifecycle-solution-agent` workflow).

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

## MCP Server Setup (Microsoft Learn)

Add the Microsoft Learn MCP server to Codex:

```bash
codex mcp add "microsoft-learn" --url "https://learn.microsoft.com/api/mcp"
```
