from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig
from aijurisdictionagents.orchestration.case_workflow import (
    CaseWorkflowRuntime,
    build_initial_case_workflow_state,
)


@pytest.mark.skipif(
    os.getenv("RUN_LOCAL_POSTGRES_CASE_WORKFLOW_TEST") != "1",
    reason="Set RUN_LOCAL_POSTGRES_CASE_WORKFLOW_TEST=1 for the local PostgreSQL integration.",
)
def test_postgres_persists_one_sanitized_terminal_projection(tmp_path: Path) -> None:
    database_url = os.environ["DB_CLOUD"]
    run_suffix = uuid4().hex
    case_id = f"synthetic-termination-{run_suffix}"
    user_id = f"synthetic-user-{run_suffix}"
    state = build_initial_case_workflow_state(
        workflow_run_id=f"synthetic-run-{run_suffix}",
        correlation_id=f"synthetic-correlation-{run_suffix}",
        case_id=case_id,
        session_id=f"synthetic-session-{run_suffix}",
        user_id=user_id,
        jurisdiction="SK",
        language="sk-SK",
        request_text="Synthetic cancellation test without personal data.",
        case_type_key="synthetic.termination",
        routing_confidence=1.0,
        routing_evidence=("synthetic_postgres_integration",),
        graph_key="unsupported_or_human_review",
        graph_version=1,
        flow_key="synthetic.termination",
        flow_version=1,
        flow_definition={"required_facts": []},
    )
    store = CaseWorkflowStore(
        CaseWorkflowStoreConfig(
            db_option="postgres",
            db_cloud=database_url,
            sqlite_path=tmp_path / "unused.sqlite3",
        )
    )
    try:
        outcome = CaseWorkflowRuntime.terminate(
            state, reason="user_cancelled", stage="postgres_integration"
        )
        saved = store.save_run(assignment_id="synthetic-assignment", outcome=outcome)

        assert saved.termination_reason == "user_cancelled"
        assert saved.status == "blocked"
        stale_outcome = CaseWorkflowRuntime.terminate(
            state, reason="operational_failure", stage="stale_concurrent_resume"
        )
        preserved = store.save_run(
            assignment_id="synthetic-assignment", outcome=stale_outcome
        )
        assert preserved.termination_reason == "user_cancelled"
        terminal_events = [
            event
            for event in store.list_events(state["workflow_run_id"], user_id=user_id)
            if event.event_type == "workflow_terminated"
        ]
        assert len(terminal_events) == 1
        assert terminal_events[0].details == {
            "input_attempt_count": 0,
            "quality_revision_count": 0,
            "technical_retry_count": 0,
            "termination_reason": "user_cancelled",
        }
    finally:
        store.delete_case_workflows(case_id=case_id, user_id=user_id)
