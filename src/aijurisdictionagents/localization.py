from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .jurisdiction import is_slovak_language


SUPPORTED_LANGUAGES = ("en", "de", "sk")


def normalize_language(language: str | None) -> str:
    if not language:
        return "en"
    normalized = language.strip().lower()
    if is_slovak_language(normalized):
        return "sk"
    if normalized.startswith("de") or normalized in {"german", "deutsch"}:
        return "de"
    if normalized.startswith("en") or normalized == "english":
        return "en"
    return "en"


def translate(key: str, language: str | None, **kwargs: object) -> str:
    lang = normalize_language(language)
    table = _load_translations(lang)
    if key not in table and lang != "en":
        table = _load_translations("en")
    template = table.get(key, key)
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


@lru_cache
def _load_translations(language: str) -> dict[str, str]:
    if language not in SUPPORTED_LANGUAGES:
        language = "en"
    base_dir = Path(__file__).resolve().parent / "localization"
    path = base_dir / f"{language}.json"
    if not path.exists() and language != "en":
        path = base_dir / "en.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
