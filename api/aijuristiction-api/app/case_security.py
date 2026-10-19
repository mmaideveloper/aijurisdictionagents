from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from aijurisdictionagents.api_db import ApiDatabaseStore


def auth_store() -> ApiDatabaseStore:
    from app.cases_api import get_store
    return get_store()


async def require_case_subject(request: Request, store: ApiDatabaseStore = Depends(auth_store)) -> str:

    payload = {}
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and "application/json" in request.headers.get("content-type", ""):
        if await request.body():
            try:
                payload = await request.json()
            except ValueError:
                raise HTTPException(422, "Invalid JSON request") from None
            if not isinstance(payload, dict):
                raise HTTPException(422, "JSON object required")
    subject = str(request.query_params.get("user_id") or payload.get("user_id") or request.headers.get("x-jurisdigta-user-id", ""))
    if payload.get("user_id") and str(payload["user_id"]) != subject:
        raise HTTPException(403, "Identity mismatch")
    user = store.authenticate_user_device_auth_token(user_id=subject, device_id=request.headers.get("x-jurisdigta-device-id", ""), token=request.headers.get("x-jurisdigta-device-token", ""))
    if user is None or not user.is_enabled:
        raise HTTPException(401, "Authentication required")
    case_id = request.path_params.get("case_id") or payload.get("case_id") or request.query_params.get("case_id")
    if case_id:
        try:
            case = store.get_case(case_id=str(case_id))
        except KeyError:
            raise HTTPException(404, "Case not found") from None
        if case.user_id != subject or case.status == "deleted":
            raise HTTPException(404, "Case not found")
    return subject
