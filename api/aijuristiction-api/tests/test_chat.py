from fastapi.testclient import TestClient

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
    assert "finish" in user_messages
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
