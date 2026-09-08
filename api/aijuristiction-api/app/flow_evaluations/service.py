from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from app.flow_evaluations.models import (
    EvaluationRunCreate,
    EvaluationRunResponse,
    FlowPromotionPreviewRequest,
    FlowPromotionPreviewResponse,
    FlowPromotionRequest,
    FlowPromotionResponse,
    FlowRollbackRequest,
    ProductionApprovalResponse,
)
from app.flow_evaluations.store import EvaluationConflictError, FlowEvaluationStore
from app.case_workflows.models import WorkflowAssignmentRequest
from app.case_workflows.service import CaseWorkflowApplicationService, WorkflowConfigurationError
from app.case_workflows.store import WorkflowAssignmentNotFoundError
from app.flow_packs.store import FlowPackImmutableError, FlowPackStore


class FlowEvaluationService:
    def __init__(
        self,
        flow_store: FlowPackStore,
        evaluation_store: FlowEvaluationStore,
        workflow_service: CaseWorkflowApplicationService | None = None,
    ) -> None:
        self._flows = flow_store
        self._evaluations = evaluation_store
        self._workflows = workflow_service

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
        if flow.lifecycle_state not in {"test_ready", "published"} or not flow.definition_hash:
            raise FlowPackImmutableError(
                "Flow must be locked for testing or already published before evaluation"
            )
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

        transition_lifecycle = flow.lifecycle_state == "test_ready"
        if transition_lifecycle:
            self._flows.transition_lifecycle(
                flow_id=flow.flow_id, expected="test_ready", target="testing"
            )
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
            if transition_lifecycle:
                self._flows.transition_lifecycle(
                    flow_id=flow.flow_id,
                    expected="testing",
                    target="test_passed" if passed else "test_ready",
                )
            return run
        except Exception:
            if transition_lifecycle:
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
        if flow.lifecycle_state not in {"test_passed", "published"}:
            raise FlowPackImmutableError(
                "Only a test-passed or published revalidated flow can receive production approval"
            )
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

    def preview_promotion(
        self, payload: FlowPromotionPreviewRequest
    ) -> FlowPromotionPreviewResponse:
        workflows = self._require_workflows()
        flow = self._flows.get(
            flow_key=payload.flow_key,
            version=payload.flow_version,
            jurisdiction=payload.jurisdiction,
        )
        approval = self._evaluations.get_latest_approval_for_flow(flow.flow_id)
        blockers: list[str] = []
        if flow.lifecycle_state not in {"production_approved", "published"} or flow.is_deleted:
            blockers.append("flow_not_production_approved")
        if not flow.definition_hash:
            blockers.append("definition_hash_missing")
        if approval is None:
            blockers.append("production_approval_missing")
        else:
            if approval.definition_hash != flow.definition_hash:
                blockers.append("approval_definition_hash_stale")
            if approval.run_expires_at <= datetime.now(timezone.utc):
                blockers.append("production_review_expired")
            if not approval.gates or not all(approval.gates.values()):
                blockers.append("evaluation_gates_failed")
            if approval.graph_version != f"{payload.graph_key}@{payload.graph_version}":
                blockers.append("tested_graph_mismatch")

        try:
            current = workflows.store.get_active_assignment(
                case_type_key=payload.case_type_key,
                jurisdiction=payload.jurisdiction,
            )
        except WorkflowAssignmentNotFoundError:
            current = None
        compatibility_status = "invalid"
        compatibility_message = "Candidate compatibility was not validated"
        try:
            compatibility_status, compatibility_message = workflows.validate_assignment(
                WorkflowAssignmentRequest(
                    **payload.model_dump(),
                    confirmation=True,
                ),
                allowed_flow_states=frozenset({"production_approved", "published"}),
            )
        except WorkflowConfigurationError as exc:
            blockers.append("assignment_incompatible")
            compatibility_message = str(exc)
        if current and (
            current.graph_key == payload.graph_key
            and current.graph_version == payload.graph_version
            and current.flow_key == payload.flow_key
            and current.flow_version == payload.flow_version
        ):
            blockers.append("assignment_already_active")
        impact = (
            "Replaces the active assignment for new workflow runs; existing runs remain pinned."
            if current
            else "Creates the first assignment for new workflow runs; existing runs are unchanged."
        )
        return FlowPromotionPreviewResponse(
            candidate_flow_id=flow.flow_id,
            candidate_definition_hash=flow.definition_hash or "",
            candidate_lifecycle_state=flow.lifecycle_state,
            requested_assignment=payload,
            current_assignment=current,
            approval=approval,
            compatibility_status=compatibility_status,
            compatibility_message=compatibility_message,
            blockers=list(dict.fromkeys(blockers)),
            impact=impact,
            can_promote=not blockers,
        )

    def promote(self, payload: FlowPromotionRequest, *, actor_id: str) -> FlowPromotionResponse:
        request_hash = _hash(payload.model_dump(mode="json"))
        existing = self._evaluations.get_promotion_by_idempotency_key(payload.idempotency_key)
        if existing:
            if existing.request_hash != request_hash:
                raise EvaluationConflictError(
                    "Idempotency key was already used for a different promotion request"
                )
            return existing
        preview = self.preview_promotion(FlowPromotionPreviewRequest(**payload.model_dump()))
        if not preview.can_promote or preview.approval is None:
            raise EvaluationConflictError(
                "Promotion is blocked: " + ", ".join(preview.blockers)
            )
        if preview.approval.approval_id != payload.approval_id:
            raise EvaluationConflictError("Selected production approval is stale")
        return self._evaluations.record_promotion(
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
            action="promote",
            flow_id=preview.candidate_flow_id,
            approval_id=payload.approval_id,
            case_type_key=payload.case_type_key,
            jurisdiction=payload.jurisdiction,
            graph_key=payload.graph_key,
            graph_version=payload.graph_version,
            flow_key=payload.flow_key,
            flow_version=payload.flow_version,
            actor_id=actor_id,
            reason=payload.reason,
            expected_current_assignment_id=payload.expected_current_assignment_id,
        )

    def rollback(
        self, promotion_id: str, payload: FlowRollbackRequest, *, actor_id: str
    ) -> FlowPromotionResponse:
        request_hash = _hash({
            "rollback_of_promotion_id": promotion_id,
            **payload.model_dump(mode="json"),
        })
        existing = self._evaluations.get_promotion_by_idempotency_key(payload.idempotency_key)
        if existing:
            if existing.request_hash != request_hash:
                raise EvaluationConflictError(
                    "Idempotency key was already used for a different rollback request"
                )
            return existing
        origin = self._evaluations.get_promotion(promotion_id)
        if origin.prior_assignment is None:
            raise EvaluationConflictError("The first assignment has no rollback target")
        workflows = self._require_workflows()
        try:
            current = workflows.store.get_active_assignment(
                case_type_key=origin.target_assignment.case_type_key,
                jurisdiction=origin.target_assignment.jurisdiction,
            )
        except WorkflowAssignmentNotFoundError as exc:
            raise EvaluationConflictError("The promoted assignment is no longer active") from exc
        if (
            current.assignment_id != payload.expected_current_assignment_id
            or current.assignment_id != origin.target_assignment.assignment_id
        ):
            raise EvaluationConflictError(
                "Active assignment changed after this promotion; refresh before rollback"
            )
        target = origin.prior_assignment
        preview_request = FlowPromotionPreviewRequest(
            case_type_key=target.case_type_key,
            jurisdiction=target.jurisdiction,
            graph_key=target.graph_key,
            graph_version=target.graph_version,
            flow_key=target.flow_key,
            flow_version=target.flow_version,
        )
        preview = self.preview_promotion(preview_request)
        if not preview.can_promote or preview.approval is None:
            raise EvaluationConflictError(
                "Rollback is blocked: " + ", ".join(preview.blockers)
            )
        return self._evaluations.record_promotion(
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
            action="rollback",
            flow_id=preview.candidate_flow_id,
            approval_id=preview.approval.approval_id,
            case_type_key=target.case_type_key,
            jurisdiction=target.jurisdiction,
            graph_key=target.graph_key,
            graph_version=target.graph_version,
            flow_key=target.flow_key,
            flow_version=target.flow_version,
            actor_id=actor_id,
            reason=payload.reason,
            expected_current_assignment_id=current.assignment_id,
            rollback_of_promotion_id=promotion_id,
        )

    def _require_workflows(self) -> CaseWorkflowApplicationService:
        if self._workflows is None:
            raise EvaluationConflictError("Workflow assignment service is unavailable")
        return self._workflows


def _hash(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
