from __future__ import annotations

from collections.abc import AsyncIterator
import os
from uuid import UUID

from fastapi import HTTPException, Request

from aijurisdictionagents.privacy import PrivacyControls, PrivacyDenied, privacy_scope, privacy_problem


async def require_chat_subject(request: Request) -> AsyncIterator[None]:
    # Offline fixtures intentionally have no real model/subject; this is never
    # used as evidence for real E2E acceptance.
    if os.getenv("LLM_PROVIDER", "").strip().lower() == "mock":
        yield
        return
    from app.chat.api import _get_store, _repository
    payload = await request.json() if request.method in {"POST", "PATCH", "PUT"} else {}
    session_id = request.path_params.get("session_id") or payload.get("session_id")
    supplied_user = str(payload.get("user_id") or "")
    user_id = supplied_user
    if session_id:
        try:
            session = _repository.get_session(UUID(str(session_id)))
        except ValueError as exc:
            raise HTTPException(422, "Invalid session identifier") from exc
        if session is None:
            raise HTTPException(404, "Session not found")
        user_id = str(session.user_id or "")
        if supplied_user and supplied_user != user_id:
            raise HTTPException(403, "Session owner mismatch")
    store = _get_store()
    user = store.authenticate_user_device_auth_token(
        user_id=user_id,
        device_id=request.headers.get("x-jurisdigta-device-id", ""),
        token=request.headers.get("x-jurisdigta-device-token", ""),
    )
    if user is None or not user.is_enabled:
        raise HTTPException(401, "Authentication required")
    supplied_email = str(payload.get("user_email") or "").strip().lower()
    if supplied_email and supplied_email != user.email.strip().lower():
        raise HTTPException(403, "Authenticated identity mismatch")
    case_id = payload.get("case_id")
    if case_id:
        try:
            case = store.get_case(case_id=str(case_id))
        except KeyError as exc:
            raise HTTPException(404, "Case not found") from exc
        if case.user_id != user_id:
            raise HTTPException(403, "Case owner mismatch")
    controls = PrivacyControls(store)
    if request.method != "GET":
        try:
            controls.require_processing(user_id)
        except PrivacyDenied as exc:
            raise HTTPException(403, privacy_problem(str(exc))) from exc
    with privacy_scope(controls, user_id):
        yield
