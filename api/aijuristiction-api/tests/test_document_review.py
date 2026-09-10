from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.document_review import ModelReview, Proposal, accepted_text, build_proposals, export_docx, export_original_docx
from app.cases_api import get_store
from services.document_processor.uploads import extract_docx, validate_upload


def test_accept_reject_export_preserves_unicode_and_original() -> None:
    paragraphs = ["Kúpna cena: 100 EUR.", "Odovzdanie: zajtra."]
    proposals = build_proposals(ModelReview(proposals=[
        Proposal(paragraph=0, original=paragraphs[0], replacement="Kúpna cena: 100 EUR vrátane DPH.", reason="Synthetic", source_ids=["law"]),
        Proposal(paragraph=1, original=paragraphs[1], replacement="Odovzdanie: dnes.", reason="Synthetic", source_ids=["law"]),
    ]), paragraphs, [{"source_id": "law"}])
    proposals[0]["decision"] = "accepted"
    proposals[1]["decision"] = "rejected"
    review = {"paragraphs": paragraphs, "proposals": proposals}
    text = accepted_text(review)
    assert "vrátane DPH" in text and "zajtra" in text and "dnes" not in text
    assert paragraphs[0] == "Kúpna cena: 100 EUR."
    output = export_docx(text)
    validate_upload("revision.docx", output)
    assert "vrátane DPH" in extract_docx(output)


@pytest.mark.parametrize("filename,payload", [("evil.exe", b"MZ"), ("fake.pdf", b"%PDF-fake"),
                                              ("fake.png", b"not-image"), ("binary.txt", b"\x00binary")])
def test_rejects_disguised_or_unsupported_files(filename: str, payload: bytes) -> None:
    with pytest.raises(ValueError):
        validate_upload(filename, payload)


def test_docx_table_order_and_entity_rejection() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Pred</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Tabuľka</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:p><w:r><w:t>Po</w:t></w:r></w:p></w:body></w:document>')
    assert extract_docx(output.getvalue()) == "Pred\n\nTabuľka\n\nPo"


def test_unknown_sources_and_overlapping_edits_fail_closed() -> None:
    proposal = Proposal(paragraph=0, original="old", replacement="new", reason="why", source_ids=["invented"])
    with pytest.raises(ValueError, match="outside"):
        build_proposals(ModelReview(proposals=[proposal]), ["old"], [{"source_id": "real"}])
    proposal.source_ids = ["real"]
    with pytest.raises(ValueError, match="overlapping"):
        build_proposals(ModelReview(proposals=[proposal, proposal]), ["old"], [{"source_id": "real"}])


def test_docx_revision_keeps_table_and_rejected_text() -> None:
    source = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(export_docx("Before\nTable\nAfter"))) as template, zipfile.ZipFile(source, "w") as target:
        for name in template.namelist():
            data = template.read(name)
            if name == "word/document.xml":
                data = data.replace(b'<w:p><w:r><w:t xml:space="preserve">Table</w:t></w:r></w:p>',
                    b'<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
            target.writestr(name, data)
    original = source.getvalue()
    review = {"paragraphs": ["Before", "Table", "After"], "proposals": [
        {"paragraph": 1, "replacement": "Updated table cell", "decision": "accepted"},
        {"paragraph": 2, "replacement": "Rejected", "decision": "rejected"}]}
    output = export_original_docx(original, review)
    with zipfile.ZipFile(io.BytesIO(output)) as archive:
        from xml.etree import ElementTree as ET
        from services.document_processor.uploads import WORD_NS
        root = ET.fromstring(archive.read("word/document.xml"))
        assert root.find(".//" + WORD_NS + "tbl") is not None
    assert "Updated table cell" in extract_docx(output)
    assert "After" in extract_docx(output) and "Rejected" not in extract_docx(output)
    assert extract_docx(original) == "Before\n\nTable\n\nAfter"


def test_future_or_missing_source_version_is_unverified() -> None:
    from datetime import date
    from app.legal_basis import basis_from_source
    source = dict(effective_from="2027-01-01", version_id="future", section_found=True,
                  content_text="Test", official_name="Synthetic act", content_scope="sections")
    assert basis_from_source(source, provision="§ 1", as_of=date(2026, 9, 10)).verification == "unverified"
    source["effective_from"] = "2026-01-01"
    assert basis_from_source(source, provision="§ 1", as_of=date(2026, 9, 10)).verification == "source_verified"
    source["section_found"] = False
    assert basis_from_source(source, provision="§ 1", as_of=date(2026, 9, 10)).verification == "unverified"


def test_private_review_disables_payload_logging_and_debug_capture(monkeypatch, caplog) -> None:
    import logging
    from aijurisdictionagents.llm import base
    events = []
    monkeypatch.setenv("LOCAL_LLM_IO_LOGGING", "true")
    monkeypatch.setattr(base, "record_debug_event", lambda *args: events.append(args))
    with caplog.at_level(logging.INFO), base.private_model_io():
        base.log_llm_request(logging.getLogger(__name__), provider="test", agent_name="review",
                             request_payload=[{"content": "PRIVATE_BODY"}])
        base.log_llm_response(logging.getLogger(__name__), provider="test", agent_name="review", raw_response="PRIVATE_BODY")
        base.execute_correlated_model_call(provider="test", model="test", agent_name="review",
            request_payload=[{"content": "PRIVATE_BODY"}], invoke=lambda: object())
    assert "PRIVATE_BODY" not in caplog.text and "PRIVATE_BODY" not in str(events)


def test_fenced_json_does_not_apply_provider_commentary() -> None:
    from app.document_review import parse_model_review
    assert parse_model_review('```json\n{"proposals":[],"questions":[]}\n```\nExtra commentary').proposals == []


def test_revision_concurrency_authorization_and_delete_cascade(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMENT_PROCESSOR_OPTION", "api")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    headers = {"x-api-key": "aijuris"}
    with TestClient(app) as client:
        user = client.post("/v1/users/sign-up", headers=headers, json={"phone_number": "+421900800623", "email": "review800@example.test", "password": "synthetic-password"}).json()["user_id"]
        case = client.post("/v1/cases", headers=headers, json={"user_id": user, "title": "Synthetic review"}).json()["case_id"]
        upload = client.post(f"/v1/cases/{case}/documents", params={"user_id": user}, headers=headers,
                             files=[("files", ("contract.txt", b"Synthetic original clause for a contract.", "text/plain"))])
        assert upload.status_code == 201
        doc = upload.json()["uploaded"][0]["doc_id"]
        store = get_store()
        headers["x-jurisdigta-device-id"] = "synthetic-review-device"
        headers["x-jurisdigta-device-token"] = store.issue_device_auth_token(user_id=user, device_id="synthetic-review-device")
        from app.document_review import content_hash
        review = store.create_document_review(case_id=case, doc_id=doc, payload={
            "original_hash": content_hash("Synthetic original clause for a contract."),
            "paragraphs": ["Synthetic original clause for a contract."], "proposals": [
                {"id": "0", "paragraph": 0, "replacement": "Synthetic accepted clause.", "decision": "pending"}],
            "warning": "Review required", "reviewed_at": "2026-09-10", "citations": [], "questions": [],
        })
        route = f"/v1/cases/{case}/documents/{doc}/review/{review['review_id']}"
        denied = client.patch(route, params={"user_id": "different-user"}, headers=headers,
                              json={"expected_revision": 1, "decisions": {"0": "accepted"}})
        assert denied.status_code == 401
        saved = client.patch(route, params={"user_id": user}, headers=headers,
                             json={"expected_revision": 1, "decisions": {"0": "accepted"}})
        assert saved.status_code == 200 and saved.json()["revision"] == 2
        retried = store.create_document_review(case_id=case, doc_id=doc, payload=review, review_id=review["review_id"])
        assert retried["revision"] == 2 and retried["proposals"][0]["decision"] == "accepted"
        stale = client.patch(route, params={"user_id": user}, headers=headers,
                             json={"expected_revision": 1, "decisions": {"0": "rejected"}})
        assert stale.status_code == 409
        exported = client.get(route + "/export", params={"user_id": user, "revision": 2, "format": "docx"}, headers=headers)
        assert exported.status_code == 200 and "accepted clause" in extract_docx(exported.content)
        store.delete_case_document(case_id=case, doc_id=doc, actor_user_id=user, correlation_id="synthetic")
        assert store.get_document_review(case_id=case, doc_id=doc) is None
