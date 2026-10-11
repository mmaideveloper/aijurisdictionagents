import pytest

from aijurisdictionagents.correlation import correlation_scope
from aijurisdictionagents.validation_audit import validation_check


def test_observation_links_parent_without_copying_content():
    events = []
    with correlation_scope(correlation_id="synthetic", request_id="turn", debug_sink=lambda *event: events.append(event)):
        with validation_check(category="output_quality", validator_id="test", artifact_id="answer-v1") as result:
            result.update(outcome="failed", reason_code="sensitive case narrative", decision="human_review", raw_text="SECRET")
    context, component, stage, status, payload = events[0]
    assert context.parent_request_id == "turn"
    assert (component, stage, status) == ("validation", "check", "failed")
    assert payload["artifact_id"] == "answer-v1"
    assert payload["reason_code"] == "reason_unavailable"
    assert payload["decision"] == "human_review"
    assert payload["score"] is None
    assert "SECRET" not in str(payload)
    assert "sensitive" not in str(payload)


def test_exception_is_recorded_and_rethrown_without_exception_content():
    events = []
    with correlation_scope(correlation_id="synthetic", debug_sink=lambda *event: events.append(event)):
        with pytest.raises(ValueError):
            with validation_check(category="input_security", validator_id="test", artifact_id=None):
                raise ValueError("private text")
    assert events[0][3] == "error"
    assert events[0][4]["artifact_link_status"] == "missing_evidence"
    assert "private text" not in str(events)


def test_attempts_have_unique_execution_ids():
    events = []
    with correlation_scope(correlation_id="synthetic", debug_sink=lambda *event: events.append(event)):
        for _ in range(2):
            with validation_check(category="output_quality", validator_id="test", artifact_id="revision-one") as result:
                result.update(outcome="passed", reason_code="output_present", decision="continue")
    assert events[0][4]["execution_id"] != events[1][4]["execution_id"]
