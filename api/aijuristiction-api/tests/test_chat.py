import json
from io import BytesIO
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pypdf import PdfReader

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
    assert "ai jurisdicta solution" in document_text
    assert "generated:" in document_text
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
    assert "nájomná zmluva" in document_text
    assert "čl. i - zmluvné strany" in document_text
    assert "čl. vi - skončenie nájmu" in document_text
    assert "podpis prenajímateľa" in document_text
    assert "doba nájmu" in document_text
    assert "vypovedna lehota" in document_text
    assert "platba vopred" in document_text


def test_document_export_for_easement_case_is_not_lease_template() -> None:
    from app.chat.api import _build_document_export_content, _build_simple_pdf
    from app.chat.models import Message, MessageRole

    session_id = uuid4()
    assistant_message = Message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        agent_name="LawyerSlovakia",
        content=(
            "Zhrnutie prípadu.\n\n"
            "CASE_UPDATE_JSON:\n"
            "{"
            '"case":{"case_id":null,"status":"intake_open","jurisdiction":{"country":"SK","language":"sk-SK"},'
            '"parties":{"client":{"name":"Klient"},"opponent":{"name":"pán Novák"}},'
            '"matter":{"category":"civil","topic":"vecne_bremeno","amount_eur":null,'
            '"key_dates":{},"facts_summary":"Spor so susedom ohľadom brány na mieste vecného bremena a prístupu k plynovej prípojke.",'
            '"client_goal":"Zabezpečiť bránku alebo iný vstup na výkon vecného bremena."},'
            '"documents":[],"open_questions":[],"next_discussion":{"scheduled_for":null,"agenda":["Pripraviť predžalobnú výzvu."]},'
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

    assert "nájomná zmluva" not in " ".join(lines).lower()
    assert any("vecného bremena" in line.lower() for line in lines)

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
    lowered = extracted.lower()
    assert "vecného bremena" in lowered
    assert "plynovej prípojke" in lowered
    assert "nájomná zmluva" not in lowered


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

    lowered_lines = " ".join(lines).lower()
    assert "nájomná zmluva" not in lowered_lines
    assert "prevodu obchodného podielu" in lowered_lines
    assert "esolutions sk s.r.o." in lowered_lines
    assert "50%" in lowered_lines or "50 %" in lowered_lines


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
                        "status": "Aktívna",
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
    assert "exact transferred share" in prompt


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
                        "seat": "Partizánska 665, 059 18 Spišské Bystré",
                        "status": "Aktívna",
                        "stakeholders": [
                            {
                                "name": "RNDr. Marek Matonok",
                                "address": "Partizánska 665/101, Spišské Bystré",
                            }
                        ],
                        "statutory_representatives": [
                            {
                                "name": "RNDr. Mária Matonoková",
                                "address": "Partizánska 665, Spišské Bystré",
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
                        "seat": "Partizánska 665, 059 18 Spišské Bystré",
                        "status": "Aktívna",
                        "stakeholders": [
                            {
                                "name": "RNDr. Marek Matonok",
                                "address": "Partizánska 665/101, Spišské Bystré",
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
                        "seat": "Partizánska 665, 059 18 Spišské Bystré",
                        "status": "Aktívna",
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
                        "seat": "Partizánska 665, 059 18 Spišské Bystré",
                        "status": "Aktívna",
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
                        "seat": "Partizánska 665, 059 18 Spišské Bystré",
                        "status": "Aktívna",
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
    assert "Already captured inputs: transferee identification, transfer price / gratuitous flag, management-change flag" in prompt
    assert "Still missing inputs: transferor identification, exact transferred share" in prompt


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
                        "seat": "Partizánska 665, 059 18 Spišské Bystré",
                        "status": "Aktívna",
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
                "1. Presné identifikačné údaje adobúdateľa. "
                "Dalsi vlastnik: Jano Hrasko Rozpravkova 12 Rozpravkovo, Slovenska Republika "
                "2. Podiel sa prevádza bezodplatne. "
                "3. Nemení iba spoločnícka štruktúra alebo aj konateľ / spôsob konania."
            )
        },
        headers=AUTH_HEADERS,
    )
    assert reply_response.status_code == 200
    assert reply_response.json()["content"] == "MODEL_INLINE_REPLY"
    assert captured_prompts
    prompt = captured_prompts[-1]
    assert "Already captured inputs: transferee identification, transfer price / gratuitous flag, management-change flag" in prompt
    assert "Still missing inputs: transferor identification, exact transferred share" in prompt


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
                        "seat": "Partizánska 665, 059 18 Spišské Bystré",
                        "status": "Aktívna",
                        "stakeholders": (
                            {
                                "name": "RNDr. Marek Matonok",
                                "address": "Partizánska 665/101, 059 18 Spišské Bystré, Slovenská republika",
                                "type": "spoločník",
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
    assert "Already captured inputs: transferor identification" in prompt
    assert "Still missing inputs: exact transferred share" in prompt


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
                        "seat": "Partizánska 665, 059 18 Spišské Bystré",
                        "status": "Aktívna",
                        "stakeholders": [
                            {
                                "name": "RNDr. Marek Matonok",
                                "address": "Partizánska 665/101, 059 18 Spišské Bystré, Slovenská republika",
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
            return SimpleNamespace(content="MODEL_CONFLICT_REPLY", agent_name="LawyerSlovakia")

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
    assert reply_response.json()["content"] == "MODEL_CONFLICT_REPLY"
    assert captured_prompts
    prompt = captured_prompts[-1]
    assert "Conflict checks:" in prompt
    assert "does not match current ORSR stakeholders" in prompt
    assert "Ask the user to confirm the authoritative transferor identity before producing final documents." in prompt


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
                        "status": "Aktívna",
                    },
                ),
            )

    captured_prompts: list[str] = []

    class _SpyLawyer:
        system_prompt = "fake-system"

        def respond(self, *, conversation, documents, sources, system_prompt_override):
            captured_prompts.append(system_prompt_override)
            return SimpleNamespace(
                content="Pripravil som finálny návrh dokumentácie.\nCASE_UPDATE_JSON:\n{}",
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
    lowered = content.lower()
    assert "pripravil som finálny návrh dokumentácie" in lowered
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
        title="Nájomná zmluva / Kündigung",
        lines=[
            "Čl. I - Zmluvné strany",
            "Ľubomír Žáček býva v Košiciach.",
            "Deutsch: Kündigung, Straße, Größe und äußerst wichtige Frist.",
        ],
        country="SK",
        language="sk-SK",
        header_line="AI Jurisdicta Solution | Generated: 2026-03-16 20:00:00 UTC",
        footer_line="AIJ | API 0.1.0 | Core 0.1.0",
        draw_logo_mark=True,
        include_title_block=True,
    )

    extracted = _pdf_text(pdf_bytes)
    assert "Nájomná zmluva / Kündigung" in extracted
    assert "Čl. I - Zmluvné strany" in extracted
    assert "Ľubomír Žáček býva v Košiciach." in extracted
    assert "Deutsch: Kündigung, Straße, Größe und äußerst wichtige Frist." in extracted


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
    assert "Používateľ nemohol odpovedať do 50 minút." not in events
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
                "Zhrnutie prípadu.\n\n"
                "CASE_UPDATE_JSON:\n"
                '{"case":{"case_id":null,"status":"intake_open","jurisdiction":{"country":"SK","language":"sk-SK"},'
                '"parties":{"client":{"name":"Jozef Novák"},"opponent":{"name":"Peter Kováč"}},'
                '"matter":{"category":"civil","topic":"vecne_bremeno","amount_eur":null,'
                '"key_dates":{},"facts_summary":"Spor o prístup k plynovej prípojke.",'
                '"client_goal":"Zabezpečiť vstup cez bránku."},'
                '"documents":[],"open_questions":[],"next_discussion":{"scheduled_for":null,"agenda":[]},'
                '"discussions_append":[]}}'
            ),
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content="Chcete, aby som vám pripravil výsledok v PDF formáte?",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Áno, priprav to prosím aj v PDF.",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content=(
                "Ďakujem. Po nahratí e-mailov a aktualizácii záznamu vo formáte JSON "
                "pripravím aj výsledok vo formáte PDF."
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
    return "\n".join(page.extract_text() or "" for page in reader.pages)
