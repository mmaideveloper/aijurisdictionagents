from __future__ import annotations

import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+421|00421|0)\s*(?:\d[\s-]*){9}(?!\d)"), "[PHONE]"),
    (re.compile(r"(?<!\d)\d{6}\s*/\s*\d{3,4}(?!\d)"), "[IDENTIFIER]"),
    (re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b"), "[DATE]"),
    (re.compile(r"\b\d{6}/\d{3,4}\b"), "[IDENTIFIER]"),
    (re.compile(r"\b[A-Z][a-z]+ova\s+[A-Z][a-z]+\b"), "[PERSON]"),
    (re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b"), "[PERSON]"),
    (re.compile(r"\b(?:ul\.|ulica)\s+[A-Z0-9][^,\n]{2,80}", re.IGNORECASE), "[ADDRESS]"),
)

_RESIDUAL_HIGH_RISK_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?<!\d)(?:\+421|00421|0)\s*(?:\d[\s-]*){9}(?!\d)"),
    re.compile(r"(?<!\d)\d{6}\s*/\s*\d{3,4}(?!\d)"),
)


def pseudonymize_court_decision_text(text: str) -> str:
    """Best-effort public-view pseudonymization before exposing decision text."""
    sanitized = text
    for pattern, replacement in _PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def validate_pseudonymized_court_decision_text(text: str) -> None:
    """Fail closed when a public derivative still contains high-risk direct identifiers."""

    if not text.strip():
        raise UnsafePseudonymizationError("Pseudonymized court-decision text is empty")
    if any(pattern.search(text) for pattern in _RESIDUAL_HIGH_RISK_PATTERNS):
        raise UnsafePseudonymizationError("Pseudonymized text contains a residual direct identifier")


class UnsafePseudonymizationError(ValueError):
    pass
