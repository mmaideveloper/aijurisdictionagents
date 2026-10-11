import pytest
from uuid import uuid4
from app.chat.api import _record_validated_revision_link
from app.chat.models import Message, MessageRole
from app.validation_evidence import build_validation_evidence
from app.chat.output_validation import AILawyerOutputMessageValidationAgent
from aijurisdictionagents.correlation import correlation_scope


def test_missing_categories_are_not_reported_as_passed_or_unsupported():
    evidence = build_validation_evidence([])
    assert len(evidence["categories"]) == 6
    assert {item["evidence_status"] for item in evidence["categories"]} == {"missing_evidence"}
    assert evidence["checks"] == []


def test_chat_cleanup_records_its_narrow_scope_without_a_grounding_score():
    events = []
    def sink(context, component, stage, status, payload):
        events.append({"event_id": "synthetic", "request_id": context.request_id, "component": component, "stage": stage, "status": status, "payload": payload})
    with correlation_scope(correlation_id="synthetic", debug_sink=sink):
        assert AILawyerOutputMessageValidationAgent().validate(content="Synthetic answer", user_profile=None) == "Synthetic answer"
    evidence = build_validation_evidence(events)
    assert evidence["checks"][0]["validator_id"] == "chat.profile_section_cleanup"
    assert evidence["checks"][0]["outcome"] == "passed"
    assert evidence["checks"][0]["artifact_link_status"] == "missing_evidence"
    assert evidence["checks"][0]["score"] is None
    grounding = next(item for item in evidence["categories"] if item["category"] == "grounding")
    assert grounding["evidence_status"] == "missing_evidence"
    assert "Synthetic answer" not in str(evidence)



@pytest.mark.parametrize('changed', [False, True])
def test_exact_candidate_links_to_delivered_revision_without_claiming_revalidation(changed):
    events = []
    def sink(context, component, stage, status, payload):
        events.append({'event_id': str(uuid4()), 'request_id': context.request_id, 'component': component, 'stage': stage, 'status': status, 'payload': payload})
    candidate_id = str(uuid4())
    original = 'Synthetic candidate'
    final = Message(session_id=uuid4(), role=MessageRole.ASSISTANT, content='Changed synthetic candidate' if changed else original, agent_name='synthetic')
    with correlation_scope(correlation_id='synthetic', debug_sink=sink):
        AILawyerOutputMessageValidationAgent().validate(content=original, user_profile=None, artifact_id=candidate_id)
        _record_validated_revision_link(candidate_id, original, final)
    evidence = build_validation_evidence(events)
    check = evidence['checks'][0]
    assert check['artifact_id'] == candidate_id
    assert check['answer_revision'] == str(final.id)
    assert check['answer_revision_status'] == ('changed_after_check' if changed else 'unchanged_since_check')
    assert original not in str(events)
    assert final.content not in str(events)
    assert build_validation_evidence(events[:1])['checks'][0]['answer_revision_status'] == 'missing_evidence'
