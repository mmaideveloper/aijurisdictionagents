from app.chat.models import Message, MessageRole, Session
from app.chat.repository import InMemoryChatRepository
from app.response_score_evidence import build_response_score_evidence
from aijurisdictionagents.correlation import correlation_scope
from aijurisdictionagents.response_score import assess_response
from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig


def test_delivered_answer_records_incomplete_score_with_exact_revision():
    repository = InMemoryChatRepository()
    session = repository.create_session(Session())
    message = Message(session_id=session.id, role=MessageRole.ASSISTANT, content="Private content")
    events = []
    def sink(context, component, stage, status, payload):
        events.append(dict(component=component, stage=stage, payload=payload))
    with correlation_scope(correlation_id=session.correlation_id, debug_sink=sink):
        repository.add_message(message)
    projected = build_response_score_evidence(events)
    result = projected["assessments"][0]
    assert result["answer_revision"] == str(message.id)
    assert result["status"] == "incomplete" and result["score"] is None
    assert "Private content" not in str(projected)


def test_historical_and_malformed_evidence_remain_unavailable():
    assert build_response_score_evidence([])["evidence_status"] == "missing_evidence"
    result = build_response_score_evidence([dict(component="response_quality", stage="assessment", payload={"score": 100, "secret": "private"})])
    assert result["invalid_records"] == 1
    assert result["assessments"] == []
    assert "private" not in str(result)


def test_contradictory_score_state_is_not_exposed():
    payload = assess_response("answer-1").model_dump(mode="json")
    payload["score"] = "100"
    result = build_response_score_evidence([dict(component="response_quality", stage="assessment", payload=payload)])
    assert result["invalid_records"] == 1 and result["assessments"] == []


def test_assessment_roundtrip_expiry_and_session_deletion(tmp_path):
    store = CaseWorkflowStore(CaseWorkflowStoreConfig(db_option="local", db_cloud="", sqlite_path=tmp_path / "audit.sqlite3"))
    assessment = assess_response("synthetic-answer")
    for correlation in ("expired", "deleted", "retained"):
        store.record_debug_event(correlation_id=correlation, session_id=correlation, request_id="request", parent_request_id="", component="response_quality", stage="assessment", status=assessment.status, payload=assessment.model_dump(mode="json"))
    restored = build_response_score_evidence(store.list_debug_events(correlation_id="retained"))
    assert restored["assessments"] == [assessment.model_dump(mode="json")]
    with store._connect() as connection:
        connection.execute("UPDATE session_debug_events SET expires_at = '2000-01-01T00:00:00+00:00' WHERE correlation_id = 'expired'")
        connection.commit()
    assert build_response_score_evidence(store.list_debug_events(correlation_id="expired"))["assessments"] == []
    store.delete_session_decision_traces(session_id="deleted")
    assert store.list_debug_events(correlation_id="deleted") == []
    assert len(store.list_debug_events(correlation_id="retained")) == 1
