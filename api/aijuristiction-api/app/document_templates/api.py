from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

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

    # Import lazily so the template API can be tested standalone while still using
    # the production document PDF renderer for visual quality checks.
    from app.chat.api import _build_professional_document_pdf

    disclaimer = resolve_template_disclaimer(template)
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
        "transfer_share": "50 %",
        "transfer_price": "5 000 EUR",
        "estimated_timeline": "spravidla niekoľko pracovných dní až týždňov",
        "employer_business_name": "Fiktiva Digital Solutions s.r.o.",
        "employer_seat": "Inovacna 18, 040 01 Kosice",
        "employer_ico": "99 999 999",
        "employer_dic": "2099999999",
        "employer_vat_id": "SK2099999999",
        "employer_register_entry": "Obchodny register Mestskeho sudu Kosice, oddiel Sro, vlozka c. 99999/V",
        "employer_bank_name": "Testovacia banka, a. s.",
        "employer_iban": "SK00 0000 0000 0000 0000 0000",
        "employer_representative": "Ing. Martin Vzorovy, konatel",
        "employer_email": "personalne@fiktiva-example.sk",
        "employer_phone": "+421 900 000 000",
        "employee_full_name": "Lucia Vzorova",
        "employee_birth_surname": "Testova",
        "employee_birth_date": "14. februara 1994",
        "employee_birth_number": "945214/0000",
        "employee_birth_place": "Poprad",
        "employee_residence": "Vzorova 27, 058 01 Poprad",
        "employee_nationality": "Slovenska republika",
        "employee_id_card_number": "TEST000001",
        "employee_email": "lucia.vzorova@example.com",
        "employee_phone": "+421 900 000 111",
        "employee_bank_account": "SK00 1111 0000 0012 3456 7890",
        "job_position": "AI vyvojar / softverovy inzinier",
        "job_description": (
            "navrh, vyvoj, testovanie a udrzba softverovych rieseni vyuzivajucich umelu inteligenciu, "
            "integracia AI modelov do informacnych systemov a tvorba technickej dokumentacie"
        ),
        "place_of_work": (
            "Inovacna 18, 040 01 Kosice a praca na dialku z uzemia Slovenskej republiky podla dohody "
            "so zamestnavatelom"
        ),
        "regular_workplace": "Kosice",
        "supervisor_name": "Ing. Peter Modelovy, veduci vyvoja",
        "start_date": "1. oktobra 2026",
        "employment_term_description": "pracovny pomer na dobu neurcitu",
        "probation_period": "3 mesiace",
        "contract_number": "PZ-2026-014",
        "weekly_working_hours": "40 hodin tyzdenne",
        "working_time_distribution": "pondelok az piatok",
        "core_working_time": "od 9.00 do 15.00 hod.",
        "flexible_working_time": "od 7.00 do 9.00 hod. a od 15.00 do 18.00 hod.",
        "break_duration": "30 minut",
        "base_monthly_salary": "3 200 EUR",
        "variable_salary_component": "do 10 % zakladnej mesacnej mzdy podla dosiahnutych pracovnych vysledkov",
        "payday": "najneskor 15. den kalendarneho mesiaca nasledujuceho po mesiaci, za ktory mzda patri",
        "salary_payment_method": "bezhotovostnym prevodom na bankovy ucet zamestnanca",
        "salary_grade": "4",
        "vacation_entitlement": "v rozsahu podla prislusnych ustanoveni Zakonnika prace",
        "notice_period": "podla Zakonnika prace a dlzky trvania pracovneho pomeru",
        "home_office_arrangement": "najviac 3 pracovne dni v tyzdni po dohode s nadriadenym",
        "work_equipment": "sluzobny notebook, mobilny telefon, pristup k vyvojovym a cloudovym nastrojom, bezpecnostny autentifikacny token",
        "employee_benefits": (
            "prispevok na stravovanie podla platnych pravnych predpisov, prispevok na vzdelavanie do vysky "
            "1 000 EUR rocne, 3 dni pracovneho volna navyse, flexibilny pracovny cas a moznost prace na dialku"
        ),
        "signature_place": "Kosice",
        "signature_date": "15. septembra 2026",
        "employer_signatory_name": "Ing. Martin Vzorovy",
        "employer_signatory_title": "konatel spolocnosti",
        "employee_signatory_name": "Lucia Vzorova",
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

