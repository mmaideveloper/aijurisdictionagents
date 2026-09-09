from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

repo_root = Path(__file__).resolve().parents[1]
api_root = repo_root / "api" / "aijuristiction-api"
src_root = repo_root / "src"
for import_root in (api_root, src_root):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

demo_db = repo_root / "runs" / "storage" / "api" / "sqlite" / "flow_evaluation_demo.sqlite3"
os.environ["API_FLOW_PACKS_SQLITE_PATH"] = str(demo_db)
os.environ["API_CASE_WORKFLOWS_SQLITE_PATH"] = str(demo_db)

from app.flow_evaluations.models import (  # noqa: E402
    EvaluationCaseCreate,
    EvaluationObservation,
    EvaluationRunCreate,
    EvaluationSuiteCreate,
    FlowPromotionPreviewRequest,
    FlowPromotionRequest,
)
from app.case_workflows.service import CaseWorkflowApplicationService  # noqa: E402
from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig  # noqa: E402
from app.flow_evaluations.service import FlowEvaluationService  # noqa: E402
from app.flow_evaluations.store import FlowEvaluationStore  # noqa: E402
from app.flow_packs.models import FlowPackCreateRequest, FlowPackLockRequest  # noqa: E402
from app.flow_packs.store import FlowPackStore  # noqa: E402


def main() -> None:
    suffix = uuid4().hex[:8]
    flow_store = FlowPackStore.from_env()
    evaluation_store = FlowEvaluationStore.from_env()
    flow_key = f"sk.urbanism.demo.{suffix}"
    flow = flow_store.create(FlowPackCreateRequest(
        flow_key=flow_key, jurisdiction="SK", domain="administrative",
        title="Urban planning demo", description="Synthetic routing demonstration.",
        definition={"graph": "urbanism", "required_facts": ["municipality"]},
        question_kind="general_legal_question", legal_domain="urbanism",
        requested_outcome="legal_information",
        positive_examples=["May I build a garage in this zone?"],
        negative_examples=["Prepare a purchase contract"],
        clarification_policy={"on_low_confidence": "ask_user"}, is_enabled=False,
    ))
    locked = flow_store.lock_for_testing(
        flow_key=flow.flow_key, version=flow.version, actor_id="demo-admin",
        payload=FlowPackLockRequest(reason="Run the synthetic demonstration"), jurisdiction="SK",
    )
    suite = evaluation_store.create_suite(EvaluationSuiteCreate(
        suite_key=f"urbanism-demo-{suffix}", version=1, jurisdiction="SK",
        title="Synthetic urbanism demo", synthetic_only=True, synthetic_data_confirmed=True,
        routing_accuracy_threshold=1.0, retention_days=1,
        cases=[EvaluationCaseCreate(
            case_key="urbanism", mode="routing_only",
            synthetic_input={"question": "May a synthetic resident build a garage?"},
            expected_route=flow_key, human_review_required=True,
        )],
    ), actor_id="demo-admin")
    evaluation_service = FlowEvaluationService(flow_store, evaluation_store)
    run = evaluation_service.evaluate(EvaluationRunCreate(
        idempotency_key=f"demo-idempotency-{suffix}", synthetic_run_id=f"demo-run-{suffix}",
        suite_id=suite.suite_id, flow_key=flow_key, flow_version=1, jurisdiction="SK",
        graph_version="urbanism_graph@1", routing_policy={"confidence_threshold": 0.85},
        provider="azurefoundry", model="configured-demo-model",
        provider_route="offline-admin-evaluation", mode="routing_only",
        observations=[EvaluationObservation(
            case_key="urbanism", actual_route=flow_key, schema_valid=True,
            provenance_valid=True, human_review_present=True,
        )],
    ), actor_id="demo-admin")
    approval = evaluation_service.approve(
        flow_key=flow_key,
        version=1,
        jurisdiction="SK",
        run_id=run.run_id,
        actor_id="demo-reviewer",
        reason="Human review of deterministic synthetic gates",
    )
    workflow_store = CaseWorkflowStore(CaseWorkflowStoreConfig(
        db_option="local", db_cloud="", sqlite_path=demo_db
    ))
    workflow_service = cast(CaseWorkflowApplicationService, SimpleNamespace(
        store=workflow_store,
        validate_assignment=lambda *_args, **_kwargs: (
            "valid", "Deterministic demo compatibility check passed"
        ),
    ))
    promotion_service = FlowEvaluationService(flow_store, evaluation_store, workflow_service)
    target = FlowPromotionPreviewRequest(
        case_type_key="sk.synthetic.urbanism",
        jurisdiction="SK",
        graph_key="urbanism_graph",
        graph_version=1,
        flow_key=flow_key,
        flow_version=1,
    )
    preview = promotion_service.preview_promotion(target)
    promotion = promotion_service.promote(FlowPromotionRequest(
        **target.model_dump(),
        idempotency_key=f"demo-promotion-{suffix}",
        approval_id=approval.approval_id,
        reason="Assign the exact reviewed demo version to new synthetic runs",
        confirmation=True,
        expected_current_assignment_id=(
            preview.current_assignment.assignment_id if preview.current_assignment else None
        ),
    ), actor_id="demo-promoter")
    print(
        f"flow={flow_key}@1 locked={locked.lifecycle_state} run={run.status} "
        f"definition_hash={run.flow_definition_hash[:12]} suite_hash={run.suite_hash[:12]} "
        f"promotion={promotion.action} assignment_hash={promotion.target_assignment_hash[:12]}"
    )


if __name__ == "__main__":
    main()
