from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.cases_api import get_store
from app.security import require_api_key
from app.voice_intent import VoiceIntentName, classify_voice_intent
from aijurisdictionagents.api_db import ApiDatabaseStore

router = APIRouter(prefix="/v1/voice", tags=["voice"], dependencies=[Depends(require_api_key)])
_LOGGER = logging.getLogger(__name__)


class VoiceIntentRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=4000)
    user_id: str | None = Field(default=None, min_length=1)
    case_id: str | None = Field(default=None, min_length=1)
    language_code: str | None = Field(default=None, min_length=2, max_length=8)
    client_type: Literal["mobile", "web", "api"] = "api"
    execute: bool = False


class VoiceIntentExecutionResult(BaseModel):
    status: Literal["executed", "not_executed"]
    case_id: str | None = None
    title: str | None = None
    message: str | None = None


class VoiceIntentResponse(BaseModel):
    intent: str
    confidence: float
    slots: dict[str, str]
    requires_confirmation: bool
    clarification_question: str | None
    routing_strategy: str
    transcript_redaction_hint: str
    execution: VoiceIntentExecutionResult


@router.post("/intent", response_model=VoiceIntentResponse)
def route_voice_intent(
    payload: VoiceIntentRequest,
    store: ApiDatabaseStore = Depends(get_store),
) -> VoiceIntentResponse:
    decision = classify_voice_intent(payload.transcript, language_code=payload.language_code)
    execution = VoiceIntentExecutionResult(status="not_executed")

    if payload.execute and decision.intent == VoiceIntentName.CREATE_CASE:
        execution = _execute_create_case(payload=payload, title=decision.slots.get("title"), store=store)

    _LOGGER.info(
        "Voice intent routed | client_type=%s intent=%s confidence=%.2f execute=%s redaction=%s",
        payload.client_type,
        decision.intent.value,
        decision.confidence,
        payload.execute,
        decision.transcript_redaction_hint,
    )
    return VoiceIntentResponse(
        intent=decision.intent.value,
        confidence=decision.confidence,
        slots=decision.slots,
        requires_confirmation=decision.requires_confirmation,
        clarification_question=decision.clarification_question,
        routing_strategy=decision.routing_strategy,
        transcript_redaction_hint=decision.transcript_redaction_hint,
        execution=execution,
    )


def _execute_create_case(
    *,
    payload: VoiceIntentRequest,
    title: str | None,
    store: ApiDatabaseStore,
) -> VoiceIntentExecutionResult:
    if not payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="user_id is required when executing create_case.",
        )
    if not title:
        return VoiceIntentExecutionResult(
            status="not_executed",
            message="Case title is required before creating a case.",
        )
    active = store.count_active_cases(user_id=payload.user_id)
    max_active_cases = store.get_case_limit(user_id=payload.user_id)
    if active >= max_active_cases:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Maximum number of cases reached ({max_active_cases})",
        )
    case = store.create_case(user_id=payload.user_id, company_id=None, title=title.strip())
    return VoiceIntentExecutionResult(
        status="executed",
        case_id=case.case_id,
        title=case.title,
    )
