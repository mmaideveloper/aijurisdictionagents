from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from test_software_assessment import source
from app.software_assessment import api, it_conversation, workflow
from app.software_assessment.it_api import OrganizationalFacts
from app.software_assessment.models import Action, AssessmentOutput, ChecklistItem, Evidence, SoftwareFacts
from app.software_assessment.organizational_it import ITContext, QUESTIONS, document_recommendations, intake, jurisdiction_blockers

pytest_plugins = ("test_software_assessment",)


def context(**overrides):
    values = {key: "Synthetic answer; expert verification needed" for key in QUESTIONS if key != "countries"}
    values.update(countries=["SK"], legal_entities="20 separate synthetic hospital legal entities",
                  purposes="Care administration; analytics; research; AI training; software testing assessed separately")
    values.update(overrides)
    return ITContext.model_validate(values)


def facts(**overrides):
    values = dict(description="Synthetic ZdravieHospital warehouse initiative", personal_data=True,
                  health_data=True, uses_ai=True, it_context=context())
    values.update(overrides)
    return OrganizationalFacts.model_validate(values)


def fail_route(**kwargs):
    raise AssertionError("No external model route before intake/jurisdiction gate")


def test_intake_is_adaptive_and_does_not_use_software_product_questions():
    assert workflow.intake_questions(facts()) == []
    questions = workflow.intake_questions(facts(it_context=context(entity_roles="", purposes="")))
    assert QUESTIONS["entity_roles"] in questions and QUESTIONS["purposes"] in questions
    assert not any("specimen" in question for question in questions)
    assert intake(context(ai_purposes=""), uses_ai=False, personal_data=True, health_data=False) == []
    assert QUESTIONS["ai_purposes"] in intake(context(ai_purposes=""), uses_ai=True, personal_data=True, health_data=False)


@pytest.mark.parametrize("countries", [["CZ"], ["SK", "CZ"], ["EU"], ["Slovakia"]])
def test_unsupported_or_unspecific_jurisdictions_do_not_reach_model(monkeypatch, countries):
    monkeypatch.setattr(workflow, "retrieve_sources", lambda *_: pytest.fail("No retrieval before intake gate"))
    result = workflow.run_assessment(facts(it_context=context(countries=countries)), [], None, "")
    assert not result["model_called"] and result["output"]["questions"]
    assert not result["output"]["actions"] and not result["sources"]


def test_country_casing_and_missing_country():
    assert not jurisdiction_blockers(context(countries=[" sk "]))
    assert QUESTIONS["countries"] in workflow.intake_questions(facts(it_context=context(countries=[])))


def test_it_api_unknowns_jurisdiction_catalog_and_generation_guards(private_case, monkeypatch):
    client, store, headers, user, case_id, _ = private_case
    monkeypatch.setattr(api, "get_routed_llm_client", fail_route)
    url = f"/v1/cases/{case_id}/it-assessments"
    payload = {"facts": {"description": "Synthetic ZdravieHospital CZ data warehouse", "it_context": {"countries": ["CZ"]}}}
    response = client.post(url, params={"user_id": user}, headers=headers, json=payload)
    assert response.status_code == 201, response.text
    value = response.json()
    assert value["kind"] == "organizational_it" and value["case_type_key"] == "sk.it.legal_analysis"
    assert value["provider"] == "not_called" and "CZ" in " ".join(value["output"]["questions"])
    identifier = value["assessment_id"]
    assert client.get(url, params={"user_id": user}, headers=headers).json()["items"][0]["assessment_id"] == identifier
    assert client.get(f"/v1/cases/{case_id}/software-assessments", params={"user_id": user}, headers=headers).json()["items"] == []
    assert client.get(url + f"/{identifier}", params={"user_id": user}, headers=headers).status_code == 200
    shared = f"/v1/cases/{case_id}/software-assessments/{identifier}"
    assert client.post(shared + "/drafts", params={"user_id": user}, headers=headers,
                       json={"expected_revision": 1, "document_title": "Synthetic recommendation"}).status_code == 409
    assert client.get(shared + "/export", params={"user_id": user, "revision": 1}, headers=headers).status_code == 409
    assert client.get(url, params={"user_id": user}, headers={"x-api-key": "aijuris"}).status_code == 401
    catalog = client.get("/v1/case-types", headers={"x-api-key": "aijuris"}).json()
    assert "sk.it.legal_analysis" in str(catalog)
    assert client.delete(url + f"/{identifier}", params={"user_id": user}, headers=headers).status_code == 204
    assert store.get_software_assessment(case_id=case_id, assessment_id=identifier) is None


def test_real_contract_uses_it_prompt_sources_and_case_private_history(private_case, monkeypatch):
    client, store, headers, user, case_id, _ = private_case
    captured = []
    output = AssessmentOutput(summary="Synthetic preliminary organizational assessment", supplier_checklist=[ChecklistItem(
        title="Purpose and entity map", category="recommended", purpose="Separate entities and processing purposes before pooling",
        owner="DPO", acceptance_criteria="List each entity, purpose and proposed legal basis")])

    class Model:
        def complete(self, agent, system, messages, tools):
            captured.append((system, messages[0].content))
            return output.model_dump_json()

    route = SimpleNamespace(client=Model(), provider="synthetic-test-provider", model="synthetic-test-model",
                            route=SimpleNamespace(provider=SimpleNamespace(is_external=True)), fallback_reason="")
    monkeypatch.setattr(api, "get_routed_llm_client", lambda **_: route)
    monkeypatch.setattr(workflow, "retrieve_sources", lambda _: ([source()], ["Synthetic source coverage only"]))
    url = f"/v1/cases/{case_id}/it-assessments"
    body = {"request_id": str(uuid4()), "facts": facts().model_dump(), "external_acknowledged": False}
    assert client.post(url, params={"user_id": user}, headers=headers, json=body).status_code == 403
    assert not captured
    body["external_acknowledged"] = True
    first = client.post(url, params={"user_id": user}, headers=headers, json=body)
    assert first.status_code == 201, first.text
    value = first.json()
    assert value["graph"] == "organizational_it_assessment@1"
    assert value["provider"] == "synthetic-test-provider" and value["sources"][0]["source_id"] == "s1"
    assert value["output"]["supplier_checklist"][0]["category"] == "recommended"
    assert "Assess organizational IT" in captured[0][0] and "20 separate" in captured[0][1]
    assert 'evidence_id null and excerpt ""' in captured[0][0]
    again = client.post(url, params={"user_id": user}, headers=headers, json=body).json()
    assert again["assessment_id"] == value["assessment_id"] and len(captured) == 1
    store.soft_delete_case(case_id=case_id, user_id=user)
    assert store.get_software_assessment(case_id=case_id, assessment_id=value["assessment_id"]) is None


def test_chat_does_not_send_facts_before_consent_and_rejects_czech_scope(private_case, monkeypatch):
    _, store, _, user, case_id, _ = private_case
    monkeypatch.setattr(api, "get_routed_llm_client", fail_route)
    first, route = it_conversation.respond(store, case_id=case_id, user_id=user, content="Právna analýza pre IT: synthetic ZdravieHospital data warehouse")
    assert QUESTIONS["countries"] in first and route is None
    blocked, _ = it_conversation.respond(store, case_id=case_id, user_id=user, content="CZ")
    assert "mimo rozsahu" in blocked and "CZ" in blocked
    next_question, _ = it_conversation.respond(store, case_id=case_id, user_id=user, content="SK")
    assert QUESTIONS["sector"] in next_question
    assert it_conversation.eligible(store, case_id, "ďalšia odpoveď")
    assert not it_conversation.eligible(store, "different-case", "software GDPR compliance")


def test_software_contract_remains_separate():
    questions = workflow.intake_questions(SoftwareFacts(description="Synthetic software without specified functions"))
    assert any("specimen" in question for question in questions)


def test_internal_policy_gap_uses_original_policy_instead_of_an_unrelated_law():
    document = Evidence(evidence_id="policy1", document_id="synthetic-policy", filename="policy.txt",
                        version=1, content_hash="synthetic", section="Paragraph 1", text="Separate hospital access is required.")
    action = Action(action_id="policy-access", finding="Access evidence missing", classification="suspected_gap",
                    basis="internal_policy", evidence_id="policy1", excerpt=document.text, source_ids=[],
                    priority="high", action="Review hospital access isolation", owner="IT owner",
                    verification="Review the access test evidence against the uploaded policy")
    workflow.validate_output(AssessmentOutput(summary="", actions=[action]), [document], [])
    with pytest.raises(workflow.AssessmentValidationError, match="legal evidence"):
        workflow.validate_output(AssessmentOutput(summary="", actions=[action.model_copy(update={"basis": "law"})]), [document], [])
    with pytest.raises(workflow.AssessmentValidationError, match="Document evidence mismatch"):
        workflow.validate_output(AssessmentOutput(summary="", actions=[action]), [], [])


def test_it_rejects_article_nine_claim_citing_only_article_thirty_two():
    action = Action(action_id="grounds", finding="Review Article 9 grounds", classification="missing_evidence",
                    source_ids=["s1"], priority="high", action="Request legal review", owner="DPO",
                    verification="Check grounds for the stated purpose")
    with pytest.raises(workflow.AssessmentValidationError, match="not retrieved"):
        workflow.validate_output(AssessmentOutput(summary="", actions=[action]), [], [source()], require_exact_provisions=True)
    retained = workflow.retain_grounded_output(AssessmentOutput(summary="", actions=[action]), [], [source()], require_exact_provisions=True)
    assert not retained.actions and any("omitted" in item for item in retained.release_blockers)
    # An uncited request for missing grounds may remain explicitly unverified.
    workflow.validate_output(AssessmentOutput(summary="", actions=[action.model_copy(update={"source_ids": []})]), [], [source()], require_exact_provisions=True)


def test_document_fallback_is_conditional_and_never_invents_legal_obligations():
    basic = document_recommendations(personal_data=False, health_data=False, uses_ai=False)
    sensitive_ai = document_recommendations(personal_data=True, health_data=True, uses_ai=True)
    assert all(item["category"] == "recommended" for item in sensitive_ai)
    assert len(sensitive_ai) > len(basic)
    assert not any("DPIA" in item["title"] for item in basic)
    assert any("DPIA" in item["title"] for item in sensitive_ai)
    assert all(item["purpose"] and item["owner"] and item["acceptance_criteria"] for item in sensitive_ai)


def test_completed_chat_still_requires_explicit_consent_and_honors_revocation(private_case, monkeypatch):
    _, store, _, user, case_id, _ = private_case
    monkeypatch.setattr(api, "get_routed_llm_client", fail_route)
    it_conversation.respond(store, case_id=case_id, user_id=user, content="Právna analýza pre IT: synthetic hospital")
    saved = store.get_software_assessment(case_id=case_id, assessment_id=it_conversation.state_id(case_id))
    saved.update(facts=facts().model_dump(), pending=None, consented=False)
    store.save_software_assessment(case_id=case_id, assessment_id=it_conversation.state_id(case_id),
                                  payload=saved, document_ids=[], expected_revision=saved["revision"])
    reply, route = it_conversation.respond(store, case_id=case_id, user_id=user, content="Please review these facts")
    assert it_conversation.CONSENT in reply and route is None
    reply, route = it_conversation.respond(store, case_id=case_id, user_id=user, content="Odvolávam súhlas")
    assert it_conversation.CONSENT in reply and route is None
    final = store.get_software_assessment(case_id=case_id, assessment_id=it_conversation.state_id(case_id))
    assert final["consented"] is False
