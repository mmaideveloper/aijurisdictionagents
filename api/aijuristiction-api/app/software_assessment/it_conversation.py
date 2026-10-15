"""Deterministic case-bound IT intake using the same assessment API as the web."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.llm.routing import RoutedLLMClient
from aijurisdictionagents.orchestration.primary_router import PrimaryClassification, PrimaryLangGraphRouter, PrimaryRouteCandidate
from app.document_templates.api import get_document_template_store
from app.software_assessment import api as shared
from app.software_assessment.conversation import CONSENT, cell, normalized
from app.software_assessment.it_api import ITAssessmentRequest, OrganizationalFacts
from app.software_assessment.organizational_it import CASE_TYPE_KEY, QUESTIONS, jurisdiction_blockers
from app.software_assessment.workflow import intake_questions


def state_id(case_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, "organizational-it-chat/" + case_id))


def eligible(store: ApiDatabaseStore, case_id: str, content: str) -> bool:
    if store.get_software_assessment(case_id=case_id, assessment_id=state_id(case_id)):
        return True
    text = normalized(content)
    return any(token in text for token in (
        "pravna analyza pre it", "pravna analyza it", "it compliance", "organizational it",
        "datovy sklad", "data warehouse", "datawarehouse", "datawarehourse"))


def render(value: dict[str, Any]) -> str:
    output = value["output"]
    lines = ["### Právna analýza pre IT · SK + EU", cell(value["warning"]), cell(output["summary"])]
    lines += ["- " + cell(text) for text in value["coverage"] + output["questions"]]
    for item in output["applicability"]:
        lines.append(f"- {cell(item['regime'])}: {cell(item['status'])} — {cell(item['reason'])}")
    source_map = {source["source_id"]: source for source in value["sources"]}
    for action in output["actions"]:
        lines.append(f"- **{cell(action['priority'])}: {cell(action['finding'])}** {cell(action['action'])} "
                     f"Pôvod: {cell(action.get('basis', 'law'))}. Zodpovednosť: {cell(action['owner'])}. "
                     f"Overenie: {cell(action['verification'])}. Stav: {cell(action['status'])}.")
        for source_id in action["source_ids"]:
            source = source_map[source_id]
            lines.append(f"[{cell(source['title'])} · {cell(source['provision'])}]({source['source_url']})")
    lines.append("### Odporúčaná dokumentácia")
    lines += ["- " + cell(item["title"]) + ": " + cell(item["purpose"]) + " — " + cell(item["category"])
              + "; obsah/dôkaz: " + cell(item["acceptance_criteria"]) for item in output["supplier_checklist"]]
    lines += ["- " + cell(text) for text in output["release_blockers"]]
    lines.append("Pred použitím vyžaduje kontrolu právnika/DPO. Dokumenty sa iba odporúčajú; nejde o potvrdenie súladu.")
    lines.append(f"Model: {cell(value['provider'])} / {cell(value['model'])}. {cell(value['fallback_reason'])}")
    return "\n\n".join(lines)


def respond(store: ApiDatabaseStore, *, case_id: str, user_id: str, content: str,
            selected_model_profile_id: str | None = None) -> tuple[str, RoutedLLMClient | None]:
    catalog = get_document_template_store().get_case_type(case_type_key=CASE_TYPE_KEY, jurisdiction="SK")
    if not catalog.is_enabled or catalog.is_deleted:
        raise ValueError("Organizational IT assessment is disabled.")
    candidate = PrimaryRouteCandidate(CASE_TYPE_KEY, catalog.name, catalog.description, (),
                                     "organizational_it_assessment", 1, "builtin.organizational_it", 1)
    decision = PrimaryLangGraphRouter(classifier=lambda *_: PrimaryClassification(
        status="matched", selected_case_type_key=CASE_TYPE_KEY, confidence=1.0,
        rationale="code_registered_organizational_it_intake")).route(
            question=content, verified_facts={}, candidates=(candidate,))
    if decision.route != "dedicated_flow":
        raise ValueError("Organizational IT route unavailable.")
    saved = store.get_software_assessment(case_id=case_id, assessment_id=state_id(case_id))
    state: dict[str, Any] = dict(saved) if saved else {
        "kind": "organizational_it_chat", "created_at": shared.now(), "warning": "Predbežná právna analýza IT",
        "facts": {"description": content, "it_context": {}}, "consented": False, "turn_count": 0,
        "output": {}, "documents": [], "sources": [], "graph": "organizational_it_assessment@1",
    }
    if len(content) > 8000 or state["turn_count"] >= 60:
        raise ValueError("Intake limit reached.")
    state["turn_count"] += 1
    clean = normalized(content.strip())
    revoked = clean in {"nesuhlasim", "odvolavam suhlas", "odvolavam suhlas s externym ai spracovanim tohto pripadu."}
    if revoked:
        state["consented"] = False
    elif clean == normalized(CONSENT):
        state["consented"] = True
    elif saved and state.get("pending") and "?" not in content:
        key = state["pending"]
        answer = re.sub(r"^\s*Q\d+\s*[:.-]\s*", "", content, flags=re.I).strip()
        if key in {"personal_data", "health_data", "uses_ai"}:
            if normalized(answer) in {"ano", "yes", "nie", "no"}:
                state["facts"][key] = normalized(answer) in {"ano", "yes"}
        else:
            state["facts"]["it_context"][key] = [part.strip().upper() for part in answer.split(",") if part.strip()] if key == "countries" else answer
    facts = OrganizationalFacts.model_validate(state["facts"])
    questions = intake_questions(facts)
    blockers = jurisdiction_blockers(facts.it_context)
    state["pending"] = None
    routes: list[RoutedLLMClient] = []
    if blockers:
        reply = "\n\n".join(blockers) + "\n\nOpravte kódy krajín, ak boli uvedené nesprávne."
        state["pending"] = "countries"
    elif questions:
        question = questions[0]
        state["pending"] = next((key for key, text in QUESTIONS.items() if text == question), None)
        if state["pending"] is None:
            state["pending"] = next(key for key in ("personal_data", "health_data", "uses_ai") if getattr(facts, key) is None)
        reply = "Právna analýza pre IT · SK + EU. Nevkladajte údaje pacientov.\n\n" + question
    elif not state["consented"]:
        reply = ("Pred odoslaním údajov nakonfigurovanému externému AI poskytovateľovi potvrďte: **" + CONSENT
                 + "** Toto potvrdenie nenahrádza právny základ spracovania údajov pacientov.")
    else:
        fingerprint = hashlib.sha256(facts.model_dump_json().encode()).hexdigest()
        request = ITAssessmentRequest(request_id=uuid5(NAMESPACE_URL, case_id + fingerprint + (selected_model_profile_id or "")), facts=facts,
                                      external_acknowledged=True, selected_model_profile_id=selected_model_profile_id)
        result = shared._create_assessment(case_id, user_id, request, store, route_sink=routes)
        state["last_assessment_id"] = result["assessment_id"]
        reply = render(result)
    state["reply"] = reply
    state["request_hash"] = hashlib.sha256(json.dumps(state["facts"], sort_keys=True).encode()).hexdigest()
    store.save_software_assessment(case_id=case_id, assessment_id=state_id(case_id), payload=state,
                                  document_ids=[], expected_revision=saved["revision"] if saved else None)
    # Model provenance is persisted by the shared assessment, never guessed here.
    return reply, routes[0] if routes else None
