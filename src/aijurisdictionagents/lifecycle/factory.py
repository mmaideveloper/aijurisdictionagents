from __future__ import annotations

from dataclasses import dataclass

from .agents import (
    CodeReviewAgent,
    DeploymentAgent,
    DeveloperAgent,
    LifecycleAgent,
    RequirementsAgent,
    SolutionAgent,
    TestAgent,
)

DEFAULT_STAGE_ORDER: tuple[str, ...] = (
    "solution",
    "requirements",
    "developer",
    "testing",
    "review",
    "deployment",
)


@dataclass(frozen=True)
class LifecycleAutomationConfig:
    enabled_stages: tuple[str, ...] = DEFAULT_STAGE_ORDER
    stop_on_failure: bool = True


def build_lifecycle_agents(config: LifecycleAutomationConfig) -> list[LifecycleAgent]:
    by_stage: dict[str, LifecycleAgent] = {
        "solution": SolutionAgent(),
        "requirements": RequirementsAgent(),
        "developer": DeveloperAgent(),
        "testing": TestAgent(),
        "review": CodeReviewAgent(),
        "deployment": DeploymentAgent(),
    }

    agents: list[LifecycleAgent] = []
    for stage in config.enabled_stages:
        key = stage.strip().lower()
        agent = by_stage.get(key)
        if agent is not None:
            agents.append(agent)
    return agents
