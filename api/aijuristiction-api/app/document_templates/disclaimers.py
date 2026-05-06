from __future__ import annotations

from collections.abc import Iterable

from app.document_templates.models import DocumentTemplateDefinition


DisclaimerContent = tuple[str, str, str]


def default_disclaimer(*, country: str, language: str | None) -> DisclaimerContent | None:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country != "SK" and not normalized_language.startswith("sk"):
        return None

    if normalized_language.startswith("en"):
        return (
            "Important notice",
            (
                "These documents are templates and working drafts only. "
                "Before they are used in any formal legal proceeding or binding agreement, "
                "they should be reviewed by a qualified lawyer and aligned with the current facts and law."
            ),
            "Non-binding legal draft; lawyer review required.",
        )
    if normalized_language.startswith("de"):
        return (
            "Wichtiger Hinweis",
            (
                "Diese Dokumente sind nur Muster und Arbeitsentwuerfe. "
                "Vor einer Verwendung in formellen Rechtsverfahren oder verbindlichen Vereinbarungen "
                "sollten sie durch einen qualifizierten Rechtsanwalt geprueft und an den aktuellen Sachverhalt sowie die geltende Rechtslage angepasst werden."
            ),
            "Unverbindlicher Rechtsentwurf; anwaltliche Pruefung erforderlich.",
        )
    return (
        "Dolezite upozornenie",
        (
            "Toto su iba vzory a pracovne navrhy. Pred pouzitim vo formalnych pravnych konaniach "
            "alebo pri uzatvarani zavaznych zmluv musia byt skontrolovane kvalifikovanym pravnikom "
            "a prisposobene aktualnemu skutkovemu stavu a platnej legislative."
        ),
        "Nezavazny pravny navrh; vyzaduje pravnu kontrolu.",
    )


def resolve_template_disclaimer(
    template: DocumentTemplateDefinition,
) -> DisclaimerContent | None:
    fallback = default_disclaimer(country=template.jurisdiction, language=template.language)
    title = template.disclaimer_title.strip()
    text = template.disclaimer_text.strip()
    footer = template.disclaimer_footer.strip()
    if title or text or footer:
        if fallback is None:
            fallback = ("", "", "")
        fallback_title, fallback_text, fallback_footer = fallback
        return (
            title or fallback_title,
            text or fallback_text,
            footer or fallback_footer,
        )
    return fallback


def resolve_disclaimer_from_templates(
    *,
    templates: Iterable[DocumentTemplateDefinition],
    country: str,
    language: str | None,
    template_kind: str | None = None,
) -> DisclaimerContent | None:
    normalized_language = (language or "").strip().lower()
    normalized_kind = (template_kind or "").strip().lower()

    ranked = sorted(
        (
            template
            for template in templates
            if template.is_enabled and not template.is_deleted
        ),
        key=lambda template: (
            0 if normalized_kind and template.template_kind == normalized_kind else 1,
            _language_rank(template.language, normalized_language),
            template.title.casefold(),
        ),
    )
    for template in ranked:
        disclaimer = resolve_template_disclaimer(template)
        if disclaimer is not None:
            return disclaimer
    return default_disclaimer(country=country, language=language)


def _language_rank(template_language: str | None, requested_language: str) -> int:
    normalized_template = (template_language or "").strip().lower()
    if requested_language and normalized_template == requested_language:
        return 0
    if requested_language and normalized_template.startswith(requested_language.split("-")[0]):
        return 1
    if normalized_template.startswith("sk"):
        return 2
    return 3
