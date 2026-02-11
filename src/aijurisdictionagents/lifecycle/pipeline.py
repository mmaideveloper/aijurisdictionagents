from __future__ import annotations

import logging
from typing import Any, Sequence

from ..observability import TraceRecorder
from .agents import LifecycleAgent
from .factory import LifecycleAutomationConfig, build_lifecycle_agents
from .models import LifecycleProject, LifecycleRunResult, LifecycleStageResult, utc_now_iso


class LifecyclePipeline:
    def __init__(
        self,
        agents: Sequence[LifecycleAgent],
        *,
        stop_on_failure: bool = True,
        trace: TraceRecorder | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.agents = list(agents)
        self.stop_on_failure = stop_on_failure
        self.trace = trace
        self.logger = logger or logging.getLogger(__name__)

    def run(self, project: LifecycleProject) -> LifecycleRunResult:
        started_at = utc_now_iso()
        context: dict[str, dict[str, Any]] = {}
        stage_results: list[LifecycleStageResult] = []
        succeeded = True

        for agent in self.agents:
            self.logger.info("Running lifecycle stage '%s' via %s", agent.stage, agent.name)
            stage_result = agent.run(project, context)
            context[stage_result.stage] = stage_result.artifacts
            stage_results.append(stage_result)

            if self.trace is not None:
                self.trace.record_event(
                    "lifecycle_stage",
                    {
                        "project_name": project.name,
                        "stage": stage_result.stage,
                        "agent": stage_result.agent_name,
                        "passed": stage_result.passed,
                        "warnings": list(stage_result.warnings),
                    },
                )

            if not stage_result.passed:
                succeeded = False
                self.logger.warning("Lifecycle stage '%s' failed.", stage_result.stage)
                if self.stop_on_failure:
                    break

        completed_at = utc_now_iso()
        run_result = LifecycleRunResult(
            project=project,
            started_at=started_at,
            completed_at=completed_at,
            succeeded=succeeded and len(stage_results) == len(self.agents),
            stage_results=tuple(stage_results),
        )

        if self.trace is not None:
            self.trace.record_event(
                "lifecycle_result",
                {
                    "project_name": project.name,
                    "succeeded": run_result.succeeded,
                    "stage_count": len(run_result.stage_results),
                },
            )

        return run_result


def build_default_pipeline(
    config: LifecycleAutomationConfig | None = None,
    *,
    trace: TraceRecorder | None = None,
    logger: logging.Logger | None = None,
) -> LifecyclePipeline:
    effective_config = config or LifecycleAutomationConfig()
    return LifecyclePipeline(
        build_lifecycle_agents(effective_config),
        stop_on_failure=effective_config.stop_on_failure,
        trace=trace,
        logger=logger,
    )
