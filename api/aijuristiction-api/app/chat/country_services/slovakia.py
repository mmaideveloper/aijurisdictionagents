from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha1
import json
import re
from threading import Lock
from typing import TypedDict
import unicodedata

from app.chat.country_services.base import (
    DirectReplyPreparation,
    build_processing_event,
    emit_processing_event,
)
from app.chat.models import Message, MessageRole, Session

from aijurisdictionagents.schemas import Document as CoreDocument
from aijurisdictionagents.tools import build_default_tool_registry

_ORSR_CACHE_LOCK = Lock()
_ORSR_CACHE: dict[tuple[str, str, str], tuple[dict[str, object] | None, str | None]] = {}


class ShareTransferConflictResolution(TypedDict):
    resolved: bool
    choice: str
    intake_facts: dict[str, str]


def prepare_slovakia_direct_reply(
    *,
    session: Session,
    messages: list[Message],
    current_content: str,
    prior_messages: list[Message],
    normalize_document_lines: Callable[[str], list[str]],
    extract_document_facts: Callable[[list[str]], dict[str, str]],
    current_turn_confirms_document_generation: Callable[[str, list[Message]], bool],
    build_share_transfer_lines: Callable[[dict[str, str]], list[str]],
    processing_event_callback: Callable[[dict[str, object]], None] | None = None,
) -> DirectReplyPreparation:
    if session.country.strip().upper() != "SK":
        return DirectReplyPreparation(supplemental_documents=[])

    if _looks_like_tool_capability_question(current_content):
        capability_events: list[dict[str, object]] = []
        emit_processing_event(
            events=capability_events,
            event=build_processing_event(
                stage="tool_capabilities",
                message="Pripravujem zoznam dostupnych overovacich nastrojov.",
            ),
            callback=processing_event_callback,
        )
        return DirectReplyPreparation(
            supplemental_documents=[],
            direct_reply=_build_slovak_tool_capabilities_reply(),
            processing_events=capability_events,
        )

    address_prompt_note = _build_slovak_address_validation_prompt_note(
        current_content=current_content,
        prior_messages=prior_messages,
    )
    property_prompt_note = _build_slovak_property_validation_prompt_note(
        current_content=current_content,
        prior_messages=prior_messages,
    )

    asks_company_registry_info = _looks_like_company_registry_information_question(current_content)
    looks_like_company_document = _looks_like_company_document_matter(
        current_content=current_content,
        prior_messages=prior_messages,
    )
    asks_share_transfer = _looks_like_share_transfer_case(
        current_content=current_content,
        prior_messages=prior_messages,
    )
    company_query = _extract_slovak_company_query(messages=messages, current_content=current_content)
    has_company_query = bool(company_query)
    payment_or_loan_confirmation_requested = _looks_like_payment_confirmation_final_request(
        current_content=current_content,
        prior_messages=prior_messages,
    )
    if payment_or_loan_confirmation_requested and not has_company_query:
        direct_processing_events: list[dict[str, object]] = []
        emit_processing_event(
            events=direct_processing_events,
            event=build_processing_event(
                stage="analysis",
                message="Analyzujem poziadavku na slovenske potvrdenie o platbe alebo pozicke.",
            ),
            callback=processing_event_callback,
        )
        _append_payment_confirmation_validation_events(
            events=direct_processing_events,
            current_content=current_content,
            company_record=None,
            callback=processing_event_callback,
        )
        return DirectReplyPreparation(
            supplemental_documents=[],
            direct_reply=_build_slovak_payment_confirmation_ready_reply(
                current_content=current_content,
                company_record=None,
            ),
            processing_events=direct_processing_events,
        )
    if (
        not asks_company_registry_info
        and not looks_like_company_document
        and not asks_share_transfer
        and not has_company_query
    ):
        non_company_prompt_note = _merge_prompt_notes(address_prompt_note, property_prompt_note)
        if non_company_prompt_note:
            return DirectReplyPreparation(supplemental_documents=[], prompt_note=non_company_prompt_note)
        return DirectReplyPreparation(supplemental_documents=[])

    analysis_message = (
        "Zistujem informacie o spolocnosti v slovenskom obchodnom registri."
        if asks_company_registry_info
        else "Analyzujem poziadavku na slovensku firemnu dokumentaciu."
    )
    processing_events: list[dict[str, object]] = []
    emit_processing_event(
        events=processing_events,
        event=build_processing_event(stage="analysis", message=analysis_message),
        callback=processing_event_callback,
    )

    if not company_query:
        return DirectReplyPreparation(supplemental_documents=[], prompt_note=address_prompt_note)

    cached_registry_lookup = _load_cached_slovak_company_registry_document(company_query)
    if cached_registry_lookup is not None:
        company_record, registry_document, cache_hit = cached_registry_lookup
    else:
        emit_processing_event(
            events=processing_events,
            event=build_processing_event(
                stage="tool_start",
                tool_name="obchodny_register_company_check",
                message=_orsr_tool_start_message(
                    company_query=company_query,
                    country=session.country,
                    language=session.language,
                ),
                details={"query": company_query},
            ),
            callback=processing_event_callback,
        )
        company_record, registry_document, cache_hit = _load_slovak_company_registry_document(company_query)
    supplemental_documents = [registry_document] if registry_document is not None else []
    prompt_note = ""
    if cache_hit:
        emit_processing_event(
            events=processing_events,
            event=build_processing_event(
                stage="tool_cache",
                tool_name="obchodny_register_company_check",
                message=_orsr_tool_cache_hit_message(
                    company_query=company_query,
                    country=session.country,
                    language=session.language,
                ),
                details={"query": company_query, "cache": "memory"},
            ),
            callback=processing_event_callback,
        )
    elif company_record:
        emit_processing_event(
            events=processing_events,
            event=build_processing_event(
                stage="tool_result",
                tool_name="obchodny_register_company_check",
                message=_orsr_tool_result_found_message(
                    company_name=str(company_record.get("name") or company_query),
                    registration_number=str(company_record.get("registration_number") or ""),
                    company_seat=str(company_record.get("seat") or ""),
                    country=session.country,
                    language=session.language,
                ),
                details=company_record,
            ),
            callback=processing_event_callback,
        )
    elif not company_record:
        emit_processing_event(
            events=processing_events,
            event=build_processing_event(
                stage="tool_result",
                tool_name="obchodny_register_company_check",
                message=_orsr_tool_result_missing_message(
                    company_query=company_query,
                    country=session.country,
                    language=session.language,
                ),
                details={"query": company_query},
            ),
            callback=processing_event_callback,
        )

    if payment_or_loan_confirmation_requested:
        _append_payment_confirmation_validation_events(
            events=processing_events,
            current_content=current_content,
            company_record=company_record,
            callback=processing_event_callback,
        )
        return DirectReplyPreparation(
            supplemental_documents=supplemental_documents,
            direct_reply=_build_slovak_payment_confirmation_ready_reply(
                current_content=current_content,
                company_record=company_record,
            ),
            processing_events=processing_events,
        )

    vehicle_authorization_facts = _extract_slovak_vehicle_authorization_facts(
        current_content=current_content,
        company_query=company_query,
        company_record=company_record,
    )
    if vehicle_authorization_facts and _looks_like_vehicle_authorization_final_request(current_content):
        emit_processing_event(
            events=processing_events,
            event=build_processing_event(
                stage="document_ready",
                message="Pripravil som slovensku a anglicku verziu splnomocnenia na vedenie firemneho vozidla.",
                details={"document_names": ["Splnomocnenie", "Power of Attorney"]},
            ),
            callback=processing_event_callback,
        )
        return DirectReplyPreparation(
            supplemental_documents=supplemental_documents,
            direct_reply=_build_slovak_vehicle_authorization_ready_reply(
                facts=vehicle_authorization_facts,
            ),
            processing_events=processing_events,
        )

    if asks_company_registry_info and not asks_share_transfer:
        prompt_note = _build_slovak_registry_question_prompt_note(
            company_query=company_query,
            company_record=company_record,
        )
        prompt_note = _merge_prompt_notes(prompt_note, address_prompt_note)
        prompt_note = _merge_prompt_notes(prompt_note, property_prompt_note)
        return DirectReplyPreparation(
            supplemental_documents=supplemental_documents,
            prompt_note=prompt_note,
            processing_events=processing_events,
        )

    if not asks_share_transfer:
        prompt_note = _build_slovak_company_prompt_note(
            company_query=company_query,
            company_record=company_record,
        )
        vehicle_authorization_note = _build_slovak_vehicle_authorization_prompt_note(
            current_content=current_content,
            company_query=company_query,
            company_record=company_record,
        )
        prompt_note = _merge_prompt_notes(prompt_note, vehicle_authorization_note)
        prompt_note = _merge_prompt_notes(prompt_note, address_prompt_note)
        prompt_note = _merge_prompt_notes(prompt_note, property_prompt_note)
        return DirectReplyPreparation(
            supplemental_documents=supplemental_documents,
            prompt_note=prompt_note,
            processing_events=processing_events,
        )

    intake_facts = _apply_company_record_share_transfer_defaults(
        intake_facts=_extract_slovak_share_transfer_request_facts(messages),
        company_record=company_record,
    )
    intake_facts = _apply_persisted_share_transfer_conflict_choice(
        messages=prior_messages,
        intake_facts=intake_facts,
        company_record=company_record,
    )
    conflict_resolution = _resolve_share_transfer_conflict_choice(
        current_content=current_content,
        prior_messages=prior_messages,
        intake_facts=intake_facts,
        company_record=company_record,
    )
    intake_facts = conflict_resolution["intake_facts"]
    provided_labels = _share_transfer_provided_labels(intake_facts)
    missing_labels = _share_transfer_missing_labels(intake_facts)
    if provided_labels:
        emit_processing_event(
            events=processing_events,
            event=build_processing_event(
                stage="intake",
                message=f"Zo zadania som zachytil: {', '.join(provided_labels)}.",
                details={"provided": provided_labels},
            ),
            callback=processing_event_callback,
        )
    if missing_labels:
        emit_processing_event(
            events=processing_events,
            event=build_processing_event(
                stage="intake",
                message=f"Pred finalnym draftom este chyba: {', '.join(missing_labels)}.",
                details={"missing": missing_labels},
            ),
            callback=processing_event_callback,
        )
    else:
        emit_processing_event(
            events=processing_events,
            event=build_processing_event(
                stage="intake",
                message="Vsetky klucove vstupy pre draft prevodu podielu uz mam k dispozicii.",
            ),
            callback=processing_event_callback,
        )

    user_confirmed_document_generation = current_turn_confirms_document_generation(
        current_content,
        prior_messages,
    )

    if conflict_resolution["resolved"]:
        emit_processing_event(
            events=processing_events,
            event=build_processing_event(
                stage="validation",
                message=(
                    "Potvrdil som, ze sa ma pri prevodcovi pouzit ORSR vlastnik."
                    if conflict_resolution["choice"] == "orsr"
                    else "Potvrdil som, ze sa ma pri prevodcovi ponechat udaj zo zadania uzivatela."
                ),
                details={"choice": conflict_resolution["choice"]},
            ),
            callback=processing_event_callback,
        )
        if not user_confirmed_document_generation:
            return DirectReplyPreparation(
                supplemental_documents=supplemental_documents,
                direct_reply=_build_slovak_share_transfer_intake_reply(
                    company_record=company_record,
                    intake_facts=intake_facts,
                ),
                processing_events=processing_events,
            )

    conflicts = _detect_share_transfer_conflicts(
        intake_facts=intake_facts,
        company_record=company_record,
    )
    if conflicts:
        emit_processing_event(
            events=processing_events,
            event=build_processing_event(
                stage="validation",
                message="Nasiel som potencialny nesulad medzi prevodcom od uzivatela a ORSR vlastnikom.",
                details={"conflicts": conflicts},
            ),
            callback=processing_event_callback,
        )
        return DirectReplyPreparation(
            supplemental_documents=supplemental_documents,
            direct_reply=_build_slovak_share_transfer_conflict_reply(
                company_record=company_record,
                intake_facts=intake_facts,
            ),
            processing_events=processing_events,
        )

    prompt_note = _build_slovak_share_transfer_model_prompt_note(
        company_query=company_query,
        company_record=company_record,
        intake_facts=intake_facts,
        provided_labels=provided_labels,
        missing_labels=missing_labels,
        conflicts=conflicts,
        user_confirmed_document_generation=user_confirmed_document_generation,
    )
    prompt_note = _merge_prompt_notes(prompt_note, address_prompt_note)
    prompt_note = _merge_prompt_notes(prompt_note, property_prompt_note)
    return DirectReplyPreparation(
        supplemental_documents=supplemental_documents,
        prompt_note=prompt_note,
        processing_events=processing_events,
    )




def _looks_like_tool_capability_question(content: str) -> bool:
    normalized = _canonicalize_slovak_text(content)
    if not normalized:
        return False
    asks_for_list = any(
        token in normalized
        for token in (
            "zoznam",
            "ake",
            "aky",
            "co mozem pouzit",
            "co vies pouzit",
            "ktore mozem pouzit",
            "vsetky",
        )
    )
    mentions_tools = any(
        token in normalized
        for token in (
            "tool",
            "tools",
            "tuls",
            "tulsy",
            "nastroj",
            "nastroje",
            "overenie",
            "overit",
            "preverenie",
            "preverit",
        )
    )
    mentions_known_domain = any(
        token in normalized
        for token in (
            "obchodnom registri",
            "obchodny register",
            "firm",
            "ico",
            "auto",
            "vozidlo",
            "vin",
            "spz",
            "adresa",
            "kataster",
            "list vlastnictva",
            "dlh",
            "dlznik",
        )
    )
    return asks_for_list and mentions_tools and mentions_known_domain


def _build_slovak_tool_capabilities_reply() -> str:
    definitions = {definition.name: definition for definition in build_default_tool_registry().list_definitions()}
    ordered_tools = [
        (
            "obchodny_register_company_check",
            "overenie slovenskej firmy v Obchodnom registri: obchodné meno, IČO, sídlo, stav, konatelia a spoločníci",
        ),
        (
            "registeradries_address_validate",
            "overenie a rozklad slovenskej adresy cez registeradries.sk",
        ),
        (
            "slovakia_property_lv_lookup",
            "príprava overenia listu vlastníctva, katastra alebo vlastníka nehnuteľnosti",
        ),
        (
            "slovakia_car_validate",
            "overenie vozidla podľa VIN alebo EČV/SPZ vrátane obmedzení k histórii vlastníkov",
        ),
        (
            "dovera_debtor_check",
            "informatívne preverenie verejného zoznamu dlžníkov zdravotnej poisťovne Dôvera",
        ),
    ]
    lines = [
        "Aktuálne viem v slovenskom režime použiť tieto overovacie nástroje:",
        "",
    ]
    for tool_name, fallback_description in ordered_tools:
        definition = definitions.get(tool_name)
        description = definition.purpose if definition is not None else fallback_description
        consent = (
            "vyžaduje výslovný súhlas používateľa"
            if definition is not None and definition.requires_explicit_user_confirmation
            else "bez dodatočného súhlasu, ak sú vstupné údaje dostupné"
        )
        required_input = ", ".join(definition.input_fields) if definition is not None else "podľa typu overenia"
        lines.extend(
            [
                f"- {tool_name}: {description}",
                f"  Vstupy: {required_input}. Súhlas: {consent}.",
            ]
        )
    lines.extend(
        [
            "",
            "Pri právne rizikových výstupoch výsledok vždy zobrazím ako text na kontrolu používateľom. "
            "Raw audio neukladám a pri nástrojoch pracujem len s údajmi potrebnými na aktuálny úkon.",
        ]
    )
    return "\n".join(lines)


def _canonicalize_slovak_text(value: str) -> str:
    repaired = value.replace("�", "á")
    decomposed = unicodedata.normalize("NFKD", repaired.casefold())
    ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^0-9a-z]+", " ", ascii_only).strip()


def _looks_like_payment_confirmation_final_request(
    *,
    current_content: str,
    prior_messages: list[Message],
) -> bool:
    user_context = " ".join(
        message.content for message in prior_messages if message.role == MessageRole.USER
    )
    normalized = _canonicalize_slovak_text(f"{user_context} {current_content}")
    payment_tokens = ("zaplat", "uhrad", "platb", "splatk")
    loan_tokens = ("pozic", "pozick", "pozical", "pozicala", "pozicali", "dlh", "dlzn")
    if "potvrdenie" not in normalized or not any(token in normalized for token in payment_tokens + loan_tokens):
        return False
    final_markers = (
        "chcem",
        "pdf",
        "vygeneruj",
        "generuj",
        "finalny",
        "finalne",
        "konecnu",
        "konecna",
        "priprav",
        "vytvor",
    )
    return any(marker in normalized for marker in final_markers)


def _append_payment_confirmation_validation_events(
    *,
    events: list[dict[str, object]],
    current_content: str,
    company_record: dict[str, object] | None,
    callback: Callable[[dict[str, object]], None] | None,
) -> None:
    registry = build_default_tool_registry()
    consented = _payment_validation_consent_given(current_content)
    if company_record and consented:
        seat = str(company_record.get("seat") or "").strip()
        if seat:
            address_result = registry.run("registeradries_address_validate", address_text=seat)
            emit_processing_event(
                events=events,
                event=build_processing_event(
                    stage="tool_result",
                    tool_name="registeradries_address_validate",
                    message=(
                        "Overenie adresy firmy je pripravene."
                        if address_result.ok
                        else "Adresu firmy sa nepodarilo namapovat cez registeradries."
                    ),
                    details={"ok": address_result.ok, "records": list(address_result.records[:1])},
                ),
                callback=callback,
            )
    spz = _extract_slovak_spz(current_content)
    if spz and consented:
        car_result = registry.run("slovakia_car_validate", spz=spz, run_api_check=True)
        emit_processing_event(
            events=events,
            event=build_processing_event(
                stage="tool_result",
                tool_name="slovakia_car_validate",
                message=(
                    f"Overenie vozidla pre SPZ {spz} je pripravene."
                    if car_result.ok
                    else f"Overenie vozidla pre SPZ {spz} zlyhalo."
                ),
                details={"ok": car_result.ok, "message": car_result.message, "records": list(car_result.records[:1])},
            ),
            callback=callback,
        )


def _payment_validation_consent_given(content: str) -> bool:
    normalized = _canonicalize_slovak_text(content)
    return any(token in normalized for token in ("suhlasim", "ano", "over", "prever"))


def _extract_slovak_spz(content: str) -> str:
    match = re.search(r"\b([A-Z]{2}\s?[0-9]{3}\s?[A-Z]{2})\b", content.upper())
    if match is None:
        return ""
    return re.sub(r"\s+", "", match.group(1))


def _build_slovak_payment_confirmation_ready_reply(
    *,
    current_content: str,
    company_record: dict[str, object] | None,
) -> str:
    facts = _extract_payment_confirmation_request_facts(
        current_content=current_content,
        company_record=company_record,
    )
    document_body = "\n".join(_build_slovak_confirmation_document_lines(facts))
    document_title = "Potvrdenie o pozicke" if facts["document_kind"] == "loan_confirmation" else "Potvrdenie o zaplateni"
    document_filename = "Potvrdenie_o_pozicke.pdf" if facts["document_kind"] == "loan_confirmation" else "Potvrdenie_o_zaplateni.pdf"
    document_path = f"documents/{document_filename}"
    case_update: dict[str, object] = {
        "case": {
            "case_id": None,
            "status": "ready_for_next_step",
            "jurisdiction": {"country": "SK", "language": "sk-SK"},
            "parties": {
                "client": {"name": facts["payer"]},
                "opponent": {"name": facts["recipient"]},
            },
            "matter": {
                "category": "civil" if facts["document_kind"] == "loan_confirmation" else "commercial",
                "topic": facts["document_kind"],
                "amount_eur": facts["amount_number"],
                "key_dates": {"splatnost": facts["due_date"]},
                "facts_summary": facts["purpose"],
                "client_goal": f"Pripravit {document_title.lower()} vo formate PDF.",
            },
            "documents": [
                {
                    "doc_id": "DOC-001",
                    "type": facts["document_kind"],
                    "title": document_title,
                    "filename": document_filename,
                    "path": document_path,
                    "content": document_body,
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "notes": "Finalny dokument pripraveny na export.",
                }
            ],
            "open_questions": [],
            "next_discussion": {"scheduled_for": None, "agenda": []},
            "discussions_append": [],
        }
    }
    verification_lines = [
        "Tu je konecna verzia dokumentu - dokument je pripraveny na export a stiahnutie.",
        "",
        "Pripravil som navrh dokumentu. Pred podpisom doplnte chybajuce udaje, skontrolujte totoznost stran a nechajte dokument pravne skontrolovat, ak sa na nom budete spoliehat.",
        "",
        "Podklady pre export:",
        f"Dokument: {document_title}",
        f"Poskytovatel / platitel: {facts['payer']}",
        f"Prijemca / dlznik: {facts['recipient']}",
        f"Suma: {facts['amount']}",
        f"Doba / datum splatnosti: {facts['due_date']}",
        f"Ucel: {facts['purpose']}",
        "",
        "Odporucane kroky pred pouzitim:",
        "1. Doplnte presnu sumu pozicky a identifikacne udaje poskytovatela pozicky.",
        "2. Overte obciansky preukaz a adresu dlznika pred podpisom.",
        "3. Podpiste dokument oboma stranami; pri vyssej sume zvazte overenie podpisov.",
        "AI navrh pred pouzitim skontrolujte clovekom.",
        "",
        document_body,
    ]
    if facts["company_summary"]:
        verification_lines.extend(["", f"Overenie firmy: {facts['company_summary']}"])
    if facts["spz"]:
        verification_lines.append(f"Overenie auta: SPZ {facts['spz']} bola spracovana cez dostupny validacny plan.")
    verification_lines.extend(["", f"CASE_UPDATE_JSON:\n{json.dumps(case_update, ensure_ascii=False)}"])
    return "\n".join(verification_lines)


def _extract_payment_confirmation_request_facts(
    *,
    current_content: str,
    company_record: dict[str, object] | None,
) -> dict[str, object]:
    normalized = _canonicalize_slovak_text(current_content)
    is_loan_confirmation = any(token in normalized for token in ("pozic", "pozick", "pozical", "dlh", "dlzn"))
    amount_match = re.search(r"\b([0-9\s]+(?:[.,][0-9]{1,2})?\s*(?:eur|eu|€))\b", current_content, re.IGNORECASE)
    if amount_match is None and is_loan_confirmation:
        amount_match = re.search(
            r"(?:na\s*)?pozic\w*\s+([0-9]+(?:[.,][0-9]{1,2})?)\b",
            normalized,
            re.IGNORECASE,
        )
    amount = " ".join(amount_match.group(1).split()) if amount_match else "Suma bude doplnena pred podpisom."
    amount_number_match = re.search(r"[0-9]+(?:[.,][0-9]{1,2})?", amount.replace(" ", ""))
    amount_number = float(amount_number_match.group(0).replace(",", ".")) if amount_number_match else None
    due_match = re.search(
        r"(?:splatn[ée]\s+k|splatnost\s+k|k\s+d[áa]tumu)\s*([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4})",
        current_content,
        re.IGNORECASE,
    )
    loan_term_match = re.search(
        r"\bna\s+([0-9]+)\s*(rok|roky|rokov|mesiac|mesiace|mesiacov)\b",
        current_content,
        re.IGNORECASE,
    )
    if due_match:
        due_date = due_match.group(1)
    elif loan_term_match:
        due_date = f"{loan_term_match.group(1)} {loan_term_match.group(2)} od odovzdania pozicky"
    elif "do konca roka" in normalized:
        due_date = "do konca roka"
    else:
        due_date = "Datum bude doplneny pred podpisom."
    spz = _extract_slovak_spz(current_content)
    purpose = "potvrdenie o prijati pozicky" if is_loan_confirmation else "splatka auta"
    if spz:
        purpose = f"splatka auta so SPZ {spz}"
    company_name = str((company_record or {}).get("name") or "").strip()
    company_ico = str((company_record or {}).get("registration_number") or "").strip()
    company_seat = str((company_record or {}).get("seat") or "").strip()
    company_summary = ""
    if company_name:
        company_summary = ", ".join(
            part
            for part in (
                company_name,
                f"IČO {company_ico}" if company_ico else "",
                company_seat,
            )
            if part
        )
    borrower_name = _extract_private_loan_borrower(current_content)
    borrower_address = _extract_private_loan_address(current_content)
    borrower_id = _extract_private_loan_identity_number(current_content)
    recipient = company_summary or company_name or borrower_name or "Prijemca bude doplneny pred podpisom."
    payer = _extract_represented_person(current_content) or "Poskytovatel pozicky bude doplneny pred podpisom."
    return {
        "document_kind": "loan_confirmation" if is_loan_confirmation else "payment_confirmation",
        "amount": amount,
        "amount_number": amount_number,
        "due_date": due_date,
        "spz": spz,
        "purpose": purpose,
        "recipient": recipient,
        "payer": payer,
        "company_summary": company_summary,
        "borrower_address": borrower_address,
        "borrower_id": borrower_id,
    }


def _extract_private_loan_borrower(content: str) -> str:
    patterns = (
        r"pozicala\s+peniaze\s+([^,.;]+)",
        r"pozical\s+peniaze\s+([^,.;]+)",
        r"(?:na\s*)?pozic\w*\s+[0-9]+(?:[.,][0-9]{1,2})?\s+pre\s+([^,.;]+)",
        r"pozicat\s+peniaze\s+[^,.;]*?\s+([A-ZÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ][^,.;]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, content, flags=re.IGNORECASE)
        if match is not None:
            return " ".join(match.group(1).strip().split())
    return ""


def _extract_private_loan_address(content: str) -> str:
    match = re.search(r"\badresa\s+([^.;]+?)(?:,\s*(?:cislo|číslo)\b|$)", content, flags=re.IGNORECASE)
    if match is None:
        return ""
    address = re.sub(r"\s+do\s+konca\s+roka\b.*$", "", match.group(1), flags=re.IGNORECASE)
    return " ".join(address.strip(" ,").split())


def _extract_private_loan_identity_number(content: str) -> str:
    match = re.search(
        r"(?:cislo|číslo)\s+obcianskeho\s*[:=]?\s*([A-Z0-9-]+)",
        content,
        flags=re.IGNORECASE,
    )
    if match is None:
        return ""
    return match.group(1).strip().upper()


def _build_slovak_confirmation_document_lines(facts: dict[str, object]) -> list[str]:
    if facts["document_kind"] != "loan_confirmation":
        return [
            "Potvrdenie o zaplateni",
            "",
            f"Platitel: {facts['payer']}",
            f"Prijemca: {facts['recipient']}",
            f"Suma: {facts['amount']}",
            f"Datum platby / splatnosti: {facts['due_date']}",
            f"Ucel platby: {facts['purpose']}",
            "",
            "Vyhlasenie:",
            "Prijemca tymto potvrdzuje prijatie uvedenej platby od platitela.",
            "",
            "V [mesto], dna [datum vystavenia]",
            "",
            "Podpis prijemcu: _______________________________",
        ]
    borrower_address = str(facts.get("borrower_address") or "Adresa dlznika bude doplnena pred podpisom.")
    borrower_id = str(facts.get("borrower_id") or "Cislo dokladu bude doplnene pred podpisom.")
    return [
        "Potvrdenie o pozicke",
        "",
        f"Poskytovatel pozicky: {facts['payer']}",
        f"Dlznik: {facts['recipient']}",
        f"Adresa dlznika: {borrower_address}",
        f"Cislo obcianskeho preukazu dlznika: {borrower_id}",
        f"Suma pozicky: {facts['amount']}",
        f"Doba / splatnost pozicky: {facts['due_date']}",
        "",
        "Vyhlasenie:",
        (
            "Poskytovatel pozicky tymto potvrdzuje, ze dlznikovi odovzdal penaznu pozicku "
            "v uvedenej sume. Dlznik podpisom potvrdzuje prevzatie pozicky a zavazuje sa ju "
            "vratit v uvedenej dobe, ak sa strany pisomne nedohodnu inak."
        ),
        "",
        "Poznamka:",
        (
            "Pred podpisom doplnte presnu sumu, datum odovzdania penazi a identifikacne udaje "
            "poskytovatela pozicky. Pri vyssej sume zvazte overenie podpisov."
        ),
        "",
        "V [mesto], dna [datum vystavenia]",
        "",
        "Podpis poskytovatela pozicky: _______________________________",
        "Podpis dlznika: _______________________________",
    ]


def _extract_represented_person(content: str) -> str:
    match = re.search(
        r"v\s+zast[úu]pen[íi]\s+([^,.;]+)",
        content,
        re.IGNORECASE,
    )
    if match is None:
        return ""
    return " ".join(match.group(1).strip().split())


def _merge_prompt_notes(primary: str, secondary: str) -> str:
    if primary and secondary:
        return f"{primary}\n\n{secondary}"
    return primary or secondary


def _build_slovak_address_validation_prompt_note(*, current_content: str, prior_messages: list[Message]) -> str:
    if not _looks_like_address_relevant_context(current_content=current_content, prior_messages=prior_messages):
        return ""

    preference = _resolve_address_validation_preference(prior_messages=prior_messages)
    if preference == "yes":
        return "\n".join(
            [
                "SLOVAK ADDRESS VALIDATION MODE:",
                "- User already opted in to address validation for this case.",
                "- When address text is present, run registeradries_address_validate and map fields: kraj, okres, city, street, house_number, psc.",
                "- Reuse the remembered consent and do not ask for the same confirmation again unless the user changes preference.",
            ]
        )
    if preference == "no":
        return "\n".join(
            [
                "SLOVAK ADDRESS VALIDATION MODE:",
                "- User declined address validation for this case.",
                "- Do not run registeradries_address_validate unless the user explicitly changes their decision.",
            ]
        )

    return "\n".join(
        [
            "SLOVAK ADDRESS VALIDATION MODE:",
            "- This turn likely requires an address.",
            "- Before using address validation tools, ask exactly one concise consent question whether the user wants address validation via registeradries.sk.",
            "- After the user answers yes/no, remember that choice for the rest of this case.",
        ]
    )




def _build_slovak_property_validation_prompt_note(*, current_content: str, prior_messages: list[Message]) -> str:
    if not _looks_like_property_relevant_context(current_content=current_content, prior_messages=prior_messages):
        return ""

    preference = _resolve_property_validation_preference(prior_messages=prior_messages)
    if preference == "yes":
        return "\n".join(
            [
                "SLOVAK PROPERTY VALIDATION MODE:",
                "- User already opted in to property LV validation for this case.",
                "- Run slovakia_property_lv_lookup whenever property ownership or LV lookup is requested.",
                "- If only person_name is available, use search_scope=all_cadastral_units_slovakia.",
                "- Reuse remembered consent and do not ask for the same confirmation again unless the user changes preference.",
            ]
        )
    if preference == "no":
        return "\n".join(
            [
                "SLOVAK PROPERTY VALIDATION MODE:",
                "- User declined property LV validation for this case.",
                "- Do not run slovakia_property_lv_lookup unless the user explicitly changes their decision.",
            ]
        )

    return "\n".join(
        [
            "SLOVAK PROPERTY VALIDATION MODE:",
            "- This turn likely requires Slovak property (list vlastníctva) verification.",
            "- Before using property validation tools, ask exactly one concise consent question whether the user wants LV lookup via slovakia_property_lv_lookup.",
            "- After the user answers yes/no, remember that choice for the rest of this case.",
        ]
    )


def _looks_like_property_relevant_context(*, current_content: str, prior_messages: list[Message]) -> bool:
    combined = " ".join(current_content.lower().split())
    property_tokens = (
        "kupno",
        "predaj",
        "predajna",
        "predajnu",
        "pozem",
        "pozemok",
        "pozemky",
        "kataster",
        "katastri",
        "katastral",
        "list vlastnictva",
        "list vlastníctva",
        "lv",
        "vlastnik",
        "vlastník",
    )
    if any(token in combined for token in property_tokens):
        return True
    for message in reversed(prior_messages[-8:]):
        if message.role != MessageRole.ASSISTANT:
            continue
        lowered = message.content.lower()
        if "list vlast" in lowered and "?" in lowered:
            return True
        if "lv" in lowered and "?" in lowered:
            return True
    return False


def _resolve_property_validation_preference(*, prior_messages: list[Message]) -> str | None:
    yes_tokens = (
        "chcem overit lv",
        "chcem overiť lv",
        "chcem vyhladat lv",
        "chcem vyhľadať lv",
        "overit list vlastnictva",
        "overiť list vlastníctva",
        "zisti pozemky",
        "zistiť pozemky",
    )
    no_tokens = (
        "nechcem overit lv",
        "nechcem overiť lv",
        "neoverovat lv",
        "neoverovať lv",
        "nechcem list vlastnictva",
        "nechcem list vlastníctva",
    )
    for index in range(len(prior_messages) - 1, -1, -1):
        user_message = prior_messages[index]
        if user_message.role != MessageRole.USER:
            continue
        user_text = " ".join(user_message.content.lower().split())
        if any(token in user_text for token in yes_tokens):
            return "yes"
        if any(token in user_text for token in no_tokens):
            return "no"
        if not _is_affirmative_or_negative_reply(user_text):
            continue
        previous_assistant = _nearest_previous_assistant(prior_messages=prior_messages, before_index=index)
        if not previous_assistant:
            continue
        assistant_text = previous_assistant.lower()
        if "lv" not in assistant_text and "list vlast" not in assistant_text and "pozem" not in assistant_text:
            continue
        return "yes" if _is_affirmative_short_reply(user_text) else "no"
    return None


def _looks_like_address_relevant_context(*, current_content: str, prior_messages: list[Message]) -> bool:
    combined = " ".join(current_content.lower().split())
    address_tokens = (
        "adresa",
        "adresu",
        "bydlisko",
        "sidlo",
        "sídlo",
        "ulica",
        "psc",
        "psč",
        "okres",
        "kraj",
        "mesto",
        "obec",
        "nehnutelnost",
        "nehnuteľnosť",
    )
    if any(token in combined for token in address_tokens):
        return True
    if re.search(r"\b\d{3}\s?\d{2}\b", combined):
        return True
    for message in reversed(prior_messages[-8:]):
        if message.role != MessageRole.ASSISTANT:
            continue
        lowered = message.content.lower()
        if "adresa" in lowered and "?" in lowered:
            return True
    return False


def _resolve_address_validation_preference(*, prior_messages: list[Message]) -> str | None:
    for index in range(len(prior_messages) - 1, -1, -1):
        user_message = prior_messages[index]
        if user_message.role != MessageRole.USER:
            continue
        user_text = " ".join(user_message.content.lower().split())
        if any(token in user_text for token in ("chcem overit adresu", "chcem validovat adresu", "overit adresu", "validovat adresu")):
            return "yes"
        if any(token in user_text for token in ("nechcem overit adresu", "nechcem validovat adresu", "neoverovat adresu")):
            return "no"
        if not _is_affirmative_or_negative_reply(user_text):
            continue
        previous_assistant = _nearest_previous_assistant(prior_messages=prior_messages, before_index=index)
        if not previous_assistant:
            continue
        assistant_text = previous_assistant.lower()
        if "over" not in assistant_text or "adres" not in assistant_text:
            continue
        return "yes" if _is_affirmative_short_reply(user_text) else "no"
    return None


def _is_affirmative_or_negative_reply(normalized_content: str) -> bool:
    if _is_affirmative_short_reply(normalized_content):
        return True
    cleaned = re.sub(r"[^0-9a-záäčďéíĺľňóôŕšťúýž]+", " ", normalized_content.lower()).strip()
    if not cleaned:
        return False
    return cleaned.split()[0] in {"nie", "no", "nein"}


def _nearest_previous_assistant(*, prior_messages: list[Message], before_index: int) -> str:
    for idx in range(before_index - 1, -1, -1):
        message = prior_messages[idx]
        if message.role == MessageRole.ASSISTANT:
            return message.content
    return ""

def _looks_like_company_document_matter(*, current_content: str, prior_messages: list[Message]) -> bool:
    combined = " ".join(current_content.lower().split())
    company_tokens = (
        "s.r.o",
        "s. r. o",
        "a.s",
        "a. s",
        "firma",
        "spolocnost",
        "spoločnosť",
        "ico",
        "ičo",
    )
    document_tokens = (
        "dokument",
        "document",
        "navrh",
        "návrh",
        "priprav",
        "vygeneruj",
        "zmluv",
        "podanie",
    )
    if any(token in combined for token in company_tokens) and any(token in combined for token in document_tokens):
        return True
    if _is_affirmative_short_reply(combined) and _assistant_recently_discussed_company_documents(prior_messages):
        return True
    return False


def _looks_like_company_registry_information_question(current_content: str) -> bool:
    combined = " ".join(current_content.lower().split())
    company_tokens = (
        "s.r.o",
        "s. r. o",
        "a.s",
        "a. s",
        "firma",
        "spolocnost",
        "spoločnosť",
        "ico",
        "ičo",
    )
    registry_information_tokens = (
        "kto je majitel",
        "kto je vlastnik",
        "kto je vlastník",
        "majitel firmy",
        "majiteľ firmy",
        "vlastnik firmy",
        "vlastník firmy",
        "kto je spolocnik",
        "kto je spoločník",
        "spolocnici",
        "spoločníci",
        "kto je konatel",
        "kto je konateľ",
        "konatelia",
        "konatel",
        "konateľ",
        "statutarny organ",
        "štatutárny orgán",
    )
    return any(token in combined for token in company_tokens) and any(
        token in combined for token in registry_information_tokens
    )


def _looks_like_share_transfer_case(*, current_content: str, prior_messages: list[Message]) -> bool:
    combined = " ".join(current_content.lower().split())
    share_transfer_tokens = (
        "prevod podielu",
        "prevod obchodneho podielu",
        "prevod obchodného podielu",
        "obchodny podiel",
        "obchodný podiel",
        "prevodca",
        "nadobudatel",
        "nadobúdateľ",
        "konatel",
        "konateľ",
        "novy vlastnik",
        "nový vlastník",
        "dalsi vlastnik",
        "ďalší vlastník",
        "spolocnicka struktura",
        "spoločnícka štruktúra",
        "bezodplatne",
        "odplatne",
        "share transfer",
    )
    if any(token in combined for token in share_transfer_tokens):
        return True
    if _looks_like_contextual_followup_reply(combined):
        if _assistant_recently_discussed_share_transfer(prior_messages):
            return True
        if _user_recently_described_share_transfer(prior_messages):
            return True
    return False


def _is_affirmative_short_reply(normalized_content: str) -> bool:
    cleaned = re.sub(r"[^0-9a-záäčďéíĺľňóôŕšťúýž]+", " ", normalized_content.lower()).strip()
    if not cleaned:
        return False
    affirmative_tokens = {
        "ano",
        "áno",
        "yes",
        "ok",
        "okej",
        "jasne",
        "jasné",
        "potvrdzujem",
        "suhlasim",
        "súhlasím",
    }
    first_token = cleaned.split()[0]
    return first_token in affirmative_tokens


def _looks_like_contextual_followup_reply(normalized_content: str) -> bool:
    cleaned = re.sub(r"\s+", " ", normalized_content.strip())
    if not cleaned or len(cleaned) > 120 or "?" in cleaned:
        return False
    if _is_affirmative_short_reply(cleaned):
        return True
    lowered = cleaned.lower()
    if any(
        token in lowered
        for token in (
            "orsr",
            "podla orsr",
            "podľa orsr",
            "podla zadania",
            "podľa zadania",
            "ponechat prevodcu",
            "ponechať prevodcu",
        )
    ):
        return True
    negative_tokens = {"nie", "no", "nein"}
    if lowered.split()[0] in negative_tokens:
        return True
    return any(character.isdigit() for character in cleaned)


def _assistant_recently_discussed_company_documents(prior_messages: list[Message]) -> bool:
    last_assistant_content = ""
    for message in reversed(prior_messages):
        if message.role == MessageRole.ASSISTANT:
            last_assistant_content = message.content.lower()
            break

    if last_assistant_content:
        if "?" in last_assistant_content and any(
            token in last_assistant_content for token in ("dokument", "dokumentu", "navrh", "návrh", "zmluv")
        ):
            return True

    relevant_tokens = (
        "zmluva o prevode obchodného podielu",
        "zmluva o prevode obchodneho podielu",
        "pripravil aj tento zvyšný balík dokumentov",
        "pripravil aj tento zvysny balik dokumentov",
        "dokumentácie k prevodu obchodného podielu",
        "dokumentacie k prevodu obchodneho podielu",
    )
    for message in reversed(prior_messages):
        if message.role != MessageRole.ASSISTANT:
            continue
        lowered = message.content.lower()
        if any(token in lowered for token in relevant_tokens):
            return True
    return False


def _assistant_recently_discussed_share_transfer(prior_messages: list[Message]) -> bool:
    relevant_tokens = (
        "prevod obchodného podielu",
        "prevod obchodneho podielu",
        "spoločnícka štruktúra",
        "spolocnicka struktura",
        "nadobúdateľ",
        "nadobudatel",
        "prevodca",
    )
    for message in reversed(prior_messages):
        if message.role != MessageRole.ASSISTANT:
            continue
        lowered = message.content.lower()
        if any(token in lowered for token in relevant_tokens):
            return True
    return False


def _assistant_recently_requested_share_transfer_conflict_resolution(
    prior_messages: list[Message],
) -> bool:
    for message in reversed(prior_messages):
        if message.role != MessageRole.ASSISTANT:
            continue
        lowered = message.content.lower()
        return (
            "ktorý prevodca je správny" in lowered
            or "ktory prevodca je spravny" in lowered
            or "má sa použiť vlastník podľa orsr" in lowered
            or "ma sa pouzit vlastnik podla orsr" in lowered
        )
    return False


def _user_recently_described_share_transfer(prior_messages: list[Message]) -> bool:
    relevant_tokens = (
        "prevod podielu",
        "obchodny podiel",
        "obchodný podiel",
        "prevodca",
        "nadobudatel",
        "nadobúdateľ",
        "spolocnicka struktura",
        "spoločnícka štruktúra",
        "bezodplatne",
        "odplatne",
        "novy vlastnik",
        "nový vlastník",
        "dalsi vlastnik",
        "ďalší vlastník",
        "splocnika",
        "spolocnika",
        "spoločníka",
    )
    for message in reversed(prior_messages):
        if message.role != MessageRole.USER:
            continue
        lowered = message.content.lower()
        if any(token in lowered for token in relevant_tokens):
            return True
    return False


def _extract_slovak_company_query(
    *,
    messages: list[Message],
    current_content: str,
) -> str | None:
    company_suffix = r"(?:s\.?\s*r\.?\s*o\.?|a\.?\s*s\.?)"
    suffix_boundary = r"(?=$|[\s,;\n\.\?!\)])"
    registration_pattern = re.compile(r"(?:\bičo\b|\bico\b)\s*[:=]?\s*([0-9]{6,10})", re.IGNORECASE)
    owner_question_company_pattern = re.compile(
        rf"(?:kto\s+je\s+(?:majitel|majiteľ|vlastnik|vlastník)\s+firmy)\s+"
        rf"([^,;\n]{{1,120}}?\b{company_suffix}{suffix_boundary})",
        re.IGNORECASE,
    )
    labeled_company_pattern = re.compile(
        rf"(?:obchodné\s+meno|obchodne\s+meno|názov|nazov|firma|firmy|fima|fimy|spoločnosť|spolocnost)\s*[:=]\s*"
        rf"([^,;\n]{{1,120}}?\b{company_suffix}{suffix_boundary})",
        re.IGNORECASE,
    )
    prefixed_company_pattern = re.compile(
        rf"(?:firma|firmy|firmu|fima|fimy|fimu|spoločnosť|spolocnost)\s+"
        rf"([^,;\n]{{1,120}}?\b{company_suffix}{suffix_boundary})",
        re.IGNORECASE,
    )
    company_pattern = re.compile(
        rf"([A-Z0-9ÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ][^,;\n]{{1,120}}?\b{company_suffix}{suffix_boundary})",
        re.IGNORECASE,
    )
    def _extract_from_text(text: str) -> str | None:
        registration_match = registration_pattern.search(text)
        if registration_match is not None:
            return registration_match.group(1).strip()
        owner_question_match = owner_question_company_pattern.search(text)
        if owner_question_match is not None:
            return _normalize_company_query(owner_question_match.group(1))
        labeled_match = labeled_company_pattern.search(text)
        if labeled_match is not None:
            return _normalize_company_query(labeled_match.group(1))
        prefixed_match = prefixed_company_pattern.search(text)
        if prefixed_match is not None:
            return _normalize_company_query(prefixed_match.group(1))
        company_matches = list(company_pattern.finditer(text))
        if company_matches:
            return _normalize_company_query(company_matches[0].group(1))
        return None

    extracted_current = _extract_from_text(current_content)
    if extracted_current:
        return extracted_current

    for message in reversed(messages):
        if message.role != MessageRole.USER:
            continue
        extracted = _extract_from_text(message.content)
        if extracted:
            return extracted
    return None


def _normalize_company_query(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" ,.;")
    company_suffix = r"(?:s\.?\s*r\.?\s*o\.?|a\.?\s*s\.?)"
    embedded_company_markers = list(
        re.finditer(
            rf"(?:firma|firmy|firmu|fima|fimy|fimu|spoločnosť|spolocnost)\s+"
            rf"([^,;\n]{{1,120}}?\b{company_suffix})(?=$|[\s,;\n\.\?!\)])",
            cleaned,
            flags=re.IGNORECASE,
        )
    )
    if embedded_company_markers:
        last_marker = embedded_company_markers[-1]
        if last_marker.start() > 0:
            cleaned = last_marker.group(1).strip(" ,.;")
    cleaned = re.sub(
        r"^(?:"
        r"kto\s+je\s+(?:majitel|majiteľ|vlastnik|vlastník)\s+firmy|"
        r".*?\b(?:obchodné\s+meno|obchodne\s+meno|názov|nazov)\s*[:=]?|"
        r"na\s+firmu|pre\s+firmu|firmu|firmy|firma|fimu|fimy|fima|"
        r"na\s+spoločnosť|na\s+spolocnost|pre\s+spoločnosť|pre\s+spolocnost|"
        r"spoločnosť|spolocnost"
        r")\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.strip(" ,.;")
    if re.search(r"s\.?\s*r\.?\s*o$", cleaned, flags=re.IGNORECASE):
        return re.sub(r"s\.?\s*r\.?\s*o$", "s.r.o.", cleaned, flags=re.IGNORECASE)
    if re.search(r"a\.?\s*s$", cleaned, flags=re.IGNORECASE):
        return re.sub(r"a\.?\s*s$", "a.s.", cleaned, flags=re.IGNORECASE)
    return cleaned


def _load_cached_slovak_company_registry_document(
    company_query: str,
) -> tuple[dict[str, object] | None, CoreDocument | None, bool] | None:
    normalized_query = _normalize_company_query(company_query)
    registry = build_default_tool_registry()
    cache_key = _orsr_cache_key(normalized_query, registry)
    with _ORSR_CACHE_LOCK:
        cached_payload = _ORSR_CACHE.get(cache_key)
    if cached_payload is None:
        return None
    return _restore_slovak_company_registry_document(
        company_query=normalized_query,
        cached_payload=cached_payload,
        cache_hit=True,
    )


def _load_slovak_company_registry_document(
    company_query: str,
) -> tuple[dict[str, object] | None, CoreDocument | None, bool]:
    normalized_query = _normalize_company_query(company_query)
    registry = build_default_tool_registry()
    cache_key = _orsr_cache_key(normalized_query, registry)
    with _ORSR_CACHE_LOCK:
        cached_payload = _ORSR_CACHE.get(cache_key)
    if cached_payload is not None:
        return _restore_slovak_company_registry_document(
            company_query=normalized_query,
            cached_payload=cached_payload,
            cache_hit=True,
        )

    result = registry.run(
        "obchodny_register_company_check",
        company_name_or_registration=normalized_query,
    )
    if not result.ok or not result.records:
        cached_payload = (None, None)
        with _ORSR_CACHE_LOCK:
            _ORSR_CACHE[cache_key] = cached_payload
        return _restore_slovak_company_registry_document(
            company_query=normalized_query,
            cached_payload=cached_payload,
            cache_hit=False,
        )

    primary = result.records[0]
    normalized_primary: dict[str, object] = {
        "name": str(primary.get("name", "")).strip(),
        "registration_number": str(primary.get("registration_number", "")).strip(),
        "seat": str(primary.get("seat", "")).strip(),
        "status": str(primary.get("status", "")).strip(),
        "stakeholders": list(primary.get("stakeholders", []) or []),
        "statutory_representatives": list(primary.get("statutory_representatives", []) or []),
        "authorization_to_execute": str(primary.get("authorization_to_execute", "")).strip(),
        "deposits": list(primary.get("deposits", []) or []),
        "equity_value": str(primary.get("equity_value", "")).strip(),
    }
    lines = [
        "Slovak business register lookup",
        f"Query: {company_query}",
        f"Result count: {len(result.records)}",
        "",
    ]
    for index, record in enumerate(result.records[:3], start=1):
        lines.extend(
            [
                f"Candidate {index}:",
                f"Name: {str(record.get('name', '')).strip() or '[missing]'}",
                f"Registration number: {str(record.get('registration_number', '')).strip() or '[missing]'}",
                f"Seat: {str(record.get('seat', '')).strip() or '[missing]'}",
                f"Status: {str(record.get('status', '')).strip() or '[missing]'}",
                "",
            ]
        )
    stakeholders = normalized_primary.get("stakeholders")
    if isinstance(stakeholders, list) and stakeholders:
        lines.append("Current stakeholders:")
        for stakeholder in stakeholders:
            if not isinstance(stakeholder, dict):
                continue
            entry = ", ".join(
                part
                for part in (
                    str(stakeholder.get("name", "")).strip(),
                    str(stakeholder.get("address", "")).strip(),
                )
                if part
            )
            if entry:
                lines.append(f"- {entry}")
        lines.append("")
    statutory_representatives = normalized_primary.get("statutory_representatives")
    if isinstance(statutory_representatives, list) and statutory_representatives:
        lines.append("Current statutory representatives:")
        for representative in statutory_representatives:
            if not isinstance(representative, dict):
                continue
            entry = ", ".join(
                part
                for part in (
                    str(representative.get("name", "")).strip(),
                    str(representative.get("address", "")).strip(),
                )
                if part
            )
            if entry:
                lines.append(f"- {entry}")
        lines.append("")
    authorization_to_execute = str(normalized_primary.get("authorization_to_execute", "")).strip()
    if authorization_to_execute:
        lines.extend(
            [
                "Authorization to execute in company name:",
                authorization_to_execute,
                "",
            ]
        )
    cached_payload = (normalized_primary, "\n".join(lines).strip())
    with _ORSR_CACHE_LOCK:
        _ORSR_CACHE[cache_key] = cached_payload
    return _restore_slovak_company_registry_document(
        company_query=normalized_query,
        cached_payload=cached_payload,
        cache_hit=False,
    )


def _restore_slovak_company_registry_document(
    *,
    company_query: str,
    cached_payload: tuple[dict[str, object] | None, str | None],
    cache_hit: bool,
) -> tuple[dict[str, object] | None, CoreDocument | None, bool]:
    cached_record, cached_content = cached_payload
    restored_record = deepcopy(cached_record) if cached_record is not None else None
    restored_document = None
    if cached_content is not None:
        restored_document = CoreDocument(
            doc_id=f"orsr-{sha1(company_query.encode('utf-8')).hexdigest()[:16]}",
            path="registry/slovak_business_register.md",
            content=cached_content,
        )
    return restored_record, restored_document, cache_hit


def _orsr_cache_key(company_query: str, registry: object) -> tuple[str, str, str]:
    registry_type = type(registry)
    return (
        company_query,
        getattr(registry_type, "__module__", ""),
        getattr(registry_type, "__qualname__", registry_type.__name__),
    )


def _build_slovak_company_prompt_note(
    *,
    company_query: str,
    company_record: dict[str, object] | None,
) -> str:
    lines = [
        "TOOL-FIRST COMPANY LOOKUP MODE:",
        f"- The system already queried obchodny_register_company_check using: {company_query}",
        "- Use the verified company data first instead of asking again for company name, IČO, seat, status, or statutory-register basics when they are already available.",
        "- If some drafting inputs are still missing, ask only for those missing items.",
        "- If the user asks to see the draft now, do not repeat prior intake questions. Produce the working draft with placeholders for any still-missing signature details.",
    ]
    if company_record:
        lines.extend(
            [
                f"- Verified company name: {company_record.get('name') or '[missing]'}",
                f"- Verified registration number: {company_record.get('registration_number') or '[missing]'}",
                f"- Verified seat: {company_record.get('seat') or '[missing]'}",
                f"- Verified status: {company_record.get('status') or '[missing]'}",
            ]
        )
        stakeholders = company_record.get("stakeholders") or []
        if isinstance(stakeholders, list) and stakeholders:
            stakeholder_entries = []
            for stakeholder in stakeholders[:3]:
                if not isinstance(stakeholder, dict):
                    continue
                entry = ", ".join(
                    part
                    for part in (
                        str(stakeholder.get("name", "")).strip(),
                        str(stakeholder.get("address", "")).strip(),
                    )
                    if part
                )
                if entry:
                    stakeholder_entries.append(entry)
            if stakeholder_entries:
                lines.append(f"- Verified current stakeholders: {'; '.join(stakeholder_entries)}")
    return "\n".join(lines)


def _build_slovak_registry_question_prompt_note(
    *,
    company_query: str,
    company_record: dict[str, object] | None,
) -> str:
    lines = [
        "SLOVAK ORSR REGISTRY ANSWER MODE:",
        f"- The system already queried obchodny_register_company_check using: {company_query}",
        "- Answer the user question using verified register data.",
        "- Keep the answer concise and factual.",
        "- If register data is missing or ambiguous, ask one short clarification question.",
        "- Do not switch to share-transfer drafting flow unless the user explicitly asks for document preparation.",
    ]
    if company_record:
        lines.extend(
            [
                f"- Verified company name: {company_record.get('name') or '[missing]'}",
                f"- Verified registration number: {company_record.get('registration_number') or '[missing]'}",
                f"- Verified seat: {company_record.get('seat') or '[missing]'}",
                f"- Verified status: {company_record.get('status') or '[missing]'}",
            ]
        )
    return "\n".join(lines)


def _build_slovak_vehicle_authorization_prompt_note(
    *,
    current_content: str,
    company_query: str,
    company_record: dict[str, object] | None,
) -> str:
    facts = _extract_slovak_vehicle_authorization_facts(
        current_content=current_content,
        company_query=company_query,
        company_record=company_record,
    )
    if not facts:
        return ""

    lines = [
        "SLOVAK VEHICLE AUTHORIZATION INTAKE MODE:",
        "- The user is asking for splnomocnenie/plna moc to use or drive a company motor vehicle.",
        "- Treat the following extracted facts as already provided. Do not ask the user to repeat them unless they later contradict them.",
        "- If the authorized person's name is captured from wording like 'pre dceru <name>', do not ask again for the daughter's name.",
        "- Ask at most one follow-up question only for a legally necessary missing item, such as the principal's statutory representative details, the authorized person's address/birth date, or whether the draft should be generated now.",
    ]
    for key, value in facts.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _extract_slovak_vehicle_authorization_facts(
    *,
    current_content: str,
    company_query: str,
    company_record: dict[str, object] | None,
) -> dict[str, str]:
    normalized = _canonicalize_slovak_text(current_content)
    if not any(token in normalized for token in ("splnomocnenie", "plna moc", "plnomoc")):
        return {}
    if not any(token in normalized for token in ("vozidlo", "vozidla", "motorove", "motoroveho", "auto", "auta")):
        return {}

    facts: dict[str, str] = {}
    authorized_person = _extract_vehicle_authorized_person(current_content)
    authorized_person_address = _extract_vehicle_authorized_person_address(current_content)
    vehicle_plate = _extract_slovak_spz(current_content)
    effective_from = _extract_slovak_effective_from_date(current_content)

    company_name = str((company_record or {}).get("name") or company_query or "").strip()
    company_ico = str((company_record or {}).get("registration_number") or "").strip()
    company_seat = str((company_record or {}).get("seat") or "").strip()
    company_parts = [
        part
        for part in (company_name, f"ICO {company_ico}" if company_ico else "", company_seat)
        if part
    ]

    if authorized_person:
        facts["authorized_person"] = authorized_person
    if authorized_person_address:
        facts["authorized_person_address"] = authorized_person_address
    if company_parts:
        facts["principal_company"] = ", ".join(company_parts)
    if vehicle_plate:
        facts["vehicle_registration_number"] = vehicle_plate
    if effective_from:
        facts["effective_from"] = effective_from
    if "dobu neurcitu" in normalized or "neurcitu dobu" in normalized:
        facts["duration"] = "na dobu neurcitu"
    return facts


def _looks_like_vehicle_authorization_final_request(content: str) -> bool:
    normalized = _canonicalize_slovak_text(content)
    if not any(token in normalized for token in ("splnomocnenie", "plna moc", "plnomoc")):
        return False
    if not any(token in normalized for token in ("vozidlo", "vozidla", "auto", "auta", "motorov")):
        return False
    final_markers = ("priprav", "vygeneruj", "vytvor", "document", "dokument")
    language_markers = (
        "slovencine",
        "slovencina",
        "slovenskom",
        "slovensky",
        "slovak",
        "anglictine",
        "anglickom",
        "anglicky",
        "english",
    )
    return any(marker in normalized for marker in final_markers) and any(
        marker in normalized for marker in language_markers
    )


def _build_slovak_vehicle_authorization_ready_reply(*, facts: dict[str, str]) -> str:
    principal_company = facts.get("principal_company") or "[doplnit obchodne meno, ICO a sidlo splnomocnitela]"
    authorized_person = facts.get("authorized_person") or "[doplnit meno splnomocnenca]"
    authorized_address = facts.get("authorized_person_address") or "[doplnit adresu splnomocnenca]"
    vehicle = facts.get("vehicle_registration_number") or "[doplnit identifikaciu vozidla / ECV / VIN]"
    effective_from = facts.get("effective_from") or "dnom podpisu"
    duration = facts.get("duration") or "do odvolania"

    return (
        "Tu su finalne verzie splnomocnenia v slovenskej a anglickej verzii. "
        "Pred podpisom overte opravnenie osoby konat za spolocnost a doplnte identifikaciu vozidla, "
        "ak nie je uvedena v tomto navrhu.\n\n"
        "**Splnomocnenie (slovenska verzia)**\n\n"
        "Splnomocnitel:\n"
        f"{principal_company}\n"
        "konajuci prostrednictvom statutarneho organu alebo inej opravnenej osoby: [doplnit meno, funkciu a pravny titul konania]\n\n"
        "Splnomocnenec:\n"
        f"{authorized_person}, adresa: {authorized_address}\n\n"
        "Rozsah splnomocnenia:\n"
        f"Splnomocnitel tymto splnomocnuje splnomocnenca na vedenie a bezne uzivanie motoroveho vozidla spolocnosti {principal_company}. "
        f"Vozidlo: {vehicle}. Splnomocnenec je opravneny vykonavat bezne ukony suvisiace s vedenim vozidla, "
        "predlozit toto splnomocnenie policajnym, spravnym, poistnym a servisnym organom alebo subjektom, "
        "a preukazat opravnenie uzivat vozidlo v rozsahu dovolenom pravnym poriadkom.\n\n"
        "Trvanie:\n"
        f"Toto splnomocnenie je ucinne od {effective_from} a plati {duration}, pokial ho splnomocnitel pisomne neodvola skor.\n\n"
        "Pravny ucel a kontrola:\n"
        "Navrh je pripraveny na pravne ucely podla vseobecnych pravidiel zastupenia v slovenskom sukromnom prave. "
        "Pred pouzitim odporucam pravnu kontrolu, overenie podpisu podla poziadaviek konkretneho uradu alebo zmluvneho partnera "
        "a overenie, ze osoba podpisujuca za spolocnost je opravnena konat.\n\n"
        "Miesto a datum: ____________________________\n\n"
        "Za splnomocnitela: ____________________________\n"
        "Meno, funkcia, podpis\n\n"
        "Splnomocnenec potvrdzuje prevzatie splnomocnenia: ____________________________\n\n"
        "**Power of Attorney (English version)**\n\n"
        "Principal:\n"
        f"{principal_company}\n"
        "acting through its statutory body or another authorized representative: [insert name, position and authority]\n\n"
        "Attorney-in-fact:\n"
        f"{authorized_person}, address: {authorized_address}\n\n"
        "Scope of authority:\n"
        f"The Principal authorizes the Attorney-in-fact to drive and ordinarily use the company motor vehicle of {principal_company}. "
        f"Vehicle: {vehicle}. The Attorney-in-fact may perform ordinary acts connected with driving and using the vehicle, "
        "present this power of attorney to police, administrative, insurance and service authorities or entities, "
        "and prove the right to use the vehicle within the scope permitted by applicable law.\n\n"
        "Term:\n"
        f"This power of attorney is effective from {effective_from} and remains valid {duration}, unless revoked earlier in writing by the Principal.\n\n"
        "Legal purpose and review:\n"
        "This draft is prepared for legal purposes under the general rules of representation in Slovak private law. "
        "Before use, legal review is recommended, including verification of signature requirements of the relevant authority or contractual partner "
        "and verification that the person signing on behalf of the company is authorized to act.\n\n"
        "Place and date: ____________________________\n\n"
        "For the Principal: ____________________________\n"
        "Name, position, signature\n\n"
        "Attorney-in-fact acknowledges receipt of this power of attorney: ____________________________\n\n"
        "Dokumenty su pripravene na stiahnutie."
    )


def _extract_vehicle_authorized_person(content: str) -> str:
    explicit_address_match = re.search(
        r"\bpre\s+([^,.;]+?)\s*,\s*adresa\b",
        content,
        flags=re.IGNORECASE,
    )
    if explicit_address_match is not None:
        return " ".join(explicit_address_match.group(1).strip().split())

    bytom_match = re.search(
        r"\bpre\s+([^,.;]+?)\s*,\s*bytom\b",
        content,
        flags=re.IGNORECASE,
    )
    if bytom_match is not None:
        return " ".join(bytom_match.group(1).strip().split())

    match = re.search(
        r"\bpre\s+(?:dceru|dc[ée]ru|syna|manzelku|manzela|osobu)\s+([^,.;]+?)(?=\s+na\s+|\s+od\s+|[,.;]|$)",
        content,
        flags=re.IGNORECASE,
    )
    if match is None:
        match = re.search(
            r"\bsplnomocnenie\s+pre\s+([^,.;]+?)(?=\s+na\s+|\s+od\s+|[,.;]|$)",
            content,
            flags=re.IGNORECASE,
        )
    if match is None:
        return ""
    return " ".join(match.group(1).strip().split())


def _extract_vehicle_authorized_person_address(content: str) -> str:
    match = re.search(
        r"\b(?:adresa|bytom)\s+([^.;]+?)(?=\s+(?:od\s+\d{1,2}\.\d{1,2}\.\d{4}|priprav|vygeneruj|vytvor)\b|[.;]|$)",
        content,
        flags=re.IGNORECASE,
    )
    if match is None:
        return ""
    return " ".join(match.group(1).strip(" ,").split())


def _extract_slovak_effective_from_date(content: str) -> str:
    match = re.search(r"\bod\s+([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4})", content, flags=re.IGNORECASE)
    if match is None:
        return ""
    return match.group(1)


def _build_slovak_share_transfer_model_prompt_note(
    *,
    company_query: str,
    company_record: dict[str, object] | None,
    intake_facts: dict[str, str],
    provided_labels: list[str],
    missing_labels: list[str],
    conflicts: list[str],
    user_confirmed_document_generation: bool,
) -> str:
    lines = [
        "SLOVAK SHARE-TRANSFER TOOL ORCHESTRATION MODE:",
        f"- The system already queried obchodny_register_company_check using: {company_query}",
        "- Use verified company data first and do not ask again for company name, IČO, seat, status when available.",
        "- Continue with share-transfer workflow and ask only for missing drafting inputs.",
        "- Do not claim that PDF or ZIP files are already created, saved, attached, or uploaded.",
        "- If the drafting package is complete, say it is ready for export or download.",
        "- Treat every item listed under 'Already captured inputs' as already answered unless the user later contradicts it.",
        "- Be proactive: recommend the full set of likely Slovak corporate steps, related document changes, filing updates, and attachments even if the user asked only about one document.",
        "- If conflicts are detected between user-provided transferor and ORSR owners, do not finalize drafts yet.",
        "- In conflict cases, ask the user to confirm whether to keep user data or ORSR owner data, then continue.",
    ]
    if company_record:
        lines.extend(
            [
                f"- Verified company name: {company_record.get('name') or '[missing]'}",
                f"- Verified registration number: {company_record.get('registration_number') or '[missing]'}",
                f"- Verified seat: {company_record.get('seat') or '[missing]'}",
                f"- Verified status: {company_record.get('status') or '[missing]'}",
            ]
        )
    if provided_labels:
        lines.append(f"- Already captured inputs: {', '.join(provided_labels)}")
        if intake_facts.get("transfer_share"):
            lines.append(
                "- Share scope is already captured, so do not ask again for the percentage or transferred share."
            )
        if intake_facts.get("management_change"):
            lines.append(
                "- Management/signing-change status is already captured, so do not ask again whether konatel or sposob konania changes."
            )
    if missing_labels:
        lines.append(f"- Still missing inputs: {', '.join(missing_labels)}")
    else:
        lines.append("- All core drafting inputs appear present.")
    lines.extend(_build_slovak_share_transfer_proactive_recommendations(intake_facts=intake_facts))
    if conflicts:
        lines.append("- Conflict checks:")
        lines.extend(f"  - {conflict}" for conflict in conflicts)
        lines.append(
            "- Ask the user to confirm the authoritative transferor identity before producing final documents."
        )
    elif user_confirmed_document_generation:
        lines.append(
            "- The user confirmed document generation in this turn. Prepare draft package now using verified data."
        )
    return "\n".join(lines)


def _build_slovak_share_transfer_proactive_recommendations(
    *, intake_facts: dict[str, str]
) -> list[str]:
    lines = [
        "- Proactively search the verified ORSR facts and the user's wording for all necessary follow-on steps and related changes.",
        "- Always consider and mention the usual Slovak follow-on package where relevant: transfer agreement, corporate approval (sole shareholder decision or general meeting minutes), updated full text of the spolocenska zmluva or zakladatelska listina, signature verification, collection-of-deeds attachments, and ORSR filing steps.",
    ]
    if intake_facts.get("transferee_details"):
        lines.append(
            "- The request already points to an additional or new owner. Explicitly assess whether the spolocenska zmluva or zakladatelska listina must be updated to reflect the new shareholder structure, ownership percentages, and any related capital/vklad wording."
        )
    if intake_facts.get("management_change"):
        lines.append(
            "- If the captured facts show that only shareholder structure changes, keep the recommendations focused on ownership documents and filings rather than re-asking about management."
        )
    return lines


def _detect_share_transfer_conflicts(
    *,
    intake_facts: dict[str, str],
    company_record: dict[str, object] | None,
) -> list[str]:
    conflicts: list[str] = []
    if not company_record:
        return conflicts

    transferor_details = intake_facts.get("transferor_details", "").strip()
    if not transferor_details:
        return conflicts

    transferor_name = _extract_primary_person_name(transferor_details)
    if not transferor_name:
        return conflicts

    stakeholders_value = company_record.get("stakeholders")
    if not isinstance(stakeholders_value, list):
        return conflicts

    stakeholder_names = [
        str(stakeholder.get("name", "")).strip()
        for stakeholder in stakeholders_value
        if isinstance(stakeholder, dict) and str(stakeholder.get("name", "")).strip()
    ]
    if not stakeholder_names:
        return conflicts

    normalized_transferor = _normalize_person_name(transferor_name)
    normalized_stakeholders = [_normalize_person_name(name) for name in stakeholder_names]
    if normalized_transferor and normalized_transferor not in normalized_stakeholders:
        conflicts.append(
            "User-provided transferor does not match current ORSR stakeholders: "
            f"user='{transferor_name}', orsr={'; '.join(stakeholder_names)}"
        )
    return conflicts


def _extract_primary_person_name(person_details: str) -> str:
    segments = [segment.strip() for segment in person_details.split(",") if segment.strip()]
    for segment in segments:
        candidate = re.sub(r"^.*?=\s*", "", segment).strip()
        if not candidate or _is_generic_transferor_reference(candidate):
            continue
        if re.search(r"[A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž].*\s+[A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž]", candidate):
            return candidate
    head = segments[0] if segments else ""
    if head:
        return re.sub(r"^.*?=\s*", "", head).strip()
    tokens = person_details.split()
    if not tokens:
        return ""
    return " ".join(tokens[:3]).strip()


def _normalize_person_name(value: str) -> str:
    lowered = value.lower()
    cleaned = re.sub(r"[^a-z0-9áäčďéíĺľňóôŕšťúýž]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _build_slovak_share_transfer_conflict_reply(
    *,
    company_record: dict[str, object] | None,
    intake_facts: dict[str, str],
) -> str:
    user_transferor = intake_facts.get("transferor_details", "").strip() or "[nevyplnené]"
    stakeholders_value = (company_record or {}).get("stakeholders")
    stakeholder_lines: list[str] = []
    if isinstance(stakeholders_value, list):
        for stakeholder in stakeholders_value:
            if not isinstance(stakeholder, dict):
                continue
            stakeholder_name = str(stakeholder.get("name", "")).strip()
            stakeholder_address = str(stakeholder.get("address", "")).strip()
            if stakeholder_name and stakeholder_address:
                stakeholder_lines.append(f"{stakeholder_name}, {stakeholder_address}")
            elif stakeholder_name:
                stakeholder_lines.append(stakeholder_name)
    orsr_transferor = "; ".join(stakeholder_lines) if stakeholder_lines else "[nepodarilo sa overiť]"
    return "\n".join(
        [
            "Najprv som overil firmu v Obchodnom registri.",
            f"Podľa ORSR je aktuálny vlastník / spoločník: {orsr_transferor}.",
            f"Vo vašom zadaní je ako prevodca uvedené: {user_transferor}.",
            "Tieto údaje sa nezhodujú, preto zatiaľ nechcem pripraviť nesprávny návrh dokumentov.",
            "Prosím potvrďte, ktorý prevodca je správny: má sa použiť vlastník podľa ORSR, alebo chcete ponechať prevodcu podľa vášho zadania?",
        ]
    )


def _build_slovak_company_registry_summary_reply(
    *,
    company_query: str,
    company_record: dict[str, object] | None,
) -> str:
    if not company_record:
        return (
            "Overil som firmu v Obchodnom registri, ale nepodarilo sa nájsť zodpovedajúci aktuálny záznam "
            f"pre '{company_query}'. Skontrolujte prosím presný názov firmy alebo IČO."
        )

    name = str(company_record.get("name", "")).strip() or "[nepodarilo sa overiť]"
    registration_number = (
        str(company_record.get("registration_number", "")).strip() or "[nepodarilo sa overiť]"
    )
    seat = str(company_record.get("seat", "")).strip() or "[nepodarilo sa overiť]"
    status = str(company_record.get("status", "")).strip() or "[nepodarilo sa overiť]"

    lines = [
        "Najprv som overil firmu v Obchodnom registri.",
        "Overené firemné údaje:",
        f"Obchodné meno: {name}",
        f"IČO: {registration_number}",
        f"Sídlo: {seat}",
        f"Stav: {status}",
    ]

    stakeholders = company_record.get("stakeholders")
    if isinstance(stakeholders, list) and stakeholders:
        lines.append("Aktuálni spoločníci (majitelia) podľa ORSR:")
        for stakeholder in stakeholders:
            if not isinstance(stakeholder, dict):
                continue
            stakeholder_name = str(stakeholder.get("name", "")).strip()
            stakeholder_address = str(stakeholder.get("address", "")).strip()
            if stakeholder_name and stakeholder_address:
                lines.append(f"- {stakeholder_name}, {stakeholder_address}")
            elif stakeholder_name:
                lines.append(f"- {stakeholder_name}")
    else:
        lines.append("Aktuálni spoločníci (majitelia): [nepodarilo sa overiť]")

    statutory_representatives = company_record.get("statutory_representatives")
    if isinstance(statutory_representatives, list) and statutory_representatives:
        lines.append("Štatutárny orgán podľa ORSR:")
        for representative in statutory_representatives:
            if not isinstance(representative, dict):
                continue
            representative_name = str(representative.get("name", "")).strip()
            representative_address = str(representative.get("address", "")).strip()
            if representative_name and representative_address:
                lines.append(f"- {representative_name}, {representative_address}")
            elif representative_name:
                lines.append(f"- {representative_name}")

    return "\n".join(lines)


def _resolve_share_transfer_conflict_choice(
    *,
    current_content: str,
    prior_messages: list[Message],
    intake_facts: dict[str, str],
    company_record: dict[str, object] | None,
) -> ShareTransferConflictResolution:
    merged = dict(intake_facts)
    if not _assistant_recently_requested_share_transfer_conflict_resolution(prior_messages):
        return {"resolved": False, "choice": "", "intake_facts": merged}

    choice = _parse_share_transfer_conflict_choice(current_content)
    if choice == "orsr":
        resolved_transferor = _get_single_orsr_transferor_details(company_record)
        if resolved_transferor:
            merged["transferor_details"] = resolved_transferor
            return {"resolved": True, "choice": "orsr", "intake_facts": merged}
        return {"resolved": False, "choice": "", "intake_facts": merged}
    if choice == "user":
        return {"resolved": True, "choice": "user", "intake_facts": merged}

    return {"resolved": False, "choice": "", "intake_facts": merged}


def _apply_persisted_share_transfer_conflict_choice(
    *,
    messages: list[Message],
    intake_facts: dict[str, str],
    company_record: dict[str, object] | None,
) -> dict[str, str]:
    merged = dict(intake_facts)
    choice = _latest_share_transfer_conflict_choice(messages)
    if choice != "orsr":
        return merged
    resolved_transferor = _get_single_orsr_transferor_details(company_record)
    if resolved_transferor:
        merged["transferor_details"] = resolved_transferor
    return merged


def _latest_share_transfer_conflict_choice(messages: list[Message]) -> str:
    pending_conflict_question = False
    latest_choice = ""
    for message in messages:
        if message.role == MessageRole.ASSISTANT:
            if _assistant_recently_requested_share_transfer_conflict_resolution([message]):
                pending_conflict_question = True
            continue
        if message.role != MessageRole.USER or not pending_conflict_question:
            continue
        choice = _parse_share_transfer_conflict_choice(message.content)
        if choice:
            latest_choice = choice
            pending_conflict_question = False
    return latest_choice


def _parse_share_transfer_conflict_choice(content: str) -> str:
    normalized = re.sub(r"[^0-9a-záäčďéíĺľňóôŕšťúýž]+", " ", content.lower()).strip()
    if not normalized:
        return ""
    selects_orsr = _is_affirmative_short_reply(normalized) or any(
        token in normalized
        for token in (
            "orsr",
            "obchodny register",
            "obchodný register",
            "obchodnom registri",
            "podla orsr",
            "podľa orsr",
            "podla registra",
            "podľa registra",
        )
    )
    if selects_orsr:
        return "orsr"
    if any(
        token in normalized
        for token in (
            "podla zadania",
            "podľa zadania",
            "podla mojho zadania",
            "podľa môjho zadania",
            "ponechat prevodcu",
            "ponechať prevodcu",
            "moj prevodca",
            "môj prevodca",
            "uzivatela",
            "užívateľa",
        )
    ):
        return "user"
    return ""


def _get_single_orsr_transferor_details(company_record: dict[str, object] | None) -> str:
    if not company_record:
        return ""
    stakeholders = company_record.get("stakeholders") or []
    if not isinstance(stakeholders, list):
        return ""
    current_stakeholders = [
        stakeholder for stakeholder in stakeholders if isinstance(stakeholder, dict) and stakeholder.get("name")
    ]
    if len(current_stakeholders) != 1:
        return ""
    stakeholder = current_stakeholders[0]
    return ", ".join(
        part
        for part in (
            str(stakeholder.get("name", "")).strip(),
            str(stakeholder.get("address", "")).strip(),
        )
        if part
    )


def _build_slovak_share_transfer_intake_reply(
    *,
    company_record: dict[str, object] | None,
    intake_facts: dict[str, str],
) -> str:
    provided_lines = _share_transfer_provided_lines(intake_facts)
    missing_lines = _share_transfer_missing_lines(intake_facts)
    lines = [
        "Najprv som overil firmu v Obchodnom registri, aby som sa nepýtal na údaje, ktoré viem získať automaticky.",
        "",
        "Overené firemné údaje:",
        f"Obchodné meno: {(company_record or {}).get('name') or '[nepodarilo sa overiť]'}",
        f"IČO: {(company_record or {}).get('registration_number') or '[nepodarilo sa overiť]'}",
        f"Sídlo: {(company_record or {}).get('seat') or '[nepodarilo sa overiť]'}",
        f"Stav: {(company_record or {}).get('status') or '[nepodarilo sa overiť]'}",
        "",
    ]
    if provided_lines:
        lines.extend(
            [
                "Zo zadania už mám tieto údaje:",
                *provided_lines,
                "",
            ]
        )
    if missing_lines:
        lines.extend(
            [
                "Na finálny návrh dokumentácie k prevodu obchodného podielu ešte potrebujem doplniť len toto:",
                *missing_lines,
                "",
                "Keď doplníte tieto zostávajúce údaje, pripravím návrh dokumentácie a ďalší postup bez opakovania už overených firemných údajov.",
            ]
        )
        return "\n".join(lines)
    else:
        lines.extend(
            [
                "Na finálny návrh už mám všetky základné vstupy k prevodu obchodného podielu.",
                "",
            ]
        )
    lines.extend(
        [
            "Ak chcete, pripravím nielen samotnú zmluvu o prevode obchodného podielu, ale aj zvyšné súvisiace dokumenty, ktoré sa pri tejto zmene zvyčajne prikladajú.",
            "Typicky ide najmä o rozhodnutie jediného spoločníka alebo zápisnicu z valného zhromaždenia, úplné znenie spoločenskej zmluvy alebo zakladateľskej listiny po zmene a checklist podania do obchodného registra.",
            "",
            "Chcete, aby som spolu s hlavnou zmluvou pripravil aj tento zvyšný balík dokumentov v jednom výstupe?",
            "Keď doplníte len chýbajúce údaje alebo rovno potvrdíte prípravu celého balíka, pripravím návrh dokumentov a postup bez ďalšieho opakovania tých istých otázok.",
        ]
    )
    return "\n".join(lines)


def _build_slovak_share_transfer_direct_reply(
    *,
    messages: list[Message],
    company_record: dict[str, object] | None,
    normalize_document_lines: Callable[[str], list[str]],
    extract_document_facts: Callable[[list[str]], dict[str, str]],
    build_share_transfer_lines: Callable[[dict[str, str]], list[str]],
) -> str:
    context_lines = normalize_document_lines(
        "\n".join(
            message.content
            for message in messages
            if message.role in {MessageRole.USER, MessageRole.ASSISTANT}
        )
    )
    facts = extract_document_facts(context_lines)
    intake_facts = _apply_company_record_share_transfer_defaults(
        intake_facts=_extract_slovak_share_transfer_request_facts(messages),
        company_record=company_record,
    )
    intake_facts = _apply_persisted_share_transfer_conflict_choice(
        messages=messages,
        intake_facts=intake_facts,
        company_record=company_record,
    )
    if company_record:
        company_name = str(company_record.get("name", "")).strip()
        if company_name:
            facts["company_name"] = company_name
        company_registration_number = str(company_record.get("registration_number", "")).strip()
        if company_registration_number:
            facts["company_identifier"] = company_registration_number
        company_seat = str(company_record.get("seat", "")).strip()
        if company_seat:
            facts["company_seat"] = company_seat
    if intake_facts["transferor_details"]:
        facts["transferor_name"] = intake_facts["transferor_details"]
    if intake_facts["transferee_details"]:
        facts["transferee_name"] = intake_facts["transferee_details"]
    if intake_facts["transfer_share"]:
        facts["transfer_share"] = intake_facts["transfer_share"]
    if intake_facts["transfer_price"]:
        facts["transfer_price"] = intake_facts["transfer_price"]

    verified_lines = [
        "Pripravil som pracovný návrh dokumentácie k prevodu obchodného podielu.",
        "Použil som údaje, ktoré sa dali overiť automaticky v Obchodnom registri. Miesta označené [doplnit] je ešte potrebné vyplniť pred podpisom alebo podaním.",
        "",
        "Overené firemné údaje:",
        f"Obchodné meno: {facts['company_name']}",
        f"IČO: {facts['company_identifier']}",
        f"Sídlo: {facts['company_seat']}",
        "",
    ]
    return "\n".join([*verified_lines, *build_share_transfer_lines(facts)])


def build_slovak_share_transfer_export_lines(
    *,
    messages: list[Message],
    normalize_document_lines: Callable[[str], list[str]],
    extract_document_facts: Callable[[list[str]], dict[str, str]],
    build_share_transfer_lines: Callable[[dict[str, str]], list[str]],
) -> list[str] | None:
    user_messages = [message for message in messages if message.role == MessageRole.USER]
    if not user_messages:
        return None
    current_content = user_messages[-1].content
    if not _looks_like_share_transfer_case(
        current_content=current_content,
        prior_messages=messages[:-1],
    ):
        return None
    company_query = _extract_slovak_company_query(messages=messages, current_content=current_content)
    company_record = None
    if company_query:
        company_record, _, _ = _load_slovak_company_registry_document(company_query)
    direct_reply = _build_slovak_share_transfer_direct_reply(
        messages=messages,
        company_record=company_record,
        normalize_document_lines=normalize_document_lines,
        extract_document_facts=extract_document_facts,
        build_share_transfer_lines=build_share_transfer_lines,
    )
    return normalize_document_lines(direct_reply)


def _extract_slovak_share_transfer_request_facts(messages: list[Message]) -> dict[str, str]:
    user_text = "\n".join(
        message.content
        for message in messages
        if message.role == MessageRole.USER
    )
    normalized_text = " ".join(user_text.lower().split())

    transferor_details = _extract_labeled_multiline_value(
        user_text,
        labels=(
            "prevodca",
            "súčasný vlastník",
            "sucasny vlastnik",
            "súčasný spoločník",
            "sucasny spolocnik",
        ),
    )
    transferee_details = _extract_labeled_multiline_value(
        user_text,
        labels=(
            "nový vlastník",
            "novy vlastnik",
            "ďalší vlastník",
            "dalsi vlastnik",
            "nadobúdateľ",
            "nadobudatel",
            "nový spoločník",
            "novy spolocnik",
        ),
    )
    if not transferee_details:
        inline_transferee_match = re.search(
            r"(?:ďalší vlastník|dalsi vlastnik|nový vlastník|novy vlastnik|nadobúdateľ|nadobudatel)\s*:\s*(.+?)(?=\s+\d+[.)]\s+|$)",
            user_text,
            re.IGNORECASE,
        )
        if inline_transferee_match is not None:
            transferee_details = " ".join(inline_transferee_match.group(1).strip(" ,;.").split())

    transfer_share = ""
    share_match = re.search(r"(?<!\d)(\d{1,3}\s*%)(?!\w)", user_text)
    if share_match is not None:
        transfer_share = re.sub(r"\s+", " ", share_match.group(1)).strip()
    elif re.search(r"(celý|cely)\s+(obchodný\s+podiel|obchodny\s+podiel)", normalized_text):
        transfer_share = "100 %"

    transfer_price = ""
    price_match = re.search(
        r"\b([0-9\s]+(?:[.,][0-9]{1,2})?\s*(?:eur|eu|€))\b",
        user_text,
        re.IGNORECASE,
    )
    if re.search(r"bezodplatn", normalized_text):
        transfer_price = "bezodplatne"
    elif price_match is not None:
        transfer_price = " ".join(price_match.group(1).split())
    elif re.search(r"\bodplatn", normalized_text):
        transfer_price = "odplatne [doplnit sumu]"

    management_change = ""
    if not (
        "alebo aj" in normalized_text
        and (
            "konateľ" in normalized_text
            or "konatel" in normalized_text
            or "spôsob konania" in normalized_text
            or "sposob konania" in normalized_text
        )
    ):
        if re.search(
            r"(mení sa iba spoločnícka štruktúra|meni sa iba spolocnicka struktura|nemení sa konateľ|nemeni sa konatel|nemení sa spôsob konania|nemeni sa sposob konania)",
            normalized_text,
        ):
            management_change = "Mení sa iba spoločnícka štruktúra; konateľ ani spôsob konania sa nemení."
        elif re.search(
            r"(mení sa aj konateľ|meni sa aj konatel|mení sa aj spôsob konania|meni sa aj sposob konania|aj konateľ|aj konatel)",
            normalized_text,
        ):
            management_change = "Mení sa aj konateľ alebo spôsob konania."
    if not management_change and re.search(
        r"(nemen[ií]\s+iba\s+spolo[cč]n[ií]cka\s+[šs]trukt[uú]ra|nemeni\s+iba\s+spolocnicka\s+struktura)",
        normalized_text,
    ):
        management_change = "Mení sa iba spoločnícka štruktúra; konateľ ani spôsob konania sa nemení."

    return {
        "transferor_details": transferor_details,
        "transferee_details": transferee_details,
        "transfer_share": transfer_share,
        "transfer_price": transfer_price,
        "management_change": management_change,
    }


def _extract_labeled_multiline_value(text: str, *, labels: tuple[str, ...]) -> str:
    lines = [line.strip() for line in text.splitlines()]
    escaped_labels = "|".join(re.escape(label) for label in labels)
    label_pattern = re.compile(rf"^(?:{escaped_labels})\s*[:=]\s*(.*)$", re.IGNORECASE)
    boundary_pattern = re.compile(
        r"^(?:\d+[.)]\s*|obchodné meno|obchodne meno|názov|nazov|firma|fima|spoločnosť|spolocnost|"
        r"nový vlastník|novy vlastnik|ďalší vlastník|dalsi vlastnik|nadobúdateľ|nadobudatel|"
        r"prevodca|súčasný vlastník|sucasny vlastnik|súčasný spoločník|sucasny spolocnik|"
        r"podiel|odplata|odplatn|bezodplatn|konateľ|konatel|spoločnícka|spolocnicka)\b",
        re.IGNORECASE,
    )
    for index, line in enumerate(lines):
        match = label_pattern.match(line)
        if match is None:
            continue
        values: list[str] = []
        inline_value = match.group(1).strip(" ,;")
        if inline_value:
            values.append(inline_value)
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor].strip(" ,;")
            if not candidate or boundary_pattern.match(candidate):
                break
            values.append(candidate)
            cursor += 1
        return ", ".join(value for value in values if value)
    return ""


def _apply_company_record_share_transfer_defaults(
    *,
    intake_facts: dict[str, str],
    company_record: dict[str, object] | None,
) -> dict[str, str]:
    if not company_record:
        return intake_facts
    merged = dict(intake_facts)
    if merged.get("transferor_details") and not _is_generic_transferor_reference(
        merged["transferor_details"]
    ):
        return merged
    stakeholders = company_record.get("stakeholders") or []
    if not isinstance(stakeholders, list):
        return merged
    current_stakeholders = [
        stakeholder for stakeholder in stakeholders if isinstance(stakeholder, dict) and stakeholder.get("name")
    ]
    if len(current_stakeholders) != 1:
        return merged
    stakeholder = current_stakeholders[0]
    merged["transferor_details"] = ", ".join(
        part
        for part in (
            str(stakeholder.get("name", "")).strip(),
            str(stakeholder.get("address", "")).strip(),
        )
        if part
    )
    return merged


def _is_generic_transferor_reference(value: str) -> bool:
    normalized = " ".join(value.lower().split())
    generic_tokens = (
        "vlastnik firmy",
        "majitel firmy",
        "majiteľ firmy",
        "sucasny vlastnik",
        "súčasný vlastník",
        "sucasny spolocnik",
        "súčasný spoločník",
        "povodny vlastnik",
        "pôvodný vlastník",
    )
    stripped = normalized
    for token in generic_tokens:
        stripped = stripped.replace(token, " ")
    stripped = re.sub(r"[^a-z0-9áäčďéíĺľňóôŕšťúýž]+", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return bool(normalized) and not stripped


def _share_transfer_provided_lines(intake_facts: dict[str, str]) -> list[str]:
    raw_lines: list[str] = []
    if intake_facts["transferor_details"]:
        raw_lines.append(f"Prevodca: {intake_facts['transferor_details']}.")
    if intake_facts["transferee_details"]:
        raw_lines.append(f"Nadobúdateľ: {intake_facts['transferee_details']}.")
    if intake_facts["transfer_share"]:
        raw_lines.append(f"Rozsah prevodu: {intake_facts['transfer_share']}.")
    if intake_facts["transfer_price"]:
        raw_lines.append(f"Odplata za prevod: {intake_facts['transfer_price']}.")
    if intake_facts["management_change"]:
        raw_lines.append(f"Zmena v orgánoch/spôsobe konania: {intake_facts['management_change']}")
    return [f"{index}. {line}" for index, line in enumerate(raw_lines, start=1)]


def _share_transfer_missing_lines(intake_facts: dict[str, str]) -> list[str]:
    raw_lines: list[str] = []
    if not intake_facts["transferor_details"]:
        raw_lines.append("Presné identifikačné údaje prevodcu.")
    if not intake_facts["transferee_details"]:
        raw_lines.append("Presné identifikačné údaje nadobúdateľa.")
    if not intake_facts["transfer_share"]:
        raw_lines.append("Presný rozsah prevádzaného podielu.")
    if not intake_facts["transfer_price"]:
        raw_lines.append("Potvrdenie, či je prevod odplatný alebo bezodplatný.")
    if not intake_facts["management_change"]:
        raw_lines.append("Potvrdenie, či sa mení iba spoločnícka štruktúra alebo aj konateľ / spôsob konania.")
    return [f"{index}. {line}" for index, line in enumerate(raw_lines, start=1)]


def _share_transfer_provided_labels(intake_facts: dict[str, str]) -> list[str]:
    labels: list[str] = []
    if intake_facts["transferor_details"]:
        labels.append("transferor identification")
    if intake_facts["transferee_details"]:
        labels.append("transferee identification")
    if intake_facts["transfer_share"]:
        labels.append("share scope")
    if intake_facts["transfer_price"]:
        labels.append("transfer price / gratuitous flag")
    if intake_facts["management_change"]:
        labels.append("management-change flag")
    return labels


def _share_transfer_missing_labels(intake_facts: dict[str, str]) -> list[str]:
    labels: list[str] = []
    if not intake_facts["transferor_details"]:
        labels.append("transferor identification")
    if not intake_facts["transferee_details"]:
        labels.append("transferee identification")
    if not intake_facts["transfer_share"]:
        labels.append("exact transferred share")
    if not intake_facts["transfer_price"]:
        labels.append("paid vs. gratuitous transfer")
    if not intake_facts["management_change"]:
        labels.append("management/signing change confirmation")
    return labels


def _orsr_tool_start_message(*, company_query: str, country: str, language: str | None) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return f"Idem overit spolocnost '{company_query}' v ORSR."
    if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        return f"Jdu overit spolecnost '{company_query}' v ORSR."
    if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        return f"Ich werde das Unternehmen '{company_query}' im ORSR pruefen."
    return f"I am going to verify company '{company_query}' in ORSR."


def _orsr_tool_cache_hit_message(*, company_query: str, country: str, language: str | None) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return f"Pouzijem uz overene ORSR data pre '{company_query}', aby som nezdrziaval dalsi krok."
    if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        return f"Pouziji uz overena ORSR data pro '{company_query}', at nezdrzuji dalsi krok."
    if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        return f"Ich verwende bereits verifizierte ORSR-Daten fuer '{company_query}', damit es schneller weitergeht."
    return f"Reusing verified ORSR data for '{company_query}' so the next step can continue faster."


def _orsr_tool_result_found_message(
    *,
    company_name: str,
    registration_number: str,
    company_seat: str = "",
    country: str,
    language: str | None,
) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    registration_text = registration_number.strip() or "ICO unavailable"
    seat_text = company_seat.strip()
    if not seat_text:
        if normalized_country == "SK" or normalized_language.startswith("sk"):
            return f"Overenie spolocnosti v ORSR je hotove: {company_name} ({registration_text})."
        if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
            return f"Overeni spolecnosti v ORSR je hotove: {company_name} ({registration_text})."
        if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
            return f"Unternehmenspruefung im ORSR abgeschlossen: {company_name} ({registration_text})."
        return f"Verification of company done in ORSR: {company_name} ({registration_text})."
    sk_company_text = f"{company_name}, ICO {registration_text}, sidlo: {seat_text}"
    localized_company_text = f"{company_name} ({registration_text}), seat: {seat_text}"
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return f"Overenie spolocnosti v ORSR je hotove: {sk_company_text}."
    if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        return f"Overeni spolecnosti v ORSR je hotove: {localized_company_text}."
    if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        return f"Unternehmenspruefung im ORSR abgeschlossen: {localized_company_text}."
    return f"Verification of company done in ORSR: {localized_company_text}."


def _orsr_tool_result_missing_message(*, company_query: str, country: str, language: str | None) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return f"Overenie spolocnosti v ORSR je hotove: pre '{company_query}' som nenasiel zhodu."
    if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        return f"Overeni spolecnosti v ORSR je hotove: pro '{company_query}' jsem nenasel shodu."
    if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        return f"Unternehmenspruefung im ORSR abgeschlossen: kein Treffer fuer '{company_query}'."
    return f"Verification of company done in ORSR: no matching record for '{company_query}'."
