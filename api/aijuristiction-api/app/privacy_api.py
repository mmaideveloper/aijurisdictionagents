from __future__ import annotations

from collections.abc import Iterator
import json
from tempfile import SpooledTemporaryFile
from typing import Any, Literal, cast
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.cases_api import get_store
from app.security import require_api_key, require_admin_api_key
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.privacy import CONSENT_SCOPES, CONSENT_VERSION, PrivacyControls, PrivacyDenied

router = APIRouter(prefix="/v1/privacy", tags=["privacy"], dependencies=[Depends(require_api_key)])


def authenticate_subject(
    user_id: str,
    device_id: str = Header(default="", alias="x-jurisdigta-device-id"),
    device_token: str = Header(default="", alias="x-jurisdigta-device-token"),
    store: ApiDatabaseStore = Depends(get_store),
) -> str:
    user = store.authenticate_user_device_auth_token(user_id=user_id, device_id=device_id, token=device_token)
    if user is None or not user.is_enabled:
        raise HTTPException(401, "Authentication required")
    return str(user.user_id)


class ConsentRequest(BaseModel):
    scope: Literal["external_models", "external_checks", "marketing", "sensitive_processing"]
    text_version: str
    granted: bool


class RestrictionRequest(BaseModel):
    restricted: bool


class ErasureRequest(BaseModel):
    operation: Literal["delete", "anonymize"] = "delete"


class ReviewRequest(BaseModel):
    approved: bool


class SubjectPolicyRequest(BaseModel):
    legal_hold: bool
    sensitive_consent_required: bool


@router.get("/subjects/{user_id}")
def privacy_status(response: Response, user_id: str = Depends(authenticate_subject), store: ApiDatabaseStore = Depends(get_store)) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    controls = PrivacyControls(store)
    return {"notice_version": CONSENT_VERSION, "scopes": CONSENT_SCOPES,
            "consents": {scope: controls.has_consent(user_id, scope) for scope in CONSENT_SCOPES},
            **controls.state(user_id), "requests": controls.requests(user_id)}


@router.post("/subjects/{user_id}/consents")
def record_consent(payload: ConsentRequest, user_id: str = Depends(authenticate_subject), store: ApiDatabaseStore = Depends(get_store)) -> dict[str, str]:
    try:
        event = PrivacyControls(store).consent(user_id, payload.scope, payload.granted, version=payload.text_version)
    except ValueError as exc:
        raise HTTPException(409, "Refresh the current consent notice before deciding") from exc
    return {"event_id": event}


@router.put("/subjects/{user_id}/restriction")
def restrict_subject(payload: RestrictionRequest, user_id: str = Depends(authenticate_subject), store: ApiDatabaseStore = Depends(get_store)) -> dict[str, bool]:
    controls = PrivacyControls(store)
    if not payload.restricted and any(item["status"] in {"pending_review", "approved_pending_execution"} for item in controls.requests(user_id)):
        raise HTTPException(409, "An erasure request is pending operator review or execution")
    controls.restrict(user_id, payload.restricted)
    return cast(dict[str, bool], controls.state(user_id))


@router.post("/subjects/{user_id}/requests", status_code=202)
def request_erasure(payload: ErasureRequest, user_id: str = Depends(authenticate_subject), store: ApiDatabaseStore = Depends(get_store)) -> dict[str, str]:
    return {"request_id": PrivacyControls(store).request_erasure(user_id, payload.operation), "status": "pending_review"}


@router.get("/subjects/{user_id}/export")
def export_subject(user_id: str = Depends(authenticate_subject), store: ApiDatabaseStore = Depends(get_store)) -> StreamingResponse:
    from app.chat.api import _repository
    data = PrivacyControls(store).export(user_id)
    data["active_sessions"] = _repository.export_subject(user_id)
    files = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    try:
        manifest: list[dict[str, str]] = []
        with ZipFile(files, "w", compression=ZIP_DEFLATED) as archive:
            for case in store.list_cases(user_id=user_id, include_deleted=True):
                assets = [(doc.doc_id, doc.storage_uri, "document") for doc in store.list_case_documents(case_id=case.case_id)]
                assets += [(item.communication_id, item.transcript_uri, "transcript") for item in store.list_case_communications(case_id=case.case_id) if item.transcript_uri]
                for index, (asset_id, uri, kind) in enumerate(assets):
                    if not uri:
                        continue
                    # Generated member names never use user-controlled filenames or storage paths.
                    member = f"files/{len(manifest)}-{index}.bin"
                    try:
                        path = store._resolve_storage_path(uri)
                        archive.write(path, member)
                        status = "included"
                    except (OSError, ValueError):
                        status = "unavailable_operator_followup_required"
                    manifest.append({"id": asset_id, "kind": kind, "member": member if status == "included" else "", "status": status})
            data["file_manifest"] = manifest
            archive.writestr("personal-data.json", json.dumps(data, ensure_ascii=False, indent=2))
        files.seek(0)
    except BaseException:
        files.close()
        raise

    def chunks() -> Iterator[bytes]:
        try:
            while block := files.read(65536):
                yield block
        finally:
            files.close()

    return StreamingResponse(chunks(), media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="privacy-export.zip"', "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/operator/requests", dependencies=[Depends(require_admin_api_key)])
def operator_requests(store: ApiDatabaseStore = Depends(get_store)) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], PrivacyControls(store).requests())


@router.put("/operator/subjects/{user_id}/policy", dependencies=[Depends(require_admin_api_key)])
def subject_policy(user_id: str, payload: SubjectPolicyRequest, store: ApiDatabaseStore = Depends(get_store)) -> dict[str, bool]:
    controls = PrivacyControls(store)
    controls.set_policy(user_id, legal_hold=payload.legal_hold, sensitive_consent_required=payload.sensitive_consent_required)
    return cast(dict[str, bool], controls.state(user_id))


@router.post("/operator/requests/{request_id}/review", dependencies=[Depends(require_admin_api_key)])
def review_request(request_id: str, payload: ReviewRequest, store: ApiDatabaseStore = Depends(get_store)) -> dict[str, str]:
    try:
        status = PrivacyControls(store).review_erasure(request_id, payload.approved)
    except KeyError as exc:
        raise HTTPException(404, "Privacy request not found") from exc
    except (ValueError, PrivacyDenied) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": status, "next_step": "Complete the documented operator erasure checklist; approval does not mean erased."}
