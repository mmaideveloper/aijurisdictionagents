import json
import base64
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


@pytest.fixture(autouse=True)
def _disable_chat_api_mcp_law_context_by_default(monkeypatch) -> None:
    import app.chat.api as chat_api

    monkeypatch.setattr(chat_api, "build_mcp_law_context", lambda **_kwargs: None)


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
        ("general", "other", "Potvrdenie o zaplatení", True),
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


def test_pdf_builder_renders_professional_footer_only_when_template_enabled() -> None:
    import app.chat.api as chat_api

    corporate_pdf = chat_api._build_simple_pdf(
        title="Car Rental Legal Memo",
        lines=["Subject: Liability review", "To: Example Recipient"],
        country="US",
        language="en-US",
        header_line="AI Jurisdicta Solution | Generated: 2026-04-21 10:00:00 UTC",
        footer_line="AIJ | API 1.0 | Core 1.0",
        footer_qr_payload={
            "generated_at": "2026-04-21 10:00:00 UTC",
            "api_version": "1.0",
            "core_system_version": "1.0",
            "case_id": "case-123",
        },
        document_verification_score="88.4%",
        disclaimer=("Important notice", "Draft only. Lawyer review required.", "Draft only"),
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

    assert "jurisdigta" in corporate_text
    assert "skore overenia dokumentu: 88.4%" in corporate_text
    assert "poprad, slovakia, 05801" in corporate_text
    assert "info@jurisdigta.eu" in corporate_text
    assert "template.net" not in corporate_text
    assert "important notice" not in corporate_text
    assert "lawyer review required" not in corporate_text

    low_score_pdf = chat_api._build_simple_pdf(
        title="Car Rental Legal Memo",
        lines=["Subject: Liability review", "To: Example Recipient"],
        country="US",
        language="en-US",
        footer_line="AIJ | API 1.0 | Core 1.0",
        footer_qr_payload={
            "generated_at": "2026-04-21 10:00:00 UTC",
            "api_version": "1.0",
            "core_system_version": "1.0",
            "case_id": "case-123",
        },
        document_verification_score="49.0%",
        disclaimer=("Important notice", "Draft only. Lawyer review required.", "Draft only"),
        draw_logo_mark=True,
        include_title_block=False,
    )
    low_score_text = _pdf_text(low_score_pdf).lower()
    assert "important notice" in low_score_text
    assert "lawyer review required" in low_score_text

    unknown_score_pdf = chat_api._build_simple_pdf(
        title="Car Rental Legal Memo",
        lines=["Subject: Liability review", "To: Example Recipient"],
        country="US",
        language="en-US",
        footer_line="AIJ | API 1.0 | Core 1.0",
        document_verification_score=None,
        disclaimer=("Important notice", "Draft only. Lawyer review required.", "Draft only"),
        draw_logo_mark=True,
        include_title_block=False,
    )
    unknown_score_text = _pdf_text(unknown_score_pdf).lower()
    assert "skore overenia dokumentu: -" in unknown_score_text
    assert "important notice" in unknown_score_text
    assert "lawyer review required" in unknown_score_text
    assert "poprad, slovakia, 05801" not in plain_text

    reader = PdfReader(BytesIO(corporate_pdf))
    page = reader.pages[0]
    assert float(page.mediabox.width) < float(page.mediabox.height)
    qr_payload = chat_api._build_professional_document_qr_payload(
        generated_at="2026-04-21 10:00:00 UTC",
        case_id="case-123",
        session_id="session-123",
        user_id="user-123",
        document_score="88.4%",
    )
    assert qr_payload["document_score"] == "88.4%"
    assert qr_payload["session_id"] == "session-123"
    assert qr_payload["user_id"] == "user-123"


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

    export_documents = client.get(
        f"/v1/chat/sessions/{session_id}/export/documents",
        headers=AUTH_HEADERS,
    )
    assert export_documents.status_code == 200
    documents_payload = export_documents.json()
    assert documents_payload["documents"]
    first_document = documents_payload["documents"][0]
    assert first_document["filename"].endswith(".pdf")

    selected_document_pdf = client.get(
        f"/v1/chat/sessions/{session_id}/export/documents/{first_document['index']}",
        headers=AUTH_HEADERS,
    )
    assert selected_document_pdf.status_code == 200
    assert selected_document_pdf.headers["content-type"].startswith("application/pdf")
    assert selected_document_pdf.content.startswith(b"%PDF")


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
    assert "jurisdigta" in document_text
    assert "skore overenia dokumentu:" in document_text
    assert "%" in document_text
    assert "poprad, slovakia, 05801" in document_text
    assert "api version" in document_text
    assert "core version" in document_text
    assert "aij | api " not in document_text
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


def test_multilingual_case_update_documents_export_as_clean_separate_assets(monkeypatch) -> None:
    from app.chat.models import Message, MessageRole, Session, SessionResult
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    repository = InMemoryChatRepository()
    monkeypatch.setattr(chat_api, "_repository", repository)

    session = repository.create_session(Session(country="SK", discussion_type="advice", language="sk-SK"))
    case_update = {
        "case": {
            "documents": [
                {
                    "title": "Splnomocnenie",
                    "filename": "splnomocnenie_sk.pdf",
                    "language": "sk-SK",
                    "content": (
                        "**SPLNOMOCNENIE**\n\n"
                        "Ja, RNDr. Marek Matonok, tymto splnomocnujem Emiliu Testovu "
                        "na pouzivanie firemneho vozidla s evidencnym cislom PP472DT.\n\n"
                        "Datum: 25. jun 2026\n\n"
                        "Podpis: ______________________"
                    ),
                },
                {
                    "title": "Power of Attorney",
                    "filename": "power_of_attorney_en.pdf",
                    "language": "en",
                    "content": (
                        "**POWER OF ATTORNEY**\n\n"
                        "I, RNDr. Marek Matonok, hereby authorize Emilia Testova to use "
                        "the company vehicle with registration number PP472DT.\n\n"
                        "Date: June 25, 2026\n\n"
                        "Signature: ______________________"
                    ),
                },
            ]
        }
    }
    assistant_content = (
        "Vyborne, pripravim splnomocnenie v slovenskej a anglickej verzii na export do PDF.\n\n"
        "---\n\n"
        "CASE_UPDATE_JSON:\n"
        f"{json.dumps(case_update, ensure_ascii=False)}"
    )
    repository.add_message(
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=assistant_content,
        )
    )
    repository.set_result(
        session.id,
        SessionResult(
            final_recommendation=assistant_content,
            judge_rationale="Direct lawyer reply prepared for session export.",
            metadata={},
        ),
    )

    options = client.get(f"/v1/chat/sessions/{session.id}/export/documents", headers=AUTH_HEADERS)
    assert options.status_code == 200
    assert [item["filename"] for item in options.json()["documents"]] == [
        "splnomocnenie_sk.pdf",
        "power_of_attorney_en.pdf",
    ]

    default_export = client.get(
        f"/v1/chat/sessions/{session.id}/export?format=pdf&kind=document",
        headers=AUTH_HEADERS,
    )
    assert default_export.status_code == 200
    assert default_export.headers["content-type"].startswith("application/zip")
    with ZipFile(BytesIO(default_export.content)) as archive:
        assert sorted(archive.namelist()) == ["power_of_attorney_en.pdf", "splnomocnenie_sk.pdf"]
        slovak_text = _pdf_text(archive.read("splnomocnenie_sk.pdf"))
        english_text = _pdf_text(archive.read("power_of_attorney_en.pdf"))
    assert "Splnomocnenie" in slovak_text
    assert "Marek Matonok" in slovak_text
    assert "splnomocnujem Emiliu" in slovak_text
    assert "______________________" in slovak_text
    assert "POWER OF ATTORNEY" not in slovak_text
    assert "Power of Attorney" in english_text
    assert "hereby authorize Emilia" in english_text
    assert "______________________" in english_text
    assert "SPLNOMOCNENIE" not in english_text
    polluted_tokens = ("Vyborne", "CASE_UPDATE_JSON", "---", "**", "ready for export")
    assert not any(token in slovak_text for token in polluted_tokens)
    assert not any(token in english_text for token in polluted_tokens)

    single_pdf = client.get(
        f"/v1/chat/sessions/{session.id}/export?format=pdf&kind=document&bundle=single_pdf",
        headers=AUTH_HEADERS,
    )
    assert single_pdf.status_code == 200
    assert single_pdf.headers["content-type"].startswith("application/pdf")
    reader = PdfReader(BytesIO(single_pdf.content))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    assert "Splnomocnenie" in page_texts[0]
    assert "Marek Matonok" in page_texts[0]
    assert any("Power of Attorney" in page_text for page_text in page_texts[1:])


def test_single_splnomocnenie_case_update_export_uses_clean_document_body(monkeypatch) -> None:
    from app.chat.models import Message, MessageRole, Session, SessionResult
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    repository = InMemoryChatRepository()
    monkeypatch.setattr(chat_api, "_repository", repository)

    session = repository.create_session(Session(country="SK", discussion_type="advice", language="sk-SK"))
    document_body = (
        "**Splnomocnenie**\n\n"
        "Ja, Marek Matonok, konatel spolocnosti ESolutions SK s.r.o., so sidlom "
        "Partizanska 665, Spisske Bystre, 05918, tymto splnomocnujem Emiliu "
        "Matonokovu na pouzivanie firemneho vozidla s evidencnym cislom PP472DT "
        "v obdobi od 1. jula 2026 do 31. decembra 2026.\n\n"
        "Podpis: ________________________"
    )
    case_update = {
        "case": {
            "documents": [
                {
                    "title": "Splnomocnenie",
                    "filename": "splnomocnenie.pdf",
                    "language": "sk-SK",
                    "content": document_body,
                }
            ]
        }
    }
    assistant_content = (
        "Vyborne, pripravim finalny navrh splnomocnenia vo formate PDF.\n\n"
        "---\n\n"
        f"{document_body}\n\n"
        "---\n\n"
        "Tu je finalny navrh splnomocnenia.\n\n"
        "CASE_UPDATE_JSON:\n"
        f"{json.dumps(case_update, ensure_ascii=False)}"
    )
    repository.add_message(
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=assistant_content,
        )
    )
    repository.set_result(
        session.id,
        SessionResult(
            final_recommendation=assistant_content,
            judge_rationale="Direct lawyer reply prepared for session export.",
            metadata={},
        ),
    )

    selected_document_pdf = client.get(
        f"/v1/chat/sessions/{session.id}/export/documents/0",
        headers=AUTH_HEADERS,
    )

    assert selected_document_pdf.status_code == 200
    pdf_text = _pdf_text(selected_document_pdf.content)
    canonical_pdf_text = _canonical_text(pdf_text)
    for expected in (
        "splnomocnenie",
        "esolutions sk s.r.o.",
        "marek matonok",
        "emiliu matonokovu",
        "partizanska 665",
        "spisske bystre",
        "05918",
        "pp472dt",
        "1. jula 2026",
        "31. decembra 2026",
    ):
        assert expected in canonical_pdf_text
    for polluted in (
        "vyborne",
        "pripravim",
        "tu je finalny navrh",
        "case_update_json",
        "system",
        "assistant",
        "---",
        "**",
    ):
        assert polluted not in canonical_pdf_text


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


def test_document_export_payment_confirmation_keeps_requested_template_with_stale_context() -> None:
    from app.chat.api import _build_document_export_content
    from app.chat.models import Message, MessageRole, SessionResult

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "Skorší kontext prípadu spomína nájomnú zmluvu a vecné bremeno, "
                "ale toto nemá byť finálny typ dokumentu."
            ),
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "Chcem potvrdenie o zaplateni. Platiteľ: Ján Novák. "
                "Príjemca: Marek Matonok. Suma: 120 EUR. "
                "Dátum platby: 22.05.2026. Účel platby: úhrada nájomného."
            ),
        ),
    ]
    result = SessionResult(
        final_recommendation=(
            "Pripravil som Potvrdenie o zaplatení podľa zadaných údajov, "
            "nie nájomnú zmluvu ani predžalobnú výzvu."
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

    normalized_title = _canonical_text(title)
    normalized_lines = _canonical_text(" ".join(lines))
    assert normalized_title == "potvrdenie o zaplateni"
    assert "jan novak" in normalized_lines
    assert "120 eur" in normalized_lines
    assert "najomna zmluva" not in normalized_lines
    assert "predzalobna vyzva" not in normalized_lines


def test_document_export_payment_confirmation_extracts_voice_case_facts() -> None:
    from app.chat.api import _build_document_export_content
    from app.chat.models import Message, MessageRole, SessionResult

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "Vytvor potvrdenie o zaplatení na sumu 5000 EUR, splatné k 1.7.2028, "
                "na firmu Esolutions SK s.r.o., v zastúpení Marek Matonok, "
                "na splátku auta so SPZ PP472DT."
            ),
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="Assistant",
            content=(
                "Tu je konecna verzia dokumentu - dokument je pripraveny na export a stiahnutie.\n\n"
                "Podklady pre export:\n"
                "Platitel: Marek Matonok\n"
                "Prijemca: ESolutions SK s.r.o., IČO: 46491261, Partizánska 665, 059 18 Spišské Bystré\n"
                "Suma: 5000 EUR\n"
                "Datum splatnosti / platby: 1.7.2028\n"
                "Ucel platby: splátka auta so SPZ PP472DT"
            ),
        ),
    ]
    result = SessionResult(
        final_recommendation="Tu je konecna verzia dokumentu - dokument je pripraveny na export a stiahnutie.",
        judge_rationale="Direct lawyer reply prepared for session export.",
        metadata={"document_ready": True},
    )

    title, lines = _build_document_export_content(
        session_id=session_id,
        messages=messages,
        result=result,
        country="SK",
        language="sk-SK",
    )

    normalized = _canonical_text(" ".join([title, *lines]))
    assert "potvrdenie o zaplateni" in normalized
    assert "marek matonok" in normalized
    assert "esolutions sk" in normalized
    assert "46491261" in normalized
    assert "5000 eur" in normalized
    assert "1.7.2028" in normalized
    assert "pp472dt" in normalized


def test_document_pdf_wrap_repairs_slovak_mojibake_before_rendering() -> None:
    from app.chat.api import _build_simple_pdf

    pdf_bytes = _build_simple_pdf(
        title="Potvrdenie o zaplatení",
        lines=["PredÅ¾alobnÃ¡ vÃ½zva", "PrÃ­jemca: Marek Matonok"],
        country="SK",
        language="SK",
        header_line="AI Jurisdicta Solution | Generated: 2026-05-22 10:00:00 UTC",
        footer_line="AIJ | API 0.1.0 | Core 0.1.0",
        draw_logo_mark=True,
        include_title_block=True,
    )

    extracted = _pdf_text(pdf_bytes)
    assert "Predžalobná výzva" in extracted
    assert "Príjemca:" in extracted and "Marek Matonok" in extracted
    assert not any(marker in extracted for marker in ("Ã", "Â", "Ä", "Å", "â"))


def test_payment_confirmation_export_uses_latest_visible_draft_sentence() -> None:
    from app.chat.api import _build_document_export_content, _build_simple_pdf
    from app.chat.models import Message, MessageRole, SessionResult

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "Potvrdenie o zaplatení\n\n"
                "Ja, Marek Novak, bytom iiiiii, 8098098 mmmmmm, Slovensko, "
                "týmto potvrdzujem, že som dňa [dátum] zaplatil sumu 5000 eur "
                "svojmu susedovi, [Meno suseda], bytom Testova 21, Poprad, 051 01, "
                "prevodom na účet."
            ),
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "Tu je konečná verzia dokumentu:\n\n"
                "---\n\n"
                "**Potvrdenie o zaplatení**\n\n"
                "Ja, Marek Novak, bytom iiiiii, 8098098 mmmmmm, Slovensko, "
                "týmto potvrdzujem, že som dňa 1. júna 2026 zaplatil sumu "
                "5000 eur (päťtisíc eur) svojmu susedovi, Jano Mrkvička, "
                "bytom Testova 21, Poprad, 051 01, prevodom na účet.\n\n"
                "Dátum: 1. júna 2026\n\n"
                "Podpis: ________________________"
            ),
        ),
    ]
    result = SessionResult(
        final_recommendation=messages[-1].content,
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

    normalized = _canonical_text(" ".join(lines))
    assert _canonical_text(title) == "potvrdenie o zaplateni"
    assert "marek novak" in normalized
    assert "iiiiii, 8098098 mmmmmm, slovensko" in normalized
    assert "jano mrkvicka" in normalized
    assert "testova 21, poprad, 051 01" in normalized
    assert "1. juna 2026" in normalized
    assert "prevodom na ucet" in normalized
    assert "meno suseda" not in normalized
    assert "bude identifikovany" not in normalized

    pdf_text = _pdf_text(
        _build_simple_pdf(
            title=title,
            lines=lines,
            country="SK",
            language="SK",
            header_line="AI Jurisdicta Solution | Generated: 2026-05-22 10:00:00 UTC",
            footer_line="AIJ | API 0.1.0 | Core 0.1.0",
            draw_logo_mark=True,
            include_title_block=True,
        )
    )
    assert "Jano Mrkvička" in pdf_text
    assert "1. júna 2026" in pdf_text


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
    assert _canonical_text(title) == "zmluva o prevode obchodneho podielu"
    assert str(session_id) not in title
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


def test_document_export_title_uses_requested_legal_document_type() -> None:
    from app.chat.api import _build_document_export_content
    from app.chat.models import Message, MessageRole, SessionResult

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content="Priprav kupno predajnu zmluvu na pozemok v katastri obce Kravany.",
        )
    ]
    result = SessionResult(
        final_recommendation="Odporucam pripravit kupno-predajnu zmluvu k prevodu pozemku.",
        judge_rationale="Direct lawyer reply prepared for session export.",
        metadata={"document_ready": True},
    )

    title, _lines = _build_document_export_content(
        session_id=session_id,
        messages=messages,
        result=result,
        country="SK",
        language="SK",
    )

    assert title == "Kupno-predajna zmluva"
    assert str(session_id) not in title


def test_document_export_uses_user_profile_defaults_for_missing_party_data() -> None:
    from app.chat.api import _build_document_export_content
    from app.chat.models import Message, MessageRole, SessionResult
    from aijurisdictionagents.api_db import User

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "Priprav najomnu zmluvu. Prenajimatel: Prenajimatel [doplnit udaje]. "
                "Najomca: Najomca [doplnit udaje]."
            ),
        )
    ]
    result = SessionResult(
        final_recommendation="Dokument je pripraveny.",
        judge_rationale="Direct lawyer reply prepared for session export.",
        metadata={"document_ready": True},
    )
    user_profile = User(
        user_id="user-1",
        phone_number="+421900111222",
        email="marek@example.com",
        first_name="Marek",
        last_name="Matonok",
        full_name="Marek Matonok",
        address="Partizanska 665",
        city="Spisske Bystre",
        country="SK",
        zip_code="059 18",
        tax_number="1070000001",
        identity_card_number="AB123456",
        date_of_birth="1980-01-02",
        social_security_number="800102/1234",
        data_processing_consent_at=None,
        data_processing_consent_version=None,
        mcp_api_key_hash=None,
        mcp_api_key_expires_at=None,
        created_at="2026-06-21T00:00:00Z",
    )

    title, lines = _build_document_export_content(
        session_id=session_id,
        messages=messages,
        result=result,
        country="SK",
        language="SK",
        user_profile=user_profile,
    )

    normalized = _canonical_text(" ".join(lines))
    assert _canonical_text(title) == "najomna zmluva"
    assert not _canonical_text(lines[0]).startswith("najomna zmluva")
    assert "marek matonok" in normalized
    assert "partizanska 665" in normalized
    assert "800102/1234" in normalized
    assert "ab123456" in normalized


def test_document_export_replaces_rental_party_placeholders_from_case_parties() -> None:
    from app.chat.api import _build_document_export_content
    from app.chat.models import Message, MessageRole, SessionResult

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "**ZMLUVA O PRENÁJME BYTU**\n\n"
                "Prenajímateľ: Prenajimatel [doplnit udaje]\n"
                "Nájomca: Najomca [doplnit udaje]\n\n"
                "CASE_UPDATE_JSON:\n"
                "{"
                '"case":{"parties":{"client":{"name":"Maria Kovacova"},'
                '"opponent":{"name":"Jan Novak"}},'
                '"matter":{"topic":"prenajom","facts_summary":"Najom bytu","client_goal":"Pripravit zmluvu"},'
                '"documents":[],"next_discussion":{"agenda":[]}}'
                "}"
            ),
        )
    ]
    result = SessionResult(
        final_recommendation="Dokument je pripraveny.",
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

    normalized = _canonical_text(" ".join(lines))
    assert _canonical_text(title) == "zmluva o prenajme bytu"
    assert "jan novak" in normalized
    assert "maria kovacova" in normalized
    assert "prenajimatel [doplnit udaje]" not in normalized
    assert "najomca [doplnit udaje]" not in normalized
    assert not _canonical_text(lines[0]).startswith("najomna zmluva")


def test_document_export_extracts_rental_data_from_draft_text_and_profile() -> None:
    from app.chat.api import _build_document_export_content
    from app.chat.models import Message, MessageRole, SessionResult
    from aijurisdictionagents.api_db import User

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "Pripravím zmluvu o prenájme.\n\n"
                "- Adresa nehnuteľnosti: Bratislava, Slavin, Pod Radom 1234\n"
                "- Mesačné nájomné: 5000 EUR\n"
                "- Doba prenájmu: 1 rok (od 1. júna 2026)\n"
                "- Podnájomník: John Kennedy, Washington, D.C., USA\n\n"
                "**Zmluva o prenájme**\n\n"
                "**Zmluvné strany:**\n"
                "Prenajímateľ: [Vaše meno a adresa]\n"
                "Podnájomník: John Kennedy, Washington, D.C., USA\n\n"
                "**Predmet zmluvy:**\n"
                "Prenajímateľ prenajíma podnájomníkovi dom nachádzajúci sa na adrese "
                "Bratislava, Slavin, Pod Radom 1234."
            ),
        )
    ]
    result = SessionResult(
        final_recommendation="Dokument je pripraveny.",
        judge_rationale="Direct lawyer reply prepared for session export.",
        metadata={"document_ready": True},
    )
    user_profile = User(
        user_id="user-1",
        phone_number="+421900111222",
        email="owner@example.com",
        first_name="Marek",
        last_name="Matonok",
        full_name="Marek Matonok",
        address="Partizanska 665",
        city="Spisske Bystre",
        country="SK",
        zip_code="059 18",
        tax_number=None,
        identity_card_number=None,
        date_of_birth=None,
        social_security_number=None,
        data_processing_consent_at=None,
        data_processing_consent_version=None,
        mcp_api_key_hash=None,
        mcp_api_key_expires_at=None,
        created_at="2026-06-21T00:00:00Z",
    )

    _title, lines = _build_document_export_content(
        session_id=session_id,
        messages=messages,
        result=result,
        country="SK",
        language="SK",
        user_profile=user_profile,
    )

    normalized = _canonical_text(" ".join(lines))
    assert "marek matonok" in normalized
    assert "partizanska 665" in normalized
    assert "john kennedy, washington" in normalized
    assert "bratislava, slavin, pod radom 1234" in normalized
    assert "byt [adresa a identifikacia]" not in normalized
    assert "protistrana" not in normalized
    assert "klient" not in normalized


def test_document_export_does_not_use_phone_number_as_profile_name() -> None:
    from app.chat.api import _build_document_export_content
    from app.chat.models import Message, MessageRole, SessionResult
    from aijurisdictionagents.api_db import User

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "**Zmluva o prenájme**\n"
                "Prenajímateľ: [Vaše meno a adresa]\n"
                "Podnájomník: John Kennedy\n"
                "Adresa nehnuteľnosti: Bratislava"
            ),
        )
    ]
    result = SessionResult(
        final_recommendation="Dokument je pripraveny.",
        judge_rationale="Direct lawyer reply prepared for session export.",
        metadata={"document_ready": True},
    )
    user_profile = User(
        user_id="user-1",
        phone_number="+421900111222",
        email="owner@example.com",
        first_name=None,
        last_name=None,
        full_name="+421900111222",
        address="Partizanska 665",
        city="Spisske Bystre",
        country="SK",
        zip_code="059 18",
        tax_number=None,
        identity_card_number=None,
        date_of_birth=None,
        social_security_number=None,
        data_processing_consent_at=None,
        data_processing_consent_version=None,
        mcp_api_key_hash=None,
        mcp_api_key_expires_at=None,
        created_at="2026-06-21T00:00:00Z",
    )

    _title, lines = _build_document_export_content(
        session_id=session_id,
        messages=messages,
        result=result,
        country="SK",
        language="SK",
        user_profile=user_profile,
    )

    normalized = _canonical_text(" ".join(lines))
    assert "+421900111222" not in normalized
    assert "partizanska 665" in normalized


def test_signed_in_user_profile_prompt_note_uses_profile_name_and_address(monkeypatch) -> None:
    from app.chat.api import _build_signed_in_user_profile_prompt_note
    from app.chat.models import Session
    import app.chat.api as chat_api
    from aijurisdictionagents.api_db import User

    user_profile = User(
        user_id="user-1",
        phone_number="+421900111222",
        email="owner@example.com",
        first_name="Marek",
        last_name="Matonok",
        full_name="Marek Matonok",
        address="Partizanska 665",
        city="Spisske Bystre",
        country="SK",
        zip_code="059 18",
        tax_number="1070000001",
        identity_card_number="AB123456",
        date_of_birth="1980-01-02",
        social_security_number="800102/1234",
        data_processing_consent_at=None,
        data_processing_consent_version=None,
        mcp_api_key_hash=None,
        mcp_api_key_expires_at=None,
        created_at="2026-06-21T00:00:00Z",
    )
    monkeypatch.setattr(
        chat_api,
        "_document_user_profile_for_session",
        lambda session: user_profile,
    )

    note = _build_signed_in_user_profile_prompt_note(Session(country="SK", language="SK"))

    assert "SIGNED-IN USER PROFILE DEFAULTS" in note
    assert "Client full name: Marek Matonok" in note
    assert "Client address: Partizanska 665, 059 18 Spisske Bystre, SK" in note
    assert "1070000001" not in note
    assert "AB123456" not in note
    assert "800102/1234" not in note


def test_current_date_prompt_note_uses_runtime_date() -> None:
    from datetime import date

    from app.chat.api import _build_current_date_prompt_note

    note = _build_current_date_prompt_note(today=date(2026, 6, 23))

    assert "CURRENT DATE CONTEXT" in note
    assert "2026-06-23" in note
    assert "23.6.2026" in note
    assert "23. juna 2026" in note
    assert "Do not invent" in note


def test_compact_free_local_prompt_blocks_mixed_language_reasoning_for_slovak() -> None:
    from app.chat.api import _build_compact_free_local_lawyer_prompt
    from app.chat.models import Session

    prompt = _build_compact_free_local_lawyer_prompt(
        session=Session(country="SK", language="SK"),
        case_memory_note="",
        user_profile_note="",
        preparation_prompt_note="",
        document_generation_requested=False,
    )

    assert "Reply in SK." in prompt
    assert "Use only Slovak (sk-SK)" in prompt
    assert "Do not mix English and Slovak" in prompt
    assert "English meta-analysis" in prompt
    assert "Do not expose hidden chain-of-thought" in prompt


def test_reply_endpoint_includes_current_date_context_in_lawyer_prompt(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(content="MODEL_REPLY", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr(
        chat_api,
        "_build_current_date_prompt_note",
        lambda: (
            "CURRENT DATE CONTEXT:\n"
            "- Today's date is 2026-06-23 (23.6.2026; 23. juna 2026).\n"
            "- If the user asks for today's/current/date-of-signature date in a document, "
            "use this date.\n"
            "- Do not invent, infer from model training data, or reuse old example dates."
        ),
    )
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
        json={"content": "Priprav splnomocnenie a pouzi dnesny datum."},
        headers=AUTH_HEADERS,
    )

    assert reply_response.status_code == 200
    assert captured_prompts
    assert "CURRENT DATE CONTEXT" in captured_prompts[-1]
    assert "2026-06-23" in captured_prompts[-1]
    assert "23.6.2026" in captured_prompts[-1]
    assert "23. juna 2026" in captured_prompts[-1]


def test_reply_endpoint_includes_signed_in_profile_defaults_in_lawyer_prompt(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(content="MODEL_REPLY", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr(
        chat_api,
        "_build_signed_in_user_profile_prompt_note",
        lambda session: "SIGNED-IN USER PROFILE DEFAULTS:\n- Client full name: Marek Matonok",
    )
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
        json={"content": "Priprav najomnu zmluvu."},
        headers=AUTH_HEADERS,
    )

    assert reply_response.status_code == 200
    assert captured_prompts
    assert "SIGNED-IN USER PROFILE DEFAULTS" in captured_prompts[-1]
    assert "Client full name: Marek Matonok" in captured_prompts[-1]


def test_free_plan_chat_reply_records_local_model_route_e2e(monkeypatch, tmp_path) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api
    import app.users.api as users_api
    from aijurisdictionagents.llm.routing import RoutedLLMClient

    class _NoopEmailScheduler:
        def enqueue(self, *, recipient: str, subject: str, body: str, metadata: dict[str, object]) -> str:
            return "email-ignored"

    class _FakeLocalLLM:
        def complete(self, agent_name, system_prompt, conversation, documents):
            return "Free local model answer from test."

    class _NoopDocumentProcessor:
        def __init__(self, store):
            self.store = store

        def process_documents(self, documents):
            return None

    def _routed_free_client(*, store, user_id, task_type="default", external_acknowledged=False):
        plan = store.get_effective_subscription_plan(user_id=user_id)
        subscription = store.get_effective_user_subscription(user_id=user_id)
        route = store.resolve_ai_model_route(
            user_id=user_id,
            plan_code=plan.plan_code,
            task_type=task_type,
            external_acknowledged=external_acknowledged,
        )
        assert route.provider is not None
        assert route.model_profile is not None
        return RoutedLLMClient(
            client=_FakeLocalLLM(),
            route=route,
            plan=plan,
            subscription=subscription,
            provider=route.provider.provider_code,
            model=route.model_profile.deployment_name or route.model_profile.model_code,
            route_type=route.route_type,
            fallback_reason="",
        )

    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "blob"))
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr(chat_api, "get_routed_llm_client", _routed_free_client)
    monkeypatch.setattr(chat_api, "DocumentProcessor", _NoopDocumentProcessor)
    app.dependency_overrides[users_api.get_email_scheduler] = lambda: _NoopEmailScheduler()
    try:
        sign_up_response = client.post(
            "/v1/users/sign-up",
            headers=AUTH_HEADERS,
            json={
                "phone_number": "+421900777888",
                "email": "free-local-e2e@example.com",
                "password": "secret",
                "first_name": "Free",
                "last_name": "Local",
            },
        )
        assert sign_up_response.status_code == 201
        user_id = sign_up_response.json()["user_id"]
        subscriptions_response = client.get(
            f"/v1/users/{user_id}/subscriptions",
            headers=AUTH_HEADERS,
        )
        assert subscriptions_response.status_code == 200
        assert subscriptions_response.json()[0]["plan_code"] == "free"

        case_response = client.post(
            "/v1/cases",
            headers=AUTH_HEADERS,
            json={"user_id": user_id, "title": "Free local routing e2e"},
        )
        assert case_response.status_code == 201
        case_id = case_response.json()["case_id"]

        session_response = client.post(
            "/v1/chat/sessions",
            headers=AUTH_HEADERS,
            json={
                "user_id": user_id,
                "case_id": case_id,
                "country": "US",
                "discussion_type": "advice",
                "language": "EN",
            },
        )
        assert session_response.status_code == 200
        session_id = session_response.json()["id"]

        reply_response = client.post(
            f"/v1/chat/sessions/{session_id}/reply",
            headers=AUTH_HEADERS,
            json={"content": "Please review my tenant dispute and suggest next steps."},
        )
        assert reply_response.status_code == 200
        assert reply_response.json()["content"] == "Free local model answer from test."

        audit_response = client.get(
            f"/v1/cases/{case_id}/ai-model-audit?user_id={user_id}&limit=5",
            headers=AUTH_HEADERS,
        )
        assert audit_response.status_code == 200
    finally:
        app.dependency_overrides.pop(users_api.get_email_scheduler, None)

    entries = audit_response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["provider"] == "local_ollama"
    assert entries[0]["model"] == "qwen3:1.7b"
    assert entries[0]["route_type"] == "free_local"
    assert entries[0]["task_type"] == "chat_reply"


def test_paid_case_chat_reply_records_external_model_route_e2e(monkeypatch, tmp_path) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api
    import app.users.api as users_api
    from aijurisdictionagents.llm.routing import RoutedLLMClient

    class _NoopEmailScheduler:
        def enqueue(self, *, recipient: str, subject: str, body: str, metadata: dict[str, object]) -> str:
            return "email-ignored"

    class _FakeExternalLLM:
        def complete(self, agent_name, system_prompt, conversation, documents):
            return "Paid external model answer from test."

    class _NoopDocumentProcessor:
        def __init__(self, store):
            self.store = store

        def process_documents(self, documents):
            return None

    def _routed_paid_client(
        *,
        store,
        user_id,
        task_type="default",
        external_acknowledged=False,
        selected_model_profile_id=None,
    ):
        plan = store.get_effective_subscription_plan(user_id=user_id)
        subscription = store.get_effective_user_subscription(user_id=user_id)
        route = store.resolve_ai_model_route(
            user_id=user_id,
            plan_code=plan.plan_code,
            task_type=task_type,
            external_acknowledged=external_acknowledged,
        )
        assert route.provider is not None
        assert route.model_profile is not None
        assert selected_model_profile_id is None
        return RoutedLLMClient(
            client=_FakeExternalLLM(),
            route=route,
            plan=plan,
            subscription=subscription,
            provider=route.provider.provider_code,
            model=route.model_profile.deployment_name or route.model_profile.model_code,
            route_type=route.route_type,
            fallback_reason="",
        )

    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "blob"))
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr(chat_api, "get_routed_llm_client", _routed_paid_client)
    monkeypatch.setattr(chat_api, "DocumentProcessor", _NoopDocumentProcessor)
    app.dependency_overrides[users_api.get_email_scheduler] = lambda: _NoopEmailScheduler()
    try:
        sign_up_response = client.post(
            "/v1/users/sign-up",
            headers=AUTH_HEADERS,
            json={
                "phone_number": "+421900777889",
                "email": "paid-external-e2e@example.com",
                "password": "secret",
                "first_name": "Paid",
                "last_name": "External",
            },
        )
        assert sign_up_response.status_code == 201
        user_id = sign_up_response.json()["user_id"]
        subscription_response = client.post(
            f"/v1/users/{user_id}/subscriptions",
            headers=AUTH_HEADERS,
            json={"plan_code": "case"},
        )
        assert subscription_response.status_code == 201
        paid_response = client.patch(
            f"/v1/users/subscriptions/{subscription_response.json()['subscription_id']}",
            headers=AUTH_HEADERS,
            json={"status": "paid"},
        )
        assert paid_response.status_code == 200
        case_response = client.post(
            "/v1/cases",
            headers=AUTH_HEADERS,
            json={"user_id": user_id, "title": "Paid external routing e2e"},
        )
        assert case_response.status_code == 201
        case_id = case_response.json()["case_id"]
        session_response = client.post(
            "/v1/chat/sessions",
            headers=AUTH_HEADERS,
            json={
                "user_id": user_id,
                "case_id": case_id,
                "country": "SK",
                "discussion_type": "advice",
                "language": "EN",
            },
        )
        assert session_response.status_code == 200
        session_id = session_response.json()["id"]

        reply_response = client.post(
            f"/v1/chat/sessions/{session_id}/reply",
            headers=AUTH_HEADERS,
            json={"content": "Please review my tenant dispute and suggest next steps."},
        )
        assert reply_response.status_code == 200
        audit_response = client.get(
            f"/v1/cases/{case_id}/ai-model-audit?user_id={user_id}&limit=5",
            headers=AUTH_HEADERS,
        )
        assert audit_response.status_code == 200
    finally:
        app.dependency_overrides.pop(users_api.get_email_scheduler, None)

    entries = audit_response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["provider"] == "azure_foundry"
    assert entries[0]["model"] == "gpt-4o-mini"
    assert entries[0]["route_type"] == "external"
    assert entries[0]["task_type"] == "chat_reply"
    assert "tenant dispute" in entries[0]["question_preview"]
    assert "Paid external model answer" not in entries[0]["question_preview"]
    assert "secret" not in audit_response.text.lower()


def test_stream_selected_model_accepts_allowlisted_email_without_session_user_id(
    monkeypatch,
    tmp_path,
) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api
    from aijurisdictionagents.llm.routing import RoutedLLMClient

    class _FakeLocalLLM:
        def complete(self, agent_name, system_prompt, conversation, documents):
            return "Admin selected local model answer from test."

    class _NoopDocumentProcessor:
        def __init__(self, store):
            self.store = store

        def process_documents(self, documents):
            return None

    observed: dict[str, str] = {}

    def _routed_selected_client(
        *,
        store,
        user_id,
        user_email="",
        task_type="default",
        external_acknowledged=False,
        selected_model_profile_id=None,
    ):
        observed["user_id"] = user_id
        observed["user_email"] = user_email
        observed["task_type"] = task_type
        observed["selected_model_profile_id"] = selected_model_profile_id or ""
        plan = (
            store.get_effective_subscription_plan(user_id=user_id)
            if user_id
            else store.get_subscription_plan(plan_code="free")
        )
        route = store.resolve_selected_ai_model_route(
            user_id=user_id,
            user_email=user_email,
            plan_code=plan.plan_code,
            task_type=task_type,
            model_profile_id=selected_model_profile_id or "",
        )
        return RoutedLLMClient(
            client=_FakeLocalLLM(),
            route=route,
            plan=plan,
            subscription=None,
            provider=route.provider.provider_code if route.provider is not None else "local_ollama",
            model=(
                route.model_profile.deployment_name or route.model_profile.model_code
                if route.model_profile is not None
                else "local_ollama_default"
            ),
            route_type=route.route_type,
            fallback_reason=route.reason,
        )

    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "blob"))
    monkeypatch.setenv("JURISDIGTA_UNLIMITED_ACCESS_EMAILS", "admin-selected@example.com")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr(chat_api, "get_routed_llm_client", _routed_selected_client)
    monkeypatch.setattr(chat_api, "DocumentProcessor", _NoopDocumentProcessor)

    store = chat_api._get_store()
    store.create_user(email="admin-selected@example.com", password="secret", full_name="Selector Email")

    session_response = client.post(
        "/v1/chat/sessions",
        headers=AUTH_HEADERS,
        json={
            "country": "SK",
            "discussion_type": "advice",
            "language": "SK",
        },
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": "Priprav navrh splnomocnenia.",
            "user_simulation_mode": "ReadUser",
            "user_email": "admin-selected@example.com",
            "model_profile_id": "local_ollama_default",
        },
    ) as response:
        assert response.status_code == 200
        events = "".join(response.iter_text())

    assert "Admin selected local model answer from test." in events
    assert observed == {
        "user_id": "",
        "user_email": "admin-selected@example.com",
        "task_type": "chat_reply",
        "selected_model_profile_id": "local_ollama_default",
    }


def test_mcp_law_context_uses_search_and_law_text_tools(monkeypatch) -> None:
    from app.chat.mcp_law_context import build_mcp_law_context

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((name, arguments))
        if name == "searchLaws":
            return {
                "results": [
                    {
                        "document_id": "doc-40-1964",
                        "law_identifier_text": "40/1964 Zb.",
                        "title": "Obciansky zakonnik",
                    }
                ]
            }
        if name == "getLawText":
            return {
                "document_id": arguments["document_id"],
                "law_identifier_text": "40/1964 Zb.",
                "title": "Obciansky zakonnik",
                "content_text": "§ 588: Z kupnej zmluvy vznikne predavajucemu povinnost predmet kupy odovzdat.",
            }
        raise AssertionError(name)

    monkeypatch.setattr("app.mcp_api._call_tool", fake_call_tool)

    context = build_mcp_law_context(
        query="Co hovori zakon 40/1964 o kupnej zmluve?",
        country="SK",
        language="sk-SK",
    )

    assert context is not None
    assert calls[0] == (
        "searchLaws",
        {
            "query": "40/1964",
            "country_code": "SK",
            "limit": 3,
            "law_number": 40,
            "law_year": 1964,
        },
    )
    assert calls[1][0] == "getLawText"
    assert calls[1][1]["document_id"] == "doc-40-1964"
    assert "INTERNAL MCP LAW TOOL CONTEXT" in context.prompt_note
    assert "searchLaws" in context.prompt_note
    assert "getLawText" in context.prompt_note
    assert "40/1964 Zb." in context.prompt_note
    assert context.document is not None
    assert context.document.path == "internal-mcp-law-context.txt"
    assert "§ 588" in context.document.content


def test_mcp_law_context_exposes_localized_user_visible_contact_notice(monkeypatch) -> None:
    from app.chat.mcp_law_context import build_mcp_law_context

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        if name == "searchLaws":
            return {
                "results": [
                    {
                        "document_id": "doc-192-2026",
                        "law_identifier_text": "192/2026 Z. z.",
                        "title": "Testovaci zakon",
                    }
                ]
            }
        if name == "getLawText":
            return {
                "document_id": arguments["document_id"],
                "law_identifier_text": "192/2026 Z. z.",
                "title": "Testovaci zakon",
                "content_text": "Testovaci obsah zakona 192/2026.",
            }
        raise AssertionError(name)

    monkeypatch.setattr("app.chat.mcp_law_context._call_mcp_tool", fake_call_tool)

    sk_context = build_mcp_law_context(
        query="Daj mi sumar zo zakona 192/2026",
        country="SK",
        language="sk-SK",
    )
    de_context = build_mcp_law_context(
        query="Daj mi sumar zo zakona 192/2026",
        country="SK",
        language="de-DE",
    )
    en_context = build_mcp_law_context(
        query="Daj mi sumar zo zakona 192/2026",
        country="SK",
        language="en-US",
    )

    assert sk_context is not None
    assert de_context is not None
    assert en_context is not None
    assert (
        sk_context.processing_event["message"]
        == "JurisDigta MCP server bol kontaktovaný na získanie najnovších právnych informácií."
    )
    assert (
        de_context.processing_event["message"]
        == "Der JurisDigta MCP-Server wurde kontaktiert, um aktuelle Rechtsinformationen abzurufen."
    )
    assert (
        en_context.processing_event["message"]
        == "JurisDigta MCP Server was contacted to retrieve the latest legal information."
    )
    details = sk_context.processing_event["details"]
    assert isinstance(details, dict)
    assert details["user_visible"] is True
    assert details["source_notice_i18n"] == {
        "sk": "JurisDigta MCP server bol kontaktovaný na získanie najnovších právnych informácií.",
        "de": "Der JurisDigta MCP-Server wurde kontaktiert, um aktuelle Rechtsinformationen abzurufen.",
        "en": "JurisDigta MCP Server was contacted to retrieve the latest legal information.",
    }


def test_mcp_law_context_uses_latest_sort_for_latest_law_question(monkeypatch) -> None:
    from app.chat.mcp_law_context import build_mcp_law_context

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((name, arguments))
        if name == "searchLaws":
            return {
                "results": [
                    {
                        "document_id": "doc-136-2026",
                        "law_identifier_text": "136/2026 Z. z.",
                        "title": "Zakon o testovacom najnovsom predpise",
                        "source_url": "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/136/",
                    }
                ]
            }
        if name == "getLawText":
            return {
                "document_id": arguments["document_id"],
                "law_identifier_text": "136/2026 Z. z.",
                "title": "Zakon o testovacom najnovsom predpise",
                "content_text": "Uvodne ustanovenia najnovsieho predpisu.",
            }
        raise AssertionError(name)

    monkeypatch.setattr("app.chat.mcp_law_context._call_mcp_tool", fake_call_tool)

    context = build_mcp_law_context(
        query="Daj mi posledny zakon v systeme?",
        country="SK",
        language="sk-SK",
    )

    assert context is not None
    assert calls[0] == (
        "searchLaws",
        {"query": "zakon", "country_code": "SK", "limit": 1, "sort": "latest"},
    )
    assert calls[1][0] == "getLawText"
    assert calls[1][1]["document_id"] == "doc-136-2026"
    assert "latest law in the JurisDigta system" in context.prompt_note
    assert "Do not show raw MCP JSON" in context.prompt_note
    assert "136/2026 Z. z." in context.prompt_note


def test_mcp_law_context_uses_combined_legal_sources_for_court_decision_query(monkeypatch) -> None:
    from app.chat.mcp_law_context import build_mcp_law_context

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((name, arguments))
        if name == "searchLegalSources":
            return {
                "laws": [],
                "court_decisions": [
                    {
                        "decision_id": f"decision-{index}",
                        "court_name": "Najvyssi sud SR",
                        "file_number": f"{index}Cdo/{2020 + index}",
                        "issue_date": f"{2020 + index}-03-01",
                        "source_url": f"https://obcan.justice.sk/infosud/-/detail/decision-{index}",
                        "score": 0.99 - index / 100,
                    }
                    for index in range(1, 6)
                ],
            }
        raise AssertionError(name)

    monkeypatch.setattr("app.chat.mcp_law_context._call_mcp_tool", fake_call_tool)

    context = build_mcp_law_context(
        query="Daj mi top 5 sudnych rozhodnuti ohladom podnajmu?",
        country="SK",
        language="sk-SK",
    )

    assert context is not None
    assert calls == [
        (
            "searchLegalSources",
            {
                "query": "Daj mi top 5 sudnych rozhodnuti ohladom podnajmu?",
                "country_code": "SK",
                "source_types": ["laws", "court_decisions"],
                "limit_per_source": 5,
            },
        )
    ]
    assert "MCP court-decision results" in context.prompt_note
    assert context.prompt_note.count("Najvyssi sud SR") == 5
    details = context.processing_event["details"]
    assert isinstance(details, dict)
    assert details["source_origin"] == "system_vector_db"
    assert details["court_decision_count"] == 5
    citations = details["citations"]
    assert isinstance(citations, list)
    assert len(citations) == 5
    assert citations[0]["source_type"] == "court_decision"
    assert citations[0]["decision_date"] == "2021-03-01"
    assert citations[0]["retrieval_tool"] == "JurisDigta MCP searchCourtDecisions"


def test_mcp_law_context_extracts_poprad_and_latest_from_typo_question(monkeypatch) -> None:
    from app.chat.mcp_law_context import build_mcp_law_context

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((name, arguments))
        return {
            "laws": [],
            "court_decisions": [
                {
                    "decision_id": "poprad-1",
                    "court_name": "Okresny sud Poprad",
                    "file_number": "20C/444/2012",
                    "issue_date": "31.12.2012",
                    "source_url": "https://example.test/poprad-1",
                }
            ],
        }

    monkeypatch.setattr("app.chat.mcp_law_context._call_mcp_tool", fake_call_tool)
    context = build_mcp_law_context(
        query="daj mi posledne sudne rozdhodnuties s okresneho sudu Poprad",
        country="SK",
        language="sk-SK",
    )

    assert context is not None
    assert calls[0][0] == "searchLegalSources"
    assert calls[0][1]["court_name"] == "Okresny sud Poprad"
    assert calls[0][1]["sort"] == "latest"


def test_mcp_law_context_blocks_web_fallback_without_user_approval(monkeypatch) -> None:
    from app.chat.mcp_law_context import build_mcp_law_context

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        assert name == "searchLegalSources"
        return {"laws": [], "court_decisions": []}

    monkeypatch.setattr("app.chat.mcp_law_context._call_mcp_tool", fake_call_tool)
    monkeypatch.setattr(
        "app.chat.mcp_law_context.AIWebSearchAgent",
        lambda: SimpleNamespace(
            search=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected web search"))
        ),
    )

    context = build_mcp_law_context(
        query="Daj mi top 5 sudnych rozhodnuti ohladom podnajmu?",
        country="SK",
        language="sk-SK",
    )

    assert context is not None
    assert "AIWebSearchAgent internet fallback was not used" in context.prompt_note
    details = context.processing_event["details"]
    assert isinstance(details, dict)
    assert details["source_origin"] == "system_vector_db"
    assert details["web_search_status"] == "blocked_pending_user_approval"
    assert details["web_search_approval_required"] is True


def test_mcp_law_context_warns_when_approved_official_web_fallback_is_used(monkeypatch) -> None:
    from app.chat.mcp_law_context import build_mcp_law_context

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        assert name == "searchLegalSources"
        return {"laws": [], "court_decisions": []}

    monkeypatch.setattr("app.chat.mcp_law_context._call_mcp_tool", fake_call_tool)
    monkeypatch.setattr(
        "app.chat.mcp_law_context.AIWebSearchAgent",
        lambda: SimpleNamespace(
            search=lambda **_kwargs: [
                SimpleNamespace(
                    title="Rozhodnutie o podnajme",
                    url="https://obcan.justice.sk/infosud/-/detail/fallback-decision",
                    snippet="Oficialny zdroj sudneho rozhodnutia.",
                ),
                SimpleNamespace(
                    title="Neoficialny blog",
                    url="https://example.com/blog",
                    snippet="Ignored unofficial source.",
                ),
            ]
        ),
    )

    context = build_mcp_law_context(
        query="Daj mi top 5 sudnych rozhodnuti ohladom podnajmu?",
        country="SK",
        language="sk-SK",
        web_search_approved=True,
    )

    assert context is not None
    assert "OFFICIAL WEB FALLBACK RESULTS" in context.prompt_note
    assert "not from JurisDigta system vector DB" in context.prompt_note
    details = context.processing_event["details"]
    assert isinstance(details, dict)
    assert details["source_origin"] == "official_web_fallback"
    assert details["warning_required"] is True
    citations = details["citations"]
    assert isinstance(citations, list)
    assert len(citations) == 1
    assert citations[0]["source_type"] == "web"
    assert citations[0]["retrieval_tool"] == "AIWebSearchAgent official web fallback"
    assert citations[0]["relevance_score"] == 0.9


def test_mcp_law_context_prefers_remote_mcp_endpoint(monkeypatch) -> None:
    from app.chat.mcp_law_context import build_mcp_law_context

    requests: list[dict[str, object]] = []

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            request = requests[-1]
            params = request["json"]["params"]  # type: ignore[index]
            name = params["name"]  # type: ignore[index]
            if name == "searchLaws":
                text = json.dumps(
                    {
                        "results": [
                            {
                                "document_id": "doc-40-1964",
                                "law_identifier_text": "40/1964 Zb.",
                                "title": "Obciansky zakonnik",
                            }
                        ]
                    }
                )
            else:
                text = json.dumps(
                    {
                        "document_id": "doc-40-1964",
                        "law_identifier_text": "40/1964 Zb.",
                        "title": "Obciansky zakonnik",
                        "content_text": "§ 588 text",
                    }
                )
            return {"result": {"content": [{"type": "text", "text": text}]}}

    class _FakeClient:
        def __init__(self, timeout: float) -> None:
            assert timeout == 10.0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
            requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse()

    monkeypatch.setenv("INTERNAL_MCP_BASE_URL", "http://jurisdigta-mcp:8070")
    monkeypatch.setenv("MCP_API_JWT_SECRET", "internal-mcp-secret")
    monkeypatch.setattr("app.chat.mcp_law_context.httpx.Client", _FakeClient)
    monkeypatch.setattr(
        "app.mcp_api._call_tool",
        lambda name, arguments: (_ for _ in ()).throw(AssertionError("unexpected in-process MCP call")),
    )

    context = build_mcp_law_context(
        query="Co hovori zakon 40/1964 o kupnej zmluve?",
        country="SK",
        language="sk-SK",
    )

    assert context is not None
    assert [request["url"] for request in requests] == [
        "http://jurisdigta-mcp:8070/mcp",
        "http://jurisdigta-mcp:8070/mcp",
    ]
    assert "§ 588 text" in context.prompt_note

def test_free_plan_latest_law_question_gets_mcp_context_before_ollama_prompt(monkeypatch) -> None:
    from app.chat.mcp_law_context import build_mcp_law_context
    from app.chat.models import Session
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    repository = InMemoryChatRepository()
    session = repository.create_session(Session(country="SK", language="sk-SK", discussion_type="advice"))
    captured_prompts: list[str] = []
    captured_document_paths: list[str] = []
    calls: list[tuple[str, dict[str, object]]] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            captured_document_paths.extend(document.path for document in documents)
            return SimpleNamespace(
                content=(
                    "Najnovsi zakon v systeme je 136/2026 Z. z. - Zakon o testovacom najnovsom predpise.\n"
                    'CASE_UPDATE_JSON: {"case":{"status":"intake_open",'
                    '"jurisdiction":{"country":"SK","language":"sk-SK"},'
                    '"facts_summary":"Najnovsi zakon v systeme","client_goal":"Zistit najnovsi zakon",'
                    '"open_questions":[]}}'
                ),
                agent_name="LawyerSlovakia",
            )

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((name, arguments))
        if name == "searchLaws":
            return {
                "results": [
                    {
                        "document_id": "doc-136-2026",
                        "law_identifier_text": "136/2026 Z. z.",
                        "title": "Zakon o testovacom najnovsom predpise",
                    }
                ]
            }
        if name == "getLawText":
            return {
                "document_id": arguments["document_id"],
                "law_identifier_text": "136/2026 Z. z.",
                "title": "Zakon o testovacom najnovsom predpise",
                "content_text": "Uvodne ustanovenia.",
            }
        raise AssertionError(name)

    monkeypatch.setattr(chat_api, "_repository", repository)
    monkeypatch.setattr(chat_api, "_warn_if_flow_pack_missing", lambda **_kwargs: None)
    monkeypatch.setattr(
        chat_api,
        "prepare_country_direct_reply",
        lambda **_kwargs: SimpleNamespace(
            direct_reply=None,
            prompt_note="",
            supplemental_documents=[],
            processing_events=[],
        ),
    )
    monkeypatch.setattr(
        chat_api,
        "_resolve_session_llm_route",
        lambda **_kwargs: SimpleNamespace(client=object(), route_type="free_local", provider="local_ollama"),
    )
    monkeypatch.setattr("aijurisdictionagents.agents.create_lawyer_agent", lambda llm, country: _SpyLawyer())
    monkeypatch.setattr(chat_api, "build_mcp_law_context", build_mcp_law_context)
    monkeypatch.setattr("app.chat.mcp_law_context._call_mcp_tool", fake_call_tool)

    _user, lawyer, visible, events, route = chat_api._run_direct_lawyer_turn(
        session_id=session.id,
        session=session,
        content="Daj mi posledny zakon v systeme?",
    )

    assert route is not None
    assert route.route_type == "free_local"
    assert route.provider == "local_ollama"
    assert lawyer.agent_name == "LawyerSlovakia"
    assert "Najnovsi zakon v systeme je 136/2026 Z. z." in visible
    assert calls[0] == (
        "searchLaws",
        {"query": "zakon", "country_code": "SK", "limit": 1, "sort": "latest"},
    )
    assert "INTERNAL MCP LAW TOOL CONTEXT" in captured_prompts[-1]
    assert "Do not show raw MCP JSON" in captured_prompts[-1]
    assert "internal-mcp-law-context.txt" in captured_document_paths
    assert any(event.get("stage") == "mcp_law_context" for event in events)


def test_mcp_status_context_calls_version_and_statistics_for_slovak_status_query(monkeypatch) -> None:
    from app.chat.mcp_status_context import build_mcp_status_context

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((name, arguments))
        if name == "getVersion":
            return {"mcp_server_version": "1.0.260512", "api_version": "1.0.260512"}
        if name == "getStatistics":
            return {
                "country_code": "SK",
                "processed_laws_count": 1245,
                "jurisdictions": ["SK"],
            }
        raise AssertionError(name)

    monkeypatch.setattr("app.chat.mcp_status_context._call_mcp_tool", fake_call_tool)

    context = build_mcp_status_context(
        query="Daj mi verziu  mcp servra a pocej importovancnych zakonou a jurisdikcii?",
        country="SK",
        language="sk-SK",
    )

    assert context is not None
    assert calls == [("getVersion", {}), ("getStatistics", {"country_code": "SK"})]
    assert "INTERNAL MCP STATUS CONTEXT" in context.prompt_note
    assert "getVersion" in context.prompt_note
    assert "getStatistics" in context.prompt_note
    assert "1.0.260512" in context.prompt_note
    assert "1245" in context.prompt_note
    assert context.document is not None
    assert context.document.path == "internal-mcp-status-context.json"
    details = context.processing_event["details"]
    assert isinstance(details, dict)
    assert details["tool_calls"] == ["getVersion", "getStatistics"]
    assert details["source_origin"] == "jurisdigta_mcp"


def test_mcp_status_context_handles_imported_laws_count_without_mcp_keyword(monkeypatch) -> None:
    from app.chat.mcp_status_context import build_mcp_status_context

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((name, arguments))
        if name == "getVersion":
            return {"mcp_server_version": "1.0.260512"}
        if name == "getStatistics":
            return {"country_code": "SK", "processed_laws_count": 1245, "jurisdictions": ["SK"]}
        raise AssertionError(name)

    monkeypatch.setattr("app.chat.mcp_status_context._call_mcp_tool", fake_call_tool)

    context = build_mcp_status_context(
        query="Koľko zákonov ma systém importovaných",
        country="SK",
        language="sk",
    )

    assert context is not None
    assert calls == [("getVersion", {}), ("getStatistics", {"country_code": "SK"})]
    assert "1245" in context.prompt_note
    assert "Koľko zákonov ma systém importovaných" in context.prompt_note


def test_free_plan_status_count_reply_uses_mcp_statistics_before_ollama(monkeypatch) -> None:
    from app.chat.models import Session
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    repository = InMemoryChatRepository()
    session = repository.create_session(Session(country="SK", language="sk-SK", discussion_type="advice"))
    captured_events: list[dict[str, object]] = []
    calls: list[tuple[str, dict[str, object]]] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            raise AssertionError("free status count should not call local LLM")

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((name, arguments))
        if name == "getVersion":
            return {"mcp_server_version": "1.0.260512", "api_version": "1.0.260512"}
        if name == "getStatistics":
            return {"country_code": "SK", "processed_laws_count": 1245, "jurisdictions": ["SK"]}
        raise AssertionError(name)

    monkeypatch.setattr(chat_api, "_repository", repository)
    monkeypatch.setattr(chat_api, "_warn_if_flow_pack_missing", lambda **_kwargs: None)
    monkeypatch.setattr(
        chat_api,
        "prepare_country_direct_reply",
        lambda **_kwargs: SimpleNamespace(
            direct_reply=None,
            prompt_note="",
            supplemental_documents=[],
            processing_events=[],
        ),
    )
    monkeypatch.setattr(
        chat_api,
        "_resolve_session_llm_route",
        lambda **_kwargs: SimpleNamespace(client=object(), route_type="free_local", provider="local_ollama"),
    )
    monkeypatch.setattr("aijurisdictionagents.agents.create_lawyer_agent", lambda llm, country: _SpyLawyer())
    monkeypatch.setattr("app.chat.mcp_status_context._call_mcp_tool", fake_call_tool)
    monkeypatch.setattr(chat_api, "build_mcp_law_context", lambda **_kwargs: None)

    _user, lawyer, visible, events, route = chat_api._run_direct_lawyer_turn(
        session_id=session.id,
        session=session,
        content="Daj mi verziu  mcp servra a pocej importovancnych zakonou a jurisdikcii?",
        processing_event_callback=captured_events.append,
    )

    assert route is not None
    assert route.route_type == "free_local"
    assert route.provider == "local_ollama"
    assert calls == [("getVersion", {}), ("getStatistics", {"country_code": "SK"})]
    assert lawyer.agent_name == "Assistant"
    assert visible == "Systém má importovaných celkovo 1 245 zákonov."
    assert any(event.get("stage") == "mcp_status_context" for event in captured_events)
    assert any(event.get("stage") == "mcp_status_context" for event in events)


def test_mcp_law_context_skips_non_slovak_non_legal_turn(monkeypatch) -> None:
    from app.chat.mcp_law_context import build_mcp_law_context

    monkeypatch.setattr(
        "app.mcp_api._call_tool",
        lambda name, arguments: (_ for _ in ()).throw(AssertionError("unexpected MCP call")),
    )

    context = build_mcp_law_context(
        query="Write a short greeting.",
        country="US",
        language="en-US",
    )

    assert context is None


def test_mcp_law_context_retrieves_for_legal_document_drafting_turn(monkeypatch) -> None:
    from app.chat.mcp_law_context import build_mcp_law_context

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((name, arguments))
        if name == "searchLaws":
            return {
                "results": [
                    {
                        "document_id": "doc-513-1991",
                        "law_identifier_text": "513/1991 Zb.",
                        "title": "Obchodny zakonnik",
                    }
                ]
            }
        if name == "getLawText":
            return {
                "document_id": arguments["document_id"],
                "law_identifier_text": "513/1991 Zb.",
                "title": "Obchodny zakonnik",
                "content_text": "Uprava obchodnych spolocnosti a obchodneho podielu.",
            }
        raise AssertionError(name)

    monkeypatch.setattr("app.chat.mcp_law_context._call_mcp_tool", fake_call_tool)

    context = build_mcp_law_context(
        query="Priprav mi vsetky dokumenty na prevod obchodneho podielu.",
        country="SK",
        language="sk-SK",
    )

    assert context is not None
    assert calls[0][0] == "searchLaws"
    assert calls[0][1]["country_code"] == "SK"
    assert calls[1][0] == "getLawText"
    assert "INTERNAL MCP LAW TOOL CONTEXT" in context.prompt_note
    assert "513/1991 Zb." in context.prompt_note


def test_reply_endpoint_injects_internal_mcp_law_context_in_prompt_and_documents(monkeypatch) -> None:
    from aijurisdictionagents.schemas import Document as CoreDocument
    from app.chat.mcp_law_context import McpLawContext
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    captured_prompts: list[str] = []
    captured_document_paths: list[str] = []
    captured_events: list[dict[str, object]] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            captured_document_paths.extend(document.path for document in documents)
            return SimpleNamespace(content="MODEL_REPLY_WITH_LAW_CONTEXT", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())
    monkeypatch.setattr(chat_api, "_warn_if_flow_pack_missing", lambda **_kwargs: None)
    monkeypatch.setattr(
        chat_api,
        "prepare_country_direct_reply",
        lambda **_kwargs: SimpleNamespace(
            direct_reply=None,
            prompt_note="",
            supplemental_documents=[],
            processing_events=[],
        ),
    )
    monkeypatch.setattr(
        chat_api,
        "build_mcp_law_context",
        lambda **_kwargs: McpLawContext(
            prompt_note="INTERNAL MCP LAW TOOL CONTEXT:\n- cite 40/1964 Zb.",
            document=CoreDocument(
                doc_id="internal-mcp-law-context",
                path="internal-mcp-law-context.txt",
                content="40/1964 Zb. § 588",
            ),
            processing_event={
                "stage": "mcp_law_context",
                "message": "MCP searched",
                "details": {"result_count": 1},
            },
        ),
    )
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

    _user, lawyer, visible, _events, _route = chat_api._run_direct_lawyer_turn(
        session_id=UUID(session_id),
        session=chat_api._repository.get_session(UUID(session_id)),
        content="Co hovori Obciansky zakonnik o kupnej zmluve?",
        processing_event_callback=captured_events.append,
    )

    assert lawyer.agent_name == "LawyerSlovakia"
    assert visible == "MODEL_REPLY_WITH_LAW_CONTEXT"
    assert captured_prompts
    assert "INTERNAL MCP LAW TOOL CONTEXT" in captured_prompts[-1]
    assert "40/1964 Zb." in captured_prompts[-1]
    assert "internal-mcp-law-context.txt" in captured_document_paths
    assert any(event.get("stage") == "mcp_law_context" for event in captured_events)


def test_free_local_reply_injects_internal_mcp_law_context_before_ollama_prompt(monkeypatch) -> None:
    from aijurisdictionagents.schemas import Document as CoreDocument
    from app.chat.mcp_law_context import McpLawContext
    from app.chat.models import Session
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    repository = InMemoryChatRepository()
    session = repository.create_session(Session(country="SK", language="sk-SK", discussion_type="advice"))
    captured_prompts: list[str] = []
    captured_document_paths: list[str] = []
    captured_events: list[dict[str, object]] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            captured_document_paths.extend(document.path for document in documents)
            return SimpleNamespace(content="FREE_LOCAL_MODEL_REPLY_WITH_MCP", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", repository)
    monkeypatch.setattr(chat_api, "_warn_if_flow_pack_missing", lambda **_kwargs: None)
    monkeypatch.setattr(
        chat_api,
        "prepare_country_direct_reply",
        lambda **_kwargs: SimpleNamespace(
            direct_reply=None,
            prompt_note="",
            supplemental_documents=[],
            processing_events=[],
        ),
    )
    monkeypatch.setattr(
        chat_api,
        "_resolve_session_llm_route",
        lambda **_kwargs: SimpleNamespace(client=object(), route_type="free_local", provider="local_ollama"),
    )
    monkeypatch.setattr(
        chat_api,
        "build_mcp_law_context",
        lambda **_kwargs: McpLawContext(
            prompt_note="INTERNAL MCP LAW TOOL CONTEXT:\n- cite 40/1964 Zb.",
            document=CoreDocument(
                doc_id="internal-mcp-law-context",
                path="internal-mcp-law-context.txt",
                content="40/1964 Zb. paragraf 588",
            ),
            processing_event={
                "stage": "mcp_law_context",
                "message": "MCP searched before local model",
                "details": {"tool_calls": ["searchLaws", "getLawText"], "result_count": 1},
            },
        ),
    )
    monkeypatch.setattr("aijurisdictionagents.agents.create_lawyer_agent", lambda llm, country: _SpyLawyer())

    _user, lawyer, visible, events, route = chat_api._run_direct_lawyer_turn(
        session_id=session.id,
        session=session,
        content="Co hovori Obciansky zakonnik o kupnej zmluve?",
        processing_event_callback=captured_events.append,
    )

    assert route is not None
    assert route.route_type == "free_local"
    assert route.provider == "local_ollama"
    assert lawyer.agent_name == "LawyerSlovakia"
    assert visible == "FREE_LOCAL_MODEL_REPLY_WITH_MCP"
    assert captured_prompts
    assert "JurisDigta Assistant, a Slovak legal intake assistant for free-plan local model routing" in captured_prompts[-1]
    assert "INTERNAL MCP LAW TOOL CONTEXT" in captured_prompts[-1]
    assert "40/1964 Zb." in captured_prompts[-1]
    assert "internal-mcp-law-context.txt" in captured_document_paths
    assert any(event.get("stage") == "mcp_law_context" for event in captured_events)
    assert any(event.get("stage") == "mcp_law_context" for event in events)


def test_uploaded_documents_contract_request_requires_extract_then_confirm_prompt(monkeypatch) -> None:
    from aijurisdictionagents.schemas import Document as CoreDocument
    from app.chat.mcp_law_context import McpLawContext
    from app.chat.models import Session
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    repository = InMemoryChatRepository()
    captured_prompts: list[str] = []
    captured_document_paths: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            captured_document_paths.extend(document.path for document in documents)
            return SimpleNamespace(content="MODEL_CONFIRM_EXTRACTED_DATA_REPLY", agent_name="LawyerSlovakia")

    monkeypatch.setattr(chat_api, "_repository", repository)
    monkeypatch.setattr(chat_api, "_warn_if_flow_pack_missing", lambda **_kwargs: None)
    monkeypatch.setattr(
        chat_api,
        "get_document_template_store",
        lambda: SimpleNamespace(find_best_match=lambda **_kwargs: (0, None)),
    )
    monkeypatch.setattr(
        chat_api,
        "prepare_country_direct_reply",
        lambda **_kwargs: SimpleNamespace(
            direct_reply=None,
            prompt_note="",
            supplemental_documents=[],
            processing_events=[],
        ),
    )
    monkeypatch.setattr(
        "aijurisdictionagents.agents.create_lawyer_agent",
        lambda llm, country: _SpyLawyer(),
    )
    monkeypatch.setattr(
        chat_api,
        "build_mcp_law_context",
        lambda **_kwargs: McpLawContext(
            prompt_note="INTERNAL MCP LAW TOOL CONTEXT:\n- cite 40/1964 Zb. before drafting lease.",
            document=CoreDocument(
                doc_id="internal-mcp-law-context",
                path="internal-mcp-law-context.txt",
                content="40/1964 Zb. najomna zmluva",
            ),
            processing_event={
                "stage": "mcp_law_context",
                "message": "MCP searched before legal-document intake",
                "details": {"tool_calls": ["searchLaws", "getLawText"], "result_count": 1},
            },
        ),
    )
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    session = repository.create_session(Session(country="SK", language="SK", discussion_type="advice"))

    _user, lawyer, visible, events, _route = chat_api._run_direct_lawyer_turn(
        session_id=session.id,
        session=session,
        content="Priprav novu najomnu zmluvu z prilozenych dokumentov.",
        supplemental_documents=[
            CoreDocument(
                doc_id="lease-source",
                path="podklady-najom.txt",
                content=(
                    "Prenajimatel: Jana Novotna. Najomca: Tomas Hlavaty. "
                    "Byt: Dunajska 12, Bratislava. Najomne: 850 EUR."
                ),
            )
        ],
    )

    assert visible == "MODEL_CONFIRM_EXTRACTED_DATA_REPLY"
    assert lawyer.agent_name == "LawyerSlovakia"
    assert any(event.get("stage") == "mcp_law_context" for event in events)
    assert captured_document_paths == ["podklady-najom.txt", "internal-mcp-law-context.txt"]
    assert captured_prompts
    prompt = captured_prompts[-1]
    assert "UPLOADED DOCUMENT CONTRACT INTAKE MODE" in prompt
    assert "INTERNAL MCP LAW TOOL CONTEXT" in prompt
    assert "review every available uploaded document" in prompt
    assert "Udaje, ktore som nasiel v dokumentoch" in prompt
    assert "Suhlasite, aby som zmluvu pripravil z tychto udajov" in prompt
    assert "Do not generate or export the final contract until the user confirms" in prompt


def test_legal_document_preparation_policy_requires_separate_outputs_and_web_source(monkeypatch) -> None:
    import app.chat.api as chat_api

    monkeypatch.setattr(
        chat_api,
        "get_document_template_store",
        lambda: SimpleNamespace(find_best_match=lambda **_kwargs: (0, None)),
    )

    note = chat_api._build_legal_document_preparation_policy_note(
        content="Priprav splnomocnenie v slovenskej a anglickej verzii z CSV so 100 splnomocnencami.",
        country="SK",
    )

    assert "LEGAL DOCUMENT PREPARATION MODE" in note
    assert "multiple languages" in note
    assert "separate final document" in note
    assert "100 separate PDF documents" in note
    assert "case.documents entry" in note
    assert "AIWebSearchAgent" in note
    assert "include the URL/title/location" in note


def test_legal_document_preparation_policy_includes_managed_template_source(monkeypatch) -> None:
    import app.chat.api as chat_api

    template = SimpleNamespace(
        title="Splnomocnenie",
        template_key="sk.civil.power_of_attorney",
        source_url="https://example.test/templates/splnomocnenie",
        body="",
    )
    monkeypatch.setattr(
        chat_api,
        "get_document_template_store",
        lambda: SimpleNamespace(find_best_match=lambda **_kwargs: (7, template)),
    )

    note = chat_api._build_legal_document_preparation_policy_note(
        content="Priprav splnomocnenie na pouzivanie firemneho auta.",
        country="SK",
    )

    assert "Managed template match: Splnomocnenie (sk.civil.power_of_attorney), score 7." in note
    assert "Managed template source location: https://example.test/templates/splnomocnenie." in note
    assert "metadata/source only and no stored body" in note
    assert "AIWebSearchAgent" in note


def test_uploaded_document_contract_confirmation_note_ignores_review_only_request() -> None:
    from aijurisdictionagents.schemas import Document as CoreDocument
    from app.chat.api import _build_uploaded_document_contract_confirmation_note

    note = _build_uploaded_document_contract_confirmation_note(
        content="Pozri zmluvu a zhrn rizika.",
        documents=[CoreDocument(doc_id="doc-1", path="zmluva.txt", content="Text zmluvy")],
    )

    assert note == ""


def test_lawyer_output_validation_removes_profile_missing_message_when_profile_complete() -> None:
    from app.chat.output_validation import AILawyerOutputMessageValidationAgent, LawyerOutputUserProfile

    content = (
        "Zmluva je pripravená.\n\n"
        "**Chýbajúce informácie / dokumenty:**\n"
        "- Vaše meno a adresa\n\n"
        "**Riziká / slabé miesta:**\n"
        "- Skontrolovať podpisy.\n\n"
        "CASE_UPDATE_JSON:\n{\"case\": {}}"
    )

    validated = AILawyerOutputMessageValidationAgent().validate(
        content=content,
        user_profile=LawyerOutputUserProfile(has_full_name=True, has_address=True),
    )

    visible = _canonical_text(validated)
    assert "vase meno a adresa" not in visible
    assert "chybajuce informacie / dokumenty" not in visible
    assert "rizika / slabe miesta" in visible
    assert "case_update_json" in visible


def test_lawyer_output_validation_tells_user_to_update_profile_when_missing() -> None:
    from app.chat.output_validation import AILawyerOutputMessageValidationAgent, LawyerOutputUserProfile

    content = (
        "Zmluva je pripravená.\n\n"
        "**Chýbajúce informácie / dokumenty:**\n"
        "- Vaše meno a adresa\n"
    )

    validated = AILawyerOutputMessageValidationAgent().validate(
        content=content,
        user_profile=LawyerOutputUserProfile(has_full_name=True, has_address=False),
    )

    visible = _canonical_text(validated)
    assert "chyba adresu" in visible
    assert "profile" in visible
    assert "vase meno a adresa" not in visible


def test_session_documents_email_uses_profile_email_after_confirmation(monkeypatch, tmp_path: Path) -> None:
    from app.chat.models import Message, MessageRole, Session, SessionResult
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api
    from aijurisdictionagents.api_db import ApiDatabaseStore

    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))
    monkeypatch.setenv("EMAIL_DB_OPTION", "local")
    monkeypatch.setenv("EMAIL_DB_LOCAL", str(tmp_path / "email.sqlite3"))
    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())

    store = ApiDatabaseStore.from_env()
    store.initialize()
    user = store.create_user(
        email="client@example.com",
        password="secret",
        phone_number="+421900123456",
        full_name="Marek Matonok",
        address="Partizanska 665",
        city="Spisske Bystre",
        zip_code="059 18",
        country="SK",
    )
    case = store.create_case(user_id=user.user_id, company_id=None, title="Najomna zmluva")
    session = chat_api._repository.create_session(
        Session(user_id=UUID(user.user_id), case_id=case.case_id, country="SK", language="SK")
    )
    chat_api._repository.add_message(
        Message(
            session_id=session.id,
            role=MessageRole.USER,
            agent_name="User",
            content="Priprav zmluvu o prenajme a potom ju posli emailom.",
        )
    )
    chat_api._repository.add_message(
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "**Zmluva o prenájme**\n"
                "Prenajímateľ: [Vaše meno a adresa]\n"
                "Podnájomník: John Kennedy, Washington, D.C., USA\n"
                "Adresa nehnuteľnosti: Bratislava, Slavin, Pod Radom 1234\n"
                "Mesačné nájomné: 5000 EUR"
            ),
        )
    )
    chat_api._repository.set_result(
        session.id,
        SessionResult(
            final_recommendation="Dokument je pripraveny.",
            judge_rationale="Direct lawyer reply prepared for session export.",
            metadata={"document_ready": True},
        ),
    )

    confirmation = client.post(
        f"/v1/chat/sessions/{session.id}/documents/send-email",
        headers=AUTH_HEADERS,
        json={},
    )
    assert confirmation.status_code == 200
    assert confirmation.json()["needs_confirmation"] is True
    assert confirmation.json()["recipient"] == "client@example.com"

    sent = client.post(
        f"/v1/chat/sessions/{session.id}/documents/send-email",
        headers=AUTH_HEADERS,
        json={"confirmed": True},
    )
    assert sent.status_code == 200
    payload = sent.json()
    assert payload["needs_confirmation"] is False
    assert payload["recipient"] == "client@example.com"
    assert payload["attachment_count"] >= 1

    with sqlite3.connect(tmp_path / "email.sqlite3") as conn:
        row = conn.execute(
            "SELECT recipient, subject, metadata_json FROM email_outbox ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row[0] == "client@example.com"
    assert "JurisDigta dokumenty" in row[1]
    metadata = json.loads(row[2])
    attachments = metadata["attachments"]
    assert attachments
    assert base64.b64decode(attachments[0]["content_base64"]).startswith(b"%PDF")


def test_chat_document_email_flow_confirms_before_queueing(monkeypatch, tmp_path: Path) -> None:
    from app.chat.models import Message, MessageRole, Session, SessionResult
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api
    from aijurisdictionagents.api_db import ApiDatabaseStore

    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))
    monkeypatch.setenv("EMAIL_DB_OPTION", "local")
    monkeypatch.setenv("EMAIL_DB_LOCAL", str(tmp_path / "email.sqlite3"))
    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())

    store = ApiDatabaseStore.from_env()
    store.initialize()
    user = store.create_user(email="flow@example.com", password="secret", phone_number="+421900000111")
    case = store.create_case(user_id=user.user_id, company_id=None, title="Email flow")
    session = chat_api._repository.create_session(
        Session(user_id=UUID(user.user_id), case_id=case.case_id, country="SK", language="SK")
    )
    previous = [
        chat_api._repository.add_message(
            Message(
                session_id=session.id,
                role=MessageRole.ASSISTANT,
                agent_name="LawyerSlovakia",
                content="**Zmluva o prenájme**\nPodnájomník: John Kennedy\nAdresa nehnuteľnosti: Bratislava",
            )
        )
    ]
    chat_api._repository.set_result(
        session.id,
        SessionResult(
            final_recommendation="Dokument je pripraveny.",
            judge_rationale="Direct lawyer reply prepared for session export.",
            metadata={"document_ready": True},
        ),
    )

    first_reply = chat_api._handle_document_email_flow(
        session_id=session.id,
        session=session,
        content="Chcem poslat dokumenty emailom",
        previous_messages=previous,
    )
    assert "flow@example.com" in first_reply
    assert "Potvrdte odoslanie" in first_reply

    confirmation_message = chat_api._repository.add_message(
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerEmail",
            content=first_reply,
        )
    )
    second_reply = chat_api._handle_document_email_flow(
        session_id=session.id,
        session=session,
        content="ano",
        previous_messages=[*previous, confirmation_message],
    )
    assert "Dokumenty boli zaradene na odoslanie" in second_reply
    with sqlite3.connect(tmp_path / "email.sqlite3") as conn:
        count = conn.execute("SELECT COUNT(*) FROM email_outbox WHERE recipient='flow@example.com'").fetchone()[0]
    assert count == 1


def test_chat_document_email_flow_confirms_explicit_recipient_from_initial_request(
    monkeypatch, tmp_path: Path
) -> None:
    from app.chat.models import Message, MessageRole, Session, SessionResult
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api
    from aijurisdictionagents.api_db import ApiDatabaseStore

    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))
    monkeypatch.setenv("EMAIL_DB_OPTION", "local")
    monkeypatch.setenv("EMAIL_DB_LOCAL", str(tmp_path / "email.sqlite3"))
    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())

    store = ApiDatabaseStore.from_env()
    store.initialize()
    user = store.create_user(email="simulator.case@example.com", password="secret", phone_number="+421900000333")
    case = store.create_case(user_id=user.user_id, company_id=None, title="Explicit email flow")
    session = chat_api._repository.create_session(
        Session(user_id=UUID(user.user_id), case_id=case.case_id, country="SK", language="SK")
    )
    previous = [
        chat_api._repository.add_message(
            Message(
                session_id=session.id,
                role=MessageRole.ASSISTANT,
                agent_name="LawyerSlovakia",
                content="**Zmluva o prenÃ¡jme**\nPodnÃ¡jomnÃ­k: John Kennedy\nAdresa nehnuteÄ¾nosti: Bratislava",
            )
        )
    ]
    chat_api._repository.set_result(
        session.id,
        SessionResult(
            final_recommendation="Dokument je pripraveny.",
            judge_rationale="Direct lawyer reply prepared for session export.",
            metadata={"document_ready": True},
        ),
    )

    reply = chat_api._handle_document_email_flow(
        session_id=session.id,
        session=session,
        content="send document by email to matonok@hotmail.com",
        previous_messages=previous,
    )

    assert "matonok@hotmail.com" in reply
    assert "simulator.case@example.com" not in reply
    assert "Potvrdte odoslanie" in reply


def test_chat_document_email_flow_uses_corrected_recipient_before_queueing(
    monkeypatch, tmp_path: Path
) -> None:
    from app.chat.models import Message, MessageRole, Session, SessionResult
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api
    from aijurisdictionagents.api_db import ApiDatabaseStore

    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))
    monkeypatch.setenv("EMAIL_DB_OPTION", "local")
    monkeypatch.setenv("EMAIL_DB_LOCAL", str(tmp_path / "email.sqlite3"))
    monkeypatch.setattr(chat_api, "_repository", InMemoryChatRepository())

    store = ApiDatabaseStore.from_env()
    store.initialize()
    user = store.create_user(email="profile@example.com", password="secret", phone_number="+421900000222")
    case = store.create_case(user_id=user.user_id, company_id=None, title="Email correction flow")
    session = chat_api._repository.create_session(
        Session(user_id=UUID(user.user_id), case_id=case.case_id, country="SK", language="SK")
    )
    draft_message = chat_api._repository.add_message(
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content="**Zmluva o prenÃ¡jme**\nPodnÃ¡jomnÃ­k: John Kennedy\nAdresa nehnuteÄ¾nosti: Bratislava",
        )
    )
    chat_api._repository.set_result(
        session.id,
        SessionResult(
            final_recommendation="Dokument je pripraveny.",
            judge_rationale="Direct lawyer reply prepared for session export.",
            metadata={"document_ready": True},
        ),
    )

    first_reply = chat_api._handle_document_email_flow(
        session_id=session.id,
        session=session,
        content="Chcem poslat dokumenty emailom",
        previous_messages=[draft_message],
    )
    assert "profile@example.com" in first_reply
    confirmation_message = chat_api._repository.add_message(
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerEmail",
            content=first_reply,
        )
    )

    corrected_reply = chat_api._handle_document_email_flow(
        session_id=session.id,
        session=session,
        content="nie na matonok@hotmail.com",
        previous_messages=[draft_message, confirmation_message],
    )
    assert "matonok@hotmail.com" in corrected_reply
    assert "profile@example.com" not in corrected_reply
    assert "Potvrdte odoslanie" in corrected_reply
    corrected_confirmation = chat_api._repository.add_message(
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerEmail",
            content=corrected_reply,
        )
    )

    sent_reply = chat_api._handle_document_email_flow(
        session_id=session.id,
        session=session,
        content="ano",
        previous_messages=[draft_message, confirmation_message, corrected_confirmation],
    )
    assert "matonok@hotmail.com" in sent_reply
    assert "profile@example.com" not in sent_reply
    with sqlite3.connect(tmp_path / "email.sqlite3") as conn:
        recipients = [
            row[0]
            for row in conn.execute(
                "SELECT recipient FROM email_outbox ORDER BY created_at"
            ).fetchall()
        ]
    assert recipients == ["matonok@hotmail.com"]


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
    from app.chat.country_services import slovakia as slovakia_service
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

    monkeypatch.setattr(slovakia_service, "_ORSR_CACHE", {})
    monkeypatch.setattr(slovakia_service, "build_default_tool_registry", lambda: _FakeRegistry())

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
    followup_stages = [event.get("stage") for event in second_preparation.processing_events]
    assert "tool_cache" in followup_stages
    assert "tool_start" not in followup_stages
    assert "tool_result" not in followup_stages
    assert not any(
        "idem overit spolocnost" in str(event.get("message", "")).lower()
        for event in second_preparation.processing_events
    )
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


def test_prepare_slovakia_direct_reply_answers_tool_capability_question_without_model() -> None:
    from app.chat.country_services.slovakia import prepare_slovakia_direct_reply
    from app.chat.models import Session

    events: list[dict[str, object]] = []
    preparation = prepare_slovakia_direct_reply(
        session=Session(country="SK", language="sk-SK"),
        messages=[],
        current_content=(
            "Chcem vediet zoznam vsetkych tulsov ktore mozem pouzit ako "
            "overenie firmy v obchodnom registri, overenie auta a dalsie."
        ),
        prior_messages=[],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
        processing_event_callback=events.append,
    )

    assert preparation.prompt_note == ""
    assert preparation.supplemental_documents == []
    assert preparation.direct_reply is not None
    assert "obchodny_register_company_check" in preparation.direct_reply
    assert "slovakia_car_validate" in preparation.direct_reply
    assert "registeradries_address_validate" in preparation.direct_reply
    assert "Raw audio neuklad" in preparation.direct_reply
    assert events
    assert events[0]["stage"] == "tool_capabilities"


def test_slovak_company_query_removes_case_preposition_prefix() -> None:
    from app.chat.country_services.slovakia import _extract_slovak_company_query

    assert (
        _extract_slovak_company_query(
            messages=[],
            current_content=(
                "Vytvor potvrdenie na sumu 5000 EUR, splatne k 1.7.2028, "
                "na firmu Esolutions SK s.r.o."
            ),
        )
        == "Esolutions SK s.r.o."
    )


def test_slovak_company_query_handles_firmy_case_and_typo_prefix() -> None:
    from app.chat.country_services.slovakia import _extract_slovak_company_query

    assert (
        _extract_slovak_company_query(
            messages=[],
            current_content=(
                "chcem splnomocnenie pre dceru Emila Matonokova na vedenie firemneho "
                "motoroveho vozidla PP472DT fimy ESolutions SK s.r.o. od 1.7.2026 "
                "na dobu neurcitu."
            ),
        )
        == "ESolutions SK s.r.o."
    )
    assert (
        _extract_slovak_company_query(
            messages=[],
            current_content="splnomocnenie pre dceru Emila Matonokova na auto firmy ESolutions SK s.r.o.",
        )
        == "ESolutions SK s.r.o."
    )


def test_prepare_slovakia_vehicle_authorization_captures_user_facts_and_company_seat(monkeypatch) -> None:
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.country_services.slovakia import prepare_slovakia_direct_reply
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
                        "seat": "Partizanska 665, 059 18 Spisske Bystre",
                        "status": "Aktivna",
                    },
                ),
            )

    slovakia_service._ORSR_CACHE.clear()
    monkeypatch.setattr(slovakia_service, "build_default_tool_registry", lambda: _FakeRegistry())
    session = Session(country="SK", language="sk-SK")
    current_content = (
        "chcem splnomocnenie pre dceru Emila Matonokova na vedenie firemneho "
        "motoroveho vozidla PP472DT fimy ESolutions SK s.r.o. od 1.7.2026 "
        "na dobu neurcitu."
    )
    messages = [Message(session_id=session.id, role=MessageRole.USER, content=current_content)]
    events: list[dict[str, object]] = []

    preparation = prepare_slovakia_direct_reply(
        session=session,
        messages=messages,
        current_content=current_content,
        prior_messages=[],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
        processing_event_callback=events.append,
    )

    prompt_note = preparation.prompt_note
    assert "SLOVAK VEHICLE AUTHORIZATION INTAKE MODE" in prompt_note
    assert "authorized_person: Emila Matonokova" in prompt_note
    assert "principal_company: ESolutions SK s.r.o., ICO 46491261, Partizanska 665" in prompt_note
    assert "vehicle_registration_number: PP472DT" in prompt_note
    assert "effective_from: 1.7.2026" in prompt_note
    assert "duration: na dobu neurcitu" in prompt_note
    assert "do not ask again for the daughter's name" in prompt_note
    assert any(
        event.get("tool_name") == "obchodny_register_company_check"
        and "sidlo: Partizanska 665, 059 18 Spisske Bystre" in str(event.get("message"))
        for event in events
    )
    slovakia_service._ORSR_CACHE.clear()


def test_prepare_slovakia_vehicle_authorization_issue_428_uses_direct_document_reply(monkeypatch) -> None:
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.country_services.slovakia import prepare_slovakia_direct_reply
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
                        "seat": "Partizanska 665, 059 18 Spisske Bystre",
                        "status": "Aktivna",
                    },
                ),
            )

    slovakia_service._ORSR_CACHE.clear()
    monkeypatch.setattr(slovakia_service, "build_default_tool_registry", lambda: _FakeRegistry())
    session = Session(country="SK", language="sk")
    current_content = (
        "Priprav mi splnomocnenie na prevadzku motoroveho vozidla firmy ESolutions SK s.r.o. "
        "pre Janka Hraska, bytom testova 10, Poprad, slovensko od 1.7.2026 na neurcito. "
        "Priprav document v slovenskom a anglickom jazyku."
    )
    messages = [Message(session_id=session.id, role=MessageRole.USER, content=current_content)]
    events: list[dict[str, object]] = []

    preparation = prepare_slovakia_direct_reply(
        session=session,
        messages=messages,
        current_content=current_content,
        prior_messages=[],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
        processing_event_callback=events.append,
    )

    assert preparation.direct_reply is not None
    assert "Janka Hraska, adresa: testova 10, Poprad, slovensko" in preparation.direct_reply
    assert "ESolutions SK s.r.o., ICO 46491261, Partizanska 665" in preparation.direct_reply
    assert "1.7.2026" in preparation.direct_reply
    assert "Splnomocnenie (slovenska verzia)" in preparation.direct_reply
    assert "Power of Attorney (English version)" in preparation.direct_reply
    assert any(event.get("stage") == "document_ready" for event in events)
    slovakia_service._ORSR_CACHE.clear()


def test_prepare_slovakia_direct_reply_runs_orsr_for_plain_company_name(monkeypatch) -> None:
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.country_services.slovakia import prepare_slovakia_direct_reply
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
                        "seat": "Partizanska 665, 059 18 Spisske Bystre",
                        "status": "Aktivna",
                    },
                ),
            )

    monkeypatch.setattr(slovakia_service, "build_default_tool_registry", lambda: _FakeRegistry())
    session = Session(country="SK", language="sk-SK")
    current_content = "ESolutions SK s.r.o."
    messages = [Message(session_id=session.id, role=MessageRole.USER, content=current_content)]
    events: list[dict[str, object]] = []

    preparation = prepare_slovakia_direct_reply(
        session=session,
        messages=messages,
        current_content=current_content,
        prior_messages=[],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
        processing_event_callback=events.append,
    )

    assert "TOOL-FIRST COMPANY LOOKUP MODE" in preparation.prompt_note
    assert "Verified company name: ESolutions SK s.r.o." in preparation.prompt_note
    assert "Verified registration number: 46491261" in preparation.prompt_note
    assert any(event.get("tool_name") == "obchodny_register_company_check" for event in events)


def test_slovak_payment_confirmation_final_request_uses_tool_first_direct_reply(monkeypatch) -> None:
    from app.chat.country_services import slovakia as slovakia_service
    from app.chat.country_services.slovakia import prepare_slovakia_direct_reply
    from app.chat.models import Message, MessageRole, Session

    class _FakeRegistry:
        def list_definitions(self):
            return ()

        def run(self, name: str, **kwargs):
            if name == "obchodny_register_company_check":
                return SimpleNamespace(
                    ok=True,
                    records=(
                        {
                            "name": "ESolutions SK s.r.o.",
                            "registration_number": "46491261",
                            "seat": "Partizánska 665, 059 18 Spišské Bystré",
                            "status": "Aktívna",
                            "stakeholders": [],
                            "statutory_representatives": [],
                        },
                    ),
                    message="found",
                )
            return SimpleNamespace(ok=True, records=({"tool": name, "kwargs": kwargs},), message="ok")

    monkeypatch.setattr(slovakia_service, "build_default_tool_registry", lambda: _FakeRegistry())
    session = Session(country="SK", language="sk-SK")
    current_content = (
        "Vytvor potvrdenie o zaplatení na sumu 5000 EUR, splatné k 1.7.2028, "
        "na firmu Esolutions SK s.r.o., v zastúpení Marek Matonok, "
        "na splátku auta so SPZ PP472DT. Súhlasím s overením firmy, adresy firmy a auta. "
        "Vygeneruj PDF."
    )
    messages = [Message(session_id=session.id, role=MessageRole.USER, content=current_content)]
    events: list[dict[str, object]] = []

    preparation = prepare_slovakia_direct_reply(
        session=session,
        messages=messages,
        current_content=current_content,
        prior_messages=[],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
        processing_event_callback=events.append,
    )

    assert preparation.direct_reply is not None
    assert "Tu je konecna verzia dokumentu" in preparation.direct_reply
    assert "CASE_UPDATE_JSON" in preparation.direct_reply
    assert "ESolutions SK s.r.o." in preparation.direct_reply
    assert "PP472DT" in preparation.direct_reply
    assert any(event.get("tool_name") == "registeradries_address_validate" for event in events)
    assert any(event.get("tool_name") == "slovakia_car_validate" for event in events)


def test_slovak_private_loan_confirmation_first_turn_generates_document() -> None:
    import app.chat.api as chat_api
    from app.chat.country_services.slovakia import prepare_slovakia_direct_reply
    from app.chat.models import Message, MessageRole, Session

    session = Session(country="SK", language="sk-SK")
    current_content = (
        "Chcem pozicat peniaze na 1 rok a chcem nejake potvrdenie o tom ze som pozicala peniaze "
        "Jankovi hraskovi, adresa testova 10, Poprad, Slovensko, cislo obcianskeho: BA12345DR."
    )
    messages = [Message(session_id=session.id, role=MessageRole.USER, content=current_content)]

    preparation = prepare_slovakia_direct_reply(
        session=session,
        messages=messages,
        current_content=current_content,
        prior_messages=[],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
    )

    assert preparation.direct_reply is not None
    assert "Potvrdenie o pozicke" in preparation.direct_reply
    assert "Jankovi hraskovi" in preparation.direct_reply
    assert "BA12345DR" in preparation.direct_reply
    assert "Podpis poskytovatela pozicky" in preparation.direct_reply
    assert "Podpis dlznika" in preparation.direct_reply
    assert "CASE_UPDATE_JSON" in preparation.direct_reply

    case_update = chat_api._extract_case_update(preparation.direct_reply)
    drafts = chat_api._generated_case_document_drafts_from_case_update(
        case_update,
        timestamp="20260711T080000Z",
    )

    assert len(drafts) == 1
    assert drafts[0].filename == "potvrdenie_o_pozicke_20260711T080000Z.pdf"
    assert "Potvrdenie o pozicke" in drafts[0].body
    assert "Jankovi hraskovi" in drafts[0].body
    assert "BA12345DR" in drafts[0].body
    assert "CASE_UPDATE_JSON" not in drafts[0].body


def test_slovak_loan_agreement_followups_do_not_regenerate_payment_confirmation() -> None:
    from app.chat.country_services.slovakia import prepare_slovakia_direct_reply
    from app.chat.models import Message, MessageRole, Session

    session = Session(country="SK", language="sk-SK")
    initial_content = (
        "Priprav mi navrh Zmluvy o pozicke medzi fyzickymi osobami. "
        "Veritel: Jan Testovaci. Dlznik: Peter Vzorovy. Vyska pozicky: 8 000 EUR. "
        "Peniaze budu odovzdane bankovym prevodom 15. 8. 2026 a vratene 15. 8. 2027. "
        "Zmluva ma obsahovat potvrdenie jej prijatia."
    )
    initial_message = Message(session_id=session.id, role=MessageRole.USER, content=initial_content)

    initial_preparation = prepare_slovakia_direct_reply(
        session=session,
        messages=[initial_message],
        current_content=initial_content,
        prior_messages=[],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
    )

    assert initial_preparation.direct_reply is None

    prior_messages = [
        initial_message,
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=(
                "Tu je konecna verzia dokumentu - dokument je pripraveny na export a stiahnutie. "
                "Ktory konkretny chybajuci udaj mam potvrdit ako prvy?"
            ),
        ),
    ]
    followups = (
        "Ake su chybajuce udaje?",
        "daj mi zoznam chybajucich udajov?",
        "aky je nazov modelu ktory pouzivam?",
        "pouzivas lokalny mcp?",
    )

    for followup in followups:
        current_message = Message(session_id=session.id, role=MessageRole.USER, content=followup)
        preparation = prepare_slovakia_direct_reply(
            session=session,
            messages=[*prior_messages, current_message],
            current_content=followup,
            prior_messages=prior_messages,
            normalize_document_lines=lambda text: [text],
            extract_document_facts=lambda lines: {},
            current_turn_confirms_document_generation=lambda content, previous_messages: False,
            build_share_transfer_lines=lambda facts: [],
        )

        assert preparation.direct_reply is None, followup
        assert preparation.processing_events == []


def test_direct_assistant_persistence_requires_current_turn_document_authorization(monkeypatch) -> None:
    from app.chat import api as chat_api
    from app.chat.models import Message, Session

    session = Session(country="SK", language="sk-SK", case_id="case-591")
    persisted_documents: list[str] = []

    def fake_persist_generated_document(*, session: Session, content: str) -> list[str]:
        persisted_documents.append(content)
        return ["document-591"]

    monkeypatch.setattr(chat_api, "_persist_generated_case_document_if_needed", fake_persist_generated_document)
    monkeypatch.setattr(chat_api, "_persist_case_message_if_needed", lambda **kwargs: None)
    monkeypatch.setattr(chat_api._repository, "add_message", lambda message: message)

    reply = "Tu je historicky CASE_UPDATE_JSON s dokumentom, ale aktualny tah je otazka."
    persisted = chat_api._persist_direct_assistant_message(
        session_id=session.id,
        session=session,
        content=reply,
        agent_name="Assistant",
        allow_document_generation=False,
    )

    assert isinstance(persisted, Message)
    assert persisted_documents == []
    assert "Generated case document:" not in persisted.content


def test_runtime_questions_receive_direct_answers_without_model_or_document_generation(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.chat import api as chat_api

    route = SimpleNamespace(model="qwen3:1.7b", provider="local_ollama")
    assert chat_api._runtime_question_reply(
        content="Aky je nazov modelu ktory pouzivam?",
        route=route,
    ) == "V tomto chate používam model qwen3:1.7b cez poskytovateľa local_ollama."

    monkeypatch.delenv("INTERNAL_MCP_BASE_URL", raising=False)
    monkeypatch.delenv("MCP_PUBLIC_BASE_URL", raising=False)
    assert chat_api._runtime_question_reply(
        content="Pouzivas lokalny MCP?",
        route=route,
    ) == "Áno. JurisDigta MCP je v tomto nasadení volané lokálne v procese API."

    prior_message = chat_api.Message(
        session_id=chat_api.Session().id,
        role=chat_api.MessageRole.ASSISTANT,
        content=(
            "Platitel: Poskytovatel pozicky bude doplneny pred podpisom. "
            "Prijemca: Prijemca bude doplneny pred podpisom. "
            "V [mesto], dna [datum vystavenia]"
        ),
    )
    missing_reply = chat_api._runtime_question_reply(
        content="Ake su chybajuce udaje?",
        route=route,
        prior_messages=[prior_message],
    )
    assert missing_reply is not None
    assert "poskytovateľ/platiteľ" in missing_reply
    assert "miesto vystavenia" in missing_reply


def test_document_export_uses_latest_legal_document_body_without_assistant_notes() -> None:
    from app.chat import api as chat_api
    from app.chat.country_services.slovakia import (
        _build_slovak_payment_confirmation_ready_reply,
        prepare_slovakia_direct_reply,
    )
    from app.chat.models import Message, MessageRole, Session

    session = Session(country="SK", language="sk-SK")
    old_reply = _build_slovak_payment_confirmation_ready_reply(
        current_content="Priprav potvrdenie o zaplateni.",
        company_record=None,
    )
    exact_prompt = (
        "priprav mi potvrdenie napozicanie 5000 pre Jana hraska, "
        "adresa testova 10, testov do konca roka"
    )
    preparation = prepare_slovakia_direct_reply(
        session=session,
        messages=[Message(session_id=session.id, role=MessageRole.USER, content=exact_prompt)],
        current_content=exact_prompt,
        prior_messages=[],
        normalize_document_lines=lambda text: [text],
        extract_document_facts=lambda lines: {},
        current_turn_confirms_document_generation=lambda content, previous_messages: False,
        build_share_transfer_lines=lambda facts: [],
    )
    assert preparation.direct_reply is not None
    messages = [
        Message(session_id=session.id, role=MessageRole.ASSISTANT, content=old_reply),
        Message(session_id=session.id, role=MessageRole.USER, content=exact_prompt),
        Message(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=preparation.direct_reply,
        ),
    ]

    assets = chat_api._build_document_export_assets(
        session_id=session.id,
        messages=messages,
        result=None,
        country="SK",
        language="sk-SK",
    )

    assert len(assets) == 1
    exported_text = "\n".join(assets[0].lines)
    assert assets[0].title == "Potvrdenie o pozicke"
    assert "5000" in exported_text
    assert "Jana hraska" in exported_text
    assert "Adresa dlznika: testova 10, testov" in exported_text
    assert "Doba / splatnost pozicky: do konca roka" in exported_text
    assert "Pripravil som navrh dokumentu" not in exported_text
    assert "Podklady pre export" not in exported_text
    assert "Odporucane kroky pred pouzitim" not in exported_text
    assert "CASE_UPDATE_JSON" not in exported_text


def test_first_turn_final_pdf_payment_request_counts_as_export_ready() -> None:
    from app.chat.api import _document_export_ready, _document_generation_confirmed
    from app.chat.models import Message, MessageRole, Session

    session = Session(country="SK", language="sk-SK")
    user_content = (
        "Vytvorenie noveho pripadu pre potvrdenie na 5000 EUR, splatne k 1.7.2028 "
        "na firmu Esolutions SK s.r.o. v zastupeni Marek Matonok na splatku auta z SPZ PP472DT. "
        "Priprav finalny dokument vo formate PDF."
    )
    assistant_content = (
        "Tu je konecna verzia dokumentu - dokument je pripraveny na export a stiahnutie.\n\n"
        "CASE_UPDATE_JSON:\n"
        '{"documents":[{"title":"Potvrdenie o zaplatení","content":"Platiteľ: Marek Matonok"}]}'
    )

    messages = [
        Message(session_id=session.id, role=MessageRole.USER, content=user_content),
        Message(session_id=session.id, role=MessageRole.ASSISTANT, content=assistant_content),
    ]

    assert _document_generation_confirmed(messages)
    assert _document_export_ready(messages)


def test_run_direct_lawyer_turn_does_not_initialize_llm_for_tool_capability_question(monkeypatch) -> None:
    import app.chat.api as chat_api
    from app.chat.repository import InMemoryChatRepository
    from app.chat.models import Session

    session = Session(country="SK", language="sk-SK")
    repository = InMemoryChatRepository()
    repository.create_session(session)

    def fail_get_llm_client() -> object:
        raise AssertionError("LLM should not be initialized for deterministic tool capability replies")

    monkeypatch.setattr(chat_api, "_repository", repository)
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", fail_get_llm_client)

    _user_message, assistant_message, visible_text, processing_events, _route = chat_api._run_direct_lawyer_turn(
        session_id=session.id,
        session=session,
        content="Ake tools mozem pouzit na overenie firmy, auta, adresy a katastra?",
    )

    assert assistant_message.agent_name == "Assistant"
    assert "obchodny_register_company_check" in visible_text
    assert "slovakia_property_lv_lookup" in visible_text
    assert any(event.get("stage") == "tool_capabilities" for event in processing_events)


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


def test_build_simple_pdf_extracts_exact_slovak_loan_confirmation_characters() -> None:
    from app.chat.api import _build_simple_pdf

    pdf_bytes = _build_simple_pdf(
        title="Potvrdenie o pôžičke",
        lines=[
            "Čl. I - Zmluvné strany",
            "Veriteľ: Anna Žáčková, bytom Testová 10, Poprad, Slovenská republika.",
            "Dlžník: Janko Hraško, číslo občianskeho preukazu BA12345DR.",
            "Predmet: pôžička na jeden rok; splatnosť a podpisy strán.",
        ],
        country="SK",
        language="sk-SK",
        footer_line="JurisDigta generated case document",
        draw_logo_mark=True,
        include_title_block=True,
    )

    extracted = _pdf_text(pdf_bytes)
    assert "Potvrdenie o pôžičke" in extracted
    assert "Čl. I" in extracted
    assert "Veriteľ" in extracted
    assert "Dlžník" in extracted
    assert "Žáčková" in extracted
    assert "Janko Hraško" in extracted
    assert "číslo občianskeho preukazu BA12345DR" in extracted
    assert "Slovenská republika" in extracted


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
            "3. **Spolocenska zmluva**: hotove."
        ),
        agent_name="LawyerSlovakia",
    )

    monkeypatch.setattr(
        chat_api,
        "_run_direct_lawyer_turn",
        lambda **kwargs: (persisted_user, persisted_lawyer, persisted_lawyer.content, [], None),
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
    third_doc = "Spolocenska zmluva"
    assert first_doc in events
    assert second_doc in events
    assert third_doc in events
    assert events.index(first_doc) < events.index('"role": "assistant"')
    assert events.index(second_doc) < events.index('"role": "assistant"')
    assert events.index(third_doc) < events.index('"role": "assistant"')


def test_stream_read_user_keeps_connection_alive_during_slow_direct_turn(monkeypatch) -> None:
    import time

    from app.chat import api as chat_api
    from app.chat.models import Message, MessageRole, SessionResult

    session_response = client.post(
        "/v1/chat/sessions",
        json={"country": "SK", "discussion_type": "advice", "language": "sk"},
        headers=AUTH_HEADERS,
    )
    assert session_response.status_code == 200
    session_id = UUID(session_response.json()["id"])

    persisted_user = Message(
        session_id=session_id,
        role=MessageRole.USER,
        content="adresa dcery a firmy je rovnaka, zober z ORSR",
        agent_name="User",
    )
    persisted_lawyer = Message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content="Overenie je hotove a dokument mozem pripravit.",
        agent_name="LawyerSlovakia",
    )

    def slow_direct_turn(**kwargs):
        time.sleep(0.05)
        return persisted_user, persisted_lawyer, persisted_lawyer.content, [], None

    monkeypatch.setattr(chat_api, "_STREAM_KEEPALIVE_SECONDS", 0.01)
    monkeypatch.setattr(chat_api, "_STREAM_STATUS_SECONDS", 0.02)
    monkeypatch.setattr(chat_api, "_run_direct_lawyer_turn", slow_direct_turn)
    monkeypatch.setattr(
        chat_api,
        "_build_direct_reply_result",
        lambda **kwargs: SessionResult(
            final_recommendation="Overenie je hotove.",
            judge_rationale="Direct lawyer reply prepared for session export.",
            metadata={"document_requested": False, "document_confirmed": False, "document_ready": False},
        ),
    )

    with client.stream(
        "POST",
        f"/v1/chat/sessions/{session_id}/stream",
        headers=AUTH_HEADERS,
        json={
            "instruction": "adresa dcery a firmy je rovnaka, zober z ORSR",
            "documents": [],
            "question_timeout_seconds": 30,
            "max_discussion_minutes": 1,
            "communication_minutes": 1,
            "user_simulation_mode": "ReadUser",
        },
    ) as response:
        assert response.status_code == 200
        events = "".join(response.iter_text())

    assert ": keepalive" in events
    assert '"stage": "still_working"' in events
    assert "Stale pracujem na odpovedi" in events
    assert "Overenie je hotove" in events
    assert events.index('"stage": "still_working"') < events.index('"role": "assistant"')


def test_existing_case_history_is_seeded_into_new_reply_session(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    from app.chat.models import MessageRole
    import app.chat.api as chat_api

    captured: dict[str, object] = {}

    class _FakeStore:
        def get_case(self, *, case_id: str):
            assert case_id == "case-123"
            return SimpleNamespace(user_id="user-1")

        def get_case_write_block_reason(self, *, case_id: str, user_id: str | None = None):
            assert case_id == "case-123"
            assert user_id == "user-1"
            return None

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


def test_case_memory_refresh_note_remembers_prior_rental_address() -> None:
    from app.chat.models import Message, MessageRole
    import app.chat.api as chat_api

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="1. Aka je presna adresa prenajimanej nehnutelnosti?",
            agent_name="LawyerSlovakia",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Bratislava, Slavin, Pod Radom 1234",
            agent_name="User",
        ),
    ]

    note = chat_api._build_case_memory_refresh_note(messages)

    assert "CASE MEMORY REFRESH" in note
    assert "Bratislava, Slavin, Pod Radom 1234" in note
    assert "Do not ask again" in note


def test_case_memory_refresh_note_remembers_prepared_document_and_parties() -> None:
    from app.chat.models import Message, MessageRole
    import app.chat.api as chat_api

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=(
                "**Najomna zmluva**\n"
                "Prenajimatel: Jana Novotna, Partizanska 1\n"
                "Najomca: Tomas Hlavaty, Dunajska 12\n"
                "Dokument je pripraveny na stiahnutie."
            ),
            agent_name="LawyerSlovakia",
        ),
    ]

    note = chat_api._build_case_memory_refresh_note(messages)

    assert "document draft was already prepared" in note
    assert "Jana Novotna" in note
    assert "Tomas Hlavaty" in note
    assert "do not restart intake" in note


def test_case_memory_removes_repeated_rental_address_question() -> None:
    from app.chat.models import Message, MessageRole
    import app.chat.api as chat_api

    session_id = uuid4()
    prior_messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Aka je presna adresa prenajimanej nehnutelnosti?",
            agent_name="LawyerSlovakia",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Bratislava, Slavin, Pod Radom 1234",
            agent_name="User",
        ),
    ]
    content = (
        "1. Aka je presna adresa prenajimanej nehnutelnosti?\n\n"
        "CASE_UPDATE_JSON:\n"
        '{"case":{"open_questions":["Aka je presna adresa prenajimanej nehnutelnosti?"]}}'
    )

    cleaned = chat_api._apply_case_memory_to_lawyer_content(
        content=content,
        prior_messages=prior_messages,
    )

    visible = chat_api._user_visible_text(cleaned)
    assert "Bratislava, Slavin, Pod Radom 1234" in visible
    assert "Aka je presna adresa" not in visible
    case_update = chat_api._extract_case_update(cleaned)
    assert case_update is not None
    assert case_update["case"]["open_questions"] == []


def test_case_memory_removes_repeated_rental_party_question_after_document_prepared() -> None:
    from app.chat.models import Message, MessageRole
    import app.chat.api as chat_api

    session_id = uuid4()
    prior_messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=(
                "**Najomna zmluva**\n"
                "Prenajimatel: Jana Novotna, Partizanska 1\n"
                "Najomca: Tomas Hlavaty, Dunajska 12\n"
                "Dokument je pripraveny na stiahnutie."
            ),
            agent_name="LawyerSlovakia",
        ),
    ]
    content = (
        "Aby som mohol zmluvu spravne vypracovat, potrebujem este niekolko detailov:\n\n"
        "2. Kto bude prenajimatel a kto najomca?\n\n"
        "CASE_UPDATE_JSON:\n"
        '{"case":{"open_questions":["Kto bude prenajimatel a kto najomca?"]}}'
    )

    cleaned = chat_api._apply_case_memory_to_lawyer_content(
        content=content,
        prior_messages=prior_messages,
    )

    visible = chat_api._user_visible_text(cleaned)
    assert "Jana Novotna" in visible
    assert "Tomas Hlavaty" in visible
    assert "Kto bude prenajimatel" not in visible
    assert "Pokracujem bez opatovneho pytania" in visible
    case_update = chat_api._extract_case_update(cleaned)
    assert case_update is not None
    assert case_update["case"]["open_questions"] == []


def test_case_memory_removes_any_previously_answered_question() -> None:
    from app.chat.models import Message, MessageRole
    import app.chat.api as chat_api

    session_id = uuid4()
    prior_messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Aka je vyska mesacneho najomneho?",
            agent_name="LawyerSlovakia",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Mesacne najomne je 500 EUR.",
            agent_name="User",
        ),
    ]
    content = (
        "Na pripravu dokumentu este potrebujem odpoved:\n"
        "1. Aka je vyska mesacneho najomneho?\n\n"
        "CASE_UPDATE_JSON:\n"
        '{"case":{"open_questions":["Aka je vyska mesacneho najomneho?"]}}'
    )

    cleaned = chat_api._apply_case_memory_to_lawyer_content(
        content=content,
        prior_messages=prior_messages,
    )

    visible = chat_api._user_visible_text(cleaned)
    assert "Mesacne najomne je 500 EUR." in visible
    assert "Aka je vyska mesacneho najomneho" not in visible
    case_update = chat_api._extract_case_update(cleaned)
    assert case_update is not None
    assert case_update["case"]["open_questions"] == []


def test_case_memory_refresh_note_lists_previous_questions_and_answers() -> None:
    from app.chat.models import Message, MessageRole
    import app.chat.api as chat_api

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Aka je vyska mesacneho najomneho?",
            agent_name="LawyerSlovakia",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="500 EUR mesacne",
            agent_name="User",
        ),
    ]

    note = chat_api._build_case_memory_refresh_note(messages)

    assert "Previously answered case questions" in note
    assert "Aka je vyska mesacneho najomneho?" in note
    assert "500 EUR mesacne" in note


def test_existing_case_history_falls_back_to_summary_when_transcript_missing(monkeypatch) -> None:
    from app.chat.repository import InMemoryChatRepository
    import app.chat.api as chat_api

    captured: dict[str, object] = {}

    class _FakeStore:
        def get_case(self, *, case_id: str):
            assert case_id == "case-123"
            return SimpleNamespace(user_id="user-1")

        def get_case_write_block_reason(self, *, case_id: str, user_id: str | None = None):
            assert case_id == "case-123"
            assert user_id == "user-1"
            return None

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
        def get_case(self, *, case_id: str):
            assert case_id == "case-123"
            return SimpleNamespace(user_id="user-1")

        def get_case_write_block_reason(self, *, case_id: str, user_id: str | None = None):
            assert case_id == "case-123"
            assert user_id == "user-1"
            return None

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
            "3. Spolocenska zmluva.\n\n"
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


def test_mojibake_affirmative_reply_confirms_pending_document_generation() -> None:
    from app.chat.api import _current_turn_confirms_document_generation
    from app.chat.models import Message, MessageRole

    session_id = uuid4()
    previous_messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Chcete, aby som tento dokument teraz vygeneroval vo formate PDF?",
        )
    ]

    assert _current_turn_confirms_document_generation("�no", previous_messages) is True


def test_standalone_affirmative_after_ready_document_returns_status_without_llm(monkeypatch) -> None:
    from app.chat import api as chat_api
    from app.chat.models import Message, MessageRole, Session
    from app.chat.repository import InMemoryChatRepository

    repository = InMemoryChatRepository()
    monkeypatch.setattr(chat_api, "_repository", repository)

    session_id = uuid4()
    session = repository.create_session(
        Session(id=session_id, country="SK", language="SK", discussion_type="court")
    )
    repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Chcem potvrdenie o zaplateni 5000 eur.",
        )
    )
    repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Chcete, aby som tento dokument teraz vygeneroval vo formate PDF?",
        )
    )
    repository.add_message(
        Message(session_id=session_id, role=MessageRole.USER, content="Ano, vygeneruj PDF."),
    )
    repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=(
                "Tu je konecna verzia dokumentu:\n\n"
                "---\n\n"
                "**Potvrdenie o zaplateni**\n\n"
                "Dokument je pripraveny na stiahnutie vo formate PDF."
            ),
        )
    )

    def _unexpected_lawyer_agent(*_args, **_kwargs):
        raise AssertionError("LLM should not be called for ready-document yes/status acknowledgement")

    monkeypatch.setattr("aijurisdictionagents.agents.create_lawyer_agent", _unexpected_lawyer_agent)
    monkeypatch.setattr("aijurisdictionagents.llm.get_llm_client", lambda: object())

    _user, lawyer, visible, events, _route = chat_api._run_direct_lawyer_turn(
        session_id=session_id,
        session=session,
        content="�no",
    )

    assert events == []
    assert lawyer.agent_name == "LawyerStatus"
    assert "pripraveny na export" in visible.lower()


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
        route=SimpleNamespace(model="gpt-4o-mini"),
    )

    assert result.metadata["document_requested"] is True
    assert result.metadata["document_confirmed"] is True
    assert result.metadata["document_ready"] is True


def test_stale_result_refreshes_when_later_messages_make_document_ready() -> None:
    from app.chat.api import _session_result_is_stale
    from app.chat.models import Message, MessageRole, SessionResult

    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Chcem potvrdenie o zaplateni 5000 eur.",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Chcete, aby som pripravil dokument aj vo formate PDF?",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Ano, vyzera to dobre, vygeneruj dokument.",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=(
                "Potvrdenie o zaplatení\n\n"
                "Dokument je pripravený na stiahnutie vo formáte PDF."
            ),
        ),
    ]
    stale_result = SessionResult(
        final_recommendation="Dokument sa pripravuje.",
        judge_rationale="Old cached result",
        metadata={
            "message_count": 3,
            "document_requested": True,
            "document_confirmed": True,
            "document_ready": False,
        },
    )

    assert _session_result_is_stale(result=stale_result, messages=messages) is True


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
    assert "Technick" not in visible
    assert f"/v1/cases/case-123/documents/doc-technical?user_id={user_id}" not in visible
    assert '"case"' not in visible


def test_generated_assistant_document_is_saved_as_case_document(monkeypatch) -> None:
    import app.chat.api as chat_api
    from app.chat.models import Session

    stored_documents: list[dict[str, object]] = []

    class _FakeStore:
        def list_case_documents(self, *, case_id: str):
            return []

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
            doc_id = f"doc-generated-{len(stored_documents) + 1}"
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
            return doc_id

    user_id = uuid4()
    session = Session(
        user_id=user_id,
        case_id="case-123",
        country="SK",
        language="SK",
        discussion_type="advice",
    )
    content = (
        "Spracovanie stale prebieha....\n\n"
        "LawyerSlovakia: Tu su finalne verzie splnomocnenia v slovenskej a anglickej verzii.\n\n"
        "**Splnomocnenie (slovenska verzia)**:\n"
        "- Splnomocnenec: Emilia Matonokova\n"
        "- Spolocnost: Esolutions SK s.r.o.\n"
        "- Prava: Vsetky pravne ukony tykajuce sa pouzivania firemneho auta.\n"
        "- Podpis: ________________________\n\n"
        "**Power of Attorney (anglicka verzia)**:\n"
        "- Attorney-in-fact: Emilia Matonokova\n"
        "- Company: Esolutions SK s.r.o.\n"
        "- Rights: All legal acts related to the use of the company vehicle.\n\n"
        "Dokumenty su pripravene na stiahnutie."
    )

    monkeypatch.setattr(chat_api, "_get_store", lambda: _FakeStore())

    doc_ids = chat_api._persist_generated_case_document_if_needed(session=session, content=content)

    assert doc_ids == ["doc-generated-1", "doc-generated-2"]
    assert len(stored_documents) == 2
    assert {item["kind"] for item in stored_documents} == {"generated_document"}
    assert {item["uploaded_by_user_id"] for item in stored_documents} == {str(user_id)}
    filenames = [str(item["original_filename"]) for item in stored_documents]
    assert filenames[0].startswith("splnomocnenie_sk_")
    assert filenames[1].startswith("power_of_attorney_en_")
    slovak_payload = str(stored_documents[0]["payload"])
    english_payload = str(stored_documents[1]["payload"])
    assert "Splnomocniteľ" in slovak_payload
    assert "Občiansky zákonník" in slovak_payload
    assert "Power of Attorney" not in slovak_payload
    assert "Attorney-in-fact" in english_payload
    assert "Splnomocnenie" not in english_payload
    assert "Dokumenty su pripravene" not in slovak_payload
    assert "Spracovanie stale prebieha" not in english_payload


def test_structured_multilingual_case_documents_are_saved_separately(monkeypatch) -> None:
    import app.chat.api as chat_api
    from app.chat.models import Session

    stored_documents: list[dict[str, object]] = []

    class _FakeStore:
        def list_case_documents(self, *, case_id: str):
            return []

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
            doc_id = f"doc-generated-{len(stored_documents) + 1}"
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
            return doc_id

    user_id = uuid4()
    session = Session(
        user_id=user_id,
        case_id="case-380",
        country="SK",
        language="SK",
        discussion_type="advice",
    )
    case_update = {
        "case": {
            "documents": [
                {
                    "title": "Splnomocnenie",
                    "filename": "splnomocnenie_sk.pdf",
                    "language": "sk-SK",
                    "content": (
                        "**SPLNOMOCNENIE**\n\n"
                        "Ja, RNDr. Marek Matonok, tymto splnomocnujem Emiliu Testovu.\n\n"
                        "---\n\n"
                        "Podpis: ______________________"
                    ),
                },
                {
                    "title": "Power of Attorney",
                    "filename": "power_of_attorney_en.pdf",
                    "language": "en",
                    "content": (
                        "**POWER OF ATTORNEY**\n\n"
                        "I, RNDr. Marek Matonok, hereby authorize Emilia Testova.\n\n"
                        "Signature: ______________________"
                    ),
                },
            ]
        }
    }
    content = (
        "Vyborne, pripravim splnomocnenie v slovenskej a anglickej verzii na export do PDF.\n\n"
        "CASE_UPDATE_JSON:\n"
        f"{json.dumps(case_update, ensure_ascii=False)}"
    )

    monkeypatch.setattr(chat_api, "_get_store", lambda: _FakeStore())

    doc_ids = chat_api._persist_generated_case_document_if_needed(session=session, content=content)

    assert doc_ids == ["doc-generated-1", "doc-generated-2"]
    assert len(stored_documents) == 2
    assert [item["version"] for item in stored_documents] == [1, 2]
    assert str(stored_documents[0]["original_filename"]).startswith("splnomocnenie_sk_")
    assert str(stored_documents[1]["original_filename"]).startswith("power_of_attorney_en_")
    slovak_payload = str(stored_documents[0]["payload"])
    english_payload = str(stored_documents[1]["payload"])
    assert "SPLNOMOCNENIE" in slovak_payload
    assert "______________________" in slovak_payload
    assert "POWER OF ATTORNEY" not in slovak_payload
    assert "POWER OF ATTORNEY" in english_payload
    assert "______________________" in english_payload
    assert "Vyborne" not in slovak_payload
    assert "CASE_UPDATE_JSON" not in english_payload
    assert "---" not in slovak_payload
    assert "**" not in english_payload


def test_contaminated_multilingual_assistant_reply_persists_clean_separate_documents(
    monkeypatch,
) -> None:
    import app.chat.api as chat_api
    from app.chat.models import Session

    stored_documents: list[dict[str, object]] = []

    class _FakeStore:
        def list_case_documents(self, *, case_id: str):
            return []

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
            doc_id = f"doc-generated-{len(stored_documents) + 1}"
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
            return doc_id

    user_id = uuid4()
    session = Session(
        user_id=user_id,
        case_id="case-407",
        country="SK",
        language="SK",
        discussion_type="advice",
    )
    content = (
        "Spracovanie stale prebieha.... LawyerSlovakia: Ospravedlnujem sa za chyby. "
        "Tu su finalne verzie splnomocnenia v slovencine a anglictine:\n\n"
        "---\n\n"
        "**SPLNOMOCNENIE**\n\n"
        "Ja, RNDr. Marek Matonok, konatel spolocnosti ESolutions SK s.r.o., "
        "tymto splnomocnujem Emiliu Testovu na vsetky ukony suvisiace s pouzivanim "
        "firemneho vozidla s evidencnym cislom PP472DT.\n\n"
        "Toto splnomocnenie je platne od 1. jula 2026 do 31. decembra 2026.\n\n"
        "V Spisskych Bystrych, dna 26. juna 2026.\n\n"
        "Podpis: ________________________\n\n"
        "---\n\n"
        "**POWER OF ATTORNEY**\n\n"
        "I, RNDr. Marek Matonok, the managing director of ESolutions SK s.r.o., "
        "hereby authorize Emilia Testova to perform all acts related to the use of "
        "the company vehicle with registration number PP472DT.\n\n"
        "This power of attorney is valid from July 1, 2026, to December 31, 2026.\n\n"
        "In Spisske Bystre, on June 26, 2026.\n\n"
        "Signature: ________________________\n\n"
        "---\n\n"
        "Teraz pripravim oba dokumenty na export do PDF. Prosim, chvilu pockajte.\n\n"
        "**Zhrnutie pripadu:**\n"
        "- Splnomocnenie pre Emiliu Testovu.\n\n"
        "**Chybajuce informacie / dokumenty:**\n"
        "- Adresa Emilie Testovej.\n\n"
        "**Rizika / slabe miesta:**\n"
        "- Neuplne udaje o adrese.\n\n"
        "**Navrhovany postup:**\n"
        "- Doplnit adresu pred podpisom."
    )

    monkeypatch.setattr(chat_api, "_get_store", lambda: _FakeStore())

    doc_ids = chat_api._persist_generated_case_document_if_needed(session=session, content=content)

    assert doc_ids == ["doc-generated-1", "doc-generated-2"]
    assert [item["version"] for item in stored_documents] == [1, 2]
    assert str(stored_documents[0]["original_filename"]).startswith("splnomocnenie_")
    assert str(stored_documents[1]["original_filename"]).startswith("power_of_attorney_")
    slovak_payload = str(stored_documents[0]["payload"])
    english_payload = str(stored_documents[1]["payload"])
    assert "SPLNOMOCNENIE" in slovak_payload
    assert "POWER OF ATTORNEY" not in slovak_payload
    assert "POWER OF ATTORNEY" in english_payload
    assert "SPLNOMOCNENIE" not in english_payload
    for payload in (slovak_payload, english_payload):
        assert "Spracovanie stale prebieha" not in payload
        assert "LawyerSlovakia" not in payload
        assert "Ospravedlnujem" not in payload
        assert "Zhrnutie pripadu" not in payload
        assert "Chybajuce informacie" not in payload
        assert "Rizika" not in payload
        assert "Navrhovany postup" not in payload
        assert "export do PDF" not in payload
        assert "---" not in payload
        assert "**" not in payload


def test_generated_payment_confirmation_document_uses_legal_filename() -> None:
    from app.chat.api import _generated_case_document_filename_for_storage

    content = (
        "Pripravim potvrdenie o zaplateni na zaklade poskytnutych udajov.\n\n"
        "**Potvrdenie o zaplatení**\n\n"
        "Ja, nizsie podpisany, potvrdzujem prijatie sumy 1000 EUR.\n\n"
        "Podpis: ____________________"
    )

    filename = _generated_case_document_filename_for_storage(content, timestamp="20260622T152930Z")

    assert filename == "potvrdenie_o_zaplateni_20260622T152930Z.pdf"


def test_pending_payment_confirmation_reply_is_synthesized_for_storage() -> None:
    from app.chat.api import _synthesized_generated_case_document_body_for_storage

    content = (
        "Pripravim potvrdenie o zaplateni s uvedenymi udajmi.\n\n"
        "- **Suma:** 1000 EUR\n"
        "- **Platitel:** Matej Mat, Stromova 10, Poprad\n"
        "- **Prijemca:** Matej Mat, Stromova 10, Poprad\n"
        "- **Datum prijatia:** 1.1.2026\n\n"
        "Teraz pripravim finalne potvrdenie o zaplateni vo formate PDF. Chvilu prosim."
    )

    body = _synthesized_generated_case_document_body_for_storage(content)

    assert "Potvrdenie" in body
    assert "Matej Mat" in body
    assert "1000 EUR" in body
    assert "Chvilu prosim" not in body


def test_technical_document_notice_does_not_block_pdf_export_readiness() -> None:
    from app.chat.api import _build_direct_reply_result
    from app.chat.models import Message, MessageRole, Session

    session_id = uuid4()
    user_id = uuid4()
    session = Session(
        id=session_id,
        user_id=user_id,
        case_id="case-123",
        country="SK",
        language="SK",
        discussion_type="advice",
    )
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content="Chcete, aby som pripravil dokument na stiahnutie?",
        ),
        Message(session_id=session_id, role=MessageRole.USER, content="ano"),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "Dokument je pripraveny na stiahnutie.\n\n"
                "Technicke udaje som ulozil do dokumentu pripadu: "
                f"/v1/cases/case-123/documents/doc-technical?user_id={user_id}\n\n"
                '{"case":{"status":"intake_open"}}'
            ),
        ),
    ]

    result = _build_direct_reply_result(
        session_id=session_id,
        session=session,
        messages=messages,
        lawyer_message=messages[-1].content,
        route=SimpleNamespace(model="gpt-4o-mini"),
    )

    assert result.metadata["document_ready"] is True
    assert "/v1/cases/" not in result.final_recommendation


def test_document_processing_status_hides_internal_filenames_from_user(caplog) -> None:
    import logging

    import app.chat.api as chat_api

    with caplog.at_level(logging.INFO, logger=chat_api._LOGGER.name):
        visible = chat_api._prepend_document_status_note(
            reply="Dokument pripravujem.",
            processed_names=["session-ready.txt"],
            unprocessed_names=[
                "session-a82ef605-e915-4286-9016-7e2063554c83.txt",
                "session-9af30e7a-8039-46fd-9158-57399d9b600e.txt",
            ],
        )

    assert visible == "Spracovanie stále prebieha....\n\nDokument pripravujem."
    assert "session-a82ef605-e915-4286-9016-7e2063554c83.txt" not in visible
    assert "session-ready.txt" not in visible
    assert "Technicke udaje" not in visible
    assert "session-a82ef605-e915-4286-9016-7e2063554c83.txt" in caplog.text
    assert "session-ready.txt" in caplog.text


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
        lambda **kwargs: (persisted_user, persisted_lawyer, persisted_lawyer.content, [], None),
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
        lambda **kwargs: (persisted_user, persisted_lawyer, persisted_lawyer.content, [], None),
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


def test_unstructured_relative_download_link_uses_previous_draft_for_case_document(monkeypatch) -> None:
    import app.chat.api as chat_api
    from app.chat.models import Message, MessageRole, Session
    from app.chat.repository import InMemoryChatRepository

    stored_documents: list[dict[str, object]] = []

    class _FakeStore:
        def list_case_documents(self, *, case_id: str):
            return []

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
            return "doc-generated-1"

    repository = InMemoryChatRepository()
    session_id = uuid4()
    user_id = uuid4()
    session = Session(
        id=session_id,
        user_id=user_id,
        case_id="case-123",
        country="SK",
        language="SK",
        discussion_type="advice",
    )
    repository.create_session(session)
    repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "**Splnomocnenie**\n\n"
                "Splnomocniteľ: Esolutions SK s.r.o.\n"
                "Splnomocnenec: Marek Matonok\n"
                "Predmet splnomocnenia: používanie firemného vozidla PP472DT.\n\n"
                "Podpis splnomocniteľa:\n"
                "________________________"
            ),
        )
    )
    current_reply = (
        "USER-FACING: Splnomocnenie bolo úspešne pripravené a je pripravené na stiahnutie.\n"
        "Môžete si ho stiahnuť pomocou nasledujúceho odkazu:\n\n"
        "[Stiahnuť splnomocnenie](documents/splnomocnenie_ESolutions_SK.pdf)"
    )

    monkeypatch.setattr(chat_api, "_repository", repository)
    monkeypatch.setattr(chat_api, "_get_store", lambda: _FakeStore())

    visible = chat_api._user_visible_text(current_reply)
    doc_ids = chat_api._persist_generated_case_document_if_needed(session=session, content=current_reply)

    assert "documents/" not in visible
    assert "Stiahnuť splnomocnenie" not in visible
    assert doc_ids == ["doc-generated-1"]
    assert stored_documents[0]["kind"] == "generated_document"
    assert stored_documents[0]["uploaded_by_user_id"] == str(user_id)
    assert "Splnomocniteľ: Esolutions SK s.r.o." in str(stored_documents[0]["payload"])
    assert "PP472DT" in str(stored_documents[0]["payload"])


def test_summary_only_previous_assistant_reply_is_not_saved_as_generated_document(monkeypatch) -> None:
    import app.chat.api as chat_api
    from app.chat.models import Message, MessageRole, Session
    from app.chat.repository import InMemoryChatRepository

    stored_documents: list[dict[str, object]] = []

    class _FakeStore:
        def list_case_documents(self, *, case_id: str):
            return []

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
            return "doc-generated-1"

    repository = InMemoryChatRepository()
    session_id = uuid4()
    user_id = uuid4()
    session = Session(
        id=session_id,
        user_id=user_id,
        case_id="case-411",
        country="SK",
        language="SK",
        discussion_type="advice",
    )
    repository.create_session(session)
    repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content="- Splnomocnenie pre Emiliu Testovu na pouzivanie firemneho auta.",
        )
    )
    current_reply = (
        "USER-FACING: Dokument je pripraveny na stiahnutie.\n\n"
        "[Stiahnut splnomocnenie](documents/splnomocnenie_20260626T183932Z.pdf)"
    )

    monkeypatch.setattr(chat_api, "_repository", repository)
    monkeypatch.setattr(chat_api, "_get_store", lambda: _FakeStore())

    doc_ids = chat_api._persist_generated_case_document_if_needed(session=session, content=current_reply)

    assert doc_ids == []
    assert stored_documents == []


def test_persisted_assistant_message_exposes_generated_document_without_refresh(monkeypatch) -> None:
    import app.chat.api as chat_api
    from app.chat.models import Session
    from app.chat.repository import InMemoryChatRepository

    session = Session(
        user_id=uuid4(),
        case_id="case-immediate-download",
        country="SK",
        language="SK",
        discussion_type="advice",
    )
    repository = InMemoryChatRepository()
    repository.create_session(session)
    monkeypatch.setattr(chat_api, "_repository", repository)
    monkeypatch.setattr(chat_api, "_persist_case_message_if_needed", lambda **_kwargs: None)
    monkeypatch.setattr(
        chat_api,
        "_persist_generated_case_document_if_needed",
        lambda **_kwargs: ["doc-new"],
    )

    persisted = chat_api._persist_direct_assistant_message(
        session_id=session.id,
        session=session,
        content="KoneÄnÃ¡ verzia dokumentu je pripravenÃ¡.",
        agent_name="Assistant",
    )

    assert "KoneÄnÃ¡ verzia dokumentu je pripravenÃ¡." in persisted.content
    assert (
        f"/v1/cases/case-immediate-download/documents/doc-new?user_id={session.user_id}"
        in persisted.content
    )
    assert chat_api._user_visible_text(persisted.content) == (
        "KoneÄnÃ¡ verzia dokumentu je pripravenÃ¡."
    )
    payload = chat_api._message_payload(persisted)
    assert payload["content"] == "KoneÄnÃ¡ verzia dokumentu je pripravenÃ¡."
    assert payload["generated_document_urls"] == [
        f"/v1/cases/case-immediate-download/documents/doc-new?user_id={session.user_id}"
    ]


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
        route=SimpleNamespace(model="gpt-4o-mini"),
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
        lambda _country, **_kwargs: result_metadata.LawKnowledgeSnapshot(
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


def test_direct_reply_result_includes_mcp_court_and_web_source_citations(monkeypatch) -> None:
    from app.chat.api import _build_direct_reply_result, _case_citation_inputs_from_result
    from app.chat.models import Message, MessageRole, Session
    import app.chat.result_metadata as result_metadata

    monkeypatch.setattr(result_metadata, "resolve_session_law_citations", lambda **_kwargs: [])
    monkeypatch.setattr(
        result_metadata,
        "get_law_knowledge_snapshot",
        lambda _country, **_kwargs: result_metadata.LawKnowledgeSnapshot(
            last_law_update_date=None,
            last_law_update_source="unavailable",
            model_knowledge_cutoff_date="2023-10-01",
            model_knowledge_cutoff_source="https://platform.openai.com/docs/models/gpt-4o-mini",
        ),
    )

    class _FakeValidator:
        def evaluate(self, **_kwargs):
            return SimpleNamespace(weighted_accuracy=91.0, summary="Validated.", scores=[])

    monkeypatch.setattr(result_metadata, "AIAgentsValidator", lambda **_kwargs: _FakeValidator())

    session_id = uuid4()
    session = Session(id=session_id, country="SK", language="SK")
    messages = [
        Message(session_id=session_id, role=MessageRole.USER, content="Daj mi top 5 sudnych rozhodnuti ohladom podnajmu?"),
        Message(session_id=session_id, role=MessageRole.ASSISTANT, content="Nasiel som relevantne rozhodnutia."),
    ]

    result = _build_direct_reply_result(
        session_id=session_id,
        session=session,
        messages=messages,
        lawyer_message=messages[-1].content,
        legal_source_citations=[
            {
                "source_type": "court_decision",
                "source_id": "decision-1",
                "source_url": "https://obcan.justice.sk/infosud/-/detail/decision-1",
                "title": "Najvyssi sud SR - 1Cdo/2021 - 2021",
                "citation_label": "Najvyssi sud SR - 1Cdo/2021 - 2021",
                "court": "Najvyssi sud SR",
                "file_number": "1Cdo/2021",
                "decision_date": "2021-03-01",
                "retrieval_tool": "JurisDigta MCP searchCourtDecisions",
                "relevance_score": 1.0,
            },
            {
                "source_type": "web",
                "source_id": "https://obcan.justice.sk/infosud/-/detail/fallback",
                "source_url": "https://obcan.justice.sk/infosud/-/detail/fallback",
                "title": "Fallback rozhodnutie",
                "citation_label": "Fallback rozhodnutie",
                "snippet": "Official web fallback.",
                "retrieval_tool": "AIWebSearchAgent official web fallback",
                "relevance_score": 0.9,
            },
        ],
    )

    assert result.metadata["legal_source_citations"][0]["source_type"] == "court_decision"
    assert result.citations[0]["filename"] == "Najvyssi sud SR - 1Cdo/2021 - 2021"
    assert "JurisDigta MCP searchCourtDecisions" in result.citations[0]["snippet"]
    persisted_inputs = _case_citation_inputs_from_result(case_id="case-1", result=result)
    assert [item["source_type"] for item in persisted_inputs] == ["court_decision", "web"]
    assert persisted_inputs[0]["decision_date"] == "2021-03-01"
    assert persisted_inputs[1]["retrieval_tool"] == "AIWebSearchAgent official web fallback"
    assert persisted_inputs[1]["relevance_score"] == 0.9


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

    snapshot = result_metadata.get_law_knowledge_snapshot("SK", model_name="gpt-4o-mini")

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

    first_snapshot = result_metadata.get_law_knowledge_snapshot("SK", model_name="gpt-4o-mini")
    assert first_snapshot.model_knowledge_cutoff_date == "2023-10-01"

    second_snapshot = result_metadata.get_law_knowledge_snapshot("SK", model_name="gpt-4o-mini")

    assert second_snapshot.last_law_update_date is None
    assert second_snapshot.last_collector_run_at is None
    assert second_snapshot.last_processed_law is None
    assert second_snapshot.model_knowledge_cutoff_date == "2023-10-01"
    assert (
        second_snapshot.model_knowledge_cutoff_source
        == "https://platform.openai.com/docs/models/gpt-4o-mini"
    )


def test_law_snapshot_does_not_web_search_for_mock_model(monkeypatch, tmp_path) -> None:
    import app.chat.result_metadata as result_metadata

    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "missing-laws.sqlite3"))
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
        lambda: SimpleNamespace(search=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected web search"))),
    )
    monkeypatch.setattr(
        result_metadata,
        "_fetch_text_from_url",
        lambda _url: (_ for _ in ()).throw(AssertionError("unexpected page fetch")),
    )

    snapshot = result_metadata.get_law_knowledge_snapshot("SK", model_name="mock")

    assert snapshot.last_law_update_date is None
    assert snapshot.last_law_update_source == "unavailable"
    assert snapshot.model_knowledge_cutoff_date is None
    assert snapshot.model_knowledge_cutoff_source == "unavailable"


def test_law_snapshot_uses_direct_openai_model_page_when_search_returns_no_results(
    monkeypatch, tmp_path
) -> None:
    import app.chat.result_metadata as result_metadata

    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "missing-laws.sqlite3"))
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

    snapshot = result_metadata.get_law_knowledge_snapshot("SK", model_name="gpt-4.1")

    assert snapshot.model_knowledge_cutoff_date == "2025-04-14"
    assert snapshot.model_knowledge_cutoff_source == "https://platform.openai.com/docs/models/gpt-4.1"


def test_law_snapshot_uses_known_model_fallback_for_custom_deployment_name(
    monkeypatch, tmp_path
) -> None:
    import app.chat.result_metadata as result_metadata

    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "missing-laws.sqlite3"))
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

    snapshot = result_metadata.get_law_knowledge_snapshot("SK", model_name="juris-gpt-4o-mini-dev")

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

    snapshot = result_metadata.get_law_knowledge_snapshot("SK", model_name="unknown-custom-model")

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


def test_enforce_single_question_turn_adds_missing_question_from_case_update() -> None:
    from app.chat.api import _enforce_single_question_turn, _extract_case_update, _user_visible_text

    raw_reply = (
        "Na dokoncenie zmluvy potrebujem este potvrdit niektore zakladne udaje:\n\n"
        "CASE_UPDATE_JSON:\n"
        '{"case":{"open_questions":["Kto bude najomca?"]}}'
    )

    normalized = _enforce_single_question_turn(raw_reply)
    visible = _user_visible_text(normalized)

    assert "Na dokoncenie zmluvy potrebujem este potvrdit" in visible
    assert "Kto bude najomca?" in visible
    case_update = _extract_case_update(normalized)
    assert isinstance(case_update, dict)
    assert case_update["case"]["open_questions"] == ["Kto bude najomca?"]


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
