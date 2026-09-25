from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import speech_api
from aijurisdictionagents.api_db import ApiDatabaseStore


@pytest.fixture
def speech(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = ApiDatabaseStore(db_path=tmp_path / "api.sqlite3", blob_root=tmp_path / "blobs")
    store.initialize()
    user = store.create_user(email="speech-synthetic@example.test", password="synthetic", full_name="Synthetic")
    case = store.create_case(user_id=user.user_id, company_id=None, title="Synthetic speech")
    token = store.issue_device_auth_token(user_id=user.user_id, device_id="test-device")
    provider = store.upsert_ai_model_provider(provider_code="speech", provider_type="azure_speech",
        display_name="Azure Speech", region="westeurope", is_external=True, enabled=True)
    profile = store.upsert_ai_model_profile(provider_id=provider.provider_id, model_code="speech-sk",
        model_parameters={"capability": "speech_to_text", "streaming": True}, eu_data_zone_capable=True)
    store.upsert_ai_task_route_policy(task_type="speech_transcription", plan_code="free",
        preferred_external_model_profile_id=profile.model_profile_id, allow_external=True,
        require_external_ack=True, require_eu_data_zone=True)
    app.dependency_overrides[speech_api.get_store] = lambda: store
    monkeypatch.setattr(speech_api, "validate_api_key", lambda _: None)
    closed = []

    class FakeStream:
        def __init__(self):
            self.events = asyncio.Queue()
            self.count = 0

        async def start(self):
            pass

        async def write(self, pcm):
            # Unit transport fixture only, never used by real E2E.
            await self.events.put({"type": "partial", "segment": self.count, "text": "Syntetický návrh"})
            await self.events.put({"type": "final", "segment": self.count, "text": f"Syntetický riadok {self.count + 1}."})
            self.count += 1

        async def finish(self):
            pass

        async def close(self):
            closed.append(True)

    monkeypatch.setattr(speech_api, "create_stream", lambda *_: FakeStream())
    route = speech_api.public_route(store.resolve_speech_route(user_id=user.user_id, case_id=case.case_id))
    start = {"type": "start", "user_id": user.user_id, "device_id": "test-device", "device_token": token,
             "api_key": "test", "case_id": case.case_id, "locale": "sk-SK", "consent": True,
             "format": "pcm_s16le_16000_mono", "route_revision": route["route_revision"]}
    yield TestClient(app), store, start, closed
    app.dependency_overrides.clear()
    speech_api._active.clear()


def test_stream_has_two_lines_before_stop_and_never_sends_chat(speech):
    client, store, start, closed = speech
    with client.websocket_connect("/v1/speech/stream") as ws:
        ws.send_json(start)
        assert ws.receive_json()["type"] == "ready"
        for segment in range(2):
            ws.send_bytes(b"\x00\x00" * 1600)
            assert ws.receive_json()["type"] == "partial"
            event = ws.receive_json()
            assert event["type"] == "final" and event["segment"] == segment
        ws.send_json({"type": "stop"})
        assert ws.receive_json()["type"] == "done"
    assert closed
    assert not store.list_case_communications(case_id=start["case_id"])
    audit = store.list_ai_model_admin_audit_events()
    assert {e.action for e in audit} >= {"speech_consent", "speech_outcome"}
    assert "Syntetický" not in str(audit)
    assert start["device_token"] not in str(audit)


@pytest.mark.parametrize("change,code", [
    ({"consent": False}, "invalid_request"), ({"device_token": "invalid"}, "authentication_required"),
    ({"route_revision": "stale"}, "route_changed"), ({"format": "webm"}, "invalid_request")])
def test_start_fails_closed(speech, change, code):
    client, _, start, closed = speech
    with client.websocket_connect("/v1/speech/stream") as ws:
        ws.send_json({**start, **change})
        assert ws.receive_json()["code"] == code
    assert not closed  # provider never opened


@pytest.mark.parametrize("control", ["cancel", "oversize", "disconnect"])
def test_terminal_paths_release_provider(speech, control):
    client, _, start, closed = speech
    with client.websocket_connect("/v1/speech/stream") as ws:
        ws.send_json(start)
        assert ws.receive_json()["type"] == "ready"
        if control == "cancel":
            ws.send_json({"type": "cancel"})
            assert ws.receive_json()["type"] == "cancelled"
        elif control == "oversize":
            ws.send_bytes(b"\0" * (speech_api.MAX_CHUNK + 2))
            assert ws.receive_json()["code"] == "audio_limit"
    assert closed


def test_cross_user_case_denied_and_chat_policy_never_used(speech):
    client, store, start, _ = speech
    other = store.create_user(email="other@example.test", password="synthetic", full_name="Other")
    case = store.create_case(user_id=other.user_id, company_id=None, title="Private")
    with client.websocket_connect("/v1/speech/stream") as ws:
        ws.send_json({**start, "case_id": case.case_id})
        assert ws.receive_json()["type"] == "error"
    for policy in store.list_ai_task_route_policies():
        if policy.task_type == "speech_transcription":
            store.upsert_ai_task_route_policy(policy_id=policy.policy_id, task_type=policy.task_type,
                plan_code="free", enabled=False)
    with pytest.raises(ValueError, match="route_unavailable"):
        store.resolve_speech_route(user_id=start["user_id"], case_id=start["case_id"])


def test_no_transcript_or_audio_in_audit_payload(speech):
    client, store, start, _ = speech
    with client.websocket_connect("/v1/speech/stream") as ws:
        ws.send_json(start)
        ws.receive_json()
        ws.send_json({"type": "cancel"})
        ws.receive_json()
    audit = json.dumps([event.new_value_summary for event in store.list_ai_model_admin_audit_events()])
    assert "device_token" not in audit and '"text"' not in audit


def test_untrusted_origin_is_rejected():
    assert not speech_api.origin_allowed("https://evil.example")
    assert not speech_api.origin_allowed("null")
    assert speech_api.origin_allowed("http://127.0.0.1:5173")
