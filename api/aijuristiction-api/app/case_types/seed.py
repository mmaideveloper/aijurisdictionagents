from __future__ import annotations

import re
import unicodedata

from app.case_types.models import CaseTypeCreateRequest
from app.document_templates.models import DocumentTemplateDefinition


def build_default_case_types(
    templates: list[DocumentTemplateDefinition],
) -> list[CaseTypeCreateRequest]:
    items: list[CaseTypeCreateRequest] = []
    for template in templates:
        items.append(
            CaseTypeCreateRequest(
                case_type_key=_case_type_key_from_template_key(template.template_key),
                jurisdiction=template.jurisdiction,
                language=template.language,
                name=template.title,
                description=_default_case_description(template),
                keywords=list(_default_case_keywords(template)),
                prompt_text=build_default_case_prompt(template),
                template_keys=[template.template_key],
                is_enabled=template.is_enabled and not template.is_deleted,
            )
        )
    return items


def build_default_case_prompt(template: DocumentTemplateDefinition) -> str:
    return (
        f"Pomoz pouzivatelovi pripravit pravny pripad alebo dokument typu '{template.title}' "
        f"pre jurisdikciu {template.jurisdiction}. Najprv si vyziadaj len nevyhnutne skutkove "
        "udaje, over ci existuje vhodna sablona v katalogu, vysvetli ake informacie este "
        "chybaju a upozorni, ze pred podanim alebo podpisom je vhodna pravna kontrola clovekom."
    )


def _case_type_key_from_template_key(template_key: str) -> str:
    return template_key


def _default_case_description(template: DocumentTemplateDefinition) -> str:
    if template.description.strip():
        return template.description.strip()
    return f"Pripad alebo workflow suvisiaci s dokumentom '{template.title}'."


def _default_case_keywords(template: DocumentTemplateDefinition) -> tuple[str, ...]:
    values = [template.title, template.template_kind, template.category, *template.keywords]
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        compact = _compact_keyword(value)
        if compact and compact not in seen:
            normalized.append(compact)
            seen.add(compact)
    return tuple(normalized)


def _compact_keyword(value: str) -> str:
    lowered = value.strip().lower()
    if not lowered:
        return ""
    decomposed = unicodedata.normalize("NFD", lowered)
    no_diacritics = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    no_punctuation = re.sub(r"[^a-z0-9]+", " ", no_diacritics)
    return " ".join(no_punctuation.split())
