from __future__ import annotations


def is_slovakia(country: str) -> bool:
    if not country:
        return False
    normalized = country.strip().lower()
    return normalized in {"sk", "svk", "slovakia", "slovak republic"}


def is_slovak_language(language: str | None) -> bool:
    if not language:
        return False
    normalized = language.strip().lower()
    return normalized.startswith("sk") or normalized in {"slovak", "slovakian", "slovensky"}
