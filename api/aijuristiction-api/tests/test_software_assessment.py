from __future__ import annotations

import io
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.cases_api import get_store
from app.document_templates.api import get_document_template_store
from app.main import app
from app.software_assessment.evidence import extract_evidence
from app.software_assessment.models import (
    CASE_TYPE_KEY, Action, AssessmentOutput, Evidence, LegalSource, SoftwareFacts,
)
from app.software_assessment.workflow import intake_questions, run_assessment, validate_output


def facts(**overrides):
    values = dict(description="Synthetic contact management software.", intended_purpose="Contact administration",
        users="Synthetic operators", lifecycle="Prototype", role="Developer", personal_data=True,
        health_data=False, uses_ai=False, medical_purpose=False, specimen_analysis=False,
        automated_decisions=False)
    values.update(overrides)
    return SoftwareFacts.model_validate(values)


def source():
    return LegalSource(source_id="s1", title="Synthetic security provision", provision="Article 32",
        source_url="https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        text="Article 32 Appropriate measures must be selected based on processing risk.")


def output():
    return AssessmentOutput(summary="Preliminary synthetic assessment", actions=[Action(
        action_id="security-1", finding="Unrestricted access is documented.", classification="suspected_gap",
        evidence_id="d2", excerpt="Everyone can read all contact records.", source_ids=["s1"],
        priority="high", action="Assess risk and implement proportionate access and encryption controls.",
        owner="Supplier security lead", verification="Review access controls and TLS configuration.")],
        recommended_documents=["Security risk assessment"])


def pdf():
    result = io.BytesIO()
    writer = canvas.Canvas(result)
    writer.drawString(50, 800, "Synthetic software purpose: contact administration.")
    writer.showPage()
    writer.drawString(50, 800, "Everyone can read all contact records.")
    writer.save()
    return result.getvalue()


@pytest.fixture
def private_case(monkeypatch):
    monkeypatch.setenv("API_KEY", "aijuris")
    get_document_template_store.cache_clear()
    with TestClient(app) as client:
        headers = {"x-api-key": "aijuris"}
        user = client.post("/v1/users/sign-up", headers=headers, json={"email": "synthetic-896@example.test",
            "phone_number": "+421900896001", "password": "synthetic-test-password"}).json()["user_id"]
        case_id = client.post("/v1/cases", headers=headers, json={"user_id": user, "title": "Synthetic 896"}).json()["case_id"]
        store = get_store()
        headers.update({"x-jurisdigta-device-id": "synthetic-896-device", "x-jurisdigta-device-token":
            store.issue_device_auth_token(user_id=user, device_id="synthetic-896-device")})
        document = client.post(f"/v1/cases/{case_id}/documents", params={"user_id": user}, headers=headers,
            files=[("files", ("supplier.pdf", pdf(), "application/pdf"))]).json()["uploaded"][0]["doc_id"]
        yield client, store, headers, user, case_id, document
    get_document_template_store.cache_clear()


def test_page_provenance_comes_from_original_pdf(private_case):
    _, store, _, _, case_id, document = private_case
    items = extract_evidence(store, case_id, [document])
    assert items[1].page == 2 and "Everyone can read" in items[1].text
    assert items[0].content_hash == items[1].content_hash
    with pytest.raises(KeyError):
        extract_evidence(store, "unrelated-case", [document])


def test_assessment_finishing_after_case_deletion_cannot_recreate_private_results(private_case):
    _, store, _, user, case_id, document = private_case
    store.soft_delete_case(case_id=case_id, user_id=user)
    identifier = str(uuid4())
    with pytest.raises(ValueError, match="removed"):
        store.save_software_assessment(case_id=case_id, assessment_id=identifier,
            payload={"request_hash": "synthetic", "private_fact": "synthetic only"}, document_ids=[document])
    assert store.get_software_assessment(case_id=case_id, assessment_id=identifier) is None


def test_unknown_intake_is_not_inferred():
    questions = intake_questions(SoftwareFacts(description="Medical software with unclear purpose."))
    assert any("specimen" in question for question in questions)
    assert any("intended purpose" in question for question in questions)
    assert intake_questions(facts()) == []


def test_retrieval_uses_separate_public_topics_not_eu_number_as_sk_identifier(monkeypatch):
    from app.software_assessment.workflow import retrieve_sources
    calls = []
    def search(name, arguments):
        calls.append((name, arguments))
        return {"results": []}
    monkeypatch.setattr("app.software_assessment.workflow._call_mcp_tool", search)
    retrieve_sources(facts())
    queries = [arguments["query"] for _, arguments in calls]
    assert "GDPR" in queries and "AI Act" in queries
    assert all("/" not in query and "Synthetic contact" not in query for query in queries)


@pytest.mark.parametrize("medical,ivd", [(True, False), (True, True), (False, True)])
def test_medical_paths_request_specialist_sources(monkeypatch, medical, ivd):
    from app.software_assessment.workflow import retrieve_sources
    queries = []
    def search(_name, arguments):
        queries.append(arguments["query"])
        return {"results": []}
    monkeypatch.setattr("app.software_assessment.workflow._call_mcp_tool", search)
    sources, _ = retrieve_sources(facts(medical_purpose=medical, specimen_analysis=ivd))
    assert "in vitro diagnostika" in queries and "zdravotnícke pomôcky" in queries
    assert sources == []


@pytest.mark.parametrize("selection_status", [403, 404])
def test_invalid_requested_model_uses_default_real_route_with_disclosure(private_case, monkeypatch, selection_status):
    from aijurisdictionagents.llm.routing import ModelRouteUnavailable
    client, _, headers, user, case_id, _ = private_case
    monkeypatch.setattr("app.software_assessment.workflow.retrieve_sources", lambda _: ([source()], ["Partial coverage"]))
    calls = []
    def route(**kwargs):
        calls.append(kwargs)
        if kwargs.get("selected_model_profile_id"):
            raise ModelRouteUnavailable("Unavailable synthetic model", status_code=selection_status)
        return SimpleNamespace(provider="real-route-test-double", model="real-model-test-double", fallback_reason="",
            route=SimpleNamespace(provider=None), client=SimpleNamespace(complete=lambda *args:
                AssessmentOutput(summary="Synthetic fallback route check").model_dump_json()))
    monkeypatch.setattr("app.software_assessment.api.get_routed_llm_client", route)
    response = client.post(f"/v1/cases/{case_id}/software-assessments", params={"user_id": user}, headers=headers,
        json=dict(facts=facts().model_dump(), selected_model_profile_id="nonexistent-model"))
    assert response.status_code == 201, response.text
    assert "configured default real model" in response.json()["fallback_reason"]
    assert len(calls) == 2 and response.json()["provider"] != "mock"


@pytest.mark.parametrize("mutation", ["excerpt", "source", "verified", "duplicate"])
def test_model_cannot_invent_evidence_or_review(mutation):
    result = output()
    evidence = [Evidence(evidence_id="d2", document_id="doc", filename="supplier.pdf", version=1,
        content_hash="hash", page=2, section="Page 2", text="Everyone can read all contact records.")]
    if mutation == "excerpt":
        result.actions[0].excerpt = "Invented plaintext storage statement"
    if mutation == "source":
        result.actions[0].source_ids = ["invented"]
    if mutation == "verified":
        result.actions[0].status = "verified"
    if mutation == "duplicate":
        result.actions.append(result.actions[0])
    with pytest.raises(ValueError):
        validate_output(result, evidence, [source()])


def test_missing_sources_do_not_call_model(monkeypatch):
    monkeypatch.setattr("app.software_assessment.workflow.retrieve_sources", lambda _: ([], ["Source coverage missing"]))
    class Forbidden:
        def complete(self, *args):
            raise AssertionError("No model assessment without legal sources")
    result = run_assessment(facts(), [], Forbidden(), "Test prompt")
    assert result["output"]["actions"] == []
    assert result["output"]["release_blockers"] == ["Source coverage missing"]


def test_rejected_action_is_not_relabelled_or_saved_as_a_valid_finding():
    from app.software_assessment.workflow import retain_grounded_output
    result = output()
    invalid = result.actions[0].model_copy(update={"action_id": "unsupported", "finding": "Invented statutory obligation",
        "source_ids": ["invented"]})
    result.actions.append(invalid)
    evidence = [Evidence(evidence_id="d2", document_id="doc", filename="supplier.pdf", version=1,
        content_hash="hash", page=2, section="Page 2", text="Everyone can read all contact records.")]
    retained = retain_grounded_output(result, evidence, [source()])
    assert [action.action_id for action in retained.actions] == ["security-1"]
    assert "Invented statutory obligation" not in retained.model_dump_json()
    assert any("failed evidence validation" in blocker for blocker in retained.release_blockers)


def test_harmless_phone_number_is_not_automatic_violation(monkeypatch):
    monkeypatch.setattr("app.software_assessment.workflow.retrieve_sources", lambda _: ([source()], ["Partial coverage"]))
    class Client:
        def complete(self, *args):
            return AssessmentOutput(summary="A phone number alone does not prove a violation.").model_dump_json()
    item = Evidence(evidence_id="d1", document_id="doc", filename="contacts.txt", version=1,
        content_hash="hash", section="Paragraph 1", text="Synthetic phone number used with access controls.")
    assert run_assessment(facts(), [item], Client(), "Test prompt")["output"]["actions"] == []


def test_legal_quotations_are_server_derived(monkeypatch):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Action.model_validate({**output().actions[0].model_dump(), "legal_excerpt": "Invented legal quotation"})
    monkeypatch.setattr("app.software_assessment.workflow.retrieve_sources", lambda _: ([source()], ["Partial coverage"]))
    client = SimpleNamespace(complete=lambda *args: output().model_dump_json())
    evidence = [Evidence(evidence_id="d2", document_id="doc", filename="supplier.pdf", version=1,
        content_hash="hash", page=2, section="Page 2", text="Everyone can read all contact records.")]
    result = run_assessment(facts(), evidence, client, "Test prompt")
    assert result["output"]["actions"][0]["legal_basis"][0]["excerpt"] == source().text


def test_model_reference_catalog_omits_storage_identifiers_and_has_exact_enums(monkeypatch):
    import json
    monkeypatch.setattr("app.software_assessment.workflow.retrieve_sources", lambda _: (
        [source().model_copy(update={"original_document_id": "internal-source-uuid"})], ["Partial coverage"]))
    def complete(_agent, prompt, messages, _documents):
        payload = json.loads(messages[0].content)
        assert list(payload["evidence"]) == ["d2"] and list(payload["legal_sources"]) == ["s1"]
        assert "internal-document-uuid" not in messages[0].content
        assert "internal-source-uuid" not in messages[0].content
        assert '"enum": ["s1"]' in prompt
        return output().model_dump_json()
    evidence = [Evidence(evidence_id="d2", document_id="internal-document-uuid", filename="supplier.pdf", version=1,
        content_hash="hash", page=2, section="Page 2", text="Everyone can read all contact records.")]
    run_assessment(facts(), evidence, SimpleNamespace(complete=complete), "Test prompt")


def test_supplier_requirements_offer_outlines_when_model_omits_draft_titles():
    from app.software_assessment.workflow import recommended_document_titles
    assert recommended_document_titles({"recommended_documents": [], "supplier_checklist": [
        {"title": "Clinical evaluation and performance evidence"},
    ]}) == ["Working outline: Clinical evaluation and performance evidence"]


def test_case_prompt_upgrade_preserves_admin_edits(private_case):
    from app.case_types.models import CaseTypeUpdateRequest
    from app.document_templates.store import DocumentTemplateStore
    template_store = get_document_template_store()
    prompt = "Reviewed custom software regulatory prompt with supplier requirements."
    template_store.update_case_type(case_type_key=CASE_TYPE_KEY, jurisdiction="SK",
        payload=CaseTypeUpdateRequest(prompt_text=prompt))
    reopened = DocumentTemplateStore.from_env().get_case_type(case_type_key=CASE_TYPE_KEY, jurisdiction="SK")
    assert reopened.prompt.prompt_text == prompt


def test_private_assessment_revision_export_and_deletion(private_case, monkeypatch):
    client, store, headers, user, case_id, document = private_case
    monkeypatch.setattr("app.software_assessment.workflow.retrieve_sources", lambda _: ([source()], ["Partial synthetic coverage"]))
    monkeypatch.setattr("app.software_assessment.api.get_routed_llm_client", lambda **kwargs: SimpleNamespace(
        client=SimpleNamespace(complete=lambda *args: output().model_dump_json()),
        provider="synthetic-test-provider", model="synthetic-test-model", fallback_reason="",
        route=SimpleNamespace(provider=None)))
    base = f"/v1/cases/{case_id}/software-assessments"
    params = {"user_id": user}
    body = dict(request_id=str(uuid4()), facts=facts().model_dump(), document_ids=[document])
    result = client.post(base, params=params, headers=headers, json=body)
    assert result.status_code == 201, result.text
    value = result.json()
    path = base + "/" + value["assessment_id"]
    assert value["documents"][1]["page"] == 2
    assert client.post(base, params=params, headers=headers, json=body).json()["assessment_id"] == value["assessment_id"]
    assert client.get(path, params={"user_id": "other"}, headers=headers).status_code == 401
    assert client.patch(path + "/actions/security-1", params=params, headers=headers,
        json=dict(expected_revision=1, status="verified", evidence_note="Synthetic evidence checked")).status_code == 409
    saved = client.patch(path + "/actions/security-1", params=params, headers=headers,
        json=dict(expected_revision=1, status="ready_for_review", evidence_note="Synthetic controls checked"))
    assert saved.status_code == 200 and saved.json()["revision"] == 2
    assert client.patch(path + "/actions/security-1", params=params, headers=headers,
        json=dict(expected_revision=1, status="open", evidence_note="Stale synthetic update")).status_code == 409
    report = client.get(path + "/export", params={**params, "revision": 2}, headers=headers)
    assert report.status_code == 200
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(report.content)).pages)
    assert "supplier.pdf" in text and "Page 2" in text and "Everyone can read" in text
    assert "not a compliance certificate" in text
    store.delete_case_document(case_id=case_id, doc_id=document, actor_user_id=user, correlation_id="synthetic-896")
    assert store.get_software_assessment(case_id=case_id, assessment_id=value["assessment_id"]) is None


def test_missing_facts_need_no_model_and_idempotency_rejects_changed_inputs(private_case, monkeypatch):
    client, _, headers, user, case_id, _ = private_case
    monkeypatch.setattr("app.software_assessment.workflow.retrieve_sources", lambda _: ([], ["No sources"]))
    base = f"/v1/cases/{case_id}/software-assessments"
    body = dict(request_id=str(uuid4()), facts={"description": "Synthetic unspecified software"})
    response = client.post(base, params={"user_id": user}, headers=headers, json=body)
    assert response.status_code == 201, response.text
    assert response.json()["provider"] == "not_called" and response.json()["output"]["questions"]
    body["facts"]["description"] = "Changed synthetic description"
    assert client.post(base, params={"user_id": user}, headers=headers, json=body).status_code == 409
