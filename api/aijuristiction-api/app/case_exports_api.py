from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import zipfile
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.case_security import require_case_subject
from app.cases_api import get_store, _build_case_export_zip
from app.security import require_api_key
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.case_exports import CaseExports, ExportDenied

router = APIRouter(prefix="/v1/case-exports", tags=["case-exports"], dependencies=[Depends(require_api_key)])
logger = logging.getLogger(__name__)


class ExportRequest(BaseModel):
    case_ids: list[str] = Field(min_length=1, max_length=50)
    purpose: str = Field(min_length=3, max_length=500)


class Decision(BaseModel):
    decision: Literal["approved", "denied", "revoked"]


@router.post("", status_code=202)
def request_export(payload: ExportRequest, user_id: str = Depends(require_case_subject), store: ApiDatabaseStore = Depends(get_store)) -> dict[str, str]:
    try:
        request_id = CaseExports(store).request(user_id, payload.case_ids, payload.purpose)
    except (ExportDenied, KeyError):
        raise HTTPException(403, "Export permission required or selected cases unavailable") from None
    return {"request_id": request_id, "status": "pending"}


@router.get("")
def list_exports(response: Response, admin: bool = False, user_id: str = Depends(require_case_subject), store: ApiDatabaseStore = Depends(get_store)) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return cast(list[dict[str, Any]], CaseExports(store).listing(user_id, admin=admin))
    except ExportDenied:
        raise HTTPException(403, "Export permission required") from None


@router.post("/{request_id}/decision")
def decide_export(request_id: str, payload: Decision, user_id: str = Depends(require_case_subject), store: ApiDatabaseStore = Depends(get_store)) -> dict[str, str]:
    try:
        CaseExports(store).decide(request_id, user_id, payload.decision)
    except ExportDenied:
        raise HTTPException(403, "Consent decision not permitted") from None
    return {"status": payload.decision}


@router.post("/{request_id}/download")
def download_export(request_id: str, user_id: str = Depends(require_case_subject), store: ApiDatabaseStore = Depends(get_store)) -> Response:
    try:
        data = CaseExports(store).download(request_id, user_id)
    except ExportDenied:
        raise HTTPException(403, "Export unavailable or consent no longer valid") from None
    return Response(data, media_type="application/zip", headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="consented-case-export.zip"'})


def process_exports(store: ApiDatabaseStore) -> None:
    service = CaseExports(store)
    service.cleanup()
    with store._connect() as conn:
        rows = store._execute(conn, "SELECT r.request_id FROM case_export_requests r WHERE r.status = 'pending' AND NOT EXISTS (SELECT 1 FROM case_export_grants g WHERE g.request_id = r.request_id AND g.decision <> 'approved')", ()).fetchall()
    for row in rows:
        request_id = str(row[0])

        def build(cases: list[tuple[str, str]]) -> bytes:
            maximum_bytes = 64 * 1024 * 1024
            source_bytes = 0
            for case_id, _ in cases:
                for document in store.list_case_documents(case_id=case_id):
                    source_bytes += store._resolve_storage_path(document.storage_uri).stat().st_size
                    if source_bytes > maximum_bytes:
                        raise ValueError("Export exceeds 64 MiB source limit; request smaller case sets")
            output = io.BytesIO()
            manifest = []
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for case_id, owner_id in cases:
                    data = _build_case_export_zip(case=store.get_case(case_id=case_id), user_id=owner_id, store=store, exported_by="consented-admin", correlation_id=request_id)
                    if len(data) + output.tell() > maximum_bytes:
                        raise ValueError("Export exceeds 64 MiB archive limit")
                    name = f"cases/{case_id}.zip"
                    archive.writestr(name, data)
                    manifest.append({"case_id": case_id, "member": name, "sha256": hashlib.sha256(data).hexdigest()})
                archive.writestr("manifest.json", json.dumps({"request_id": request_id, "cases": manifest}))
            return output.getvalue()

        try:
            service.generate(request_id, build)
        except ExportDenied:
            service.fail(request_id)
            continue
        except Exception:
            # No case text, exception detail, or credentials in operational logs.
            service.fail(request_id)
            logger.error("case_export_generation_failed request_id=%s", request_id)


async def export_worker(store: ApiDatabaseStore) -> None:
    while True:
        try:
            await asyncio.to_thread(process_exports, store)
        except Exception:
            logger.error("case_export_worker_failed")
        await asyncio.sleep(15)
