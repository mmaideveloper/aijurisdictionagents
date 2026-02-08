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
