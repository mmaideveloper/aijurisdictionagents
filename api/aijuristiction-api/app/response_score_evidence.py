"""Read immutable assessment records without recomputing historical scores."""
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from aijurisdictionagents.response_score import ResponseAssessment


def build_response_score_evidence(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    assessments = []
    invalid = 0
    for event in events:
        if event.get("component") != "response_quality" or event.get("stage") != "assessment":
            continue
        try:
            assessment = ResponseAssessment.model_validate(event.get("payload"))
        except ValidationError:
            invalid += 1
            continue
        assessments.append(assessment.model_dump(mode="json"))
    return {"schema_version": 1, "assessments": assessments, "invalid_records": invalid,
            "evidence_status": "recorded" if assessments else "missing_evidence"}
