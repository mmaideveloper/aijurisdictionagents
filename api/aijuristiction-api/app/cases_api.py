from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.security import require_api_key

from aijurisdictionagents.api_db import ApiDatabaseStore, Case

router = APIRouter(prefix='/v1/cases', tags=['cases'], dependencies=[Depends(require_api_key)])
_MAX_ACTIVE_CASES = 5


class CaseResponse(BaseModel):
    case_id: str
    user_id: str
    company_id: str | None = None
    title: str
    status: str
    created_at: str
    updated_at: str


class CreateCaseRequest(BaseModel):
    user_id: str = Field(min_length=1)
    title: str = Field(min_length=1)


class UpdateCaseRequest(BaseModel):
    user_id: str = Field(min_length=1)
    title: str = Field(min_length=1)


def get_store() -> ApiDatabaseStore:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


@router.get('', response_model=list[CaseResponse])
def list_cases(user_id: str, store: ApiDatabaseStore = Depends(get_store)) -> list[CaseResponse]:
    return [_to_case_response(item) for item in store.list_cases(user_id=user_id)]


@router.post('', response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(payload: CreateCaseRequest, store: ApiDatabaseStore = Depends(get_store)) -> CaseResponse:
    active = store.count_active_cases(user_id=payload.user_id)
    if active >= _MAX_ACTIVE_CASES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Maximum number of cases reached ({_MAX_ACTIVE_CASES})',
        )
    case = store.create_case(user_id=payload.user_id, company_id=None, title=payload.title.strip())
    return _to_case_response(case)


@router.patch('/{case_id}', response_model=CaseResponse)
def rename_case(case_id: str, payload: UpdateCaseRequest, store: ApiDatabaseStore = Depends(get_store)) -> CaseResponse:
    try:
        case = store.update_case_title(case_id=case_id, user_id=payload.user_id, title=payload.title.strip())
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_case_response(case)


@router.delete('/{case_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: str, user_id: str, store: ApiDatabaseStore = Depends(get_store)) -> None:
    try:
        store.soft_delete_case(case_id=case_id, user_id=user_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _to_case_response(case: Case) -> CaseResponse:
    return CaseResponse(
        case_id=case.case_id,
        user_id=case.user_id,
        company_id=case.company_id,
        title=case.title,
        status=case.status,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )
