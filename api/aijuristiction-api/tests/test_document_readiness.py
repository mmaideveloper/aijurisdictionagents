"""Persistence, not chat completion, is the document readiness boundary (#835)."""
from io import BytesIO
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfReader
import pytest

from app.chat import api
from app.chat.models import Message, MessageRole, Session, SessionResult
from app.main import app


@pytest.fixture
def saved_case():
    client = TestClient(app)
    headers = {"x-api-key": "aijuris"}
    user = client.post("/v1/users/sign-up", headers=headers, json={
        "phone_number": "+421900000835", "email": "readiness@example.test", "password": "test-only"
    })
    assert user.status_code == 201, user.text
    user_id = user.json()["user_id"]
    case = client.post("/v1/cases", headers=headers, json={"user_id": user_id, "title": "Synthetic draft"})
    assert case.status_code == 201, case.text
    session = Session(case_id=case.json()["case_id"], user_id=UUID(user_id), country="SK", language="sk-SK")
    api._repository.create_session(session)
    return client, headers, session, api._get_store()


def _message(session, content):
    return Message(session_id=session.id, role=MessageRole.ASSISTANT, content=content)


def test_ready_prose_and_completed_metadata_without_storage_are_not_ready(saved_case):
    _, _, session, _ = saved_case
    message = _message(session, 'Balik dokumentov je pripraveny na export a stiahnutie. CASE_UPDATE_JSON: {"case": {"documents": []}}')
    assert not api._document_export_ready([message])
    content = api._attach_generated_case_document_references(session=session, content=message.content, doc_ids=[])
    assert "nepodarilo uložiť" in content
    result = SessionResult(final_recommendation=message.content, judge_rationale="", citations=[],
                           metadata={"document_ready": True, "document_confirmed": True})
    assert api._session_result_is_stale(result=result, messages=[message])
    assert api._document_completion_processing_events(session=session, messages=[message], result=result) == []


def test_saved_document_has_viewer_source_valid_pdf_and_rejects_missing_access(saved_case):
    client, headers, session, store = saved_case
    drafts = [api._GeneratedCaseDocumentDraft(filename="synthetic.pdf", body="Splnomocnenie\n\nSplnomocnitel: Test s.r.o.\nSplnomocnenec: Test Osoba\nRozsah: prevzatie zasielky.")]
    ids = api._persist_generated_case_document_drafts(session=session, case_id=session.case_id, drafts=drafts)
    content = api._attach_generated_case_document_references(session=session, content="Dokument je pripraveny na stiahnutie.", doc_ids=ids)
    assert api._document_export_ready([_message(session, content)])
    url = f"/v1/cases/{session.case_id}/documents/{ids[0]}"
    source = client.get(url, params={"user_id": str(session.user_id)}, headers=headers)
    assert source.status_code == 200
    assert source.content.strip()
    pdf = client.get(url + "/pdf", params={"user_id": str(session.user_id)}, headers=headers)
    assert pdf.status_code == 200, pdf.text[:100]
    assert pdf.content.startswith(b"%PDF-")
    assert PdfReader(BytesIO(pdf.content)).pages
    denied = client.get(url + "/pdf", params={"user_id": "other-user"}, headers=headers)
    assert denied.status_code == 404  # The API hides cases from non-owners.
    missing = client.get(url.replace(ids[0], "missing") + "/pdf", params={"user_id": str(session.user_id)}, headers=headers)
    assert missing.status_code == 404
    # Identical retry must reuse a successful write rather than create another document.
    assert api._persist_generated_case_document_drafts(session=session, case_id=session.case_id, drafts=drafts) == ids
    assert len(store.list_case_documents(case_id=session.case_id)) == 1
    store.delete_case_document(case_id=session.case_id, doc_id=ids[0], actor_user_id=str(session.user_id), correlation_id="test-835")
    assert not api._document_export_ready([_message(session, content)])


@pytest.mark.parametrize("failure", ["exception", "missing_id", "empty_body"])
def test_storage_failure_is_actionable_and_not_success(saved_case, monkeypatch, failure):
    _, _, session, store = saved_case
    def fail(**kwargs):
        if failure == "exception":
            raise OSError("private storage details must not escape")
        return ""
    monkeypatch.setattr(store, "add_case_document", fail)
    monkeypatch.setattr(api, "_get_store", lambda: store)
    with pytest.raises(HTTPException) as error:
        api._persist_generated_case_document_drafts(session=session, case_id=session.case_id, drafts=[
            api._GeneratedCaseDocumentDraft(filename="synthetic.pdf", body="" if failure == "empty_body" else "Synthetic draft")
        ])
    assert error.value.status_code == 503
    payload = api._correlated_error_payload(None, error.value)
    assert payload["code"] == "document_generation_failed"
    assert "nepodarilo uložiť" in payload["message"]
    assert "private storage" not in str(payload)


def test_partial_package_retry_reuses_first_saved_document(saved_case, monkeypatch):
    _, _, session, store = saved_case
    original_add = store.add_case_document
    calls = 0
    def fail_second(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("storage unavailable")
        return original_add(**kwargs)
    monkeypatch.setattr(store, "add_case_document", fail_second)
    monkeypatch.setattr(api, "_get_store", lambda: store)
    drafts = [api._GeneratedCaseDocumentDraft(filename=f"draft-{i}.pdf", body=f"Synthetic draft {i}") for i in range(2)]
    with pytest.raises(HTTPException):
        api._persist_generated_case_document_drafts(session=session, case_id=session.case_id, drafts=drafts)
    monkeypatch.setattr(store, "add_case_document", original_add)
    ids = api._persist_generated_case_document_drafts(session=session, case_id=session.case_id, drafts=drafts)
    assert len(set(ids)) == 2
    assert len(store.list_case_documents(case_id=session.case_id)) == 2


@pytest.mark.parametrize("content", ["", "Finished.", "Dokument je pripraveny na stiahnutie."])
def test_confirmed_generation_with_no_artifact_never_emits_success(saved_case, monkeypatch, content):
    _, _, session, _ = saved_case
    api._repository.add_message(_message(session, "Mam pripravit finalny dokument aj vo formate PDF?"))
    api._repository.add_message(Message(session_id=session.id, role=MessageRole.USER,
                                        content="Please generate the PDF document."))
    monkeypatch.setattr(api, "_validate_lawyer_output_message", lambda **kwargs: kwargs["content"])
    monkeypatch.setattr(api, "_persist_generated_case_document_if_needed", lambda **kwargs: [])
    result = api._persist_direct_assistant_message(
        session_id=session.id, session=session, content=content, agent_name="Assistant"
    )
    assert "nepodarilo uložiť" in result.content
    assert result.generated_document_ids == []
    assert not api._document_export_ready([result])


def test_immediate_reply_returns_saved_ids_and_ready_status(saved_case, monkeypatch):
    _, _, session, _ = saved_case
    ids = api._persist_generated_case_document_drafts(session=session, case_id=session.case_id, drafts=[
        api._GeneratedCaseDocumentDraft(filename="synthetic.pdf", body="Synthetic legal draft")
    ])
    monkeypatch.setattr(api, "_validate_lawyer_output_message", lambda **kwargs: kwargs["content"])
    monkeypatch.setattr(api, "_persist_generated_case_document_if_needed", lambda **kwargs: ids)
    message = api._persist_direct_assistant_message(
        session_id=session.id, session=session,
        content="Dokument je pripraveny na stiahnutie.", agent_name="Assistant"
    )
    assert message.generated_document_ids == ids
    assert api._message_payload(message)["generated_document_ids"] == ids
    assert api._document_export_ready([message])
