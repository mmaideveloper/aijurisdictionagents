"""Visible synthetic draft -> critique -> revision demo; optionally durable PostgreSQL."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import sys
from typing import Any, Iterator
from urllib.parse import urlsplit
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from langgraph.checkpoint.memory import InMemorySaver
from aijurisdictionagents.orchestration.case_workflow import (
    CaseWorkflowRuntime,
    CaseWorkflowState,
    DeterministicCaseWorkflowServices,
    build_initial_case_workflow_state,
)


class ReflectionDemoServices(DeterministicCaseWorkflowServices):
    """A deliberately incomplete synthetic first draft exercises real graph edges."""

    def draft_documents(self, state: CaseWorkflowState) -> tuple[str, list[dict[str, Any]]]:
        revised = bool(state.get("retry_count"))
        answer = "AI-assisted draft: Synthetic A paid Synthetic B" + (
            " 100 EUR." if revised else "."
        )
        answer += " Human review required before use."
        if revised:
            print("CRITIQUE:", state["critique"]["instruction"])
        print("REVISED RESPONSE:" if revised else "PREVIOUS RESPONSE:", answer)
        return answer, [
            {"provider": "deterministic", "model": "synthetic-demo", "artifact_type": "draft"}
        ]

    def review_output(self, state: CaseWorkflowState) -> tuple[bool, str]:
        return (
            (True, "verified_facts_preserved")
            if "100 EUR" in state["final_answer"]
            else (False, "verified_fact_missing_from_output")
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Use loopback DB_CLOUD and reopen PostgresSaver before resuming",
    )
    args = parser.parse_args()
    run_demo(postgres=args.postgres)


def run_demo(*, postgres: bool = False) -> None:
    run_id = "reflection-demo-" + str(uuid4())
    memory = InMemorySaver()

    @contextmanager
    def saver() -> Iterator[Any]:
        if not postgres:
            yield memory
            return
        from dotenv import load_dotenv
        from langgraph.checkpoint.postgres import PostgresSaver
        from aijurisdictionagents.api_db.config import ApiDataConfig

        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
        config = ApiDataConfig.from_env()
        if urlsplit(config.db_cloud).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("Demo requires loopback PostgreSQL")
        with PostgresSaver.from_conn_string(config.db_cloud) as checkpoint:
            checkpoint.setup()
            yield checkpoint

    services = ReflectionDemoServices(
        legal_requirements=({"content": "Synthetic payment requirement"},),
        legal_source_ids=("synthetic-reflection-law",),
    )
    state = build_initial_case_workflow_state(
        workflow_run_id=run_id,
        correlation_id=run_id,
        case_id=run_id,
        session_id=run_id,
        user_id="synthetic-demo-user",
        jurisdiction="SK",
        language="en",
        request_text="Prepare a synthetic payment confirmation.",
        case_type_key="sk.civil.payment_confirmation",
        routing_confidence=1.0,
        routing_evidence=["synthetic demo"],
        graph_key="legal_document_workflow",
        graph_version=5,
        flow_key="synthetic.reflection",
        flow_version=1,
        flow_definition={
            "required_facts": ["amount"],
            "mcp_retrieval": {
                "schema_version": 1,
                "policy_id": "synthetic.reflection.v1",
                "required": True,
                "case_type_keys": ["sk.civil.payment_confirmation"],
                "jurisdictions": ["SK"],
                "query_keys": ["payment_confirmation_legal_requirements"],
                "default_query": "payment",
            },
            "tool_policy": {"schema_version": 1, "tools": []},
            "presentation_policy": {
                "schema_version": 1,
                "policy_id": "synthetic.presentation.v1",
                "default_renderer": "text",
                "renderers": [{"renderer_id": "text", "version": 1}],
                "user_overrides": ["text"],
            },
        },
    )
    with saver() as checkpoint:
        first = CaseWorkflowRuntime(services=services, checkpointer=checkpoint).start(state)
        assert first.is_waiting
        print("INTERRUPTED: amount required; constructing a new runtime before resume.")
    with saver() as checkpoint:
        runtime = CaseWorkflowRuntime(services=services, checkpointer=checkpoint)
        result = runtime.resume(
            graph_key=state["graph_key"], graph_version=5, workflow_run_id=run_id, value="100 EUR"
        )
        assert result.state["status"] == "completed"
        assert result.state["retry_count"] == 1
        assert result.state["quality_revision_count"] == 1
        print("PASS: one revision; provider=deterministic; model=synthetic-demo; status=completed")
        print(
            "Durability:",
            "PostgreSQL; reopened saver"
            if postgres
            else "offline reference only; memory is not durable",
        )
        checkpoint.delete_thread(run_id)


if __name__ == "__main__":
    main()
