import json
from io import BytesIO
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import app


client = TestClient(app)
AUTH_HEADERS = {"x-api-key": "aijuris"}


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
        conn.commit()

    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(laws_db))
    monkeypatch.setenv("MODEL_KNOWLEDGE_CUTOFF_DATE", "2020-12-31")

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
    assert result.metadata["model_knowledge_cutoff_date"] == "2020-12-31"
    assert result.metadata["model_knowledge_cutoff_source"] == "model_knowledge_cutoff_cache"
    assert result.metadata["law_reference_links"] == [
        "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/11/",
        "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/2/",
    ]
    assert result.metadata["api_version"]


def test_law_snapshot_falls_back_to_model_cutoff_and_writes_cache(monkeypatch, tmp_path) -> None:
    from app.chat.result_metadata import get_law_knowledge_snapshot

    cache_path = tmp_path / "model-knowledge-cutoff.json"
    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "missing-laws.sqlite3"))
    monkeypatch.setenv("MODEL_KNOWLEDGE_CUTOFF_CACHE_FILE", str(cache_path))
    monkeypatch.setenv("MODEL_KNOWLEDGE_CUTOFF_DATE", "2024-12-31")
    monkeypatch.setenv("LLM_PROVIDER", "azurefoundry")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")

    snapshot = get_law_knowledge_snapshot("SK")

    assert snapshot.last_law_update_date is None
    assert snapshot.last_law_update_source == "unavailable"
    assert snapshot.model_knowledge_cutoff_date == "2024-12-31"
    assert snapshot.model_knowledge_cutoff_source == "model_knowledge_cutoff_cache"
    assert snapshot.reference_links == ()

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["model_knowledge_cutoff_date"] == "2024-12-31"
    assert payload["source"] == "model_knowledge_cutoff_cache"
    assert payload["provider"] == "azurefoundry"
    assert payload["deployment"] == "gpt-4.1"


def test_law_snapshot_reuses_cached_model_cutoff_without_expiration(monkeypatch, tmp_path) -> None:
    from app.chat.result_metadata import get_law_knowledge_snapshot

    cache_path = tmp_path / "model-knowledge-cutoff.json"
    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(tmp_path / "missing-laws.sqlite3"))
    monkeypatch.setenv("MODEL_KNOWLEDGE_CUTOFF_CACHE_FILE", str(cache_path))
    monkeypatch.setenv("MODEL_KNOWLEDGE_CUTOFF_DATE", "2024-12-31")

    first_snapshot = get_law_knowledge_snapshot("SK")
    assert first_snapshot.model_knowledge_cutoff_date == "2024-12-31"

    monkeypatch.setenv("MODEL_KNOWLEDGE_CUTOFF_DATE", "2026-01-01")
    second_snapshot = get_law_knowledge_snapshot("SK")

    assert second_snapshot.last_law_update_date is None
    assert second_snapshot.model_knowledge_cutoff_date == "2024-12-31"
    assert second_snapshot.model_knowledge_cutoff_source == "model_knowledge_cutoff_cache"


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


def _pdf_text(payload: bytes) -> str:
    reader = PdfReader(BytesIO(payload))
    return "\n".join(page.extract_text() or "" for page in reader.pages)
