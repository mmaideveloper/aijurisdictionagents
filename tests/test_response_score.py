from decimal import Decimal

import pytest
from pydantic import ValidationError

from aijurisdictionagents.response_score import DimensionAssessment, GateAssessment, GATES, WEIGHTS, assess_response


def evidence():
    return dict(answer_revision="answer-1", evaluator_id="synthetic", evaluator_version="1", evidence_ids=("evidence-1",), source_versions=("source-v1",))


def complete(values=(90, 80, 100, 70)):
    dimensions = [DimensionAssessment(**evidence(), dimension=name, value=value) for name, value in zip(WEIGHTS, values)]
    gates = [GateAssessment(**evidence(), gate=name, outcome="passed") for name in GATES]
    return dimensions, gates


def test_arithmetic_and_existing_human_review_are_preserved():
    dimensions, gates = complete()
    result = assess_response("answer-1", dimensions=dimensions, gates=gates)
    assert result.score == Decimal("87.00")
    assert result.requires_human_review
    assert result.status == "scored"
    assert result.policy_digest
    assert result.weights == WEIGHTS


def test_critical_failure_cannot_be_averaged_away():
    dimensions, gates = complete((100, 100, 100, 100))
    gates[0] = gates[0].model_copy(update={"outcome": "failed"})
    result = assess_response("answer-1", dimensions=dimensions, gates=gates)
    assert result.status == "blocked" and result.score is None


def test_missing_dimensions_sources_and_new_revision_never_reuse_score():
    dimensions, gates = complete()
    assert assess_response("answer-2", dimensions=dimensions, gates=gates).score is None
    assert assess_response("answer-1", dimensions=dimensions[:-1], gates=gates).score is None
    dimensions[0] = dimensions[0].model_copy(update={"source_versions": ()})
    result = assess_response("answer-1", dimensions=dimensions, gates=gates)
    assert result.status == "incomplete" and result.score is None
    assert "grounding_source_versions" in result.missing_evidence


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "101"])
def test_invalid_scores_rejected(value):
    with pytest.raises(ValidationError):
        DimensionAssessment(**evidence(), dimension="clarity", value=value)


def test_duplicate_and_sensitive_evidence_rejected():
    dimensions, gates = complete()
    with pytest.raises(ValueError, match="Duplicate"):
        assess_response("answer-1", dimensions=dimensions + dimensions, gates=gates)
    with pytest.raises(ValidationError):
        DimensionAssessment(**{**evidence(), "evaluator_id": "private narrative"}, dimension="clarity", value=50)


def test_rounding_and_threshold():
    dimensions, gates = complete((85, 85, 85, Decimal("85.05")))
    result = assess_response("answer-1", dimensions=dimensions, gates=gates, existing_human_review=False)
    assert result.score == Decimal("85.01")
    assert not result.requires_human_review
    assert assess_response("answer-1").requires_human_review
