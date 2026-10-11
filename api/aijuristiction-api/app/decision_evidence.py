"""Safe explanation projection; never derive hidden reasoning from model I/O."""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,254}$")
# Only known deterministic decisions are exposed as explanations. New producers
# must register their semantic code, rather than sending arbitrary narrative.
_REASONS = frozenset({
    "workflow_routed", "workflow_assignment_pinned", "langgraph_run_started",
    "input_validation_completed", "output_validation_completed", "privacy_safety_validation_completed",
    "workflow_interrupted", "workflow_resumed", "workflow_terminated", "documents_drafted",
    "verified_facts_preserved", "verified_fact_missing_from_output", "empty_document_draft",
    "unresolved_placeholder", "tool_executed_without_consent", "legal_provenance_missing",
    "privacy_and_provenance_passed", "privacy_policy_passed", "output_present", "output_missing",
    "all_required_reviews_passed", "required_review_failed", "human_review_required",
    "quality_approved", "quality_revision_requested", "technical_retry_scheduled",
})


def _id(value: object) -> str | None:
    return value if isinstance(value, str) and _ID.fullmatch(value) else None


def build_decision_evidence(
    decisions: Sequence[Mapping[str, Any]], graph: dict[str, Any],
) -> dict[str, Any]:
    result = []
    for event in decisions:
        decision = event.get("decision")
        if not isinstance(decision, Mapping):
            continue
        reason = decision.get("reason_code")
        actor = event.get("actor")
        safe_reason = reason if isinstance(reason, str) and reason in _REASONS else None
        # A model actor tag alone does not prove a provider-supported summary.
        result.append({
            "schema_version": 1, "event_id": _id(event.get("event_id")),
            "workflow_run_id": _id(event.get("workflow_run_id")),
            "stage": _id(event.get("stage")),
            "explanation_kind": "recorded_decision_code",
            "decision_actor": actor if actor in {"system", "orchestrator", "model"} else "unknown",
            "reason_code": safe_reason,
            "explanation_status": "recorded" if safe_reason else "unavailable",
            "model_supplied_summary": {"status": "unavailable", "reason": "no_reviewed_summary_recorded"},
        })
    by_event = {item["event_id"]: item for item in result if item["event_id"]}
    for run in graph.get("runs", []):
        for occurrence in run.get("occurrences", []):
            decision = by_event.get(occurrence.get("event_id"))
            # Exact durable ID and owning run must both match. No timestamp join.
            if decision and decision["workflow_run_id"] == run.get("workflow_run_id"):
                occurrence["decision_evidence"] = decision
    return {
        "schema_version": 1, "engine": "langgraph" if graph.get("runs") else "unknown",
        "explanations": result,
        "model_supplied_summary_status": "unavailable",
        "model_supplied_summary_reason": "no_reviewed_summary_recorded",
        "link_basis": "recorded_event_id_and_run_id",
    }
