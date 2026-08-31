from __future__ import annotations

import os
from uuid import uuid4

from app.chat.case_type_detection import (
    _clarification_reply,
    _detection_trace,
    _is_legal_research_request,
    resolve_case_catalog_context,
)
from app.chat.models import Message, MessageRole, Session

from aijurisdictionagents.api_db import ApiDatabaseStore, CaseCatalogSelection


def test_law_lookup_is_legal_research_not_document_case_detection() -> None:
    assert _is_legal_research_request(
        "Podľa aktuálnych údajov vysvetli obsah právneho predpisu č. 192/2026 Z. z."
    )
    assert _is_legal_research_request("Čo ustanovuje zákon č. 40/1964 Zb.?")
    assert _is_legal_research_request("Summarize legal act 192/2026 from the official source.")
    assert _is_legal_research_request(
        "Zobraz mi poslednych 5 novych zakonov aj so sumarom coho sa tykaju."
    )


def test_document_drafting_request_is_not_misclassified_as_legal_research() -> None:
    assert not _is_legal_research_request("Priprav návrh na platenie výživného.")


def test_latest_law_research_bypasses_ambiguous_case_catalog_selection() -> None:
    class _FailIfUsedStore:
        def __getattr__(self, name: str):
            raise AssertionError(f"Case catalog store must not be used for legal research: {name}")

    context = resolve_case_catalog_context(
        session_id=uuid4(),
        session=Session(
            country="SK",
            language="sk-SK",
            user_id=uuid4(),
            case_id="synthetic-payment-case",
        ),
        current_content=(
            "chcem vediet ktory je posledny zakon schvaleny na slovensku a coho sa tyka"
        ),
        prior_messages=[],
        route=object(),
        store=_FailIfUsedStore(),
        template_store=_FailIfUsedStore(),
        document_generation_requested=False,
    )

    assert context.selection is None
    assert context.direct_reply is None


def test_detection_trace_preserves_first_message_identity_across_retry() -> None:
    session_id = uuid4()
    selection = CaseCatalogSelection(
        selection_id="selection-1",
        selection_scope="session",
        entity_id=str(session_id),
        case_id="case-1",
        session_id=str(session_id),
        case_type_id="case-type-1",
        case_type_key="sk.real_estate.lease_agreement",
        case_type_name="Najomna zmluva",
        prompt_ids=(),
        template_ids=(),
        template_keys=(),
        status="ambiguous",
        confidence_score=0.55,
        confidence_gap=0.06,
        source="chat.case_type_detection_agent",
        first_message_preview="Chcem pripravit zmluvu k bytu.",
        first_message_sha256="hash-first-message",
        clarification_question="Ide o najom, alebo o kupu nehnutelnosti?",
        created_at="2026-08-21T10:00:00+00:00",
        updated_at="2026-08-21T10:01:00+00:00",
    )
    prior_messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Chcem pripravit zmluvu k bytu.",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Potrebujem este upresnit typ zmluvy.",
        ),
    ]

    trace = _detection_trace(
        prior_messages=prior_messages,
        current_content="Ide o najom bytu.",
        selection=selection,
    )

    assert trace.first_message_preview == "Chcem pripravit zmluvu k bytu."
    assert trace.first_message_sha256 == "hash-first-message"
    assert trace.detection_text == "Chcem pripravit zmluvu k bytu.\nIde o najom bytu."


def test_clarification_reply_uses_specific_question() -> None:
    session = Session(country="SK", language="SK")

    reply = _clarification_reply(
        session=session,
        question="Ide o najom, alebo o kupu nehnutelnosti?",
    )

    assert "Ide o najom, alebo o kupu nehnutelnosti?" in reply


def test_case_catalog_store_allows_session_selection_without_case(tmp_path) -> None:
    os.environ["DB_OPTION"] = "local"
    os.environ["STORAGE_OPTION"] = "local"
    os.environ["DB_LOCAL"] = str(tmp_path / "api.sqlite3")
    os.environ["STORE_LOCAL"] = str(tmp_path / "storage")

    store = ApiDatabaseStore.from_env()
    store.initialize()

    selection = store.upsert_case_catalog_selection(
        selection_scope="session",
        entity_id="session-1",
        case_id="",
        session_id="session-1",
        case_type_id="case-type-1",
        case_type_key="sk.real_estate.lease_agreement",
        case_type_name="Najomna zmluva",
        status="ambiguous",
        confidence_score=0.55,
        confidence_gap=0.06,
        source="chat.case_type_detection_agent",
        first_message_preview="Chcem pripravit zmluvu k bytu.",
        first_message_sha256="hash-first-message",
        clarification_question="Ide o najom, alebo o kupu nehnutelnosti?",
    )
    event = store.record_case_catalog_event(
        case_id="",
        session_id="session-1",
        event_type="case_type_detection.ambiguous",
        status="ambiguous",
        severity="info",
        summary="Automatic case-type detection needs clarification.",
        details={"clarification_question": "Ide o najom, alebo o kupu nehnutelnosti?"},
    )

    assert selection.case_id == ""
    assert event.case_id == ""
