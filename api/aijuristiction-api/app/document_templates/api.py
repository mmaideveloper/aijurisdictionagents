from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from app.document_templates.catalog import render_template
from app.document_templates.disclaimers import resolve_template_disclaimer
from app.document_templates.models import (
    DocumentTemplateCreateRequest,
    DocumentTemplateDefinition,
    DocumentTemplateListResponse,
    DocumentTemplateMatchResponse,
    DocumentTemplateResponse,
    DocumentTemplateVersionListResponse,
    DocumentTemplateUpdateRequest,
)
from app.document_templates.store import (
    DocumentTemplateAmbiguousError,
    DocumentTemplateConflictError,
    DocumentTemplateNotFoundError,
    DocumentTemplateStore,
)
from app.security import require_api_key


router = APIRouter(
    prefix="/v1/document-templates",
    tags=["document-templates"],
    dependencies=[Depends(require_api_key)],
)


@lru_cache(maxsize=1)
def get_document_template_store() -> DocumentTemplateStore:
    return DocumentTemplateStore.from_env()


@router.get("", response_model=DocumentTemplateListResponse)
def list_document_templates(
    include_deleted: bool = Query(default=False),
    jurisdiction: str | None = Query(default=None),
    category: str | None = Query(default=None),
    template_kind: str | None = Query(default=None),
    latest_only: bool = Query(default=False),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateListResponse:
    items = store.list(
        include_deleted=include_deleted,
        jurisdiction=jurisdiction,
        category=category,
        template_kind=template_kind,
        latest_only=latest_only,
    )
    return DocumentTemplateListResponse(items=[DocumentTemplateResponse.from_definition(item) for item in items])


@router.get("/{template_key}/versions", response_model=DocumentTemplateVersionListResponse)
def list_document_template_versions(
    template_key: str,
    jurisdiction: str = Query(min_length=2, max_length=8),
    include_deleted: bool = Query(default=False),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateVersionListResponse:
    items = store.list_versions(
        template_key=template_key,
        jurisdiction=jurisdiction,
        include_deleted=include_deleted,
    )
    return DocumentTemplateVersionListResponse(items=[DocumentTemplateResponse.from_definition(item) for item in items])


@router.get("/{template_key}", response_model=DocumentTemplateResponse)
def get_document_template(
    template_key: str,
    jurisdiction: str | None = Query(default=None),
    version: int | None = Query(default=None, ge=1),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateResponse:
    try:
        return DocumentTemplateResponse.from_definition(
            store.get(template_key=template_key, jurisdiction=jurisdiction, version=version)
        )
    except DocumentTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentTemplateAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{template_key}/preview/pdf")
def preview_document_template_pdf(
    template_key: str,
    jurisdiction: str | None = Query(default=None),
    version: int | None = Query(default=None, ge=1),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> Response:
    try:
        template = store.get(template_key=template_key, jurisdiction=jurisdiction, version=version)
    except DocumentTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentTemplateAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    rendered = render_template(
        template=template,
        facts=_template_preview_facts(),
        country=template.jurisdiction,
        language=template.language,
    )
    lines = rendered.lines or _metadata_only_preview_lines(template)
    if rendered.unresolved_fields:
        lines.extend(
            [
                "",
                "Nevyriešené polia náhľadu:",
                *[f"- {field}" for field in rendered.unresolved_fields],
            ]
        )
    if rendered.follow_up_question:
        lines.extend(["", "Prvá odporúčaná doplňujúca otázka:", rendered.follow_up_question])
    disclaimer = resolve_template_disclaimer(template)

    # Import lazily so the template API can be tested standalone while still using
    # the production document PDF renderer for visual quality checks.
    try:
        from app.chat.api import _build_professional_document_pdf
    except ModuleNotFoundError:
        pdf_content = _build_standalone_template_preview_pdf(
            title=rendered.title or template.title,
            lines=lines,
            country=template.jurisdiction,
            language=template.language,
            footer_line=f"AIJ | Template preview | {template.template_key}",
            disclaimer=disclaimer,
        )
    else:
        pdf_content = _build_professional_document_pdf(
            title=rendered.title or template.title,
            lines=lines,
            country=template.jurisdiction,
            language=template.language,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            case_id=f"template-preview:{template.template_key}",
            footer_line=f"AIJ | Template preview | {template.template_key}",
            verification_score=None,
            disclaimer=disclaimer,
        )
    filename = _template_preview_filename(template)
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=DocumentTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_document_template(
    payload: DocumentTemplateCreateRequest,
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateResponse:
    try:
        return DocumentTemplateResponse.from_definition(store.create(payload))
    except DocumentTemplateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{template_key}", response_model=DocumentTemplateResponse)
def update_document_template(
    template_key: str,
    payload: DocumentTemplateUpdateRequest,
    jurisdiction: str | None = Query(default=None),
    version: int | None = Query(default=None, ge=1),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateResponse:
    try:
        return DocumentTemplateResponse.from_definition(
            store.update(template_key=template_key, payload=payload, jurisdiction=jurisdiction, version=version)
        )
    except DocumentTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentTemplateAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DocumentTemplateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{template_key}", response_model=DocumentTemplateResponse)
def delete_document_template(
    template_key: str,
    jurisdiction: str | None = Query(default=None),
    version: int | None = Query(default=None, ge=1),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateResponse:
    try:
        return DocumentTemplateResponse.from_definition(
            store.soft_delete(template_key=template_key, jurisdiction=jurisdiction, version=version)
        )
    except DocumentTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentTemplateAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/match/search", response_model=DocumentTemplateMatchResponse)
def match_document_template(
    request_text: str = Query(min_length=3),
    country: str = Query(min_length=2, max_length=8),
    template_kind: str | None = Query(default=None),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateMatchResponse:
    score, matched = store.find_best_match(
        request_text=request_text,
        country=country,
        template_kind=template_kind,
    )
    return DocumentTemplateMatchResponse(
        matched=matched is not None,
        score=score,
        template=DocumentTemplateResponse.from_definition(matched) if matched is not None else None,
    )


def _template_preview_facts() -> dict[str, str]:
    return {
        "prenajimatel": "Ján Novák, trvale bytom Hlavná 12, 058 01 Poprad",
        "najomca": "Mária Kováčová, trvale bytom Dunajská 8, 811 08 Bratislava",
        "predmet": "Byt č. 12 na adrese Ludvíka Svobodu 2953/50, Poprad",
        "doba": "Na dobu určitú od 01.05.2026 do 30.04.2027",
        "najomne": "600 EUR mesačne, splatné do 5. dňa príslušného mesiaca",
        "deposit": "600 EUR",
        "notice": "Výpovedná lehota 1 mesiac; pri podstatnom porušení zmluvy okamžité skončenie",
        "client_name": "Ján Novák",
        "opponent_name": "Mária Kováčová",
        "topic": "nájom bytu",
        "company_name": "ESolutions SK s.r.o.",
        "company_identifier": "12345678",
        "company_seat": "Pribinova 10, 811 09 Bratislava",
        "transferor_name": "Peter Horváth, trvale bytom Kvetná 4, Žilina",
        "transferee_name": "Jana Černá, trvale bytom Horská 7, Košice",
        "nehnutelnost": "Byt č. 12 na adrese Ludvíka Svobodu 2953/50, Poprad, zapísaný na LV č. 1234",
        "transfer_share": "50 %",
        "transfer_price": "5 000 EUR",
        "estimated_timeline": "spravidla niekoľko pracovných dní až týždňov",
        "employer_business_name": "Fiktíva Digital Solutions",
        "employer_seat": "Inovačná 18, 040 01 Košice",
        "employer_ico": "99 999 999",
        "employer_representative": "Ing. Martin Vzorový, konateľ",
        "employer_email": "personalne@fiktiva-example.sk",
        "employer_phone": "+421 900 000 000",
        "employee_full_name": "Lucia Vzorová",
        "employee_birth_date": "14. februára 1994",
        "employee_birth_number": "945214/0000",
        "employee_residence": "Vzorová 27, 058 01 Poprad",
        "employee_id_card_number": "TEST000001",
        "employee_email": "lucia.vzorova@example.com",
        "employee_phone": "+421 900 000 111",
        "job_position": "AI vývojár / softvérový inžinier",
        "job_description": "návrh, vývoj, testovanie a údržba AI riešení",
        "place_of_work": "Inovačná 18, 040 01 Košice a práca na diaľku v SR podľa dohody",
        "start_date": "1. októbra 2026",
        "employment_term_description": "pracovný pomer na dobu neurčitú",
        "probation_period": "3 mesiace",
        "base_monthly_salary": "3 200 EUR brutto",
        "variable_salary_component": "do 10 % základnej mesačnej mzdy podľa výsledkov",
        "salary_payday": "najneskôr 15. deň kalendárneho mesiaca",
        "salary_payment_method": "bezhotovostným prevodom na účet zamestnanca",
        "weekly_working_hours": "40 hodín",
        "working_time_distribution": "pondelok až piatok",
        "vacation_entitlement": "v rozsahu podľa Zákonníka práce",
        "additional_work_conditions": "home office najviac 3 dni týždenne; notebook a mobilný telefón",
        "signature_place": "Košice",
        "signature_date": "15. septembra 2026",
        "employer_signatory_name": "Ing. Martin Vzorový",
        "employee_signatory_name": "Lucia Vzorová",
    }


def _metadata_only_preview_lines(template: DocumentTemplateDefinition) -> list[str]:
    lines = [
        template.title,
        "",
        "Táto šablóna zatiaľ nemá uložené telo dokumentu.",
        "PDF náhľad zobrazuje metadáta šablóny, aby bolo možné otestovať typografiu a export.",
        "",
        f"Jurisdikcia: {template.jurisdiction}",
        f"Jazyk: {template.language or '[neuvedené]'}",
        f"Kategória: {template.category}",
        f"Typ šablóny: {template.template_kind}",
        f"Zdroj: {template.source_url}",
    ]
    if template.description:
        lines.extend(["", "Popis:", template.description])
    if template.placeholders:
        lines.extend(["", "Očakávané polia:", *[f"- {field}" for field in template.placeholders]])
    return lines


def _template_preview_filename(template: DocumentTemplateDefinition) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", template.template_key).strip("._-")
    return f"{stem or 'document_template'}-preview.pdf"


def _build_standalone_template_preview_pdf(
    *,
    title: str,
    lines: list[str],
    country: str,
    language: str | None,
    footer_line: str,
    disclaimer: tuple[str, str, str] | None,
) -> bytes:
    regular_font, bold_font = _resolve_template_preview_fonts(country=country, language=language)
    page_width, page_height = A4
    margin_left = 52.0
    margin_top = 60.0
    margin_bottom = 44.0
    line_height = 15.0
    body_font_size = 11.0
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
    pdf.setTitle(title.strip() or "Dokument")
    pdf.setAuthor("JurisDigta")
    pdf.setSubject("Template preview")
    intro_lines = [
        title,
        "",
        "JurisDigta",
    ]
    if (language or "").strip().lower().startswith("sk") or (country or "").strip().upper() == "SK":
        intro_lines.extend(
            [
                "Jurisdikcia: Slovenská republika",
                "Typ dokumentu: právny návrh",
                "",
            ]
        )
    wrapped_lines = _wrap_template_preview_lines(
        intro_lines + _template_preview_disclaimer_lines(disclaimer) + list(lines),
        width=88,
    )

    def draw_footer() -> None:
        footer = "JurisDigta | Poprad, Slovakia, 05801 | Skore overenia dokumentu: -"
        if disclaimer is not None and disclaimer[2].strip():
            footer = f"{footer} | {disclaimer[2].strip()}"
        pdf.setFont(regular_font, 9)
        pdf.drawString(margin_left, margin_bottom - 10, footer)

    y = page_height - margin_top
    for index, line in enumerate(wrapped_lines):
        if y <= margin_bottom + 20:
            draw_footer()
            pdf.showPage()
            y = page_height - margin_top
        if index == 0:
            pdf.setFont(bold_font, 16)
            pdf.drawString(margin_left, y, line)
            y -= line_height * 1.4
            continue
        if not line.strip():
            y -= line_height * 0.7
            continue
        if _looks_like_template_preview_heading(line):
            pdf.setFont(bold_font, body_font_size + 1)
        else:
            pdf.setFont(regular_font, body_font_size)
        pdf.drawString(margin_left, y, line)
        y -= line_height
    draw_footer()
    pdf.save()
    return buffer.getvalue()


def _template_preview_disclaimer_lines(disclaimer: tuple[str, str, str] | None) -> list[str]:
    if disclaimer is None:
        return []
    title, text, _footer = disclaimer
    lines: list[str] = []
    if title.strip():
        lines.append(title.strip())
    if text.strip():
        lines.append(text.strip())
    if lines:
        lines.append("")
    return lines


def _wrap_template_preview_lines(lines: list[str], *, width: int) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            wrapped.append("")
            continue
        current = stripped
        while len(current) > width:
            split_at = current.rfind(" ", 0, width)
            if split_at <= 0:
                split_at = width
            wrapped.append(current[:split_at].rstrip())
            current = current[split_at:].lstrip()
        wrapped.append(current)
    return wrapped


def _looks_like_template_preview_heading(line: str) -> bool:
    normalized = line.strip()
    if normalized.startswith("Článok") or normalized.startswith("Clanok"):
        return True
    return normalized.isupper() and len(normalized) <= 80


def _resolve_template_preview_fonts(*, country: str, language: str | None) -> tuple[str, str]:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country in {"SK", "CZ", "DE", "AT"} or normalized_language.startswith(("sk", "cs", "de")):
        font_candidates = [
            ("AIJTemplateDejaVuSerif", "DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf"),
            ("AIJTemplateDejaVuSans", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
        ]
        font_dirs = [
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/usr/local/share/fonts"),
            Path("C:/Windows/Fonts"),
        ]
        for font_name, regular_name, bold_name in font_candidates:
            for font_dir in font_dirs:
                regular_path = font_dir / regular_name
                bold_path = font_dir / bold_name
                if regular_path.exists() and bold_path.exists():
                    if font_name not in pdfmetrics.getRegisteredFontNames():
                        pdfmetrics.registerFont(TTFont(font_name, str(regular_path)))
                    bold_font_name = f"{font_name}-Bold"
                    if bold_font_name not in pdfmetrics.getRegisteredFontNames():
                        pdfmetrics.registerFont(TTFont(bold_font_name, str(bold_path)))
                    return font_name, bold_font_name
    return "Helvetica", "Helvetica-Bold"

