from __future__ import annotations

import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b"), "[DATE]"),
    (re.compile(r"\b\d{6}/\d{3,4}\b"), "[IDENTIFIER]"),
    (re.compile(r"\b[A-Z][a-z]+ova\s+[A-Z][a-z]+\b"), "[PERSON]"),
    (re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b"), "[PERSON]"),
    (re.compile(r"\b(?:ul\.|ulica)\s+[A-Z0-9][^,\n]{2,80}", re.IGNORECASE), "[ADDRESS]"),
)


def pseudonymize_court_decision_text(text: str) -> str:
    """Best-effort public-view pseudonymization before exposing decision text."""
    sanitized = text
    for pattern, replacement in _PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized
