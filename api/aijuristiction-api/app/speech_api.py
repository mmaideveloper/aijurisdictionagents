"""Authenticated, consent-bound streaming dictation; never writes a chat message."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import hashlib
import json
import os
import re
import time
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

from app.auth.service import validate_api_key
from app.cases_api import get_store, _ensure_case_access
from app.security import require_api_key
from app.speech_stream import AzureSpeechStream, SpeechStream
from aijurisdictionagents.api_db import ApiDatabaseStore, AIModelRouteSelection

router = APIRouter(prefix="/v1/speech", tags=["speech"])
MAX_SECONDS = 120
MAX_BYTES = 16000 * 2 * MAX_SECONDS
MAX_CHUNK = 16000
_active: set[str] = set()


class SpeechIdentity(BaseModel):
    user_id: str = Field(max_length=100)
    device_id: str = Field(max_length=200)
    device_token: str = Field(max_length=2000)


class Start(SpeechIdentity):
    type: Literal["start"]
    api_key: str = Field(max_length=2000)
    case_id: str = Field(min_length=1, max_length=100)
    locale: Literal["sk-SK", "en-US", "de-DE"]
    consent: Literal[True]
    route_revision: str = Field(min_length=1, max_length=64)
    format: Literal["pcm_s16le_16000_mono"]


def authenticate(store: ApiDatabaseStore, identity: SpeechIdentity) -> Any:
    if not identity.user_id or not identity.device_id or not identity.device_token:
        raise HTTPException(401, "authentication_required")
    user = store.authenticate_user_device_auth_token(
        user_id=identity.user_id, device_id=identity.device_id, token=identity.device_token
    )
    if user is None or not user.is_enabled:
        raise HTTPException(401, "authentication_required")
    return user


def speech_route(store: ApiDatabaseStore, user_id: str, case_id: str) -> AIModelRouteSelection:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    try:
        route = store.resolve_speech_route(user_id=user_id, case_id=case_id)
    except (ValueError, KeyError):
        raise HTTPException(409, "route_unavailable") from None
    if route.provider is None or route.model_profile is None:
        raise HTTPException(409, "route_unavailable")
    if not route.provider.is_external or route.provider.is_local:
        raise HTTPException(409, "route_unavailable")
    if route.provider.provider_type != "azure_speech" or not re.fullmatch(r"[a-z0-9-]{3,40}", route.provider.region):
        raise HTTPException(409, "route_unavailable")
    return route


def public_route(route: AIModelRouteSelection) -> dict[str, Any]:
    provider, profile = route.provider, route.model_profile
    assert provider is not None and profile is not None
    revision = hashlib.sha256(json.dumps([
        provider.provider_id, provider.updated_at, profile.model_profile_id, profile.updated_at,
        route.policy.updated_at if route.policy else "", route.route_type,
    ]).encode()).hexdigest()
    return {"provider": provider.display_name, "model": profile.model_code,
            "model_profile_id": profile.model_profile_id, "region": provider.region,
            "external": provider.is_external, "route_type": route.route_type,
            "route_revision": revision, "max_seconds": MAX_SECONDS,
            "locales": str(profile.model_parameters.get("locales", "sk-SK,en-US,de-DE")).split(",")}


@router.get("/cases/{case_id}/route", dependencies=[Depends(require_api_key)])
def get_route(case_id: str, user_id: str, store: ApiDatabaseStore = Depends(get_store),
              device_id: str = Header(default="", alias="x-jurisdigta-device-id"),
              device_token: str = Header(default="", alias="x-jurisdigta-device-token")) -> dict[str, Any]:
    user = authenticate(store, SpeechIdentity(user_id=user_id, device_id=device_id, device_token=device_token))
    result = public_route(speech_route(store, user_id, case_id))
    result["profiles"] = []
    if user.role == "admin":
        for profile in store.list_ai_model_profiles():
            try:
                candidate = store.resolve_speech_route(user_id=user_id, case_id=case_id,
                    candidate_profile_id=profile.model_profile_id)
            except (ValueError, KeyError):
                continue
            provider = candidate.provider
            if (provider is not None and provider.provider_type == "azure_speech"
                    and provider.is_external and not provider.is_local
                    and re.fullmatch(r"[a-z0-9-]{3,40}", provider.region)):
                result["profiles"].append({"id": profile.model_profile_id, "label": profile.model_code})
    return result


class Override(BaseModel):
    model_profile_id: str | None = Field(default=None, max_length=100)


@router.put("/cases/{case_id}/override", dependencies=[Depends(require_api_key)])
def set_override(case_id: str, user_id: str, payload: Override,
                 store: ApiDatabaseStore = Depends(get_store),
                 device_id: str = Header(default="", alias="x-jurisdigta-device-id"),
                 device_token: str = Header(default="", alias="x-jurisdigta-device-token")) -> dict[str, bool]:
    user = authenticate(store, SpeechIdentity(user_id=user_id, device_id=device_id, device_token=device_token))
    if user.role != "admin":
        raise HTTPException(403, "admin_required")
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    if payload.model_profile_id:
        profiles = get_route(case_id, user_id, store, device_id, device_token)["profiles"]
        if not any(p["id"] == payload.model_profile_id for p in profiles):
            raise HTTPException(422, "incompatible_profile")
        try:
            store.resolve_speech_route(user_id=user_id, case_id=case_id, candidate_profile_id=payload.model_profile_id)
        except ValueError:
            raise HTTPException(422, "incompatible_profile") from None
    store.set_case_speech_override(case_id=case_id, model_profile_id=payload.model_profile_id)
    store.record_ai_model_admin_audit_event(admin_user_id=user_id, admin_email=user.email,
        action="speech_override", entity_type="case", entity_id=case_id,
        new_value_summary={"model_profile_id": payload.model_profile_id}, reason="Explicit STT-only selection")
    return {"saved": True}


def create_stream(store: ApiDatabaseStore, route: AIModelRouteSelection, locale: str) -> SpeechStream:
    assert route.provider is not None
    keys = [c.secret_value for c in store.list_ai_model_credentials(provider_id=route.provider.provider_id, reveal=True)
            if c.enabled and c.secret_type == "api_key" and c.secret_value]
    if len(keys) != 1:
        raise HTTPException(503, "speech_credential_unavailable")
    return AzureSpeechStream(key=str(keys[0]), region=route.provider.region, locale=locale)


def origin_allowed(origin: str | None) -> bool:
    # Native mobile clients have no Origin; they still require device authentication.
    if origin is None:
        return True
    allowed = {"https://agent.jurisdigta.eu", "https://web.jurisdigta.eu"}
    allowed.update(x.strip() for x in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if x.strip() != "*")
    return origin in allowed or bool(re.fullmatch(r"http://(localhost|127\.0\.0\.1):[0-9]{2,5}", origin))


@router.websocket("/stream")
async def stream_speech(ws: WebSocket, store: ApiDatabaseStore = Depends(get_store)) -> None:
    if not origin_allowed(ws.headers.get("origin")):
        await ws.close(code=1008)
        return
    await ws.accept()
    session_id = str(uuid4())
    started = time.monotonic()
    stream: SpeechStream | None = None
    sender: asyncio.Task[None] | None = None
    identity: Start | None = None
    admitted = False
    byte_count = 0
    outcome = "failed"
    route_info: dict[str, Any] = {}
    send_lock = asyncio.Lock()
    final_count = 0
    provider_failed = False

    async def send(event: dict[str, Any]) -> None:
        async with send_lock:
            await asyncio.wait_for(ws.send_json({**event, "session_id": session_id}), 5)

    async def forward() -> None:
        nonlocal final_count, provider_failed
        assert stream is not None
        while True:
            event = await stream.events.get()
            if event["type"] == "final":
                final_count += 1
            if event["type"] == "error":
                provider_failed = True
            try:
                await send(event)
            finally:
                stream.events.task_done()
            if provider_failed:
                await ws.close(code=1011)
                return

    try:
        raw = await asyncio.wait_for(ws.receive_text(), 10)
        if len(raw) > 8192:
            raise HTTPException(422, "invalid_start")
        identity = Start.model_validate_json(raw)
        validate_api_key(identity.api_key)
        authenticate(store, identity)
        if identity.user_id in _active or len(_active) >= 20:
            raise HTTPException(429, "busy")
        route = speech_route(store, identity.user_id, identity.case_id)
        route_info = public_route(route)
        if identity.route_revision != route_info["route_revision"]:
            raise HTTPException(409, "route_changed")
        if identity.locale not in route_info["locales"]:
            raise HTTPException(422, "locale_unavailable")
        _active.add(identity.user_id)
        admitted = True
        store.record_ai_model_admin_audit_event(admin_user_id=identity.user_id, admin_email="",
            action="speech_consent", entity_type="case", entity_id=identity.case_id,
            new_value_summary={**route_info, "locale": identity.locale, "consent_version": "speech-v1"},
            correlation_id=session_id)
        stream = create_stream(store, route, identity.locale)
        await asyncio.wait_for(stream.start(), 15)
        sender = asyncio.create_task(forward())
        await send({"type": "ready", **route_info})
        deadline = time.monotonic() + MAX_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HTTPException(422, "duration_limit")
            packet = await asyncio.wait_for(ws.receive(), min(remaining, 15))
            if packet["type"] == "websocket.disconnect":
                outcome = "disconnected"
                break
            pcm = packet.get("bytes")
            if pcm is not None:
                byte_count += len(pcm)
                if not pcm or len(pcm) > MAX_CHUNK or len(pcm) % 2 or byte_count > MAX_BYTES:
                    raise HTTPException(422, "audio_limit")
                await stream.write(pcm)
                continue
            control = packet.get("text", "")
            if len(control) > 100:
                raise HTTPException(422, "invalid_control")
            command = json.loads(control)
            if command == {"type": "cancel"}:
                outcome = "cancelled"
                await send({"type": "cancelled"})
                break
            if command != {"type": "stop"}:
                raise HTTPException(422, "invalid_control")
            await stream.finish()
            await asyncio.wait_for(stream.events.join(), 5)
            if provider_failed:
                break
            if not final_count:
                raise HTTPException(422, "no_speech")
            outcome = "completed"
            await send({"type": "done"})
            break
    except WebSocketDisconnect:
        outcome = "disconnected"
    except (ValidationError, json.JSONDecodeError):
        with suppress(Exception):
            await send({"type": "error", "code": "invalid_request"})
    except HTTPException as exc:
        with suppress(Exception):
            await send({"type": "error", "code": str(exc.detail) if exc.status_code != 401 else "authentication_required"})
    except TimeoutError:
        with suppress(Exception):
            await send({"type": "error", "code": "timeout"})
    except Exception:
        # Provider errors can contain credentials and audio metadata. Never forward/log them.
        with suppress(Exception):
            await send({"type": "error", "code": "provider_failed"})
    finally:
        if sender:
            sender.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await sender
        if stream:
            with suppress(Exception):
                await stream.close()
        if admitted and identity:
            _active.discard(identity.user_id)
            store.record_ai_model_admin_audit_event(admin_user_id=identity.user_id, admin_email="",
                action="speech_outcome", entity_type="case", entity_id=identity.case_id,
                new_value_summary={"outcome": outcome, "bytes": byte_count,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "profile": route_info.get("model_profile_id"), "task_type": "speech_transcription"},
                correlation_id=session_id)
        with suppress(Exception):
            await ws.close()
