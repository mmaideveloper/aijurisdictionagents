"""Exact locale aliases; free-form metadata must never become policy."""
from __future__ import annotations

LANGUAGE_ALIASES = {
    "en": "en", "en-us": "en", "en-gb": "en", "english": "en",
    "de": "de", "de-de": "de", "de-at": "de", "de-ch": "de",
    "german": "de", "deutsch": "de",
    "sk": "sk", "sk-sk": "sk", "slovak": "sk", "slovakian": "sk",
    "slovensky": "sk", "slovakia": "sk",
}
# Country codes with explicit application handling, including generic legal intake.
SUPPORTED_COUNTRIES = frozenset({"SK", "CZ", "DE", "AT", "CH"})
COUNTRY_ALIASES = {"SVK": "SK", "SLOVAKIA": "SK", "SLOVAK REPUBLIC": "SK", "SLOVENSKO": "SK"}


def validated_language(value: str | None) -> str | None:
    if value is None:
        return None
    language = LANGUAGE_ALIASES.get(value.strip().casefold())
    if language is None:
        raise ValueError("unsupported_language")
    return language


def validated_country(value: str) -> str:
    country = value.strip().upper()
    country = COUNTRY_ALIASES.get(country, country)
    if country not in SUPPORTED_COUNTRIES:
        raise ValueError("unsupported_country")
    return country
