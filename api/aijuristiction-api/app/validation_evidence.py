"""Project actual validator observations; absence never means a passing check."""
from typing import Any, Mapping, Sequence

from aijurisdictionagents.validation_audit import CATEGORIES, identifier


def build_validation_evidence(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    checks = []
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
        checks.append(check)
    return {
        "schema_version": 1,
        "checks": checks,
        "categories": [{"category": category, "evidence_status": "recorded" if any(
            item["category"] == category for item in checks
        ) else "missing_evidence"} for category in CATEGORIES],
        "scope": "retained_events_only",
    }
