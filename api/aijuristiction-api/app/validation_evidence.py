"""Project actual validator observations; absence never means a passing check."""
from typing import Any, Mapping, Sequence

from aijurisdictionagents.validation_audit import CATEGORIES, identifier


def build_validation_evidence(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    checks = []
    revisions = {}
    for event in events:
        payload = event.get("payload")
        if event.get("component") == "validation" and event.get("stage") == "answer_revision_link" and isinstance(payload, dict):
            artifact = identifier(payload.get("artifact_id"))
            answer = identifier(payload.get("answer_revision"))
            if artifact and answer and isinstance(payload.get("content_unchanged_since_check"), bool):
                revisions[artifact] = {"answer_revision": answer, "answer_revision_status": (
                    "unchanged_since_check" if payload["content_unchanged_since_check"] else "changed_after_check"
                )}
    for event in events:
        if event.get("component") != "validation" or event.get("stage") != "check":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("category") not in CATEGORIES:
            continue
        check = {key: identifier(payload.get(key)) for key in (
            "category", "execution_id", "validator_id", "validator_version", "instrumentation_version",
            "artifact_id", "artifact_link_status", "outcome", "reason_code", "decision", "score_status",
        )}
        check.update(event_id=identifier(event.get("event_id")), request_id=identifier(event.get("request_id")), score=None)
        check.update(revisions.get(check["artifact_id"], {"answer_revision": None, "answer_revision_status": "missing_evidence"}))
        checks.append(check)
    return {
        "schema_version": 1,
        "checks": checks,
        "categories": [{"category": category, "evidence_status": "recorded" if any(
            item["category"] == category for item in checks
        ) else "missing_evidence"} for category in CATEGORIES],
        "scope": "retained_events_only",
    }
