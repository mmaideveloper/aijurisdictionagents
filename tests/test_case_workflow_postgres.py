"""Opt-in PostgreSQL integration checks; never connect to a non-loopback database."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import uuid4

from langgraph.checkpoint.postgres import PostgresSaver
import pytest

from app.case_workflows.service import CaseWorkflowApplicationService, WorkflowConfigurationError
from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig
from aijurisdictionagents.orchestration.case_workflow import CaseWorkflowRuntime
from test_case_workflow import _state, RevisingServices


@pytest.fixture
def durable_workflow(tmp_path: Path):
    target = os.getenv("DB_CLOUD", "")
    if os.getenv("DB_OPTION") != "postgres" or urlsplit(target).hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        pytest.skip(
            "Requires explicitly configured synthetic loopback PostgreSQL DB_OPTION/DB_CLOUD"
        )
    state = _state(graph_version=5)
    state["workflow_run_id"] = "reflection-integration-" + str(uuid4())
    state["case_id"] = state["workflow_run_id"]
    state["correlation_id"] = state["workflow_run_id"]
    state["session_id"] = state["workflow_run_id"]
    store = CaseWorkflowStore(
        CaseWorkflowStoreConfig("postgres", target, tmp_path / "unused.sqlite3")
    )
    with ExitStack() as stack:

        def make_service():
            saver = stack.enter_context(PostgresSaver.from_conn_string(target))
            saver.setup()
            runtime = CaseWorkflowRuntime(
                services=RevisingServices(legal_source_ids=("synthetic-law",)), checkpointer=saver
            )
            return CaseWorkflowApplicationService(
                store=store,
                runtime=runtime,
                flow_store=cast(Any, None),
                template_store=cast(Any, None),
            )

        first = make_service()
        outcome = first.runtime.start(state)
        store.save_run(assignment_id="synthetic-assignment-753", outcome=outcome)
        try:
            yield state, first, make_service, store
        finally:
            store.delete_case_workflows(case_id=state["case_id"], user_id=state["user_id"])


def test_two_instances_serialize_duplicate_resume(durable_workflow):
    state, first, make_service, store = durable_workflow
    second = make_service()
    run = store.get_run(state["workflow_run_id"], user_id=state["user_id"])
    token = run.pending_action["resume_token"]

    def resume(service):
        try:
            service.resume(
                state["workflow_run_id"],
                user_id=state["user_id"],
                value="Synthetic A",
                resume_token=token,
            )
            return "accepted"
        except WorkflowConfigurationError as exc:
            assert "workflow_resume_stale" in str(exc)
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(resume, [first, second])) == ["accepted", "stale"]
    current = store.get_run_state(state["workflow_run_id"], user_id=state["user_id"])
    assert current["facts"] == {"payer": "Synthetic A"}
    assert sum(e["event_type"] == "workflow_resumed" for e in current["events"]) == 1


def test_projection_failure_is_repaired_without_reexecuting_resume(durable_workflow, monkeypatch):
    state, first, make_service, store = durable_workflow
    token = store.get_run(state["workflow_run_id"], user_id=state["user_id"]).pending_action[
        "resume_token"
    ]
    original = store.save_run

    def fail_after_checkpoint(**kwargs):
        if kwargs["outcome"].state.get("facts", {}).get("payer") == "Synthetic A":
            raise RuntimeError("synthetic_projection_write_failure")
        return original(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(store, "save_run", fail_after_checkpoint)
        with pytest.raises(RuntimeError, match="synthetic_projection_write_failure"):
            first.resume(
                state["workflow_run_id"],
                user_id=state["user_id"],
                value="Synthetic A",
                resume_token=token,
            )
    # A separately constructed saver/runtime observes the committed checkpoint.
    second = make_service()
    with pytest.raises(WorkflowConfigurationError, match="workflow_resume_stale"):
        second.resume(
            state["workflow_run_id"],
            user_id=state["user_id"],
            value="Synthetic A",
            resume_token=token,
        )
    recovered = store.get_run_state(state["workflow_run_id"], user_id=state["user_id"])
    assert recovered["facts"] == {"payer": "Synthetic A"}
    assert sum(e["event_type"] == "workflow_resumed" for e in recovered["events"]) == 1


def test_checkpoint_survives_a_separate_interpreter(durable_workflow):
    state, first, make_service, store = durable_workflow
    code = """
import os, sys
from langgraph.checkpoint.postgres import PostgresSaver
from aijurisdictionagents.orchestration.case_workflow import CaseWorkflowRuntime, DeterministicCaseWorkflowServices
with PostgresSaver.from_conn_string(os.environ['DB_CLOUD']) as saver:
    runtime = CaseWorkflowRuntime(services=DeterministicCaseWorkflowServices(), checkpointer=saver)
    outcome = runtime.resume(graph_key='legal_document_workflow', graph_version=5,
        workflow_run_id=sys.argv[1], value='Synthetic A')
    assert outcome.is_waiting and outcome.state['facts']['payer'] == 'Synthetic A'
"""
    subprocess.run(
        [sys.executable, "-c", code, state["workflow_run_id"]], check=True, capture_output=True
    )
    second = make_service()
    recovered = second.runtime.checkpoint_outcome(state)
    result = second.resume(
        state["workflow_run_id"],
        user_id=state["user_id"],
        value="Synthetic B",
        resume_token=recovered.state["pending_action"]["resume_token"],
    )
    assert result.status == "waiting_for_user"
    current = store.get_run_state(state["workflow_run_id"], user_id=state["user_id"])
    assert current["facts"] == {"payer": "Synthetic A", "recipient": "Synthetic B"}
