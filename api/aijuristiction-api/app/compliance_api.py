from __future__ import annotations

from dataclasses import asdict
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.security import require_api_key
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.compliance import CONSENT_SCOPES, ComplianceService


router = APIRouter(
    prefix="/v1/compliance",
    tags=["compliance"],
    dependencies=[Depends(require_api_key)],
)


class ConsentDecisionRequest(BaseModel):
    scope: str = Field(min_length=3, max_length=80)
    notice_version: str = Field(min_length=1, max_length=80)
    granted: bool
    source: Literal["ui", "api", "registration", "operator"] = "api"
    country: str = Field(default="", max_length=8)
    purpose: str = Field(default="", max_length=250)
    session_id: str = Field(default="", max_length=200)
    expires_at: str | None = None


class ProcessingRestrictionRequest(BaseModel):
    restricted: bool = True
    reason_code: str = Field(min_length=2, max_length=80)


class DsarActionRequest(BaseModel):
    action: Literal["delete", "anonymize"]
    confirmed: bool = False


class RetentionRunRequest(BaseModel):
    confirmed: bool = False


def get_compliance_service() -> ComplianceService:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return ComplianceService(store)


@router.get("/consent-scopes", response_model=list[str])
def list_consent_scopes() -> list[str]:
    return sorted(CONSENT_SCOPES)


@router.get("/users/{user_id}/consents")
def list_consents(
    user_id: str,
    service: ComplianceService = Depends(get_compliance_service),
) -> dict[str, object]:
    return {"user_id": user_id, "events": [asdict(item) for item in service.list_consents(user_id=user_id)]}


@router.post("/users/{user_id}/consents", status_code=status.HTTP_201_CREATED)
def record_consent(
    user_id: str,
    payload: ConsentDecisionRequest,
    request: Request,
    service: ComplianceService = Depends(get_compliance_service),
) -> dict[str, object]:
    try:
        event = service.record_consent(
            user_id=user_id,
            scope=payload.scope,
            notice_version=payload.notice_version,
            granted=payload.granted,
            source=payload.source,
            country=payload.country,
            purpose=payload.purpose,
            session_id=payload.session_id,
            expires_at=payload.expires_at,
            correlation_id=getattr(request.state, "correlation_id", ""),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return asdict(event)


@router.get("/users/{user_id}/processing-restriction")
def get_processing_restriction(
    user_id: str,
    service: ComplianceService = Depends(get_compliance_service),
) -> dict[str, object]:
    return {"user_id": user_id, "restricted": service.is_processing_restricted(user_id=user_id)}


@router.put("/users/{user_id}/processing-restriction")
def set_processing_restriction(
    user_id: str,
    payload: ProcessingRestrictionRequest,
    request: Request,
    service: ComplianceService = Depends(get_compliance_service),
) -> dict[str, object]:
    try:
        service.set_processing_restriction(
            user_id=user_id,
            restricted=payload.restricted,
            reason_code=payload.reason_code,
            correlation_id=getattr(request.state, "correlation_id", ""),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"user_id": user_id, "restricted": payload.restricted}


@router.get("/users/{user_id}/dsar/export")
def export_subject_data(
    user_id: str,
    service: ComplianceService = Depends(get_compliance_service),
) -> dict[str, object]:
    try:
        return cast(dict[str, object], service.export_subject_data(user_id=user_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/users/{user_id}/dsar/actions")
def execute_dsar_action(
    user_id: str,
    payload: DsarActionRequest,
    request: Request,
    service: ComplianceService = Depends(get_compliance_service),
) -> dict[str, object]:
    if not payload.confirmed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Explicit confirmation is required for irreversible DSAR erasure.",
        )
    try:
        return cast(
            dict[str, object],
            service.erase_subject_data(
                user_id=user_id,
                mode=payload.action,
                correlation_id=getattr(request.state, "correlation_id", ""),
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/retention/run")
def run_retention(
    payload: RetentionRunRequest,
    service: ComplianceService = Depends(get_compliance_service),
) -> dict[str, object]:
    if not payload.confirmed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Explicit operator confirmation is required for retention deletion.",
        )
    return cast(dict[str, object], asdict(service.run_retention()))


@router.head("/retention/run", include_in_schema=False)
def retention_capability() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
