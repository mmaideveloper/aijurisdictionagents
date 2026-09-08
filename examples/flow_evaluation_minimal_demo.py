from __future__ import annotations

import os
from pathlib import Path
import sys
from uuid import uuid4

repo_root = Path(__file__).resolve().parents[1]
api_root = repo_root / "api" / "aijuristiction-api"
src_root = repo_root / "src"
for import_root in (api_root, src_root):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

demo_db = repo_root / "runs" / "storage" / "api" / "sqlite" / "flow_evaluation_demo.sqlite3"
os.environ["API_FLOW_PACKS_SQLITE_PATH"] = str(demo_db)

from app.flow_evaluations.models import (  # noqa: E402
    EvaluationCaseCreate,
    EvaluationObservation,
    EvaluationRunCreate,
    EvaluationSuiteCreate,
)
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
    run = FlowEvaluationService(flow_store, evaluation_store).evaluate(EvaluationRunCreate(
        idempotency_key=f"demo-idempotency-{suffix}", synthetic_run_id=f"demo-run-{suffix}",
        suite_id=suite.suite_id, flow_key=flow_key, flow_version=1, jurisdiction="SK",
        graph_version="urbanism-v1", routing_policy={"confidence_threshold": 0.85},
        provider="azurefoundry", model="configured-demo-model",
        provider_route="offline-admin-evaluation", mode="routing_only",
        observations=[EvaluationObservation(
            case_key="urbanism", actual_route=flow_key, schema_valid=True,
            provenance_valid=True, human_review_present=True,
        )],
    ), actor_id="demo-admin")
    print(
        f"flow={flow_key}@1 lifecycle={locked.lifecycle_state} run={run.status} "
        f"definition_hash={run.flow_definition_hash[:12]} suite_hash={run.suite_hash[:12]}"
    )


if __name__ == "__main__":
    main()
