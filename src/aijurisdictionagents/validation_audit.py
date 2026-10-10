"""Metadata-only observations of checks actually invoked by the runtime."""
from __future__ import annotations

from contextlib import contextmanager
import re
import time
from typing import Iterator
from uuid import uuid4

from . import __version__
from .correlation import child_operation, record_debug_event

CATEGORIES = (
    "input_structure", "input_security", "output_quality", "output_security",
    "grounding", "hallucination_assessment",
)
_REASONS = frozenset({
    "required_facts_present", "required_facts_missing", "unresolved_placeholder",
    "empty_document_draft", "verified_fact_missing_from_output", "verified_facts_preserved",
    "tool_executed_without_consent", "legal_provenance_missing", "privacy_and_provenance_passed",
    "output_present", "output_missing", "privacy_policy_passed", "empty_output",
    "profile_section_unchanged", "profile_section_rewritten",
})
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,199}$")


def identifier(value: object) -> str | None:
    return value if isinstance(value, str) and _ID.fullmatch(value) else None


@contextmanager
def validation_check(
    *, category: str, validator_id: str, artifact_id: str | None,
    validator_version: str | None = None,
) -> Iterator[dict[str, object]]:
    if category not in CATEGORIES:
        raise ValueError("Unknown validation category")
    result: dict[str, object] = {}
    started = time.monotonic()
    execution_id = str(uuid4())
    with child_operation():
        try:
            yield result
        except Exception:
            result = {"outcome": "error", "decision": "error", "reason_code": "validator_error"}
            raise
        finally:
            outcome = result.get("outcome", "missing_evidence")
            if outcome not in {"passed", "failed", "blocked", "error", "not_run", "unsupported"}:
                outcome = "missing_evidence"
            reason = result.get("reason_code")
            record_debug_event("validation", "check", str(outcome), {
                "schema_version": 1, "category": category,
                "execution_id": execution_id, "validator_id": identifier(validator_id),
                "validator_version": identifier(validator_version), "instrumentation_version": __version__,
                "artifact_id": identifier(artifact_id),
                "artifact_link_status": "recorded" if identifier(artifact_id) else "missing_evidence",
                "outcome": outcome,
                "reason_code": reason if reason in _REASONS or reason == "validator_error" else "reason_unavailable",
                "decision": result.get("decision") if result.get("decision") in {
                    "continue", "rewrite", "collect_input", "human_review", "block", "error",
                } else "unavailable",
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "score": None, "score_status": "not_produced",
            })
