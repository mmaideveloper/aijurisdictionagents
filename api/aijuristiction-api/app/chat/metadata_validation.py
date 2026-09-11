from typing import cast
from aijurisdictionagents import locales


def validated_country(value: str) -> str:
    return cast(str, locales.validated_country(value))


def validated_language(value: str | None) -> str | None:
    return cast(str | None, locales.validated_language(value))


def correction_message(language: str | None) -> str:
    try:
        locale = validated_language(language)
    except ValueError:
        locale = "en"
    return {
        "sk": "Pred pokračovaním opravte krajinu a jazyk konverzácie. História a dokumenty zostávajú zachované.",
        "de": "Bitte korrigieren Sie Land und Sprache, bevor Sie fortfahren. Verlauf und Dokumente bleiben erhalten.",
    }.get(locale or "en", "Please correct the conversation country and language before continuing. History and documents are preserved.")
