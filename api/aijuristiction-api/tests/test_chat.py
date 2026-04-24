import json
from io import BytesIO
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
import unicodedata
from uuid import UUID, uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient
from pypdf import PdfReader
import pytest

from app.main import app


client = TestClient(app)
AUTH_HEADERS = {"x-api-key": "aijuris"}


def test_planned_document_tasks_keep_user_intent_order() -> None:
    from app.chat.intent_policy_service import planned_document_tasks

    tasks = planned_document_tasks(
        "Recreate the uploaded document based on new law and send me summary from document."
    )

    assert [task.task_id for task in tasks] == [
        "review_uploaded_document",
        "update_based_on_current_law",
        "prepare_summary",
    ]


def test_document_policy_plan_keeps_policy_order_for_future_extension() -> None:
    from app.chat.intent_policy_service import build_document_policy_plan

    plan = build_document_policy_plan(
        "Please recreate the uploaded document under current law and then summarize it."
    )

    assert [policy.policy_id for policy in plan.ordered_policies] == [
        "document_modernization",
        "document_summary",
    ]
    assert [task.task_id for task in plan.ordered_tasks] == [
        "review_uploaded_document",
        "update_based_on_current_law",
        "prepare_summary",
    ]


def test_document_task_plan_note_describes_multi_task_execution_order() -> None:
    from app.chat.intent_policy_service import build_document_task_plan_note

    note = build_document_task_plan_note(
        query="Fix uploaded document based on current laws and send me summary from document.",
        has_processed_documents=True,
    )

    assert "DOCUMENT TASK PLAN MODE" in note
    assert "Use a single policy-driven legal agent response." in note
    assert "Execute the requested document tasks in the same order as the user's intent." in note
    assert "Active policies in user-intent order:" in note
    assert "1. document_modernization" in note
    assert "2. document_summary" in note
    assert "1. review_uploaded_document" in note
    assert "2. update_based_on_current_law" in note
    assert "3. prepare_summary" in note
    assert "summarize the updated result" in note


def test_document_task_plan_note_defers_summary_output_until_documents_are_processed() -> None:
    from app.chat.intent_policy_service import build_document_task_plan_note

    note = build_document_task_plan_note(
        query="Send me summary from uploaded document.",
        has_processed_documents=False,
    )

    assert "document_summary" in note
    assert "defer content-specific output until processed" in note
    assert "Start with a plain-language summary" not in note


def test_create_session_and_messages_roundtrip() -> None:
    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    create_message_response = client.post(
        "/v1/chat/messages",
        json={
            "session_id": session_id,
            "role": "user",
            "content": "Hello API",
        },
        headers=AUTH_HEADERS,
    )
    assert create_message_response.status_code == 200
    assert create_message_response.json()["content"] == "Hello API"

    list_response = client.get(f"/v1/chat/sessions/{session_id}/messages", headers=AUTH_HEADERS)
    assert list_response.status_code == 200
    messages = list_response.json()
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


def test_third_party_template_classifier_marks_internal_memorandum_as_non_corporate() -> None:
    import app.chat.api as chat_api

    is_third_party = chat_api._is_third_party_document(
        document_kind="general",
        entry={"type": "other", "filename": "internal-memo.pdf"},
        title="Generated internal memo",
        lines=[
            "Legal summary and next-step memorandum",
            "Recommended next steps:",
        ],
    )

    assert is_third_party is False


def test_third_party_template_classifier_marks_contract_asset_as_corporate() -> None:
    import app.chat.api as chat_api

    is_third_party = chat_api._is_third_party_document(
        document_kind="general",
        entry={"type": "contract", "filename": "agreement.pdf"},
        title="Agreement",
        lines=["Contract between parties."],
    )

    assert is_third_party is True


@pytest.mark.parametrize(
    ("document_kind", "entry_type", "title", "expected"),
    [
        ("rental_agreement", "contract", "Nájomná zmluva", True),
        ("rental_agreement", "inventory", "Inventárny zoznam", True),
        ("rental_agreement", "handover_protocol", "Protokol o odovzdaní", True),
        ("share_transfer", "minutes", "Zápisnica z rozhodnutia", True),
        ("share_transfer", "registry_filing", "Podanie na ORSR", True),
        ("general", "other", "Internal legal memo", False),
    ],
)
def test_third_party_template_classifier_by_document_templates(
    document_kind: str,
    entry_type: str,
    title: str,
    expected: bool,
) -> None:
    import app.chat.api as chat_api

    is_third_party = chat_api._is_third_party_document(
        document_kind=document_kind,
        entry={"type": entry_type, "filename": "template.pdf"},
        title=title,
        lines=[title, "Template content body."],
    )

    assert is_third_party is expected


def test_pdf_builder_renders_corporate_header_only_when_template_enabled() -> None:
    import app.chat.api as chat_api

    corporate_pdf = chat_api._build_simple_pdf(
        title="Car Rental Legal Memo",
        lines=["Subject: Liability review", "To: Example Recipient"],
        country="US",
        language="en-US",
        header_line="AI Jurisdicta Solution | Generated: 2026-04-21 10:00:00 UTC",
        footer_line="AIJ | API 1.0 | Core 1.0",
        draw_logo_mark=True,
        include_title_block=False,
    )
    plain_pdf = chat_api._build_simple_pdf(
        title="Internal legal summary",
        lines=["Recommended next steps:", "1. Collect documents."],
        country="US",
        language="en-US",
        footer_line="AIJ | API 1.0 | Core 1.0",
        draw_logo_mark=False,
        include_title_block=True,
    )

    corporate_text = _pdf_text(corporate_pdf).lower()
    plain_text = _pdf_text(plain_pdf).lower()

    assert "poprad, slovakia, 05801" in corporate_text
    assert "info@jurisdigta.eu" in corporate_text
    assert "template.net" not in corporate_text
    assert "api version" in corporate_text
    assert "system core version" in corporate_text
    assert "poprad, slovakia, 05801" not in plain_text

    reader = PdfReader(BytesIO(corporate_pdf))
    page = reader.pages[0]
    assert float(page.mediabox.width) < float(page.mediabox.height)


def test_stream_core_orchestration_and_export_json_pdf() -> None:
    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "en-US"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": "Need legal advice about lease termination.",
            "documents": [{"doc_id": "d1", "path": "lease.txt", "content": "Lease terms"}],
            "question_timeout_seconds": 1,
            "max_discussion_minutes": 0.05,
            "communication_minutes": 0.03,
            "user_simulation_mode": "AIUserSimulatorAgent",
        },
    ) as response:
        assert response.status_code == 200
        events = "".join(response.iter_text())

    assert "event: message" in events
    assert "event: result" in events
    assert "event: done" in events
    assert '"role": "user"' in events

    result_response = client.get(f"/v1/chat/sessions/{session_id}/result", headers=AUTH_HEADERS)
    assert result_response.status_code == 200
    assert "final_recommendation" in result_response.json()

    export_json = client.get(
        f"/v1/chat/sessions/{session_id}/export?format=json", headers=AUTH_HEADERS
    )
    assert export_json.status_code == 200
    assert export_json.headers["content-type"].startswith("application/json")

    export_pdf = client.get(
        f"/v1/chat/sessions/{session_id}/export?format=pdf", headers=AUTH_HEADERS
    )
    assert export_pdf.status_code == 200
    assert export_pdf.headers["content-type"].startswith("application/pdf")
    assert export_pdf.content.startswith(b"%PDF")

    export_doc_pdf = client.get(
        f"/v1/chat/sessions/{session_id}/export?format=pdf&kind=document",
        headers=AUTH_HEADERS,
    )
    assert export_doc_pdf.status_code == 200
    assert export_doc_pdf.headers["content-type"].startswith("application/pdf")
    assert export_doc_pdf.content.startswith(b"%PDF")
    doc_disposition = export_doc_pdf.headers.get("content-disposition", "")
    assert f"{session_id}-" in doc_disposition
    assert "-final-document.pdf" in doc_disposition


def test_default_inputs_meaningful_discussion_and_pdf_exports() -> None:
    defaults_path = (
        Path(__file__).resolve().parents[2] / "chat-simulator-app" / "static" / "default-inputs.json"
    )
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": defaults["instruction"],
            "documents": [],
            "question_timeout_seconds": 1,
            "max_discussion_minutes": 0.2,
            "communication_minutes": 0.2,
            "user_simulation_mode": "AIUserSimulatorAgent",
        },
    ) as response:
        assert response.status_code == 200
        events = "".join(response.iter_text())

    assert "event: done" in events

    messages_response = client.get(
        f"/v1/chat/sessions/{session_id}/messages",
        headers=AUTH_HEADERS,
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()

    assistant_messages = [m["content"] for m in messages if m["role"] == "assistant"]
    user_messages = [m["content"].strip().lower() for m in messages if m["role"] == "user"]
    assert assistant_messages
    assert any(("?" in content and "pdf" not in content.lower()) for content in assistant_messages)
    assert any("navrh najomnej zmluvy" in content.lower() for content in assistant_messages)
    assert any("pdf" in content for content in user_messages)
    assert any("dakujem" in content or "thank you" in content for content in user_messages)
    assert "to je vsetko" in user_messages

    summary_pdf = client.get(
        f"/v1/chat/sessions/{session_id}/export?format=pdf&kind=summary",
        headers=AUTH_HEADERS,
    )
    assert summary_pdf.status_code == 200
    assert summary_pdf.content.startswith(b"%PDF")

    document_pdf = client.get(
        f"/v1/chat/sessions/{session_id}/export?format=pdf&kind=document",
        headers=AUTH_HEADERS,
    )
    assert document_pdf.status_code == 200
    assert document_pdf.content.startswith(b"%PDF")

    summary_text = _pdf_text(summary_pdf.content).lower()
    document_text = _pdf_text(document_pdf.content).lower()
    assert "ai jurisdiction" in summary_text
    assert "jurisdicta" in document_text
    assert "poprad, slovakia, 05801" in document_text
    assert "api version" in document_text
    assert "system core version" in document_text
    assert "aij | api " in document_text
    assert "api " in document_text
    assert "core " in document_text
    assert "generovany dokument podla diskusie" not in document_text
    assert "session id:" not in document_text
    assert "krajina:" not in document_text
    assert "jazyk:" not in document_text
    assert "session id" in summary_text
    assert "zhrnutie" in summary_text or "summary" in summary_text
    assert "validation" in summary_text or "validacia" in summary_text
    assert "accuracy" in summary_text or "presnost" in summary_text
    assert "zmluva" in document_text
    assert "zmluvn" in document_text and "strany" in document_text
    assert "podpis prenaj" in document_text
    assert "vypovedna lehota" in document_text or "lehota" in document_text
    assert "platba vopred" in document_text

def test_document_export_returns_zip_from_visible_multi_document_sections_without_case_update_documents(
    monkeypatch,
) -> None:
    from app.chat.models import Message, MessageRole, Session, SessionResult
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    repository = InMemoryChatRepository()
    monkeypatch.setattr(chat_api, "_repository", repository)

    session = repository.create_session(Session(country="SK", discussion_type="advice", language="SK"))
    repository.add_message(
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "SkvelÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©, pripravÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­m celÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½ balÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­k dokumentov.\n\n"
                "---\n\n"
                "**Zmluva o prevode podielu**\n\n"
                "Text nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡vrhu zmluvy.\n\n"
                "---\n\n"
                "**ZÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡pisnica z rozhodnutia spoloÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚ÂnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­kov**\n\n"
                "Text zÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡pisnice.\n\n"
                "---\n\n"
                "**AktualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡cia spoloÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚Âenskej zmluvy**\n\n"
                "Text aktualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡cie.\n\n"
                "---\n\n"
                "**Podanie na ORSR**\n\n"
                "Text podania.\n\n"
                "---\n\n"
                "BalÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­k dokumentov je pripravenÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½ na export."
            ),
        )
    )
    repository.set_result(
        session.id,
        SessionResult(
            final_recommendation="BalÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­k dokumentov je pripravenÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½ na export.",
            judge_rationale="Direct lawyer reply prepared for session export.",
            metadata={},
        ),
    )

    response = client.get(
        f"/v1/chat/sessions/{session.id}/export?format=pdf&kind=document",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with ZipFile(BytesIO(response.content)) as archive:
        names = sorted(archive.namelist())
        assert len(names) == 4
        assert "Zmluva_o_prevode_podielu.pdf" in names
        assert "Podanie_na_ORSR.pdf" in names
        for name in names:
            assert archive.read(name).startswith(b"%PDF")


def test_fallback_document_entries_ignore_single_contract_section_headings() -> None:
    from app.chat.api import _fallback_document_entries_for_export
    from app.chat.models import Message, MessageRole

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "Rozumiem. Tu je navrh najomnej zmluvy.\n\n"
                "1. Zmluvne strany\n"
                "Jana Novotna a Tomas Hlavaty.\n\n"
                "2. Predmet zmluvy\n"
                "Prenajom bytu na Dunajskej 12.\n\n"
                "3. Doba najmu\n"
                "Najom zacina 01.04.2026.\n\n"
                "4. Skoncenie najmu\n"
                "Vypovedna lehota je jeden mesiac."
            ),
        )
    ]

    assert _fallback_document_entries_for_export(
        messages=messages,
        result=None,
        document_kind="rental_agreement",
    ) == []


def test_document_export_returns_zip_for_visible_slovak_rental_package() -> None:
    from app.chat.models import Message, MessageRole, Session, SessionResult
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    repository = InMemoryChatRepository()
    original_repository = chat_api._repository
    chat_api._repository = repository
    try:
        session = repository.create_session(Session(country="SK", discussion_type="advice", language="sk-SK"))
        content = (
            "Kompletný balík dokumentov je pripravený na export.\n\n"
            "---\n\n"
            "**Zmluva o nájme bytu**\n\n"
            "Prenajímateľ prenajíma nájomcovi byt na adrese: Ludvíka Svobodu 2953/50, Poprad.\n\n"
            "---\n\n"
            "**Inventárny zoznam:**\n\n"
            "[Zoznam vybavenia a stavu bytu]\n\n"
            "---\n\n"
            "**Potvrdenie o prevzatí bytu:**\n\n"
            "Nájomca potvrdzuje prevzatie bytu v dohodnutom stave."
        )
        repository.add_message(
            Message(
                session_id=session.id,
                role=MessageRole.ASSISTANT,
                agent_name="LawyerSlovakia",
                content=content,
            )
        )
        repository.set_result(
            session.id,
            SessionResult(
                final_recommendation=content,
                judge_rationale="Direct lawyer reply prepared for session export.",
                metadata={},
            ),
        )

        response = client.get(
            f"/v1/chat/sessions/{session.id}/export?format=pdf&kind=document",
            headers=AUTH_HEADERS,
        )
    finally:
        chat_api._repository = original_repository

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with ZipFile(BytesIO(response.content)) as archive:
        names = sorted(archive.namelist())
        assert names == [
            "Inventarny_zoznam.pdf",
            "Najomna_zmluva.pdf",
            "Protokol_o_odovzdani_a_prevzati_bytu.pdf",
        ]
        for name in names:
            assert archive.read(name).startswith(b"%PDF")


def test_slovak_rental_export_lines_do_not_contain_mojibake() -> None:
    from app.chat.api import _build_standard_slovak_agreement_lines

    facts = {
        "prenajimatel": "Prenajímateľ [doplniť údaje]",
        "najomca": "Nájomca [doplniť údaje]",
        "predmet": "Byt na adrese Ludvíka Svobodu 2953/50, Poprad",
        "doba": "Na dobu určitú 1 rok",
        "najomne": "600 EUR mesačne",
        "advance": "2 mesačné nájomné vopred",
        "deposit": "1 mesačné nájomné",
        "notice": "Výpovedná lehota 1 mesiac",
    }

    text = "\n".join(_build_standard_slovak_agreement_lines(facts))

    assert "Nájomná zmluva" in text
    assert "Čl. I - Zmluvné strany" in text
    assert "Prenajímateľ" in text
    assert "600 EUR mesačne" in text
    assert not any(marker in text for marker in ("Ã", "Â", "Ä", "Å", "â"))


def test_document_export_for_easement_case_is_not_lease_template() -> None:
    from app.chat.api import _build_document_export_content, _build_simple_pdf
    from app.chat.models import Message, MessageRole

    session_id = uuid4()
    assistant_message = Message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        agent_name="LawyerSlovakia",
        content=(
            "Zhrnutie prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­padu.\n\n"
            "CASE_UPDATE_JSON:\n"
            "{"
            '"case":{"case_id":null,"status":"intake_open","jurisdiction":{"country":"SK","language":"sk-SK"},'
            '"parties":{"client":{"name":"Klient"},"opponent":{"name":"pÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡n NovÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡k"}},'
            '"matter":{"category":"civil","topic":"vecne_bremeno","amount_eur":null,'
            '"key_dates":{},"facts_summary":"Spor so susedom ohÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚Â¾adom brÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ny na mieste vecnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ho bremena a prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­stupu k plynovej prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­pojke.",'
            '"client_goal":"ZabezpeÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚ÂiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¥ brÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nku alebo inÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½ vstup na vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½kon vecnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ho bremena."},'
            '"documents":[],"open_questions":[],"next_discussion":{"scheduled_for":null,"agenda":["PripraviÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¥ predÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾alobnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âº vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½zvu."]},'
            '"discussions_append":[]}'
            "}"
        ),
    )

    title, lines = _build_document_export_content(
        session_id=session_id,
        messages=[assistant_message],
        result=None,
        country="SK",
        language="SK",
    )

    normalized_lines = _canonical_text(" ".join(lines))
    assert "najomna zmluva" not in normalized_lines
    assert "bremena" in normalized_lines and ("vecn" in normalized_lines or "vkonu" in normalized_lines)
    pdf_bytes = _build_simple_pdf(
        title=title,
        lines=lines,
        country="SK",
        language="SK",
        header_line="AI Jurisdicta Solution | Generated: 2026-03-10 16:00:00 UTC",
        footer_line="AIJ | API 0.1.0 | Core 0.1.0",
        draw_logo_mark=True,
        include_title_block=True,
    )
    extracted = _pdf_text(pdf_bytes)
    lowered = _canonical_text(extracted)
    assert "bremena" in lowered and ("vecn" in lowered or "vkonu" in lowered)
    assert "plynovej" in lowered and ("pripoj" in lowered or "pojk" in lowered)
    assert "najomna zmluva" not in lowered


def test_document_export_for_company_share_transfer_uses_full_session_context() -> None:
    from app.chat.api import _build_document_export_content
    from app.chat.models import Message, MessageRole, SessionResult

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "Chcel by som z konatela firmy spravit splocnika s 50% spoluucastou. "
                "Fima ESolutions SK s.r.o., Spisske Bystre. Priprav mi vsetky potrebne documenty."
            ),
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content="Najprv potrebujem doplnit niekolko udajov k prevodu podielu.",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "1. 100%, 2. 0 EUR (manzelka), konatelka. "
                "Chcem pripravit vsetky potrebne documenty a instrukcie kde ich podat."
            ),
        ),
    ]
    result = SessionResult(
        final_recommendation=(
            "Pripravim navrh na prevod obchodneho podielu v spolocnosti ESolutions SK s.r.o. "
            "vratane podkladov pre obchodny register."
        ),
        judge_rationale="Direct lawyer reply prepared for session export.",
        metadata={"document_ready": True},
    )

    title, lines = _build_document_export_content(
        session_id=session_id,
        messages=messages,
        result=result,
        country="SK",
        language="SK",
    )

    lowered_lines = _canonical_text(" ".join(lines))
    assert "najomna zmluva" not in lowered_lines
    assert "prevodu obchodneho podielu" in lowered_lines
    assert "esolutions sk s.r.o." in lowered_lines
    assert "50%" in lowered_lines or "50 %" in lowered_lines


def test_document_export_for_company_share_transfer_uses_verified_company_package(monkeypatch) -> None:
    from app.chat.api import _build_document_export_content
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.models import Message, MessageRole, SessionResult

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            assert kwargs["company_name_or_registration"] == "ESolutions SK s.r.o."
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "Partizanska 665, 059 18 Spisske Bystre",
                        "status": "Aktivna",
                        "stakeholders": (
                            {
                                "name": "RNDr. Marek Matonok",
                                "address": "Partizanska 665/101, 059 18 Spisske Bystre, Slovenska republika",
                            },
                        ),
                    },
                ),
            )

    slovakia_service._ORSR_CACHE.clear()
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "Priprav mi postup a dokumentaciu pre pridanie noveho vlastnika firmy.\n"
                "Nazov: ESolutions SK s.r.o.\n"
                "Prevodca = vlastnik firmy\n"
                "Dalsi vlastnik: Jano Hrasko, Rozpravkova 12, Rozpravkovo\n"
                "Kazdy z vlastnikov ma 50%.\n"
                "Podiel sa prevadza bezodplatne.\n"
                "Meni sa iba spolocnicka struktura."
            ),
        ),
    ]
    result = SessionResult(
        final_recommendation="Pripravil som balik dokumentov k prevodu obchodneho podielu.",
        judge_rationale="Direct lawyer reply prepared for session export.",
        metadata={"document_ready": True},
    )

    title, lines = _build_document_export_content(
        session_id=session_id,
        messages=messages,
        result=result,
        country="SK",
        language="SK",
    )

    lowered_lines = " ".join(lines).lower()
    assert "esolutions sk s.r.o." in lowered_lines
    assert "46491261" in lowered_lines
    assert "partizanska 665, 059 18 spisske bystre" in lowered_lines
    assert "rndr. marek matonok" in lowered_lines
    assert "jano hrasko" in lowered_lines
    assert "50%" in lowered_lines or "50 %" in lowered_lines
    assert "navrh rozhodnutia jedineho spolocnika" in lowered_lines
    assert "navrh aktualizovaneho uplneho znenia spolocenskej zmluvy" in lowered_lines
    slovakia_service._ORSR_CACHE.clear()


def test_reply_endpoint_share_transfer_uses_registry_first(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            assert kwargs["company_name_or_registration"] == "ESolutions SK s.r.o."
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "12345678",
                        "seat": "Spisske Bystre",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                    },
                ),
            )

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(content="MODEL_SHARE_TRANSFER_REPLY", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _SpyLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={
            "content": (
                "Chcel by som z konatela firmy spravit splocnika s 50% spoluucastou. "
                "Firma ESolutions SK s.r.o., Spisske Bystre. Priprav mi vsetky potrebne dokumenty."
            )
        },
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    assert reply_response.json()["content"] == "MODEL_SHARE_TRANSFER_REPLY"
    assert captured_prompts
    prompt = captured_prompts[-1]
    assert "SLOVAK SHARE-TRANSFER TOOL ORCHESTRATION MODE" in prompt
    assert "Verified company name: ESolutions SK s.r.o." in prompt
    assert "Verified registration number: 12345678" in prompt
    assert "Still missing inputs:" in prompt
    assert "Already captured inputs: share scope" in prompt
    assert "Share scope is already captured" in prompt


def test_reply_endpoint_share_transfer_keeps_registry_context_for_short_followups(monkeypatch) -> None:
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    class _FakeRegistry:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, name: str, **kwargs):
            self.calls += 1
            assert name == "obchodny_register_company_check"
            assert kwargs["company_name_or_registration"] == "ESolutions SK s.r.o."
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "12345678",
                        "seat": "Spisske Bystre",
                        "status": "Aktivna",
                    },
                ),
            )

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(content="MODEL_SHARE_TRANSFER_REPLY", agent_name="LawyerSlovakia")

    fake_registry = _FakeRegistry()
    slovakia_service._ORSR_CACHE.clear()
    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: fake_registry)
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _SpyLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    first_reply = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={
            "content": (
                "Priprav mi postup a dokumentaciu pre pridanie noveho vlastnika firmy.\n"
                "Nazov: ESolutions SK s.r.o.\n"
                "Dalsi vlastnik: Jano Hrasko, Rozpravkova 12, Rozpravkovo.\n"
                "Podiel sa prevadza bezodplatne."
            )
        },
        headers=AUTH_HEADERS,
    )
    assert first_reply.status_code == 200

    second_reply = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "50%"},
        headers=AUTH_HEADERS,
    )
    assert second_reply.status_code == 200

    third_reply = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "nie"},
        headers=AUTH_HEADERS,
    )
    assert third_reply.status_code == 200

    assert len(captured_prompts) == 3
    assert fake_registry.calls == 1
    assert all("SLOVAK SHARE-TRANSFER TOOL ORCHESTRATION MODE" in prompt for prompt in captured_prompts)
    assert "Verified registration number: 12345678" in captured_prompts[-1]
    slovakia_service._ORSR_CACHE.clear()


def test_reply_endpoint_company_owner_question_uses_registry_summary(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            assert kwargs["company_name_or_registration"] == "ESolutions SK s.r.o."
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                        "stakeholders": [
                            {
                                "name": "RNDr. Marek Matonok",
                                "address": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665/101, SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                            }
                        ],
                        "statutory_representatives": [
                            {
                                "name": "RNDr. MÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ria MatonokovÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡",
                                "address": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665, SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                            }
                        ],
                    },
                ),
            )

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(content="MODEL_OWNER_REPLY", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _SpyLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "Kto je majitel firmy ESolutions SK s.r.o.?"},
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    assert reply_response.json()["content"] == "MODEL_OWNER_REPLY"
    assert captured_prompts
    prompt = captured_prompts[-1]
    assert "SLOVAK ORSR REGISTRY ANSWER MODE" in prompt
    assert "Verified company name: ESolutions SK s.r.o." in prompt
    assert "Verified registration number: 46491261" in prompt
    assert "Do not switch to share-transfer drafting flow" in prompt


def test_reply_endpoint_company_owner_question_is_not_overridden_by_prior_share_transfer(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                        "stakeholders": [
                            {
                                "name": "RNDr. Marek Matonok",
                                "address": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665/101, SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                            }
                        ],
                    },
                ),
            )

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(content="MODEL_GENERIC_REPLY", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _SpyLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    transfer_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={
            "content": (
                "Priprav mi postup a dokumentaciu pre pridanie noveho vlastnika firmy: "
                "Nazov: ESolutions SK s.r.o. Dalsi vlastnik: Jano Hrasko."
            )
        },
        headers=AUTH_HEADERS,
    )
    assert transfer_response.status_code == 200

    owner_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "Kto je majitel firmy ESolutions SK s.r.o.?"},
        headers=AUTH_HEADERS,
    )
    assert owner_response.status_code == 200
    assert len(captured_prompts) >= 2
    first_prompt = captured_prompts[-2]
    second_prompt = captured_prompts[-1]
    assert "SLOVAK SHARE-TRANSFER TOOL ORCHESTRATION MODE" in first_prompt
    assert "SLOVAK ORSR REGISTRY ANSWER MODE" in second_prompt
    assert "SLOVAK SHARE-TRANSFER TOOL ORCHESTRATION MODE" not in second_prompt


def test_stream_share_transfer_with_labeled_company_name_uses_registry_first(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            assert kwargs["company_name_or_registration"] == "ESolutions SK s.r.o."
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                    },
                ),
            )

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(content="MODEL_STREAM_REPLY", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _SpyLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": (
                "Priprav mi postup a documentaciu pre pridanie noveho vlastnika firmy:\n"
                "Nazov: ESolutions SK s.r.o.\n\n"
                "Novy vlastnik:\n"
                "Jano Hrasko\n"
                "Rozpravkova 12\n"
                "Rozpravkovo,\n"
                "Slovenska Republika"
            ),
            "documents": [],
            "user_simulation_mode": "ReadUser",
            "communication_minutes": 30,
            "max_discussion_minutes": 60,
        },
    ) as response:
        assert response.status_code == 200
        events = "".join(response.iter_text())

    event_payloads = [
        json.loads(line.removeprefix("data: "))
        for line in events.splitlines()
        if line.startswith("data: ")
    ]
    assistant_content = next(
        payload["content"]
        for payload in event_payloads
        if payload.get("role") == "assistant"
    )
    processing_payloads = [
        payload
        for payload in event_payloads
        if payload.get("stage")
    ]
    lowered = assistant_content.lower()
    assert "model_stream_reply" in lowered
    assert captured_prompts
    assert "SLOVAK SHARE-TRANSFER TOOL ORCHESTRATION MODE" in captured_prompts[-1]
    assert "Verified registration number: 46491261" in captured_prompts[-1]
    assert any(payload.get("tool_name") == "obchodny_register_company_check" for payload in processing_payloads)
    assert any(payload.get("stage") == "processing" for payload in processing_payloads)
    assert any("spracovavam" in str(payload.get("message", "")).lower() for payload in processing_payloads)
    assert any(payload.get("stage") == "thinking" for payload in processing_payloads)
    assert any("premyslam" in str(payload.get("message", "")).lower() for payload in processing_payloads)
    assert any("idem overit spolocnost" in str(payload.get("message", "")).lower() for payload in processing_payloads)
    assert any("overenie spolocnosti v orsr je hotove" in str(payload.get("message", "")).lower() for payload in processing_payloads)


def test_prepare_country_direct_reply_emits_tool_lifecycle_callbacks(monkeypatch) -> None:
    from app.chat.country_services import prepare_country_direct_reply
    from app.chat.models import Message, MessageRole, Session

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            assert kwargs["company_name_or_registration"] == "ESolutions SK s.r.o."
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                    },
                ),
            )

    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())

    session = Session(country="SK", discussion_type="advice", language="SK")
    messages = [
        Message(
            session_id=session.id,
            role=MessageRole.USER,
            content=(
                "Priprav mi postup a documentaciu pre pridanie noveho vlastnika firmy:\n"
                "Nazov: ESolutions SK s.r.o."
            ),
        )
    ]
    callback_events: list[dict[str, object]] = []
    preparation = prepare_country_direct_reply(
        session=session,
        messages=messages,
        current_content=messages[0].content,
        prior_messages=[],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
        processing_event_callback=callback_events.append,
    )

    assert callback_events == preparation.processing_events
    stages = [str(event.get("stage", "")) for event in callback_events]
    assert "tool_start" in stages
    assert "tool_result" in stages
    assert stages.index("tool_start") < stages.index("tool_result")
    assert any("idem overit spolocnost" in str(event.get("message", "")).lower() for event in callback_events)
    assert any("overenie spolocnosti v orsr je hotove" in str(event.get("message", "")).lower() for event in callback_events)


def test_prepare_country_direct_reply_reuses_cached_registry_lookup_for_followup(monkeypatch) -> None:
    from app.chat.country_services import prepare_country_direct_reply
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.models import Message, MessageRole, Session

    class _FakeRegistry:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, name: str, **kwargs):
            self.calls += 1
            assert name == "obchodny_register_company_check"
            assert kwargs["company_name_or_registration"] == "ESolutions SK s.r.o."
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "Partizanska 665, 059 18 Spisske Bystre",
                        "status": "Aktivna",
                    },
                ),
            )

    fake_registry = _FakeRegistry()
    slovakia_service._ORSR_CACHE.clear()
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: fake_registry)

    session = Session(country="SK", discussion_type="advice", language="SK")
    initial_content = (
        "Priprav mi postup a dokumentaciu pre pridanie noveho vlastnika firmy.\n"
        "Nazov: ESolutions SK s.r.o.\n"
        "Dalsi vlastnik: Jano Hrasko.\n"
        "Podiel sa prevadza bezodplatne."
    )
    initial_messages = [
        Message(
            session_id=session.id,
            role=MessageRole.USER,
            content=initial_content,
        )
    ]
    first_preparation = prepare_country_direct_reply(
        session=session,
        messages=initial_messages,
        current_content=initial_content,
        prior_messages=[],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
    )
    assert "SLOVAK SHARE-TRANSFER TOOL ORCHESTRATION MODE" in first_preparation.prompt_note

    followup_messages = [
        *initial_messages,
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content="Potvrdte prosim presny rozsah prevadzaneho podielu.",
            agent_name="LawyerSlovakia",
        ),
        Message(
            session_id=session.id,
            role=MessageRole.USER,
            content="50%",
            agent_name="User",
        ),
    ]
    second_preparation = prepare_country_direct_reply(
        session=session,
        messages=followup_messages,
        current_content="50%",
        prior_messages=followup_messages[:-1],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
    )

    assert fake_registry.calls == 1
    assert "SLOVAK SHARE-TRANSFER TOOL ORCHESTRATION MODE" in second_preparation.prompt_note
    assert "Verified registration number: 46491261" in second_preparation.prompt_note
    assert any(event.get("stage") == "tool_cache" for event in second_preparation.processing_events)
    slovakia_service._ORSR_CACHE.clear()


def test_prepare_country_direct_reply_skips_unconfigured_countries() -> None:
    from app.chat.country_services import prepare_country_direct_reply
    from app.chat.models import Message, MessageRole, Session

    session = Session(country="AT", discussion_type="advice", language="DE")
    messages = [
        Message(
            session_id=session.id,
            role=MessageRole.USER,
            content=(
                "Priprav mi postup a dokumentaciu pre pridanie noveho vlastnika firmy. "
                "Nazov: ESolutions SK s.r.o."
            ),
        )
    ]

    preparation = prepare_country_direct_reply(
        session=session,
        messages=messages,
        current_content=messages[0].content,
        prior_messages=[],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {"company_name": "", "company_identifier": "", "company_seat": ""},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
    )

    assert preparation.supplemental_documents == []
    assert preparation.prompt_note == ""
    assert preparation.direct_reply is None
    assert preparation.processing_events == []


def test_reply_endpoint_share_transfer_asks_only_for_missing_items(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            assert kwargs["company_name_or_registration"] == "ESolutions SK s.r.o."
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                    },
                ),
            )

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(content="MODEL_MISSING_FIELDS_REPLY", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _SpyLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={
            "content": (
                "Priprav mi postup a dokumentaciu pre pridanie noveho vlastnika firmy:\n"
                "Nazov: ESolutions SK s.r.o.\n"
                "Dalsi vlastnik: Jano Hrasko\n"
                "Rozpravkova 12\n"
                "Rozpravkovo,\n"
                "Slovenska Republika\n"
                "Prevadza sa 50% podiel.\n"
                "Podiel sa prevadza bezodplatne.\n"
                "Nemeni iba spolocnicka struktura alebo aj konatel / sposob konania."
            )
        },
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    assert reply_response.json()["content"] == "MODEL_MISSING_FIELDS_REPLY"
    assert captured_prompts
    prompt = captured_prompts[-1]
    assert "Already captured inputs: transferee identification, share scope, transfer price / gratuitous flag, management-change flag" in prompt
    assert "Still missing inputs: transferor identification" in prompt
    assert "Share scope is already captured" in prompt
    assert "Management/signing-change status is already captured" in prompt
    assert "spolocenska zmluva or zakladatelska listina" in prompt


def test_reply_endpoint_share_transfer_inline_numbered_text_detects_transferee_and_management_flag(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            assert kwargs["company_name_or_registration"] == "ESolutions SK s.r.o."
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                    },
                ),
            )

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(content="MODEL_INLINE_REPLY", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _SpyLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={
            "content": (
                "Priprav mi postup a documentaciu pre pridanie noveho vlastnika firmy: "
                "info: 0.Nazov: ESolutions SK s.r.o. "
                "1. PresnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© identifikaÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚ÂnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºdaje adobÃƒÆ’Ã†â€™Ãƒâ€šÃ‚ÂºdateÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚Â¾a. "
                "Dalsi vlastnik: Jano Hrasko Rozpravkova 12 Rozpravkovo, Slovenska Republika "
                "1a. Prevadza sa 50% podiel. "
                "2. Podiel sa prevÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡dza bezodplatne. "
                "3. NemenÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ iba spoloÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚ÂnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­cka ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡truktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºra alebo aj konateÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚Â¾ / spÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´sob konania."
            )
        },
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    assert reply_response.json()["content"] == "MODEL_INLINE_REPLY"
    assert captured_prompts
    prompt = captured_prompts[-1]
    normalized_prompt = _canonical_text(prompt)
    assert "already captured inputs:" in normalized_prompt
    assert "transferee identification" in normalized_prompt
    assert "share scope" in normalized_prompt
    assert "still missing inputs: transferor identification" in normalized_prompt
    assert "additional or new owner" in normalized_prompt
def test_extract_slovak_share_transfer_request_facts_detects_first_turn_share_scope() -> None:
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.models import Message, MessageRole

    session_id = uuid4()
    facts = slovakia_service._extract_slovak_share_transfer_request_facts(
        [
            Message(
                session_id=session_id,
                role=MessageRole.USER,
                content=(
                    "Priprav mi postup a dokumentaciu pre pridanie noveho vlastnika firmy. "
                    "Nazov: ESolutions SK s.r.o. "
                    "Dalsi vlastnik: Jano Hrasko, Rozpravkova 12, Rozpravkovo. "
                    "Prevadza sa 50% podiel. "
                    "Podiel sa prevadza bezodplatne. "
                    "Nemeni sa konatel ani sposob konania."
                ),
            )
        ]
    )

    assert facts["transferee_details"].startswith("Jano Hrasko")
    assert facts["transfer_share"] == "50%"
    assert facts["transfer_price"] == "bezodplatne"
    assert facts["management_change"]


def test_apply_company_record_share_transfer_defaults_replaces_generic_transferor_reference() -> None:
    from app.chat.country_services import slovakia as slovakia_service

    merged = slovakia_service._apply_company_record_share_transfer_defaults(
        intake_facts={
            "transferor_details": "vlastnik firmy",
            "transferee_details": "Jano Hrasko",
            "transfer_share": "50%",
            "transfer_price": "bezodplatne",
            "management_change": "Meni sa iba spolocnicka struktura; konatel ani sposob konania sa nemeni.",
        },
        company_record={
            "stakeholders": [
                {
                    "name": "RNDr. Marek Matonok",
                    "address": "Partizanska 665/101, 059 18 Spisske Bystre, Slovenska republika",
                }
            ]
        },
    )

    assert merged["transferor_details"].startswith("RNDr. Marek Matonok")


def test_apply_company_record_share_transfer_defaults_keeps_specific_transferor_details() -> None:
    from app.chat.country_services import slovakia as slovakia_service

    merged = slovakia_service._apply_company_record_share_transfer_defaults(
        intake_facts={
            "transferor_details": "vlastnik firmy, Mar Mat, Testova 30, Poprad",
            "transferee_details": "Jano Hrasko",
            "transfer_share": "50%",
            "transfer_price": "bezodplatne",
            "management_change": "Meni sa iba spolocnicka struktura; konatel ani sposob konania sa nemeni.",
        },
        company_record={
            "stakeholders": [
                {
                    "name": "RNDr. Marek Matonok",
                    "address": "Partizanska 665/101, 059 18 Spisske Bystre, Slovenska republika",
                }
            ]
        },
    )

    assert merged["transferor_details"] == "vlastnik firmy, Mar Mat, Testova 30, Poprad"


def test_slovakia_address_validation_prompt_note_requires_consent_when_preference_unknown() -> None:
    from app.chat.country_services import slovakia as slovakia_service

    note = slovakia_service._build_slovak_address_validation_prompt_note(
        current_content="Moja adresa je Námestie slobody 1, 811 06 Bratislava.",
        prior_messages=[],
    )

    assert "consent question" in note.lower()
    assert "registeradries.sk" in note


def test_slovakia_address_validation_preference_is_reused_after_user_confirmation() -> None:
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.models import Message, MessageRole

    session_id = uuid4()
    prior_messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Chcete overiť adresu cez registeradries.sk?",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Áno, overte adresu.",
        ),
    ]

    note = slovakia_service._build_slovak_address_validation_prompt_note(
        current_content="Adresa pre zmluvu: Námestie slobody 1, 811 06 Bratislava.",
        prior_messages=prior_messages,
    )

    assert "already opted in" in note
    assert "registeradries_address_validate" in note




def test_slovakia_property_validation_prompt_note_requires_consent_when_preference_unknown() -> None:
    from app.chat.country_services import slovakia as slovakia_service

    note = slovakia_service._build_slovak_property_validation_prompt_note(
        current_content="Priprav kupno predajnu zmluvu na pozemkoch v katastri obce Kravany, adresa je ...",
        prior_messages=[],
    )

    assert "consent question" in note.lower()
    assert "slovakia_property_lv_lookup" in note


def test_slovakia_property_validation_preference_is_reused_after_user_confirmation() -> None:
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.models import Message, MessageRole

    session_id = uuid4()
    prior_messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Chcete overiť list vlastníctva cez slovakia_property_lv_lookup?",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Áno, overte to.",
        ),
    ]

    note = slovakia_service._build_slovak_property_validation_prompt_note(
        current_content="Zisti mi pozemky usera Jana Novaka.",
        prior_messages=prior_messages,
    )

    assert "already opted in" in note
    assert "all_cadastral_units_slovakia" in note


def test_prepare_slovakia_direct_reply_adds_property_consent_note_for_property_contract_request() -> None:
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.models import Session

    session = Session(country="SK")
    current_content = "Priprav kupno predajnu zmluvu na pozemkoch nachadzajuci sa v katastri obce Kravany, na adrese ..."
    preparation = slovakia_service.prepare_slovakia_direct_reply(
        session=session,
        messages=[],
        current_content=current_content,
        prior_messages=[],
        normalize_document_lines=lambda content: content.splitlines(),
        extract_document_facts=lambda _lines: {},
        current_turn_confirms_document_generation=lambda *_args, **_kwargs: False,
        build_share_transfer_lines=lambda _facts: [],
    )

    assert preparation.prompt_note is not None
    assert "SLOVAK PROPERTY VALIDATION MODE" in preparation.prompt_note
    assert "consent question" in preparation.prompt_note.lower()


def test_prepare_slovakia_direct_reply_reuses_property_consent_for_owner_lookup_request() -> None:
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.models import Message, MessageRole, Session

    session_id = uuid4()
    prior_messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Chcete overiť list vlastníctva cez slovakia_property_lv_lookup?",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Ano.",
        ),
    ]
    session = Session(country="SK")
    current_content = "Zisti mi pozemky usera Jana Novaka."

    preparation = slovakia_service.prepare_slovakia_direct_reply(
        session=session,
        messages=prior_messages,
        current_content=current_content,
        prior_messages=prior_messages,
        normalize_document_lines=lambda content: content.splitlines(),
        extract_document_facts=lambda _lines: {},
        current_turn_confirms_document_generation=lambda *_args, **_kwargs: False,
        build_share_transfer_lines=lambda _facts: [],
    )

    assert preparation.prompt_note is not None
    assert "already opted in" in preparation.prompt_note.lower()
    assert "slovakia_property_lv_lookup" in preparation.prompt_note

def test_reply_endpoint_share_transfer_uses_single_current_stakeholder_as_transferor(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            assert kwargs["company_name_or_registration"] == "ESolutions SK s.r.o."
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                        "stakeholders": (
                            {
                                "name": "RNDr. Marek Matonok",
                                "address": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665/101, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©, SlovenskÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ republika",
                                "type": "spoloÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚ÂnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­k",
                            },
                        ),
                    },
                ),
            )

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(content="MODEL_TRANSFEROR_DEFAULT_REPLY", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _SpyLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={
            "content": (
                "Priprav mi postup a dokumentaciu pre pridanie noveho vlastnika firmy:\n"
                "Nazov: ESolutions SK s.r.o.\n"
                "Dalsi vlastnik: Jano Hrasko\n"
                "Rozpravkova 12\n"
                "Rozpravkovo,\n"
                "Slovenska Republika\n"
                "Podiel sa prevadza bezodplatne.\n"
                "Nemeni iba spolocnicka struktura alebo aj konatel / sposob konania."
            )
        },
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    assert reply_response.json()["content"] == "MODEL_TRANSFEROR_DEFAULT_REPLY"
    assert captured_prompts
    prompt = captured_prompts[-1]
    normalized_prompt = _canonical_text(prompt)
    assert "still missing inputs:" in normalized_prompt
    assert "share" in normalized_prompt


def test_reply_endpoint_share_transfer_detects_owner_mismatch_and_requests_confirmation(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                        "stakeholders": [
                            {
                                "name": "RNDr. Marek Matonok",
                                "address": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665/101, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©, SlovenskÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ republika",
                            }
                        ],
                    },
                ),
            )

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={
            "content": (
                "Priprav mi postup a dokumentaciu pre pridanie noveho vlastnika firmy.\n"
                "Nazov: ESolutions SK s.r.o.\n"
                "Prevodca: Mar Mat, Testova 30, Poprad.\n"
                "Dalsi vlastnik: Jano Hrasko, Rozpravkova 12, Rozpravkovo.\n"
                "Podiel sa prevadza bezodplatne."
            )
        },
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    content = _canonical_text(reply_response.json()["content"])
    assert (
        ("prevodca" in content and "orsr" in content)
        or "potrebujem doplnit klucove udaje" in content
    )



def test_reply_endpoint_share_transfer_orsr_confirmation_does_not_reask_company_ico(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api
    import app.chat.country_services.slovakia as slovakia_service

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                        "stakeholders": [
                            {
                                "name": "RNDr. Marek Matonok",
                                "address": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665/101, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©, SlovenskÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ republika",
                            }
                        ],
                    },
                ),
            )

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())
    slovakia_service._ORSR_CACHE.clear()

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    first_reply = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={
            "content": (
                "Priprav mi postup a documentaciu pre pridanie noveho vlastnika firmy:\n"
                "Nazov: ESolutions SK s.r.o.\n"
                "Prevodca = vlastnik firmy\n"
                "Mar Mat\n"
                "Testova 30\n"
                "Poprad\n"
                "Dalsi vlastnik:\n"
                "Jano Hrasko\n"
                "Rozpravkova 12\n"
                "Rozpravkovo\n"
                "Slovenska Republika\n"
                "Podiel sa prevadza bezodplatne, kazdy z vlastnikov ma 50%.\n"
                "Meni sa iba spolocnicka struktura, nie konatel / sposob konania.\n"
                "Novy spolumajitel od 1.7.2026."
            )
        },
        headers=AUTH_HEADERS,
    )
    assert first_reply.status_code == 200
    first_content = _canonical_text(first_reply.json()["content"])
    assert "orsr" in first_content and "vlastnik" in first_content
    second_reply = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "podla ORSR"},
        headers=AUTH_HEADERS,
    )
    assert second_reply.status_code == 200
    content = _canonical_text(second_reply.json()["content"])
    assert "poskytnut ico" not in content
    assert "obchodn" in content or "balk dokumentov" in content



def test_reply_endpoint_share_transfer_orsr_confirmation_persists_for_document_generation(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api
    import app.chat.country_services.slovakia as slovakia_service

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "46491261",
                        "seat": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                        "stakeholders": [
                            {
                                "name": "RNDr. Marek Matonok",
                                "address": "PartizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nska 665/101, 059 18 SpiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡skÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© BystrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©, SlovenskÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ republika",
                            }
                        ],
                    },
                ),
            )

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(
                content="Pripravil som finÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lny nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡vrh dokumentÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡cie.\nCASE_UPDATE_JSON:\n{}",
                agent_name="LawyerSlovakia",
            )

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())
    slovakia_service._ORSR_CACHE.clear()
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _SpyLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    first_reply = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={
            "content": (
                "Priprav mi postup a documentaciu pre pridanie noveho vlastnika firmy:\n"
                "Nazov: ESolutions SK s.r.o.\n"
                "Prevodca = vlastnik firmy\n"
                "Mar Mat\n"
                "Testova 30\n"
                "Poprad\n"
                "Dalsi vlastnik:\n"
                "Jano Hrasko\n"
                "Rozpravkova 12\n"
                "Rozpravkovo\n"
                "Slovenska Republika\n"
                "Podiel sa prevadza bezodplatne, kazdy z vlastnikov ma 50%.\n"
                "Meni sa iba spolocnicka struktura, nie konatel / sposob konania.\n"
                "Novy spolumajitel od 1.7.2026."
            )
        },
        headers=AUTH_HEADERS,
    )
    assert first_reply.status_code == 200
    first_content = _canonical_text(first_reply.json()["content"])
    assert "orsr" in first_content and "vlastnik" in first_content
    second_reply = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "podla ORSR"},
        headers=AUTH_HEADERS,
    )
    assert second_reply.status_code == 200
    second_content = _canonical_text(second_reply.json()["content"])
    assert "vstup" in second_content or "navrh" in second_content
    third_reply = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "ano"},
        headers=AUTH_HEADERS,
    )
    assert third_reply.status_code == 200
    content = _canonical_text(third_reply.json()["content"])
    assert "navrh dokument" in content
    assert "prevodca je spravny" not in content
    assert captured_prompts
    assert "ask the user to confirm the authoritative transferor identity" not in captured_prompts[-1].lower()


def test_reply_endpoint_share_transfer_confirmation_returns_working_draft(monkeypatch) -> None:
    from app.chat.models import Message, MessageRole
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    class _FakeRegistry:
        def run(self, name: str, **kwargs):
            assert name == "obchodny_register_company_check"
            return SimpleNamespace(
                ok=True,
                records=(
                    {
                        "name": "ESolutions SK s.r.o.",
                        "registration_number": "12345678",
                        "seat": "Spisske Bystre",
                        "status": "AktÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vna",
                    },
                ),
            )

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(
                content="Pripravil som finÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lny nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡vrh dokumentÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡cie.\nCASE_UPDATE_JSON:\n{}",
                agent_name="LawyerSlovakia",
            )

    repository = InMemoryChatRepository()
    monkeypatch.setattr(chat_api, "_repository", repository)
    monkeypatch.setattr("app.chat.country_services.slovakia.build_default_tool_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _SpyLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = UUID(session_response.json()["id"])

    repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "Chcel by som z konatela firmy spravit splocnika s 50% spoluucastou. "
                "Firma ESolutions SK s.r.o., Spisske Bystre. Priprav mi vsetky potrebne dokumenty."
            ),
        )
    )
    repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "Navrh dokumentu som do chatu nezobrazila. "
                "Chcete ho vidiet po doplneni poslednych udajov?"
            ),
        )
    )
    repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "1. 100%, 2. 0 EUR (manzelka), konatelka. "
                "Chcem pripravit vsetky potrebne dokumenty a instrukcie kde ich podat."
            ),
        )
    )
    repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content="Navrh dokumentu som do chatu nezobrazila. Chcete ho vidiet?",
        )
    )

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "Ano, zobraz ho prosim."},
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    content = reply_response.json()["content"]
    lowered = _canonical_text(content)
    assert "navrh dokument" in lowered
    assert "case_update_json" not in lowered
    list_response = client.get(
        f"/v1/chat/sessions/{session_id}/messages",
        headers=AUTH_HEADERS,
    )
    assert list_response.status_code == 200
    listed_messages = list_response.json()
    assistant_listed = [item for item in listed_messages if item["role"] == "assistant"]
    assert assistant_listed
    assert all("case_update_json" not in item["content"].lower() for item in assistant_listed)
    persisted_messages = repository.list_messages(session_id)
    assert any(
        message.role == MessageRole.ASSISTANT and "case_update_json" in message.content.lower()
        for message in persisted_messages
    )
    assert captured_prompts
    prompt = captured_prompts[-1]
    assert "SLOVAK SHARE-TRANSFER TOOL ORCHESTRATION MODE" in prompt
    assert "The user confirmed document generation in this turn" in prompt
    assert "DOCUMENT GENERATION MODE" in prompt
    assert "Do not claim that PDF or ZIP files are already created" in prompt

    result_response = client.get(
        f"/v1/chat/sessions/{session_id}/result",
        headers=AUTH_HEADERS,
    )
    assert result_response.status_code == 200
    metadata = result_response.json()["metadata"]
    assert metadata["document_requested"] is True
    assert metadata["document_confirmed"] is True
    assert metadata["document_ready"] is True


def test_build_simple_pdf_preserves_slovak_and_german_characters() -> None:
    from app.chat.api import _build_simple_pdf

    pdf_bytes = _build_simple_pdf(
        title="NÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡jomnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ zmluva / KÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¼ndigung",
        lines=[
            "ÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€¦Ã¢â‚¬â„¢l. I - ZmluvnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© strany",
            "ÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚Â½ubomÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­r ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â½ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚Âek bÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½va v KoÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡iciach.",
            "Deutsch: KÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¼ndigung, StraÃƒÆ’Ã†â€™Ãƒâ€¦Ã‚Â¸e, GrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¶ÃƒÆ’Ã†â€™Ãƒâ€¦Ã‚Â¸e und ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¤uÃƒÆ’Ã†â€™Ãƒâ€¦Ã‚Â¸erst wichtige Frist.",
        ],
        country="SK",
        language="sk-SK",
        header_line="AI Jurisdicta Solution | Generated: 2026-03-16 20:00:00 UTC",
        footer_line="AIJ | API 0.1.0 | Core 0.1.0",
        draw_logo_mark=True,
        include_title_block=True,
    )

    extracted = _pdf_text(pdf_bytes)
    normalized_extracted = _canonical_text(extracted)
    assert "strany" in normalized_extracted
    assert "ubom" in normalized_extracted or "lubom" in normalized_extracted
    assert "deutsch" in normalized_extracted
    assert "deutsch" in normalized_extracted and ("kundigung" in normalized_extracted or "kndigung" in normalized_extracted)
    assert "jurisdikcia: slovensk" in normalized_extracted and "republika" in normalized_extracted

def test_create_message_returns_404_for_unknown_session() -> None:
    response = client.post(
        "/v1/chat/messages",
        json={
            "session_id": "00000000-0000-0000-0000-000000000000",
            "role": "user",
            "content": "Hi",
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404


def test_reply_endpoint_persists_user_and_returns_lawyer_message() -> None:
    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "sk"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "Priprav vzor o prenajme"},
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    lawyer_message = reply_response.json()
    assert lawyer_message["role"] == "assistant"
    assert "vzor" in lawyer_message["content"].lower() or "zmluv" in lawyer_message["content"].lower()

    list_response = client.get(
        f"/v1/chat/sessions/{session_id}/messages",
        headers=AUTH_HEADERS,
    )
    assert list_response.status_code == 200
    messages = list_response.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"

    reply_response_2 = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "Doplnam, ze zmluva bola podpisana pisomne."},
        headers=AUTH_HEADERS,
    )
    assert reply_response_2.status_code == 200
    lawyer_message_2 = reply_response_2.json()
    assert lawyer_message_2["role"] == "assistant"
    assert "vzor najomnej zmluvy" in lawyer_message_2["content"].lower()


def test_stream_read_user_pauses_and_waits_for_manual_reply() -> None:
    from app.chat import api as chat_api
    from app.chat.models import SessionState

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": "Potrebujem poradit so sporom o najom bytu.",
            "documents": [],
            "question_timeout_seconds": 3000,
            "max_discussion_minutes": 15,
            "communication_minutes": 3,
            "user_simulation_mode": "ReadUser",
        },
    ) as response:
        assert response.status_code == 200
        events = "".join(response.iter_text())

    assert "event: waiting_for_reply" in events
    assert '"status": "waiting_for_reply"' in events
    assert "PouÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vateÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚Â¾ nemohol odpovedaÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¥ do 50 minÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºt." not in events
    assert "spracovavam" in events.lower()
    assert '"role": "assistant"' in events
    assert "premyslam" in events.lower()
    assert "event: result" not in events

    session = chat_api._repository.get_session(UUID(session_id))
    assert session is not None
    assert session.state == SessionState.ACTIVE

    messages_response = client.get(
        f"/v1/chat/sessions/{session_id}/messages",
        headers=AUTH_HEADERS,
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert "?" in messages[1]["content"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "Spor vznikol v januari 2026 a moj ciel je ukoncit najom."},
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    reply_content = reply_response.json()["content"].lower()
    assert "pravne posudenie" in reply_content or "dalsi krok" in reply_content


def test_stream_read_user_emits_document_name_progress_before_final_message(monkeypatch) -> None:
    from app.chat import api as chat_api
    from app.chat.models import Message, MessageRole, SessionResult

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = UUID(session_response.json()["id"])

    persisted_user = Message(
        session_id=session_id,
        role=MessageRole.USER,
        content="ano",
        agent_name="User",
    )
    persisted_lawyer = Message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=(
            "Pripravil som balik dokumentov.\n"
            "1. **Zmluva o prevode obchodneho podielu**: hotove.\n"
            "2. **Rozhodnutie jedineho spolocnika / zapisnica**: hotove.\n"
            "3. **Aktualizovane uplne znenie spolocenskej zmluvy / zakladatelskej listiny**: hotove."
        ),
        agent_name="LawyerSlovakia",
    )

    monkeypatch.setattr(
        chat_api,
        "_run_direct_lawyer_turn",
        lambda **kwargs: (persisted_user, persisted_lawyer, persisted_lawyer.content, []),
    )
    monkeypatch.setattr(
        chat_api,
        "_build_direct_reply_result",
        lambda **kwargs: SessionResult(
            final_recommendation="Pripravil som balik dokumentov.",
            judge_rationale="Direct lawyer reply prepared for session export.",
            metadata={"document_requested": True, "document_confirmed": True, "document_ready": True},
        ),
    )

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": "ano",
            "documents": [],
            "question_timeout_seconds": 30,
            "max_discussion_minutes": 1,
            "communication_minutes": 1,
            "user_simulation_mode": "ReadUser",
        },
    ) as response:
        assert response.status_code == 200
        events = "".join(response.iter_text())

    first_doc = "Zmluva o prevode obchodneho podielu"
    second_doc = "Rozhodnutie jedineho spolocnika / zapisnica"
    third_doc = "Aktualizovane uplne znenie spolocenskej zmluvy / zakladatelskej listiny"
    assert first_doc in events
    assert second_doc in events
    assert third_doc in events
    assert events.index(first_doc) < events.index('"role": "assistant"')
    assert events.index(second_doc) < events.index('"role": "assistant"')
    assert events.index(third_doc) < events.index('"role": "assistant"')


def test_existing_case_history_is_seeded_into_new_reply_session(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    from app.chat.models import MessageRole
    import app.chat.api as chat_api

    captured: dict[str, object] = {}

    class _FakeStore:
        def list_case_communications(self, *, case_id: str, limit=None, offset: int = 0):
            assert case_id == "case-123"
            return [
                SimpleNamespace(
                    summary="ASSISTANT: Existing answer from history (agent=LawyerSlovakia)",
                    transcript_uri=None,
                ),
                SimpleNamespace(
                    summary="USER: Existing user question from history",
                    transcript_uri=None,
                ),
            ]

        def add_case_message(self, *, case_id: str, role: str, content: str, agent_name: str | None = None):
            return "comm-id"

    class _FakeLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured["conversation"] = conversation
            captured["system_prompt_override"] = system_prompt_override
            return SimpleNamespace(
                content="Follow-up response based on prior case history.",
                agent_name="LawyerSlovakia",
            )

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr(chat_api, "_get_store", lambda: _FakeStore())
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _FakeLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={
            "country": "SK",
            "discussion_type": "advice",
            "language": "SK",
            "case_id": "case-123",
        },
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    seeded_messages_response = client.get(
        f"/v1/chat/sessions/{session_id}/messages",
        headers=AUTH_HEADERS,
    )
    assert seeded_messages_response.status_code == 200
    seeded_messages = seeded_messages_response.json()
    assert [item["role"] for item in seeded_messages] == ["user", "assistant"]
    assert seeded_messages[0]["content"] == "Existing user question from history"
    assert seeded_messages[1]["content"] == "Existing answer from history"

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "Please continue with this case."},
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200

    conversation = captured["conversation"]
    assert isinstance(conversation, list)
    assert len(conversation) == 3
    assert conversation[0].role == MessageRole.USER.value
    assert conversation[0].content == "Existing user question from history"
    assert conversation[1].role == MessageRole.ASSISTANT.value
    assert conversation[1].content == "Existing answer from history"
    assert conversation[2].role == MessageRole.USER.value
    assert conversation[2].content == "Please continue with this case."


def test_existing_case_history_falls_back_to_summary_when_transcript_missing(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    captured: dict[str, object] = {}

    class _FakeStore:
        def list_case_communications(self, *, case_id: str, limit=None, offset: int = 0):
            assert case_id == "case-123"
            return [
                SimpleNamespace(
                    case_id=case_id,
                    communication_id="comm-1",
                    summary="ASSISTANT: Prior answer kept in summary (agent=LawyerSlovakia)",
                    transcript_uri="missing://transcript",
                ),
            ]

        def read_storage_text(self, *, storage_uri: str) -> str:
            raise FileNotFoundError(storage_uri)

        def add_case_message(self, *, case_id: str, role: str, content: str, agent_name: str | None = None):
            return "comm-id"

    class _FakeLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured["conversation"] = conversation
            return SimpleNamespace(
                content="Follow-up response based on resilient case history.",
                agent_name="LawyerSlovakia",
            )

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr(chat_api, "_get_store", lambda: _FakeStore())
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _FakeLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={
            "country": "SK",
            "discussion_type": "advice",
            "language": "SK",
            "case_id": "case-123",
        },
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "New follow-up question"},
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200

    conversation = captured["conversation"]
    assert isinstance(conversation, list)
    assert conversation[0].content == "Prior answer kept in summary"
    assert conversation[1].content == "New follow-up question"


def test_reply_persists_session_history_document_to_case(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    persisted_history: list[dict[str, str | None]] = []

    class _FakeStore:
        def list_case_communications(self, *, case_id: str, limit=None, offset: int = 0):
            return []

        def add_case_message(self, *, case_id: str, role: str, content: str, agent_name: str | None = None):
            return "comm-id"

        def add_case_session_history_document(
            self,
            *,
            case_id: str,
            session_id: str,
            content: str,
            uploaded_by_user_id: str | None = None,
        ) -> str:
            persisted_history.append(
                {
                    "case_id": case_id,
                    "session_id": session_id,
                    "content": content,
                    "uploaded_by_user_id": uploaded_by_user_id,
                }
            )
            return "doc-history"

    class _FakeLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            return SimpleNamespace(
                content="Stored response for conversation memory.",
                agent_name="LawyerSlovakia",
            )

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr(chat_api, "_get_store", lambda: _FakeStore())
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _FakeLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session_response = client.post(
        "/v1/chat/sessions",
        json={
            "country": "SK",
            "discussion_type": "advice",
            "language": "SK",
            "case_id": "case-123",
        },
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "Please save this discussion for later reuse."},
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    assert len(persisted_history) == 1
    assert persisted_history[0]["case_id"] == "case-123"
    assert persisted_history[0]["session_id"] == session_id
    persisted_transcript = str(persisted_history[0]["content"])
    assert "USER: Please save this discussion for later reuse. (agent=User)" in persisted_transcript
    assert "ASSISTANT: Stored response for conversation memory. (agent=LawyerSlovakia)" in persisted_transcript


def test_case_memory_reuses_previous_session_messages_and_documents(monkeypatch, tmp_path) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))

    class _FakeEmbeddingClient:
        def embed_texts(self, texts: list[str]) -> SimpleNamespace:
            return SimpleNamespace(
                model_name="fake-embedding-model",
                vectors=[[float(index + 1), float(len(text))] for index, text in enumerate(texts)],
            )

    captured_documents: list[list[str]] = []

    class _FakeLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_documents.append([doc.path for doc in documents])
            return SimpleNamespace(
                content="Stored response for cross-session memory.",
                agent_name="LawyerSlovakia",
            )

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr(
        "services.document_processor.service.get_embedding_client",
        lambda: _FakeEmbeddingClient(),
    )
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _FakeLawyer(),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    response = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900000333",
            "email": "memory-user@example.com",
            "password": "secret",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["user_id"]

    case_response = client.post(
        "/v1/cases",
        headers=AUTH_HEADERS,
        json={"user_id": user_id, "title": "Cross-session memory"},
    )
    assert case_response.status_code == 201
    case_id = case_response.json()["case_id"]

    session_one = client.post(
        "/v1/chat/sessions",
        json={
            "user_id": user_id,
            "case_id": case_id,
            "country": "SK",
            "discussion_type": "advice",
            "language": "SK",
        },
        headers=AUTH_HEADERS,
    )
    assert session_one.status_code == 200
    session_one_id = session_one.json()["id"]

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_one_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": "Please review the uploaded lease document.",
            "documents": [
                {
                    "doc_id": "doc-1",
                    "path": "lease-session-1.txt",
                    "content": "Lease clause from session one.",
                }
            ],
            "user_simulation_mode": "ReadUser",
        },
    ) as stream_one:
        assert stream_one.status_code == 200
        assert "event: done" in "".join(stream_one.iter_text())

    session_two = client.post(
        "/v1/chat/sessions",
        json={
            "user_id": user_id,
            "case_id": case_id,
            "country": "SK",
            "discussion_type": "advice",
            "language": "SK",
        },
        headers=AUTH_HEADERS,
    )
    assert session_two.status_code == 200
    session_two_id = session_two.json()["id"]

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_two_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": "Please review the uploaded payment evidence.",
            "documents": [
                {
                    "doc_id": "doc-2",
                    "path": "payment-session-2.txt",
                    "content": "Payment evidence from session two.",
                }
            ],
            "user_simulation_mode": "ReadUser",
        },
    ) as stream_two:
        assert stream_two.status_code == 200
        assert "event: done" in "".join(stream_two.iter_text())

    session_three = client.post(
        "/v1/chat/sessions",
        json={
            "user_id": user_id,
            "case_id": case_id,
            "country": "SK",
            "discussion_type": "advice",
            "language": "SK",
        },
        headers=AUTH_HEADERS,
    )
    assert session_three.status_code == 200
    session_three_id = session_three.json()["id"]

    seeded_messages_response = client.get(
        f"/v1/chat/sessions/{session_three_id}/messages",
        headers=AUTH_HEADERS,
    )
    assert seeded_messages_response.status_code == 200
    seeded_messages = seeded_messages_response.json()
    assert len(seeded_messages) == 4
    assert seeded_messages[0]["content"] == "Please review the uploaded lease document."
    assert seeded_messages[2]["content"] == "Please review the uploaded payment evidence."

    memory_response = client.get(
        f"/v1/cases/{case_id}/documents/context?user_id={user_id}",
        headers=AUTH_HEADERS,
    )
    assert memory_response.status_code == 200
    memory_payload = memory_response.json()
    processed_documents = memory_payload["processed_documents"]
    assert "lease-session-1.txt" in processed_documents
    assert "payment-session-2.txt" in processed_documents
    assert f"session-{session_one_id}.txt" in processed_documents
    assert f"session-{session_two_id}.txt" in processed_documents

    reply_response = client.post(
        f"/v1/chat/sessions/{session_three_id}/reply",
        json={"content": "Summarize all uploaded documents and prior discussions."},
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    assert captured_documents
    final_document_paths = captured_documents[-1]
    assert any(path.startswith("lease-session-1.txt") for path in final_document_paths)
    assert any(path.startswith("payment-session-2.txt") for path in final_document_paths)
    assert any(path.startswith(f"session-{session_one_id}.txt") for path in final_document_paths)
    assert any(path.startswith(f"session-{session_two_id}.txt") for path in final_document_paths)


def test_reply_endpoint_respects_session_language_sk() -> None:
    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "Please review my lease dispute and suggest next step."},
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    lawyer_message = reply_response.json()["content"].lower()
    assert "pravne posudenie" in lawyer_message or "aby som mohol pripravit presny navrh" in lawyer_message


def test_reply_endpoint_requires_confirmation_before_document_pdf_ready() -> None:
    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "court", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    first_reply = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={
            "content": (
                "Priprav vzor najomnej zmluvy. "
                "Prenajimatel je Jana Novotna, najomca Tomas Hlavaty, "
                "byt je na adrese Dunajska 12, Bratislava, "
                "najomne je 850 EUR a zaciatok najmu je 01.04.2026."
            )
        },
        headers=AUTH_HEADERS,
    )
    assert first_reply.status_code == 200
    first_content = first_reply.json()["content"].lower()
    assert "pdf" in first_content
    assert "?" in first_reply.json()["content"]

    first_result = client.get(
        f"/v1/chat/sessions/{session_id}/result",
        headers=AUTH_HEADERS,
    )
    assert first_result.status_code == 200
    first_metadata = first_result.json()["metadata"]
    assert first_metadata["document_requested"] is True
    assert first_metadata["document_confirmed"] is False
    assert first_metadata["document_ready"] is False

    second_reply = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        json={"content": "Ano, prosim priprav to aj vo formate PDF."},
        headers=AUTH_HEADERS,
    )
    assert second_reply.status_code == 200
    second_content = second_reply.json()["content"].lower()
    assert "pripravil som" in second_content or "export do pdf" in second_content

    second_result = client.get(
        f"/v1/chat/sessions/{session_id}/result",
        headers=AUTH_HEADERS,
    )
    assert second_result.status_code == 200
    second_metadata = second_result.json()["metadata"]
    assert second_metadata["document_requested"] is True
    assert second_metadata["document_confirmed"] is True
    assert second_metadata["document_ready"] is True
    assert "validation_accuracy" in second_metadata
    assert "validation_summary" in second_metadata
    assert "core_version" in second_metadata

    export_doc_pdf = client.get(
        f"/v1/chat/sessions/{session_id}/export?format=pdf&kind=document",
        headers=AUTH_HEADERS,
    )
    assert export_doc_pdf.status_code == 200
    assert export_doc_pdf.content.startswith(b"%PDF")


def test_processing_placeholder_reply_is_replaced_with_document_ready_message() -> None:
    from app.chat.api import _finalize_document_ready_reply_if_needed
    from app.chat.models import Message, MessageRole, Session

    session = Session(country="SK", language="sk-SK")
    messages = [
        Message(session_id=session.id, role=MessageRole.USER, content="Priprav mi zmluvu o prevode podielu."),
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content="Mam pripravit finalny balik dokumentov aj na export do PDF?",
            agent_name="LawyerSlovakia",
        ),
        Message(session_id=session.id, role=MessageRole.USER, content="Ano, prosim."),
    ]

    finalized = _finalize_document_ready_reply_if_needed(
        session=session,
        messages=messages,
        lawyer_content=(
            "Pripravim nasledujuce dokumenty:\n"
            "1. Zmluva o prevode obchodneho podielu.\n"
            "2. Zapisnica z rozhodnutia spolocnika.\n"
            "3. Aktualizovane uplne znenie spolocenskej zmluvy.\n\n"
            "Prosim, dajte mi chvilu."
        ),
    )

    assert "pripraveny na export" in finalized.lower()
    assert "Zmluva o prevode obchodneho podielu" in finalized
    assert "Zapisnica z rozhodnutia spolocnika" in finalized


def test_explicit_slovak_document_update_request_is_recognized() -> None:
    from app.chat.api import _user_requested_document_generation

    assert _user_requested_document_generation(
        content="Pozri na dokument a oprav ho podla poslednych zmien zakona.",
        previous_messages=[],
    ) is True


def test_document_export_ready_after_confirmation_with_prior_case_update() -> None:
    from app.chat.api import _build_direct_reply_result
    from app.chat.models import Message, MessageRole, Session

    session_id = uuid4()
    session = Session(id=session_id, country="SK", language="SK", discussion_type="court")
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "Zhrnutie prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­padu.\n\n"
                "CASE_UPDATE_JSON:\n"
                '{"case":{"case_id":null,"status":"intake_open","jurisdiction":{"country":"SK","language":"sk-SK"},'
                '"parties":{"client":{"name":"Jozef NovÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡k"},"opponent":{"name":"Peter KovÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚Â"}},'
                '"matter":{"category":"civil","topic":"vecne_bremeno","amount_eur":null,'
                '"key_dates":{},"facts_summary":"Spor o prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­stup k plynovej prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­pojke.",'
                '"client_goal":"ZabezpeÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚ÂiÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¥ vstup cez brÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡nku."},'
                '"documents":[],"open_questions":[],"next_discussion":{"scheduled_for":null,"agenda":[]},'
                '"discussions_append":[]}}'
            ),
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content="Chcete, aby som vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡m pripravil vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½sledok v PDF formÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡te?",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âno, priprav to prosÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­m aj v PDF.",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "ÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€¦Ã‚Â½akujem. Po nahratÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ e-mailov a aktualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡cii zÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡znamu vo formÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡te JSON "
                "pripravÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­m aj vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½sledok vo formÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡te PDF."
            ),
        ),
    ]

    result = _build_direct_reply_result(
        session_id=session_id,
        session=session,
        messages=messages,
        lawyer_message=messages[-1].content,
    )

    assert result.metadata["document_requested"] is True
    assert result.metadata["document_confirmed"] is True
    assert result.metadata["document_ready"] is True


def test_extract_case_update_parses_fenced_json_without_case_update_marker() -> None:
    from app.chat.api import _extract_case_update, _user_visible_text

    content = (
        "VÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½borne, dokumenty sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âº teraz pripravenÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© na export.\n\n"
        "Tu je JSON pre uchovanie prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­padu:\n\n"
        "```json\n"
        '{"case":{"case_id":null,"status":"intake_open","jurisdiction":{"country":"SK","language":"sk-SK"},'
        '"parties":{"client":{"name":"RNDr. Marek Matonok"},"opponent":{"name":"Jano Hrasko"}},'
        '"matter":{"category":"commercial","topic":"prevod podielu","amount_eur":null,"key_dates":{},'
        '"facts_summary":"Prevod podielu.","client_goal":"Pripravit dokumenty."},'
        '"documents":[],"open_questions":["Kto je prevodca?"],"next_discussion":{"scheduled_for":null,"agenda":[]},'
        '"discussions_append":[]}}'
        "\n```"
    )

    case_update = _extract_case_update(content)

    assert case_update is not None
    assert case_update["case"]["matter"]["topic"] == "prevod podielu"
    assert _user_visible_text(content) == "VÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½borne, dokumenty sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âº teraz pripravenÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© na export."


def test_user_visible_text_strips_technical_json_preamble_before_case_update_marker() -> None:
    from app.chat.api import _user_visible_text

    content = (
        "VÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½borne, dokumenty sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âº teraz pripravenÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© na export.\n\n"
        "Tu je JSON pre uchovanie prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­padu:\n\n"
        "CASE_UPDATE_JSON:\n"
        '{"case":{"case_id":null,"status":"ready_for_next_step","jurisdiction":{"country":"SK","language":"sk-SK"},'
        '"parties":{"client":{"name":"RNDr. Marek Matonok"},"opponent":{"name":"Jano Hrasko"}},'
        '"matter":{"category":"commercial","topic":"prevod podielu","amount_eur":null,"key_dates":{},'
        '"facts_summary":"Prevod podielu.","client_goal":"Pripravit dokumenty."},'
        '"documents":[],"open_questions":[],"next_discussion":{"scheduled_for":null,"agenda":[]},'
        '"discussions_append":[]}}'
    )

    assert _user_visible_text(content) == "VÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½borne, dokumenty sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âº teraz pripravenÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© na export."


def test_user_visible_text_strips_bare_case_json_without_marker() -> None:
    from app.chat.api import _extract_case_update, _user_visible_text

    content = (
        "Tu je finalny navrh zmluvy na podnajom.\n\n"
        "{\n"
        '  "case": {\n'
        '    "case_id": null,\n'
        '    "status": "intake_open",\n'
        '    "jurisdiction": {"country": "SK", "language": "sk-SK"},\n'
        '    "documents": [],\n'
        '    "open_questions": ["Kto je prenajimatel?"],\n'
        '    "discussions_append": []\n'
        "  }\n"
        "}"
    )

    assert _user_visible_text(content) == "Tu je finalny navrh zmluvy na podnajom."
    case_update = _extract_case_update(content)
    assert case_update is not None
    assert case_update["case"]["status"] == "intake_open"


def test_assistant_technical_payload_is_saved_as_case_document_and_linked(monkeypatch) -> None:
    import app.chat.api as chat_api
    from app.chat.models import Session

    stored_documents: list[dict[str, object]] = []

    class _FakeStore:
        def add_case_document(
            self,
            *,
            case_id: str,
            kind: str,
            version: int,
            original_filename: str,
            payload: bytes,
            uploaded_by_user_id: str | None = None,
        ) -> str:
            stored_documents.append(
                {
                    "case_id": case_id,
                    "kind": kind,
                    "version": version,
                    "original_filename": original_filename,
                    "payload": payload.decode("utf-8"),
                    "uploaded_by_user_id": uploaded_by_user_id,
                }
            )
            return "doc-technical"

    user_id = uuid4()
    session = Session(
        user_id=user_id,
        case_id="case-123",
        country="SK",
        language="SK",
        discussion_type="advice",
    )
    content = (
        "Tu je finalny navrh zmluvy na podnajom.\n\n"
        "{\n"
        '  "case": {\n'
        '    "case_id": null,\n'
        '    "status": "intake_open",\n'
        '    "jurisdiction": {"country": "SK", "language": "sk-SK"},\n'
        '    "open_questions": ["Kto je prenajimatel?"],\n'
        '    "documents": []\n'
        "  }\n"
        "}"
    )

    monkeypatch.setattr(chat_api, "_get_store", lambda: _FakeStore())

    persisted_content = chat_api._attach_technical_payload_to_case_if_needed(
        session=session,
        content=content,
    )
    visible = chat_api._user_visible_text(persisted_content)

    assert len(stored_documents) == 1
    assert stored_documents[0]["kind"] == "technical_payload"
    assert stored_documents[0]["uploaded_by_user_id"] == str(user_id)
    stored_payload = json.loads(str(stored_documents[0]["payload"]))
    assert stored_payload["case"]["status"] == "intake_open"
    assert "Technick" in visible
    assert f"/v1/cases/case-123/documents/doc-technical?user_id={user_id}" in visible
    assert '"case"' not in visible


def test_stream_read_user_completes_when_bare_technical_json_contains_question(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    from app.chat.models import Message, MessageRole, SessionState
    import app.chat.api as chat_api

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = UUID(session_response.json()["id"])

    persisted_user = Message(
        session_id=session_id,
        role=MessageRole.USER,
        content="ano",
        agent_name="User",
    )
    persisted_lawyer = Message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=(
            "Tu je finalny navrh zmluvy na podnajom.\n\n"
            "{\n"
            '  "case": {\n'
            '    "case_id": null,\n'
            '    "status": "intake_open",\n'
            '    "jurisdiction": {"country": "SK", "language": "sk-SK"},\n'
            '    "open_questions": ["Kto je prenajimatel?"],\n'
            '    "documents": []\n'
            "  }\n"
            "}"
        ),
        agent_name="LawyerSlovakia",
    )

    monkeypatch.setattr(
        chat_api,
        "_run_direct_lawyer_turn",
        lambda **kwargs: (persisted_user, persisted_lawyer, persisted_lawyer.content, []),
    )

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": "ano",
            "documents": [],
            "question_timeout_seconds": 300,
            "max_discussion_minutes": 15,
            "communication_minutes": 3,
            "user_simulation_mode": "ReadUser",
        },
    ) as response:
        assert response.status_code == 200
        events = "".join(response.iter_text())

    assert "waiting_for_reply" not in events
    assert '"case"' not in events
    assert "event: result" in events

    session = chat_api._repository.get_session(session_id)
    assert session is not None
    assert session.state == SessionState.COMPLETED

    result_response = client.get(
        f"/v1/chat/sessions/{session_id}/result",
        headers=AUTH_HEADERS,
    )
    assert result_response.status_code == 200


def test_user_visible_text_strips_fake_relative_download_links_and_json_preamble(monkeypatch) -> None:
    from app.chat.api import _user_visible_text
    import app.chat.api as chat_api
    from app.chat.models import Message, MessageRole, SessionState

    content = (
        "Dokumenty sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âº teraz pripravenÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© na export.\n\n"
        "MÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾ete si ich stiahnuÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¥ pomocou nasledujÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºcich odkazov:\n\n"
        "1. [Zmluva o prevode podielu](documents/Zmluva_o_prevedeni_podielu.pdf)\n"
        "2. [ZÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡pisnica z rozhodnutia spoloÃƒÆ’Ã¢â‚¬Å¾Ãƒâ€šÃ‚ÂnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­kov](documents/Zapisnica_z_rozhodnutia.pdf)\n"
        "3. [AktualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡cia spolocenskej zmluvy](documents/Aktualizacia_spolocenskej_zmluvy.pdf)\n\n"
        "Tu je JSON pre uchovanie prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­padu:\n\n"
        "CASE_UPDATE_JSON:\n"
        '{"case":{"case_id":null,"status":"ready_for_next_step","jurisdiction":{"country":"SK","language":"sk-SK"},'
        '"parties":{"client":{"name":"RNDr. Marek Matonok"},"opponent":{"name":"Jano Hrasko"}},'
        '"matter":{"category":"commercial","topic":"prevod podielu","amount_eur":null,"key_dates":{},'
        '"facts_summary":"Prevod podielu.","client_goal":"Pripravit dokumenty."},'
        '"documents":[{"doc_id":"DOC-001","type":"contract","filename":"zmluva.pdf","path":"documents/zmluva.pdf","received_at":"2026-04-17T18:00:00Z","notes":""}],'
        '"open_questions":[],"next_discussion":{"scheduled_for":null,"agenda":[]},'
        '"discussions_append":[]}}'
    )

    visible = _user_visible_text(content)
    normalized_visible = _canonical_text(visible)
    assert normalized_visible.startswith("dokumenty")
    assert "export" in normalized_visible
    assert "documents/" not in visible
    assert "case_update_json" not in visible.lower()

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = UUID(session_response.json()["id"])

    persisted_user = Message(
        session_id=session_id,
        role=MessageRole.USER,
        content="ano",
        agent_name="User",
    )
    persisted_lawyer = Message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=(
            "VÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â½borne, dokumenty sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âº teraz pripravenÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© na export.\n\n"
            "Tu je JSON pre uchovanie prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­padu:\n\n"
            "```json\n"
            '{"case":{"case_id":null,"status":"intake_open","jurisdiction":{"country":"SK","language":"sk-SK"},'
            '"parties":{"client":{"name":"RNDr. Marek Matonok"},"opponent":{"name":"Jano Hrasko"}},'
            '"matter":{"category":"commercial","topic":"prevod podielu","amount_eur":null,"key_dates":{},'
            '"facts_summary":"Prevod podielu.","client_goal":"Pripravit dokumenty."},'
            '"documents":[{"doc_id":"DOC-001","type":"contract","filename":"zmluva.pdf","path":"documents/zmluva.pdf","received_at":"2026-04-17T18:00:00Z","notes":""}],'
            '"open_questions":["Kto je prevodca?"],"next_discussion":{"scheduled_for":null,"agenda":[]},'
            '"discussions_append":[]}}'
            "\n```"
        ),
        agent_name="LawyerSlovakia",
    )

    monkeypatch.setattr(
        chat_api,
        "_run_direct_lawyer_turn",
        lambda **kwargs: (persisted_user, persisted_lawyer, persisted_lawyer.content, []),
    )

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": "ano",
            "documents": [],
            "question_timeout_seconds": 300,
            "max_discussion_minutes": 15,
            "communication_minutes": 3,
            "user_simulation_mode": "ReadUser",
        },
    ) as response:
        assert response.status_code == 200
        events = "".join(response.iter_text())

    assert "event: result" in events
    assert "waiting_for_reply" not in events

    session = chat_api._repository.get_session(session_id)
    assert session is not None
    assert session.state == SessionState.COMPLETED

    result_response = client.get(
        f"/v1/chat/sessions/{session_id}/result",
        headers=AUTH_HEADERS,
    )
    assert result_response.status_code == 200

    export_response = client.get(
        f"/v1/chat/sessions/{session_id}/export?format=pdf&kind=document",
        headers=AUTH_HEADERS,
    )
    assert export_response.status_code == 200
    assert export_response.content.startswith(b"%PDF")


def test_completed_read_user_session_returns_document_status_followup() -> None:
    from app.chat import api as chat_api
    from app.chat.models import Message, MessageRole, SessionResult

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "sk-SK"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = UUID(session_response.json()["id"])
    session = chat_api._repository.get_session(session_id)
    assert session is not None

    seeded_messages = [
        Message(session_id=session_id, role=MessageRole.USER, content="Priprav mi balik dokumentov."),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Mam pripravit finalny balik dokumentov aj na export do PDF?",
            agent_name="LawyerSlovakia",
        ),
        Message(session_id=session_id, role=MessageRole.USER, content="Ano, prosim."),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=(
                "Balik dokumentov je pripraveny na export a stiahnutie.\n\n"
                "Pripravene dokumenty:\n"
                "1. Zmluva o prevode obchodneho podielu\n"
                "2. Zapisnica z rozhodnutia spolocnika"
            ),
            agent_name="LawyerSlovakia",
        ),
    ]
    for message in seeded_messages:
        chat_api._repository.add_message(message)
    chat_api._repository.set_result(
        session_id,
        SessionResult(
            final_recommendation=seeded_messages[-1].content,
            judge_rationale="Stored ready package.",
            metadata={
                "document_requested": True,
                "document_confirmed": True,
                "document_ready": True,
            },
        ),
    )

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": "Aky je stav dokumentov?",
            "documents": [],
            "question_timeout_seconds": 300,
            "max_discussion_minutes": 15,
            "communication_minutes": 3,
            "user_simulation_mode": "ReadUser",
        },
    ) as response:
        assert response.status_code == 200
        events = "".join(response.iter_text())

    assert "event: processing" in events
    assert '"stage": "document_status"' in events
    assert "stav dokumentov" in events.lower()
    assert "pripraveny na export a stiahnutie" in events.lower()
    assert "event: done" in events

    result_response = client.get(
        f"/v1/chat/sessions/{session_id}/result",
        headers=AUTH_HEADERS,
    )
    assert result_response.status_code == 200
    assert result_response.json()["metadata"]["document_ready"] is True


def test_direct_reply_result_uses_latest_law_store_timestamp(monkeypatch, tmp_path) -> None:
    from app.chat.api import _build_direct_reply_result
    from app.chat.models import Message, MessageRole, Session
    import app.chat.result_metadata as result_metadata

    laws_db = tmp_path / "laws.sqlite3"
    with sqlite3.connect(laws_db) as conn:
        conn.execute(
            """
            CREATE TABLE law_documents (
                document_id TEXT PRIMARY KEY,
                country_code TEXT NOT NULL,
                last_stored_at TEXT NOT NULL,
                source_url TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE collector_progress (
                country_code TEXT PRIMARY KEY,
                source_system TEXT,
                last_collector_run_at TEXT,
                last_processed_law_year INTEGER,
                last_processed_law_number INTEGER,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO law_documents(document_id, country_code, last_stored_at, source_url)
            VALUES ('doc-1', 'SK', '2026-02-10T12:30:00Z', 'https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/2/')
            """
        )
        conn.execute(
            """
            INSERT INTO law_documents(document_id, country_code, last_stored_at, source_url)
            VALUES ('doc-2', 'SK', '2026-03-11T08:15:00Z', 'https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/11/')
            """
        )
        conn.execute(
            """
            INSERT INTO collector_progress(
                country_code, source_system, last_collector_run_at, last_processed_law_year, last_processed_law_number, updated_at
            )
            VALUES ('SK', 'slovlex', '2026-03-30T14:00:00Z', 2026, 234, '2026-03-30T14:00:00Z')
            """
        )
        conn.commit()

    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(laws_db))
    monkeypatch.setenv("LLM_PROVIDER", "azurefoundry")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    monkeypatch.setattr(
        result_metadata.ApiDatabaseStore,
        "from_env",
        lambda: SimpleNamespace(
            get_permanent_memory=lambda _key: SimpleNamespace(
                value={
                    "llm_modelname": "gpt-4o-mini",
                    "cutoff_date": "2023-10-01",
                    "cutoff_source": "https://platform.openai.com/docs/models/gpt-4o-mini",
                },
                source_url="https://platform.openai.com/docs/models/gpt-4o-mini",
            )
        ),
    )

    session_id = uuid4()
    session = Session(id=session_id, country="SK", language="EN", discussion_type="court")
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Please review my uploaded lease amendment and tell me what is missing.",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content="The document is missing a termination clause and clear effective date.",
        ),
    ]

    result = _build_direct_reply_result(
        session_id=session_id,
        session=session,
        messages=messages,
        lawyer_message=messages[-1].content,
    )

    assert result.metadata["knowledge_last_updated_at"] == "2026-03-11T08:15:00Z"
    assert result.metadata["last_law_update_date"] == "2026-03-11T08:15:00Z"
    assert result.metadata["last_law_update_source"] == "law_documents_country"
    assert result.metadata["last_collector_run_at"] == "2026-03-30T14:00:00Z (SK:slovlex)"
    assert result.metadata["last_processed_law"] == "234/2026"
    assert result.metadata["model_knowledge_cutoff_date"] == "2023-10-01"
    assert (
        result.metadata["model_knowledge_cutoff_source"]
        == "https://platform.openai.com/docs/models/gpt-4o-mini"
    )
    assert result.metadata["law_reference_links"] == [
        "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/11/",
        "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/2/",
    ]
    assert result.metadata["api_version"]


def test_direct_reply_result_includes_structured_law_citations(monkeypatch) -> None:
    from app.chat.api import _build_direct_reply_result
    from app.chat.models import Message, MessageRole, Session
    import app.chat.result_metadata as result_metadata

    monkeypatch.setattr(
        result_metadata,
        "resolve_session_law_citations",
        lambda **_kwargs: [
            {
                "law_identifier": "1/1993 Z. z.",
                "label": "1/1993 Z. z. - Prvy zakon",
                "title": "Prvy zakon",
                "version_token": "19930101",
                "effective_from": "1993-01-01",
                "open_url": "/v1/laws/source?country_code=SK&collection_code=ZZ&law_year=1993&law_number=1&version_token=19930101&artifact_kind=html",
                "summary": "1/1993 Z. z. (Prvy zakon), version 19930101, effective from 1993-01-01",
            }
        ],
    )
    monkeypatch.setattr(
        result_metadata,
        "get_law_knowledge_snapshot",
        lambda _country: result_metadata.LawKnowledgeSnapshot(
            last_law_update_date="2026-04-01T00:00:00Z",
            last_law_update_source="law_documents_country",
            model_knowledge_cutoff_date="2023-10-01",
            model_knowledge_cutoff_source="https://platform.openai.com/docs/models/gpt-4o-mini",
        ),
    )

    class _FakeValidator:
        def evaluate(self, **_kwargs):
            return SimpleNamespace(
                weighted_accuracy=92.5,
                summary="Validated.",
                scores=[],
            )

    monkeypatch.setattr(result_metadata, "AIAgentsValidator", lambda **_kwargs: _FakeValidator())

    session_id = uuid4()
    session = Session(id=session_id, country="SK", language="SK")
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Priprav mi dokument a odkaz na zakon 1/1993.",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Pripravil som navrh a doplnil pravny zaklad.",
        ),
    ]

    result = _build_direct_reply_result(
        session_id=session_id,
        session=session,
        messages=messages,
        lawyer_message=messages[-1].content,
    )

    assert result.metadata["law_citations"][0]["law_identifier"] == "1/1993 Z. z."
    assert result.citations[0]["filename"] == "1/1993 Z. z."
    assert "effective from 1993-01-01" in result.citations[0]["snippet"]


def test_law_snapshot_falls_back_to_model_cutoff_and_writes_cache(monkeypatch, tmp_path) -> None:
    import app.chat.result_metadata as result_metadata

    class _FakeStore:
        def __init__(self) -> None:
            self.entry = None

        def get_permanent_memory(self, key: str) -> SimpleNamespace | None:
            assert key == "llm_model_setup"
            return self.entry

        def upsert_permanent_memory(
            self,
            *,
            key: str,
            value: dict[str, str],
            entry_type: str,
            source_url: str | None = None,
        ) -> None:
            assert key == "llm_model_setup"
            assert entry_type == "llm_model_metadata"
            self.entry = SimpleNamespace(value=value, source_url=source_url)

    cache_path = tmp_path / "model-knowledge-cutoff.json"
    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "missing-laws.sqlite3"))
    monkeypatch.setenv("MODEL_KNOWLEDGE_CUTOFF_CACHE_FILE", str(cache_path))
    monkeypatch.setenv("LLM_PROVIDER", "azurefoundry")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    fake_store = _FakeStore()
    monkeypatch.setattr(result_metadata.ApiDatabaseStore, "from_env", lambda: fake_store)
    monkeypatch.setattr(
        result_metadata,
        "AIWebSearchAgent",
        lambda: SimpleNamespace(
            search=lambda **_kwargs: [
                SimpleNamespace(
                    title="GPT-4o mini",
                    url="https://platform.openai.com/docs/models/gpt-4o-mini",
                    snippet="GPT-4o mini model card. Oct 01, 2023 knowledge cutoff.",
                )
            ]
        ),
    )

    snapshot = result_metadata.get_law_knowledge_snapshot("SK")

    assert snapshot.last_law_update_date is None
    assert snapshot.last_law_update_source == "unavailable"
    assert snapshot.last_collector_run_at is None
    assert snapshot.last_processed_law is None
    assert snapshot.model_knowledge_cutoff_date == "2023-10-01"
    assert (
        snapshot.model_knowledge_cutoff_source
        == "https://platform.openai.com/docs/models/gpt-4o-mini"
    )
    assert snapshot.reference_links == ()
    assert fake_store.entry is not None
    assert fake_store.entry.value["llm_modelname"] == "gpt-4o-mini"
    assert fake_store.entry.value["cutoff_date"] == "2023-10-01"
    assert cache_path.exists()
    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache_payload["llm_modelname"] == "gpt-4o-mini"
    assert cache_payload["model_knowledge_cutoff_date"] == "2023-10-01"


def test_law_snapshot_reuses_cached_model_cutoff_without_expiration(monkeypatch, tmp_path) -> None:
    import app.chat.result_metadata as result_metadata

    cached_store_entry = SimpleNamespace(
        value={
            "llm_modelname": "gpt-4o-mini",
            "cutoff_date": "2023-10-01",
            "cutoff_source": "https://platform.openai.com/docs/models/gpt-4o-mini",
        },
        source_url="https://platform.openai.com/docs/models/gpt-4o-mini",
    )

    cache_path = tmp_path / "model-knowledge-cutoff.json"
    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "missing-laws.sqlite3"))
    monkeypatch.setenv("MODEL_KNOWLEDGE_CUTOFF_CACHE_FILE", str(cache_path))
    monkeypatch.setenv("LLM_PROVIDER", "azurefoundry")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    monkeypatch.setattr(
        result_metadata.ApiDatabaseStore,
        "from_env",
        lambda: SimpleNamespace(get_permanent_memory=lambda _key: cached_store_entry),
    )
    monkeypatch.setattr(
        result_metadata,
        "AIWebSearchAgent",
        lambda: SimpleNamespace(search=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected web search"))),
    )

    first_snapshot = result_metadata.get_law_knowledge_snapshot("SK")
    assert first_snapshot.model_knowledge_cutoff_date == "2023-10-01"

    second_snapshot = result_metadata.get_law_knowledge_snapshot("SK")

    assert second_snapshot.last_law_update_date is None
    assert second_snapshot.last_collector_run_at is None
    assert second_snapshot.last_processed_law is None
    assert second_snapshot.model_knowledge_cutoff_date == "2023-10-01"
    assert (
        second_snapshot.model_knowledge_cutoff_source
        == "https://platform.openai.com/docs/models/gpt-4o-mini"
    )


def test_law_snapshot_uses_direct_openai_model_page_when_search_returns_no_results(
    monkeypatch, tmp_path
) -> None:
    import app.chat.result_metadata as result_metadata

    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "missing-laws.sqlite3"))
    monkeypatch.setenv("LLM_PROVIDER", "azurefoundry")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")
    monkeypatch.delenv("MODEL_KNOWLEDGE_CUTOFF_CACHE_FILE", raising=False)
    monkeypatch.setattr(
        result_metadata.ApiDatabaseStore,
        "from_env",
        lambda: SimpleNamespace(
            get_permanent_memory=lambda _key: None,
            upsert_permanent_memory=lambda **_kwargs: None,
        ),
    )
    monkeypatch.setattr(
        result_metadata,
        "AIWebSearchAgent",
        lambda: SimpleNamespace(search=lambda **_kwargs: []),
    )
    monkeypatch.setattr(
        result_metadata,
        "_fetch_text_from_url",
        lambda url: "GPT-4.1 model page. Apr 14, 2025 knowledge cutoff."
        if url == "https://platform.openai.com/docs/models/gpt-4.1"
        else None,
    )

    snapshot = result_metadata.get_law_knowledge_snapshot("SK")

    assert snapshot.model_knowledge_cutoff_date == "2025-04-14"
    assert snapshot.model_knowledge_cutoff_source == "https://platform.openai.com/docs/models/gpt-4.1"


def test_law_snapshot_uses_known_model_fallback_for_custom_deployment_name(
    monkeypatch, tmp_path
) -> None:
    import app.chat.result_metadata as result_metadata

    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "missing-laws.sqlite3"))
    monkeypatch.setenv("LLM_PROVIDER", "azurefoundry")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "juris-gpt-4o-mini-dev")
    monkeypatch.delenv("MODEL_KNOWLEDGE_CUTOFF_CACHE_FILE", raising=False)
    monkeypatch.setattr(
        result_metadata.ApiDatabaseStore,
        "from_env",
        lambda: SimpleNamespace(
            get_permanent_memory=lambda _key: None,
            upsert_permanent_memory=lambda **_kwargs: None,
        ),
    )
    monkeypatch.setattr(
        result_metadata,
        "AIWebSearchAgent",
        lambda: SimpleNamespace(search=lambda **_kwargs: []),
    )
    monkeypatch.setattr(result_metadata, "_fetch_text_from_url", lambda _url: None)

    snapshot = result_metadata.get_law_knowledge_snapshot("SK")

    assert snapshot.model_knowledge_cutoff_date == "2023-10-01"
    assert (
        snapshot.model_knowledge_cutoff_source
        == "https://platform.openai.com/docs/models/gpt-4o-mini"
    )


def test_law_snapshot_returns_unavailable_model_cutoff_when_all_resolution_paths_fail(
    monkeypatch, tmp_path
) -> None:
    import app.chat.result_metadata as result_metadata

    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "missing-laws.sqlite3"))
    monkeypatch.setenv("LLM_PROVIDER", "azurefoundry")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "unknown-custom-model")
    monkeypatch.delenv("MODEL_KNOWLEDGE_CUTOFF_CACHE_FILE", raising=False)
    monkeypatch.setattr(
        result_metadata.ApiDatabaseStore,
        "from_env",
        lambda: SimpleNamespace(
            get_permanent_memory=lambda _key: None,
            upsert_permanent_memory=lambda **_kwargs: None,
        ),
    )
    monkeypatch.setattr(
        result_metadata,
        "AIWebSearchAgent",
        lambda: SimpleNamespace(search=lambda **_kwargs: []),
    )
    monkeypatch.setattr(result_metadata, "_fetch_text_from_url", lambda _url: None)

    snapshot = result_metadata.get_law_knowledge_snapshot("SK")

    assert snapshot.model_knowledge_cutoff_date is None
    assert snapshot.model_knowledge_cutoff_source == "unavailable"


def test_summary_export_content_includes_system_versions_and_law_links() -> None:
    from app.chat.api import _build_summary_export_content
    from app.chat.models import Message, MessageRole, SessionResult

    session_id = uuid4()
    result = SessionResult(
        final_recommendation="Send a written demand first and prepare court filing only if the counterparty does not comply.",
        judge_rationale="The uploaded documents support the user's claim and the missing performance deadline should be fixed first.",
        citations=[
            {
                "filename": "Act 40/1964",
                "snippet": "Section 517 covers delay and written demand before escalation.",
            }
        ],
        metadata={
            "api_version": "1.0.260322",
            "core_version": "1.0.260202",
            "last_law_update_date": "2026-03-20T00:00:00Z",
            "last_law_update_source": "law_documents_country",
            "law_reference_links": [
                "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/"
            ],
            "validation_summary": "The recommendation is legally plausible but depends on proving delivery of the written notice.",
        },
    )
    messages = [
        Message(session_id=session_id, role=MessageRole.USER, content="My supplier missed the deadline."),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="You should send a written demand and preserve delivery evidence.",
        ),
    ]

    _title, lines = _build_summary_export_content(
        session_id=session_id,
        result=result,
        messages=messages,
        country="SK",
        language="EN",
    )

    joined = "\n".join(lines)
    assert "Generation date:" in joined
    assert "API version: 1.0.260322" in joined
    assert "System core version: 1.0.260202" in joined
    assert "Last law update date available to the system: 2026-03-20T00:00:00Z" in joined
    assert "User recommendation" in joined
    assert "Final recommendation:" in joined
    assert "Official law links available in the system" in joined
    assert "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/" in joined


def test_summary_export_content_includes_document_evaluation_law_basis_for_recreate_request() -> None:
    from app.chat.api import _build_summary_export_content
    from app.chat.models import Message, MessageRole, SessionResult

    session_id = uuid4()
    result = SessionResult(
        final_recommendation="I reviewed the uploaded lease agreement, updated the outdated clauses, and prepared the revised version.",
        judge_rationale="The uploaded document required modernization under current rental-law requirements.",
        citations=[],
        metadata={
            "api_version": "1.0.260322",
            "core_version": "1.0.260202",
            "last_law_update_date": "2026-03-20T00:00:00Z",
            "last_law_update_source": "law_documents_country",
            "law_reference_links": [
                "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/"
            ],
            "validation_summary": "The recreated document reflects the currently available legal basis.",
        },
    )
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Please review the uploaded document and recreate it under current law.",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="I reviewed the uploaded document and prepared the updated version.",
        ),
    ]

    _title, lines = _build_summary_export_content(
        session_id=session_id,
        result=result,
        messages=messages,
        country="SK",
        language="EN",
    )

    joined = "\n".join(lines)
    assert "Legal basis used to evaluate the document" in joined
    assert "The document was evaluated against the latest legal materials available to the system as of 2026-03-20T00:00:00Z." in joined
    assert "Legal source used by the system: law_documents_country" in joined
    assert "Law references used for the document evaluation:" in joined
    assert "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/" in joined


def test_chat_endpoints_require_api_key() -> None:
    response = client.post("/v1/chat/sessions", json={})
    assert response.status_code == 401


def test_ai_user_simulator_finishes_after_pdf_request_and_thanks(monkeypatch) -> None:
    from aijurisdictionagents.agents.user_simulator import AIUserSimulatorAgent

    monkeypatch.setattr(
        AIUserSimulatorAgent,
        "prepare_random_answer",
        lambda self, question, conversation, documents: "finish",
    )

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "sk"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": "Potrebujem poradit s prenajmom bytu.",
            "documents": [],
            "question_timeout_seconds": 1,
            "max_discussion_minutes": 0.05,
            "communication_minutes": 0.05,
            "user_simulation_mode": "AIUserSimulatorAgent",
        },
    ) as response:
        assert response.status_code == 200
        events = "".join(response.iter_text())

    assert "event: done" in events

    messages_response = client.get(
        f"/v1/chat/sessions/{session_id}/messages",
        headers=AUTH_HEADERS,
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    user_messages = [m["content"].strip().lower() for m in messages if m["role"] == "user"]
    assert len(user_messages) >= 2
    assert user_messages[1] != "finish"
    assert any("pdf" in content for content in user_messages)
    assert any("dakujem" in content or "thank you" in content for content in user_messages)
    assert "to je vsetko" in user_messages
    assert len(messages) > 2


def test_normalize_simulator_reply_avoids_exact_repeat() -> None:
    from app.chat.api import _normalize_simulator_reply

    reply = _normalize_simulator_reply(
        "I have a written contract copy.",
        language="en",
        turn_index=2,
        previous_reply="I have a written contract copy.",
    )
    assert reply != "I have a written contract copy."


def test_normalize_simulator_reply_rejects_question_form() -> None:
    from app.chat.api import _normalize_simulator_reply

    reply = _normalize_simulator_reply(
        "Potrebujem od vas potvrdit, ci treba plnu moc?",
        language="sk",
        turn_index=0,
        previous_reply="",
    )
    assert "?" not in reply
    assert "Prosim pokracujte" in reply


def test_repeated_question_reply_mentions_repeat_count() -> None:
    from app.chat.api import _repeated_question_reply

    reply = _repeated_question_reply("en", "Can you provide the contract date?", 3)
    assert "Repeated question (3x)" in reply


def test_should_finish_followup_after_clarification() -> None:
    from app.chat.api import _should_finish_followup

    assert _should_finish_followup(
        assistant_messages_seen=2,
        answered_agent_questions=1,
        followup_prompts_seen=1,
    )


def test_is_pdf_format_question_detects_pdf_prompt() -> None:
    from app.chat.api import _is_pdf_format_question

    assert _is_pdf_format_question("Do you want the final result in PDF format?")
    assert not _is_pdf_format_question("Please provide your contract date.")


def test_enforce_single_question_turn_keeps_only_first_question() -> None:
    from app.chat.api import _enforce_single_question_turn, _extract_case_update, _user_visible_text

    raw_reply = (
        "Potrebujem doplnit viac informacii.\n"
        "1. Potvrdite, ci prevodca je RNDr. Marek Matonok?\n"
        "2. Potvrdite presny rozsah podielu?\n"
        "3. Meni sa konatel?\n"
        "CASE_UPDATE_JSON:\n"
        '{"case":{"open_questions":["Potvrdite prevodcu?","Potvrdite rozsah podielu?","Meni sa konatel?"]}}'
    )

    normalized = _enforce_single_question_turn(raw_reply)
    visible = _user_visible_text(normalized)
    assert "RNDr. Marek Matonok?" in visible
    assert "presny rozsah podielu?" not in visible
    assert "Meni sa konatel?" not in visible
    assert visible.count("?") == 1

    case_update = _extract_case_update(normalized)
    assert isinstance(case_update, dict)
    case_payload = case_update.get("case")
    assert isinstance(case_payload, dict)
    assert case_payload.get("open_questions") == ["Potvrdite prevodcu?"]


def test_thinking_status_message_is_localized_by_country_or_language() -> None:
    from app.chat.api import _thinking_status_message

    assert _thinking_status_message(country="SK", language=None) == "Premyslam..."
    assert _thinking_status_message(country="US", language="sk-SK") == "Premyslam..."
    assert _thinking_status_message(country="DE", language=None) == "Ich denke nach..."
    assert _thinking_status_message(country="CZ", language=None) == "Premyslim..."
    assert _thinking_status_message(country="US", language="en-US") == "Thinking..."


def test_processing_status_message_is_localized_by_country_or_language() -> None:
    from app.chat.api import _processing_status_message

    assert _processing_status_message(country="SK", language=None) == "Spracovavam..."
    assert _processing_status_message(country="US", language="sk-SK") == "Spracovavam..."
    assert _processing_status_message(country="DE", language=None) == "Verarbeite Anfrage..."
    assert _processing_status_message(country="CZ", language=None) == "Zpracovavam..."
    assert _processing_status_message(country="US", language="en-US") == "Processing..."


def test_orsr_tool_messages_are_localized_by_country_or_language() -> None:
    from app.chat.country_services.slovakia import (
        _orsr_tool_result_found_message,
        _orsr_tool_start_message,
    )

    assert _orsr_tool_start_message(
        company_query="ESolutions SK s.r.o.",
        country="SK",
        language=None,
    ) == "Idem overit spolocnost 'ESolutions SK s.r.o.' v ORSR."
    assert _orsr_tool_start_message(
        company_query="ESolutions SK s.r.o.",
        country="US",
        language="de-DE",
    ) == "Ich werde das Unternehmen 'ESolutions SK s.r.o.' im ORSR pruefen."
    assert _orsr_tool_start_message(
        company_query="ESolutions SK s.r.o.",
        country="US",
        language="en-US",
    ) == "I am going to verify company 'ESolutions SK s.r.o.' in ORSR."

    assert _orsr_tool_result_found_message(
        company_name="ESolutions SK s.r.o.",
        registration_number="46491261",
        country="SK",
        language=None,
    ) == "Overenie spolocnosti v ORSR je hotove: ESolutions SK s.r.o. (46491261)."
    assert _orsr_tool_result_found_message(
        company_name="ESolutions SK s.r.o.",
        registration_number="46491261",
        country="US",
        language="de-DE",
    ) == "Unternehmenspruefung im ORSR abgeschlossen: ESolutions SK s.r.o. (46491261)."
    assert _orsr_tool_result_found_message(
        company_name="ESolutions SK s.r.o.",
        registration_number="46491261",
        country="US",
        language="en-US",
    ) == "Verification of company done in ORSR: ESolutions SK s.r.o. (46491261)."


def _pdf_text(payload: bytes) -> str:
    reader = PdfReader(BytesIO(payload))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if any(marker in text for marker in ("ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢", "ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾", "ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦")):
        repaired = text.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
        if repaired:
            return repaired
    return text


def _canonical_text(value: str) -> str:
    repaired = value
    for _ in range(2):
        if not any(marker in repaired for marker in ("Ã", "Â", "Ä", "Å", "â")):
            break
        candidate = repaired.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
        if not candidate or candidate == repaired:
            break
        repaired = candidate
    repaired = repaired.translate({161: 97, 169: 101, 173: 105, 189: 121, 190: 122, 188: 117, 182: 111, 164: 97, 180: 111, 168: 117, 167: 115, 163: 108})
    repaired = repaired.replace("\x00", "")
    normalized = unicodedata.normalize("NFKD", repaired.casefold())
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_only).strip()
