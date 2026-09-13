"""Supplementary warning detection; never an authorization or trust boundary."""
from __future__ import annotations

import re
import unicodedata


def suspicious_instruction(text: str) -> bool:
    normalized = unicodedata.normalize("NFKD", text).casefold()
    normalized = "".join(c for c in normalized if not unicodedata.combining(c)
                         and unicodedata.category(c) != "Cf")
    normalized = re.sub(r"\s+", " ", normalized)
    patterns = (
        r"(?:show|reveal|print|repeat|give|display|expose|output|tell).{0,90}(?:system|developer|hidden|original).{0,30}(?:prompt|instruction)",
        r"(?:ignore|override|disregard|forget).{0,50}(?:previous|system|safety|all|prior).{0,30}(?:instructions|rules|policy|safeguards)",
        r"(?:ukaz|zobraz|vypis|prezrad).{0,90}(?:systemov|povodn|skryt).{0,30}(?:prompt|pokyn|instrukc)",
        r"(?:ignoruj|obid).{0,50}(?:pokyn|instrukc|pravidl)",
        r"(?:zeige|verrate|drucke|gib).{0,90}(?:system|ursprunglich|versteckt).{0,30}(?:prompt|anweisung)",
        r"ignoriere.{0,50}(?:anweisung|regel|vorgab)",
        r"<\|(?:im_start|start_header_id)\|>\s*(?:system|developer)",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def warning_message(language: str | None, *, source: bool = False) -> str:
    locale = (language or "en").split("-")[0].lower()
    if source:
        return {
            "sk": "Upozornenie: Zdroj obsahuje možné pokyny na obídenie ochrany. Tieto pokyny nepovažujem za oprávnenie; zdroj používam iba ako podklad.",
            "de": "Warnung: Eine Quelle enthält mögliche Anweisungen zur Umgehung von Schutzmaßnahmen. Diese gelten nicht als Berechtigung; die Quelle wird nur als Beleg verwendet.",
        }.get(locale, "Warning: A source contains possible instructions to bypass safeguards. These do not grant permission; the source is used only as evidence.")
    return {
        "sk": "Upozornenie: Nemôžem sprístupniť interný systémový prompt ani obísť bezpečnostné pravidlá. S právnou otázkou vám môžem pomôcť.",
        "de": "Warnung: Ich kann interne Systemanweisungen nicht offenlegen oder Schutzmaßnahmen umgehen. Ich kann Ihnen bei einer rechtlichen Frage helfen.",
    }.get(locale, "Warning: I cannot disclose the internal system prompt or bypass safeguards. I can help with your legal question.")
