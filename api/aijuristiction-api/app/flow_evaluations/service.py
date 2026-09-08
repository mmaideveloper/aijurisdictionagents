from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from app.flow_evaluations.models import (
    EvaluationRunCreate,
    EvaluationRunResponse,
    ProductionApprovalResponse,
)
from app.flow_evaluations.store import EvaluationConflictError, FlowEvaluationStore
from app.flow_packs.store import FlowPackImmutableError, FlowPackStore


class FlowEvaluationService:
    def __init__(self, flow_store: FlowPackStore, evaluation_store: FlowEvaluationStore) -> None:
        self._flows = flow_store
        self._evaluations = evaluation_store

    def evaluate(self, payload: EvaluationRunCreate, *, actor_id: str) -> EvaluationRunResponse:
        existing = self._evaluations.get_run_by_idempotency_key(payload.idempotency_key)
        if existing:
            if (
                existing.synthetic_run_id != payload.synthetic_run_id
                or existing.suite_id != payload.suite_id
                or existing.flow_key != payload.flow_key
                or existing.flow_version != payload.flow_version
                or existing.mode != payload.mode
            ):
                raise EvaluationConflictError(
                    "Idempotency key was already used for a different evaluation request"
                )
            return existing
        flow = self._flows.get(
            flow_key=payload.flow_key,
            version=payload.flow_version,
            jurisdiction=payload.jurisdiction,
        )
        if flow.lifecycle_state != "test_ready" or not flow.definition_hash:
            raise FlowPackImmutableError("Flow must be locked in test_ready state before evaluation")
        suite = self._evaluations.get_suite(payload.suite_id)
        if suite.jurisdiction != flow.jurisdiction:
            raise EvaluationConflictError("Evaluation suite and flow jurisdictions do not match")
        cases = self._evaluations.get_cases(payload.suite_id, mode=payload.mode)
        if not cases:
            raise EvaluationConflictError(f"Suite has no '{payload.mode}' cases")
        case_by_key = {str(case["case_key"]): case for case in cases}
        observations = {item.case_key: item for item in payload.observations}
        if len(observations) != len(payload.observations):
            raise EvaluationConflictError("Observation case keys must be unique")
        if set(observations) != set(case_by_key):
            raise EvaluationConflictError("Observations must match the complete pinned suite mode")

        self._flows.transition_lifecycle(flow_id=flow.flow_id, expected="test_ready", target="testing")
        try:
            results: list[dict[str, Any]] = []
            routing_matches = 0
            for case_key, case in case_by_key.items():
                observation = observations[case_key]
                route_matches = observation.actual_route == str(case["expected_route"])
                routing_matches += int(route_matches)
                required_sources = set(json.loads(str(case["required_source_ids_json"])))
                citations_valid = required_sources.issubset(set(observation.source_ids))
                human_review_valid = (
                    not bool(case["human_review_required"]) or observation.human_review_present
                )
                checks = {
                    "route": route_matches,
                    "schema": observation.schema_valid,
                    "citations": citations_valid,
                    "provenance": observation.provenance_valid,
                    "privacy": observation.privacy_violation_count == 0,
                    "auto_finalization": not observation.unsupported_auto_finalization,
                    "human_review": human_review_valid,
                }
                results.append({
                    "result_id": str(uuid4()), "run_id": "", "case_id": str(case["case_id"]),
                    "actual_route": observation.actual_route,
                    "source_ids_json": json.dumps(observation.source_ids, sort_keys=True),
                    "schema_valid": int(observation.schema_valid),
                    "provenance_valid": int(observation.provenance_valid),
                    "privacy_violation_count": observation.privacy_violation_count,
                    "unsupported_auto_finalization": int(observation.unsupported_auto_finalization),
                    "human_review_present": int(observation.human_review_present),
                    "passed": int(all(checks.values())),
                    "reason_codes_json": json.dumps(
                        [name for name, passed in checks.items() if not passed], sort_keys=True
                    ),
                })
            accuracy = routing_matches / len(cases)
            gates = {
                "routing_threshold": accuracy >= suite.routing_accuracy_threshold,
                "schema_policy": all(item["schema_valid"] for item in results),
                "citations_provenance": all(
                    "citations" not in json.loads(item["reason_codes_json"])
                    and item["provenance_valid"] for item in results
                ),
                "privacy": all(item["privacy_violation_count"] == 0 for item in results),
                "auto_finalization": all(not item["unsupported_auto_finalization"] for item in results),
                "human_review": all(
                    "human_review" not in json.loads(item["reason_codes_json"]) for item in results
                ),
            }
            passed = all(gates.values())
            run_id = str(uuid4())
            for result in results:
                result["run_id"] = run_id
            now = datetime.now(timezone.utc).isoformat()
            policy_json = json.dumps(payload.routing_policy, ensure_ascii=False, sort_keys=True)
            values = {
                "run_id": run_id, "idempotency_key": payload.idempotency_key,
                "synthetic_run_id": payload.synthetic_run_id, "suite_id": suite.suite_id,
                "suite_key": suite.suite_key, "suite_version": suite.version,
                "suite_hash": suite.suite_hash, "flow_id": flow.flow_id, "flow_key": flow.flow_key,
                "flow_version": flow.version, "flow_definition_hash": flow.definition_hash,
                "graph_version": payload.graph_version, "routing_policy_json": policy_json,
                "routing_policy_hash": hashlib.sha256(policy_json.encode("utf-8")).hexdigest(),
                "provider": payload.provider, "model": payload.model,
                "provider_route": payload.provider_route, "mode": payload.mode,
                "status": "passed" if passed else "failed",
                "metrics_json": json.dumps({
                    "case_count": len(cases), "routing_accuracy": accuracy,
                    "routing_accuracy_threshold": suite.routing_accuracy_threshold,
                }, sort_keys=True),
                "gates_json": json.dumps(gates, sort_keys=True), "created_by": actor_id,
                "created_at": now, "expires_at": self._evaluations.expiry(suite.retention_days),
            }
            run = self._evaluations.record_run(values=values, results=results)
            self._flows.transition_lifecycle(
                flow_id=flow.flow_id,
                expected="testing",
                target="test_passed" if passed else "test_ready",
            )
            return run
        except Exception:
            try:
                self._flows.transition_lifecycle(
                    flow_id=flow.flow_id, expected="testing", target="test_ready"
                )
            except FlowPackImmutableError:
                pass
            raise

    def approve(
        self, *, flow_key: str, version: int, jurisdiction: str, run_id: str,
        actor_id: str, reason: str,
    ) -> ProductionApprovalResponse:
        flow = self._flows.get(flow_key=flow_key, version=version, jurisdiction=jurisdiction)
        run = self._evaluations.get_run(run_id)
        latest_run = self._evaluations.get_latest_run_for_flow(flow.flow_id)
        if flow.lifecycle_state != "test_passed":
            raise FlowPackImmutableError("Only a test-passed flow can receive production approval")
        if run.status != "passed" or run.flow_id != flow.flow_id:
            raise EvaluationConflictError("Approval must reference a successful run for this flow version")
        if latest_run is None or latest_run.run_id != run.run_id:
            raise EvaluationConflictError("Approval must reference the latest evaluation run")
        if run.flow_definition_hash != flow.definition_hash:
            raise EvaluationConflictError("Evaluation is stale because the flow definition hash changed")
        approval = self._evaluations.create_approval(
            flow_id=flow.flow_id, run=run, actor_id=actor_id, reason=reason
        )
        return approval
