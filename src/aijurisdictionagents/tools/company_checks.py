from __future__ import annotations

import re
from typing import Optional
import unicodedata

from .registry import ToolRegistry, build_default_tool_registry


def answer_slovak_company_seat_question(
    user_question: str,
    *,
    registry: ToolRegistry | None = None,
) -> str | None:
    """Recognize Slovak 'where is company based?' questions and answer via ORSR tool."""

    company_name = _extract_company_name(user_question)
    if not company_name:
        return None

    expected_city = _extract_expected_city(user_question)
    runtime_registry = registry or build_default_tool_registry()

    if not runtime_registry.has_tool("obchodny_register_company_check"):
        return (
            "Nedokážem spustiť kontrolu v Obchodnom registri, pretože nástroj "
            "obchodny_register_company_check nie je dostupný."
        )

    result = runtime_registry.run(
        "obchodny_register_company_check",
        company_name_or_registration=company_name,
    )
    if not result.ok:
        return f"Kontrola v Obchodnom registri zlyhala: {result.message}"

    if not result.records:
        return (
            f"Pre spoločnosť '{company_name}' som v Obchodnom registri nenašiel žiadny záznam. "
            "Skontrolujte prosím názov alebo IČO."
        )

    first = result.records[0]
    seat = str(first.get("seat", "")).strip()
    legal_name = str(first.get("name", "")).strip() or company_name
    registration = str(first.get("registration_number", "")).strip()

    if expected_city:
        yes_no = "Áno" if _city_matches(expected_city, seat) else "Nie"
        return (
            f"{yes_no}, podľa Obchodného registra má spoločnosť {legal_name} "
            f"(IČO/registrácia: {registration or 'neuvedené'}) sídlo: {seat or 'neuvedené'}."
        )

    return (
        f"Podľa Obchodného registra má spoločnosť {legal_name} "
        f"(IČO/registrácia: {registration or 'neuvedené'}) sídlo: {seat or 'neuvedené'}."
    )


def _extract_company_name(question: str) -> Optional[str]:
    compact = " ".join(question.split())
    patterns = [
        r"spolocnost\s+(.+?)\s+sidli",
        r"spoločnosť\s+(.+?)\s+sídli",
        r"firm[auy]\s+(.+?)\s+sidli",
        r"firm[auy]\s+(.+?)\s+sídli",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" ,.?")
    return None


def _extract_expected_city(question: str) -> Optional[str]:
    compact = " ".join(question.split())
    match = re.search(r"s[ií]dli\s+v\s+([^?.!,]+)", compact, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def _city_matches(expected_city: str, seat: str) -> bool:
    expected = _normalize_text(expected_city)
    actual = _normalize_text(seat)
    if expected in actual:
        return True
    if expected.endswith("e") and len(expected) > 4:
        return expected[:-1] in actual
    return False


def _normalize_text(text: str) -> str:
    no_diacritics = "".join(
        char
        for char in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^a-z0-9 ]+", " ", no_diacritics).strip()
