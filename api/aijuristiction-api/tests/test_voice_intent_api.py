from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


AUTH_HEADERS = {"x-api-key": "aijuris"}


def test_voice_intent_extracts_case_title_for_web_client() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/voice/intent",
        headers=AUTH_HEADERS,
        json={
            "client_type": "web",
            "language_code": "SK",
            "transcript": "chcem vytvoriť prípad s nazovom splnomocnenie 1.0, pošli",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "create_case"
    assert payload["confidence"] >= 0.9
    assert payload["slots"] == {"title": "splnomocnenie 1.0"}
    assert payload["execution"]["status"] == "not_executed"
    assert payload["transcript_redaction_hint"] == "store_title_only"


def test_voice_intent_extracts_case_title_after_repeat_prefix() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/voice/intent",
        headers=AUTH_HEADERS,
        json={
            "client_type": "web",
            "language_code": "SK",
            "transcript": "Ešte raz vytvor nový prípad test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "create_case"
    assert payload["slots"] == {"title": "test"}


def test_voice_intent_extracts_case_title_from_conditional_stt_phrasing() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/voice/intent",
        headers=AUTH_HEADERS,
        json={
            "client_type": "mobile",
            "language_code": "SK",
            "transcript": "chcel by som vytvorit novy pripad s nazvom je dopravna nehoda koniec",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "create_case"
    assert payload["slots"] == {"title": "dopravna nehoda"}


def test_voice_intent_extracts_case_title_when_prosim_is_inside_command() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/voice/intent",
        headers=AUTH_HEADERS,
        json={
            "client_type": "mobile",
            "language_code": "SK",
            "transcript": "vytvor prosim novy pripad pod nazvom reklamacia auta posli",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "create_case"
    assert payload["slots"] == {"title": "reklamacia auta"}


def test_voice_intent_execute_create_case_after_case_store_dependency_warmup(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))
    client = TestClient(app)

    user_response = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900000992",
            "email": "voice-warmup@example.com",
            "password": "secret",
        },
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["user_id"]

    warmup_response = client.get(f"/v1/cases?user_id={user_id}", headers=AUTH_HEADERS)
    assert warmup_response.status_code == 200
    assert warmup_response.json() == []

    voice_response = client.post(
        "/v1/voice/intent",
        headers=AUTH_HEADERS,
        json={
            "client_type": "mobile",
            "language_code": "SK",
            "user_id": user_id,
            "execute": True,
            "transcript": "vytvor prosim novy pripad pod nazvom reklamacia auta posli",
        },
    )

    assert voice_response.status_code == 200
    payload = voice_response.json()
    assert payload["intent"] == "create_case"
    assert payload["execution"]["status"] == "executed"
    assert payload["execution"]["title"] == "reklamacia auta"


def test_voice_intent_uses_end_words_as_send_markers() -> None:
    client = TestClient(app)

    send_response = client.post(
        "/v1/voice/intent",
        headers=AUTH_HEADERS,
        json={"client_type": "web", "language_code": "SK", "transcript": "koniec"},
    )
    create_response = client.post(
        "/v1/voice/intent",
        headers=AUTH_HEADERS,
        json={
            "client_type": "web",
            "language_code": "SK",
            "transcript": "Ešte raz vytvor nový prípad test koniec",
        },
    )

    assert send_response.status_code == 200
    assert send_response.json()["intent"] == "send_message"
    assert create_response.status_code == 200
    assert create_response.json()["slots"] == {"title": "test"}


def test_voice_intent_asks_clarification_when_case_title_is_missing() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/voice/intent",
        headers=AUTH_HEADERS,
        json={
            "client_type": "mobile",
            "language_code": "SK",
            "transcript": "vytvor nový prípad",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "create_case"
    assert payload["slots"] == {}
    assert payload["clarification_question"] == "Čo mám urobiť s touto správou?"


def test_voice_intent_recognizes_confirmation_answers_for_web_and_mobile() -> None:
    client = TestClient(app)

    yes_response = client.post(
        "/v1/voice/intent",
        headers=AUTH_HEADERS,
        json={"client_type": "web", "language_code": "SK", "transcript": "áno"},
    )
    no_response = client.post(
        "/v1/voice/intent",
        headers=AUTH_HEADERS,
        json={"client_type": "mobile", "language_code": "SK", "transcript": "nie"},
    )

    assert yes_response.status_code == 200
    assert no_response.status_code == 200
    assert yes_response.json()["intent"] == "confirm_yes"
    assert no_response.json()["intent"] == "confirm_no"
    assert yes_response.json()["requires_confirmation"] is False
    assert no_response.json()["requires_confirmation"] is False


def test_voice_intent_can_execute_create_case(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))
    client = TestClient(app)
    user_response = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900000991",
            "email": "voice-router@example.com",
            "password": "secret",
        },
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["user_id"]

    response = client.post(
        "/v1/voice/intent",
        headers=AUTH_HEADERS,
        json={
            "client_type": "web",
            "language_code": "SK",
            "user_id": user_id,
            "execute": True,
            "transcript": "chcem vytvoriť prípad s názvom splnomocnenie 1.0, pošli",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "create_case"
    assert payload["execution"]["status"] == "executed"
    assert payload["execution"]["title"] == "splnomocnenie 1.0"

    cases = client.get(f"/v1/cases?user_id={user_id}", headers=AUTH_HEADERS)
    assert cases.status_code == 200
    assert [item["title"] for item in cases.json()] == ["splnomocnenie 1.0"]
