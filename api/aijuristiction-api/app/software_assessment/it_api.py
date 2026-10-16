"""Distinct organizational IT resource backed by shared assessment safeguards."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import Field

from aijurisdictionagents.api_db import ApiDatabaseStore
from app.cases_api import _ensure_case_access, get_store
from app.document_review import require_review_user
from app.security import require_api_key
from app.software_assessment import api as shared
from app.software_assessment.models import AssessmentRequest, SoftwareFacts
from app.software_assessment.organizational_it import ITContext


class OrganizationalFacts(SoftwareFacts):
    it_context: ITContext = Field(default_factory=ITContext)


class ITAssessmentRequest(AssessmentRequest):
    facts: OrganizationalFacts


router = APIRouter(prefix="/v1/cases/{case_id}/it-assessments", tags=["organizational-it"],
                   dependencies=[Depends(require_api_key), Depends(require_review_user)])


@router.post("", status_code=201)
def create(case_id: str, user_id: str, request: ITAssessmentRequest,
           store: ApiDatabaseStore = Depends(get_store)) -> dict[str, Any]:
    return shared.create_assessment(case_id, user_id, request, store)


@router.get("")
def list_assessments(case_id: str, user_id: str,
                     store: ApiDatabaseStore = Depends(get_store)) -> dict[str, Any]:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    return {"items": [{key: item[key] for key in ("assessment_id", "revision", "created_at", "warning")}
                      for item in store.list_software_assessments(case_id=case_id)
                      if item.get("kind") == "organizational_it"]}


# Read/review/delete share the existing authenticated case-private resource contract.
# Document generation and export are intentionally not registered here.
router.add_api_route("/{assessment_id}", shared.get_assessment, methods=["GET"])
router.add_api_route("/{assessment_id}", shared.delete_assessment, methods=["DELETE"], status_code=204)
router.add_api_route("/{assessment_id}/actions/{action_id}", shared.decide_action, methods=["PATCH"])
router.add_api_route("/{assessment_id}/supplier-checklist/{item_index}", shared.review_supplier, methods=["PATCH"])
