from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.flow_evaluations.api import get_flow_evaluation_store
from app.case_workflows.service import get_case_workflow_service
from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig
from app.flow_packs.api import get_flow_pack_store
from app.main import app

client = TestClient(app)
HEADERS = {"x-api-key": "aijuris", "x-admin-api-key": "admin-secret"}


@pytest.fixture(autouse=True)
def isolated_stores() -> Iterator[None]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        os.environ["API_FLOW_PACKS_SQLITE_PATH"] = str(Path(tmp_dir) / "flows.sqlite3")
        os.environ["API_CASE_WORKFLOWS_SQLITE_PATH"] = str(Path(tmp_dir) / "workflows.sqlite3")
        os.environ["JURISDIGTA_ADMIN_API_KEY"] = "admin-secret"
        workflow_store = CaseWorkflowStore(CaseWorkflowStoreConfig(
            db_option="local", db_cloud="", sqlite_path=Path(tmp_dir) / "workflows.sqlite3"
        ))
        workflow_service = SimpleNamespace(
            store=workflow_store,
            validate_assignment=lambda *_args, **_kwargs: (
                "valid", "Graph, case type, and immutable flow version are compatible"
            ),
        )
        app.dependency_overrides[get_case_workflow_service] = lambda: workflow_service
        get_flow_pack_store.cache_clear()
        get_flow_evaluation_store.cache_clear()
        yield
        app.dependency_overrides.pop(get_case_workflow_service, None)
        get_flow_pack_store.cache_clear()
        get_flow_evaluation_store.cache_clear()
        os.environ.pop("API_FLOW_PACKS_SQLITE_PATH", None)
        os.environ.pop("API_CASE_WORKFLOWS_SQLITE_PATH", None)
        os.environ.pop("JURISDIGTA_ADMIN_API_KEY", None)


def _create_and_lock_flow() -> tuple[str, dict[str, object]]:
    flow_key = f"sk.urbanism.general.{uuid4().hex[:8]}"
    flow_payload: dict[str, object] = {
        "flow_key": flow_key, "jurisdiction": "SK", "domain": "administrative",
        "title": "Urban planning questions", "description": "Synthetic urban planning test flow",
        "definition": {"graph": "urbanism", "required_facts": ["municipality"]},
        "question_kind": "general_legal_question", "legal_domain": "urbanism",
        "requested_outcome": "legal_information",
        "positive_examples": ["Can I build a garage in this zone?"],
        "negative_examples": ["Create a purchase contract"],
        "clarification_policy": {"on_low_confidence": "ask_user"}, "is_enabled": False,
    }
    created = client.post("/v1/flow-packs", headers=HEADERS, json=flow_payload)
    assert created.status_code == 201
    locked = client.post(
        f"/v1/flow-packs/{flow_key}/versions/1/lock-for-testing", headers=HEADERS,
        json={"reason": "Synthetic suite prepared"},
    )
    assert locked.status_code == 200
    return flow_key, locked.json()


def test_admin_cannot_create_an_enabled_flow_or_skip_evaluation() -> None:
    payload = {
        "flow_key": f"sk.urbanism.bypass.{uuid4().hex[:8]}", "jurisdiction": "SK",
        "domain": "administrative", "title": "Bypass attempt",
        "description": "A valid flow that must still start as draft.",
        "definition": {"graph": "urbanism"}, "question_kind": "legal_question",
        "legal_domain": "urbanism", "requested_outcome": "legal_information",
        "positive_examples": ["Is this building allowed?"], "negative_examples": [],
        "clarification_policy": {"on_low_confidence": "ask_user"}, "is_enabled": True,
    }
    response = client.post("/v1/flow-packs", headers=HEADERS, json=payload)
    assert response.status_code == 409


def _create_suite(flow_key: str) -> dict[str, object]:
    response = client.post("/v1/flow-evaluations/suites", headers=HEADERS, json={
        "suite_key": f"urbanism-routing-{uuid4().hex[:8]}", "version": 1,
        "jurisdiction": "SK", "title": "Synthetic urbanism routing suite",
        "synthetic_only": True, "synthetic_data_confirmed": True,
        "routing_accuracy_threshold": 1.0, "retention_days": 7,
        "cases": [{
            "case_key": "urbanism-positive", "mode": "routing_only",
            "synthetic_input": {"question": "May a synthetic resident build a garage?"},
            "expected_route": flow_key, "required_source_ids": [],
            "human_review_required": True,
        }],
    })
    assert response.status_code == 201
    assert "synthetic_input" not in response.text
    return response.json()


def _run_payload(flow_key: str, suite_id: object, *, privacy_violations: int = 0) -> dict[str, object]:
    return {
        "idempotency_key": f"idem-{uuid4()}", "synthetic_run_id": f"syn-{uuid4()}",
        "suite_id": suite_id, "flow_key": flow_key, "flow_version": 1, "jurisdiction": "SK",
        "graph_version": "urbanism_graph@1",
        "routing_policy": {"confidence_threshold": 0.85, "margin": 0.15},
        "provider": "azurefoundry", "model": "configured-test-model",
        "provider_route": "offline-admin-evaluation", "mode": "routing_only",
        "observations": [{
            "case_key": "urbanism-positive", "actual_route": flow_key, "source_ids": [],
            "schema_valid": True, "provenance_valid": True,
            "privacy_violation_count": privacy_violations,
            "unsupported_auto_finalization": False, "human_review_present": True,
        }],
    }


def test_successful_offline_evaluation_approval_publish_and_retire() -> None:
    db_path = Path(os.environ["API_FLOW_PACKS_SQLITE_PATH"])
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("CREATE TABLE case_workflow_assignments (marker TEXT)")
        conn.execute("CREATE TABLE sessions (marker TEXT)")
        conn.execute("INSERT INTO case_workflow_assignments VALUES ('production-sentinel')")
        conn.execute("INSERT INTO sessions VALUES ('user-session-sentinel')")
        conn.commit()
    flow_key, locked = _create_and_lock_flow()
    suite = _create_suite(flow_key)
    payload = _run_payload(flow_key, suite["suite_id"])
    run = client.post("/v1/flow-evaluations/runs", headers=HEADERS, json=payload)
    assert run.status_code == 201
    run_body = run.json()
    assert run_body["status"] == "passed"
    assert run_body["flow_definition_hash"] == locked["definition_hash"]
    assert run_body["gates"]["privacy"] is True
    assert "observations" not in run.text

    repeated = client.post("/v1/flow-evaluations/runs", headers=HEADERS, json=payload)
    assert repeated.status_code == 201
    assert repeated.json()["run_id"] == run_body["run_id"]

    approval = client.post(
        f"/v1/flow-evaluations/flows/{flow_key}/versions/1/production-approval",
        params={"jurisdiction": "SK"}, headers=HEADERS,
        json={"run_id": run_body["run_id"], "reason": "Human reviewer accepted all gates"},
    )
    assert approval.status_code == 200
    published = client.post(f"/v1/flow-packs/{flow_key}/versions/1/enable", headers=HEADERS)
    assert published.status_code == 200
    assert published.json()["lifecycle_state"] == "published"
    retired = client.post(f"/v1/flow-packs/{flow_key}/versions/1/disable", headers=HEADERS)
    assert retired.status_code == 200
    assert retired.json()["lifecycle_state"] == "retired"
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT marker FROM case_workflow_assignments").fetchall() == [
            ("production-sentinel",)
        ]
        assert conn.execute("SELECT marker FROM sessions").fetchall() == [("user-session-sentinel",)]


def test_privacy_gate_failure_cannot_be_approved() -> None:
    flow_key, _ = _create_and_lock_flow()
    suite = _create_suite(flow_key)
    run = client.post(
        "/v1/flow-evaluations/runs", headers=HEADERS,
        json=_run_payload(flow_key, suite["suite_id"], privacy_violations=1),
    )
    assert run.status_code == 201
    assert run.json()["status"] == "failed"
    assert run.json()["gates"]["privacy"] is False
    approval = client.post(
        f"/v1/flow-evaluations/flows/{flow_key}/versions/1/production-approval",
        params={"jurisdiction": "SK"}, headers=HEADERS,
        json={"run_id": run.json()["run_id"], "reason": "Should not be accepted"},
    )
    assert approval.status_code == 409
    current = client.get(
        f"/v1/flow-packs/{flow_key}/versions/1", params={"jurisdiction": "SK"}, headers=HEADERS
    )
    assert current.json()["lifecycle_state"] == "test_ready"


def _approve(flow_key: str) -> dict[str, object]:
    suite = _create_suite(flow_key)
    run = client.post(
        "/v1/flow-evaluations/runs",
        headers=HEADERS,
        json=_run_payload(flow_key, suite["suite_id"]),
    )
    assert run.status_code == 201
    approval = client.post(
        f"/v1/flow-evaluations/flows/{flow_key}/versions/1/production-approval",
        params={"jurisdiction": "SK"},
        headers=HEADERS,
        json={"run_id": run.json()["run_id"], "reason": "Human reviewer accepted all gates"},
    )
    assert approval.status_code == 200
    return approval.json()


def test_promotion_is_atomic_idempotent_audited_and_rollback_uses_same_gates() -> None:
    prior_key, _ = _create_and_lock_flow()
    _approve(prior_key)
    prior_publish = client.post(
        f"/v1/flow-packs/{prior_key}/versions/1/enable", headers=HEADERS
    )
    assert prior_publish.status_code == 200
    refreshed_prior_approval = _approve(prior_key)
    assert refreshed_prior_approval["approval_id"]
    still_published = client.get(
        f"/v1/flow-packs/{prior_key}/versions/1",
        params={"jurisdiction": "SK"},
        headers=HEADERS,
    )
    assert still_published.json()["lifecycle_state"] == "published"

    workflow_store = app.dependency_overrides[get_case_workflow_service]().store
    prior_assignment = workflow_store.assign(
        case_type_key="sk.synthetic.urbanism",
        jurisdiction="SK",
        graph_key="urbanism_graph",
        graph_version=1,
        flow_key=prior_key,
        flow_version=1,
        created_by="seed-admin",
    )
    pinned_run_id = f"run-{uuid4()}"
    with closing(sqlite3.connect(os.environ["API_CASE_WORKFLOWS_SQLITE_PATH"])) as conn:
        conn.execute(
            "INSERT INTO case_workflow_runs (workflow_run_id, correlation_id, case_id, "
            "session_id, user_id, jurisdiction, case_type_key, assignment_id, graph_key, "
            "graph_version, flow_key, flow_version, status, current_stage, termination_reason, "
            "state_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?)",
            (
                pinned_run_id, "correlation-1", "synthetic-case-1", "session-1", "user-1",
                "SK", "sk.synthetic.urbanism", prior_assignment.assignment_id,
                "urbanism_graph", 1, prior_key, 1, "waiting_for_user", "intake", "",
                "{}", "2026-08-01T00:00:00+00:00", "2026-08-01T00:00:00+00:00",
            ),
        )
        conn.commit()
    candidate_key, _ = _create_and_lock_flow()
    approval = _approve(candidate_key)

    preview_payload = {
        "case_type_key": "sk.synthetic.urbanism",
        "jurisdiction": "SK",
        "graph_key": "urbanism_graph",
        "graph_version": 1,
        "flow_key": candidate_key,
        "flow_version": 1,
    }
    preview = client.post(
        "/v1/flow-evaluations/promotions/preview",
        headers=HEADERS,
        json=preview_payload,
    )
    assert preview.status_code == 200
    assert preview.json()["can_promote"] is True
    assert preview.json()["current_assignment"]["assignment_id"] == prior_assignment.assignment_id
    assert preview.json()["approval"]["approval_id"] == approval["approval_id"]

    promotion_payload = {
        **preview_payload,
        "idempotency_key": f"promotion-{uuid4()}",
        "approval_id": approval["approval_id"],
        "reason": "Promote exact tested candidate for synthetic new runs",
        "confirmation": True,
        "expected_current_assignment_id": prior_assignment.assignment_id,
    }
    promoted = client.post(
        "/v1/flow-evaluations/promotions", headers=HEADERS, json=promotion_payload
    )
    assert promoted.status_code == 201, promoted.text
    promoted_body = promoted.json()
    assert promoted_body["action"] == "promote"
    assert promoted_body["prior_assignment"]["assignment_id"] == prior_assignment.assignment_id
    assert promoted_body["target_assignment"]["flow_key"] == candidate_key
    assert promoted_body["approval"]["suite_hash"]
    assert promoted_body["target_assignment_hash"]
    assert promoted_body["retention_until"] > promoted_body["promoted_at"]

    repeated = client.post(
        "/v1/flow-evaluations/promotions", headers=HEADERS, json=promotion_payload
    )
    assert repeated.status_code == 201
    assert repeated.json()["promotion_id"] == promoted_body["promotion_id"]
    active = workflow_store.get_active_assignment(
        case_type_key="sk.synthetic.urbanism", jurisdiction="SK"
    )
    assert active.assignment_id == promoted_body["target_assignment"]["assignment_id"]

    rollback = client.post(
        f"/v1/flow-evaluations/promotions/{promoted_body['promotion_id']}/rollback",
        headers=HEADERS,
        json={
            "idempotency_key": f"rollback-{uuid4()}",
            "reason": "Restore the prior reviewed immutable version",
            "confirmation": True,
            "expected_current_assignment_id": active.assignment_id,
        },
    )
    assert rollback.status_code == 201, rollback.text
    rollback_body = rollback.json()
    assert rollback_body["action"] == "rollback"
    assert rollback_body["rollback_of_promotion_id"] == promoted_body["promotion_id"]
    assert rollback_body["target_assignment"]["flow_key"] == prior_key
    history = client.get(
        "/v1/flow-evaluations/promotions",
        params={"jurisdiction": "SK", "case_type_key": "sk.synthetic.urbanism"},
        headers=HEADERS,
    )
    assert history.status_code == 200
    assert [item["action"] for item in history.json()["items"]] == ["rollback", "promote"]
    with closing(sqlite3.connect(os.environ["API_CASE_WORKFLOWS_SQLITE_PATH"])) as conn:
        pinned = conn.execute(
            "SELECT assignment_id, graph_key, graph_version, flow_key, flow_version "
            "FROM case_workflow_runs WHERE workflow_run_id = ?",
            (pinned_run_id,),
        ).fetchone()
    assert pinned == (prior_assignment.assignment_id, "urbanism_graph", 1, prior_key, 1)

    with closing(sqlite3.connect(os.environ["API_FLOW_PACKS_SQLITE_PATH"])) as conn:
        conn.execute(
            "UPDATE flow_promotion_provenance SET retention_until = ?",
            ("2020-01-01T00:00:00+00:00",),
        )
        conn.commit()
    purge = client.delete("/v1/flow-evaluations/promotions/expired", headers=HEADERS)
    assert purge.status_code == 200
    assert purge.json() == {"deleted_promotions": 2}
    history_after_purge = client.get(
        "/v1/flow-evaluations/promotions",
        params={"jurisdiction": "SK", "case_type_key": "sk.synthetic.urbanism"},
        headers=HEADERS,
    )
    assert history_after_purge.json()["items"] == []


def test_unapproved_flow_cannot_be_promoted() -> None:
    flow_key, _ = _create_and_lock_flow()
    payload = {
        "case_type_key": "sk.synthetic.urbanism",
        "jurisdiction": "SK",
        "graph_key": "urbanism_graph",
        "graph_version": 1,
        "flow_key": flow_key,
        "flow_version": 1,
    }
    preview = client.post(
        "/v1/flow-evaluations/promotions/preview", headers=HEADERS, json=payload
    )
    assert preview.status_code == 200
    assert preview.json()["can_promote"] is False
    assert "production_approval_missing" in preview.json()["blockers"]


def test_promotion_rejects_a_stale_assignment_preview() -> None:
    prior_key, _ = _create_and_lock_flow()
    _approve(prior_key)
    assert client.post(f"/v1/flow-packs/{prior_key}/versions/1/enable", headers=HEADERS).status_code == 200
    workflow_store = app.dependency_overrides[get_case_workflow_service]().store
    prior = workflow_store.assign(
        case_type_key="sk.synthetic.urbanism",
        jurisdiction="SK",
        graph_key="urbanism_graph",
        graph_version=1,
        flow_key=prior_key,
        flow_version=1,
        created_by="seed-admin",
    )
    candidate_key, _ = _create_and_lock_flow()
    approval = _approve(candidate_key)
    replacement = workflow_store.assign(
        case_type_key="sk.synthetic.urbanism",
        jurisdiction="SK",
        graph_key="urbanism_graph",
        graph_version=1,
        flow_key=prior_key,
        flow_version=1,
        created_by="concurrent-admin",
    )

    response = client.post(
        "/v1/flow-evaluations/promotions",
        headers=HEADERS,
        json={
            "idempotency_key": f"promotion-{uuid4()}",
            "approval_id": approval["approval_id"],
            "case_type_key": "sk.synthetic.urbanism",
            "jurisdiction": "SK",
            "graph_key": "urbanism_graph",
            "graph_version": 1,
            "flow_key": candidate_key,
            "flow_version": 1,
            "reason": "Attempt promotion from stale preview",
            "confirmation": True,
            "expected_current_assignment_id": prior.assignment_id,
        },
    )
    assert response.status_code == 409
    assert "changed after preview" in response.json()["detail"]
    active = workflow_store.get_active_assignment(
        case_type_key="sk.synthetic.urbanism", jurisdiction="SK"
    )
    assert active.assignment_id == replacement.assignment_id
