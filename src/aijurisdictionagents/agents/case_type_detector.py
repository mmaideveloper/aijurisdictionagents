from __future__ import annotations

import json
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Sequence

from ..llm import LLMClient
from ..schemas import Document, Message


@dataclass(frozen=True)
class CaseTypeCandidate:
    case_type_id: str
    case_type_key: str
    name: str
    description: str
    keywords: tuple[str, ...]
    has_prompt: bool
    template_titles: tuple[str, ...]


@dataclass(frozen=True)
class CaseTypeDetectionResult:
    status: str
    selected_case_type_key: str | None
    confidence: float
    second_case_type_key: str | None
    second_confidence: float
    clarification_question: str
    rationale: str


class AICaseTypeDetectionAgent:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def detect(
        self,
        *,
        request_text: str,
        country: str,
        candidates: Sequence[CaseTypeCandidate],
        verified_facts: Mapping[str, str] | None = None,
    ) -> CaseTypeDetectionResult:
        if not candidates:
            return CaseTypeDetectionResult(
                status="no_match",
                selected_case_type_key=None,
                confidence=0.0,
                second_case_type_key=None,
                second_confidence=0.0,
                clarification_question="",
                rationale="No case-type candidates were available.",
            )
        llm_complete = getattr(self._llm, "complete", None)
        if not callable(llm_complete):
            return CaseTypeDetectionResult(
                status="no_match",
                selected_case_type_key=None,
                confidence=0.0,
                second_case_type_key=None,
                second_confidence=0.0,
                clarification_question="",
                rationale="LLM client does not support case-type detection completion.",
            )
        payload = [
            {
                "case_type_id": item.case_type_id,
                "case_type_key": item.case_type_key,
                "name": item.name,
                "description": item.description,
                "keywords": list(item.keywords),
                "has_prompt": item.has_prompt,
                "template_titles": list(item.template_titles),
            }
            for item in candidates
        ]
        minimized_facts = {
            str(key).strip()[:100]: " ".join(str(value).split())[:500]
            for key, value in sorted((verified_facts or {}).items())[:50]
            if str(key).strip() and str(value).strip()
        }
        verified_fact_text = json.dumps(minimized_facts, ensure_ascii=False, indent=2)
        conversation = [
            Message(
                role="user",
                agent_name="User",
                content=(
                    f"Country/jurisdiction: {country.strip().upper() or 'unknown'}\n"
                    f"Current user question:\n{request_text.strip()[:12000]}\n\n"
                    f"Verified case facts only:\n{verified_fact_text}"
                ),
            )
        ]
        documents = [
            Document(
                doc_id="case-type-candidates",
                path="case-type-candidates.json",
                content=json.dumps(payload, ensure_ascii=False, indent=2),
            )
        ]
        raw_response = llm_complete(
            "AICaseTypeDetectionAgent",
            _CASE_TYPE_DETECTION_PROMPT,
            conversation,
            documents,
        )
        return _parse_detection_response(raw_response)


_CASE_TYPE_DETECTION_PROMPT = """
You are AICaseTypeDetectionAgent for JurisDigta.

Task:
- Classify the current user question, using only the supplied verified facts as context, into one
  of the provided case types.
- Use only the supplied candidate catalog. Do not invent new case types.
- Never infer a case type from unverified personal data or unavailable conversation history.
- Prefer the candidate whose legal workflow and requested outcome fit best.
- If the request is too ambiguous, return status "ambiguous".
- If none of the candidates fit, return status "no_match".

Confidence rules:
- confidence is a float from 0.0 to 1.0.
- second_confidence is the confidence of the second-best candidate, or 0.0.
- Be conservative. Do not claim high confidence on vague facts.

Clarification rules:
- If status is "ambiguous", provide exactly one short clarification question.
- Otherwise clarification_question should be an empty string.

Return JSON only with this shape:
{
  "status": "matched|ambiguous|no_match",
  "selected_case_type_key": "..." or null,
  "confidence": 0.0,
  "second_case_type_key": "..." or null,
  "second_confidence": 0.0,
  "clarification_question": "",
  "rationale": ""
}
""".strip()


def _parse_detection_response(raw_response: str) -> CaseTypeDetectionResult:
    try:
        payload = json.loads(_extract_json_object(raw_response))
    except json.JSONDecodeError:
        payload = {}
    status = str(payload.get("status") or "no_match").strip().lower()
    if status not in {"matched", "ambiguous", "no_match"}:
        status = "no_match"
    selected_case_type_key = _optional_text(payload.get("selected_case_type_key"))
    second_case_type_key = _optional_text(payload.get("second_case_type_key"))
    confidence = _clamp_confidence(payload.get("confidence"))
    second_confidence = _clamp_confidence(payload.get("second_confidence"))
    clarification_question = str(payload.get("clarification_question") or "").strip()
    rationale = str(payload.get("rationale") or "").strip()
    if status != "ambiguous":
        clarification_question = ""
    if status == "matched" and not selected_case_type_key:
        status = "no_match"
        confidence = 0.0
    return CaseTypeDetectionResult(
        status=status,
        selected_case_type_key=selected_case_type_key,
        confidence=confidence,
        second_case_type_key=second_case_type_key,
        second_confidence=second_confidence,
        clarification_question=clarification_question,
        rationale=rationale,
    )


def _extract_json_object(raw_response: str) -> str:
    content = raw_response.strip()
    if content.startswith("{") and content.endswith("}"):
        return content
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        return content[start : end + 1]
    return "{}"


def _clamp_confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(parsed, 1.0))


def _optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None
