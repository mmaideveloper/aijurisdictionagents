from __future__ import annotations

from io import BytesIO
from pathlib import Path
import unicodedata

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.document_templates.api import get_document_template_store, router
from app.document_templates.catalog import apply_employment_profile_defaults, render_template
from app.document_templates.models import DocumentTemplateCreateRequest, DocumentTemplateUpdateRequest
from app.document_templates.store import DocumentTemplateStore, DocumentTemplateStoreConfig
from app.security import require_api_key


def _build_store(tmp_path: Path) -> DocumentTemplateStore:
    return DocumentTemplateStore(
        DocumentTemplateStoreConfig(
            db_option="sqlite",
            db_cloud="",
            sqlite_path=tmp_path / "document_templates.sqlite3",
        )
    )


def _build_client(store: DocumentTemplateStore) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_document_template_store] = lambda: store
    app.dependency_overrides[require_api_key] = lambda: None
    return TestClient(app)


def _canonical_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    plain = "".join(char for char in normalized if not unicodedata.combining(char)).lower()
    return " ".join(plain.split())


def test_document_template_store_seeds_initial_template_catalog(tmp_path: Path) -> None:
    store = _build_store(tmp_path)

    items = store.list(jurisdiction="SK")

    keys = {item.template_key for item in items}
    assert "sk.company.share_transfer" in keys
    assert "sk.real_estate.lease_agreement" in keys
    assert "sk.authorization.general_power_of_attorney" in keys
    assert "sk.employment.employment_contract" in keys
    assert "sk.justice.fees.exemption_fo" in keys
    assert "sk.justice.company_registry.initial_registration" in keys

    employment = store.get(template_key="sk.employment.employment_contract", jurisdiction="SK")
    assert employment.source_url == "https://www.aksamec.sk/vzory/pracovna-zmluva-vzor/"
    assert "§ 42 a nasl. zákona č. 311/2001 Z. z." in employment.body
    assert "Článok I" in employment.body
    assert "Článok IV" in employment.body
    assert "Článok VII" in employment.body
    assert "{{employer_business_name}}" in employment.body
    assert "{{employee_full_name}}" in employment.body
    assert "principal_identification" not in employment.placeholders
    assert "agent_identification" not in employment.placeholders
    assert "employee_residence" in employment.placeholders
    assert "base_monthly_salary" in employment.placeholders
    assert {reference.source_kind for reference in employment.source_refs} == {
        "external_template_page",
        "official_legislation",
    }
    assert {reference.url for reference in employment.source_refs} == {
        "https://www.aksamec.sk/vzory/pracovna-zmluva-vzor/",
        "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2001/311/",
    }
    assert "ľudskú a právnu kontrolu" in employment.disclaimer_footer

    lease = store.get(template_key="sk.real_estate.lease_agreement", jurisdiction="SK")
    assert lease.source_url == "https://www.aksamec.sk/najomna-zmluva-vzor-2026/"
    assert "§ 685 a nasl. zákona č. 40/1964 Zb." in lease.body
    assert "Článok I" in lease.body
    assert "Článok III" in lease.body
    assert "Článok VI" in lease.body
    assert "{{landlord_identification}}" in lease.body
    assert "{{tenant_identification}}" in lease.body
    assert "{{utilities_terms}}" in lease.body
    assert "principal_identification" not in lease.placeholders
    assert "landlord_identification" in lease.placeholders
    assert "property_identification" in lease.placeholders
    assert "termination_terms" in lease.placeholders
    assert {reference.source_kind for reference in lease.source_refs} == {
        "external_template_page",
        "official_legislation",
    }
    assert {reference.url for reference in lease.source_refs} == {
        "https://www.aksamec.sk/najomna-zmluva-vzor-2026/",
        "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1964/40/",
    }
    assert "ľudskú a právnu kontrolu" in lease.disclaimer_footer

    sale_purchase = store.get(template_key="sk.real_estate.sale_purchase", jurisdiction="SK")
    assert sale_purchase.source_url == "https://www.aksamec.sk/kupna-zmluva-2026/"
    assert "§ 588 a nasl. zákona č. 40/1964 Zb." in sale_purchase.body
    assert "Článok I" in sale_purchase.body
    assert "Článok II" in sale_purchase.body
    assert "Článok V" in sale_purchase.body
    assert "{{seller_identification}}" in sale_purchase.body
    assert "{{buyer_identification}}" in sale_purchase.body
    assert "{{filing_party}}" in sale_purchase.body
    assert "principal_identification" not in sale_purchase.placeholders
    assert "seller_identification" in sale_purchase.placeholders
    assert "buyer_identification" in sale_purchase.placeholders
    assert "purchase_price" in sale_purchase.placeholders
    assert "filing_cost_terms" in sale_purchase.placeholders
    assert {reference.source_kind for reference in sale_purchase.source_refs} == {
        "external_template_page",
        "official_legislation",
    }
    assert {reference.url for reference in sale_purchase.source_refs} == {
        "https://www.aksamec.sk/kupna-zmluva-2026/",
        "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1964/40/",
    }
    assert "ľudskú a právnu kontrolu" in sale_purchase.disclaimer_footer


def test_document_template_store_versions_legacy_empty_employment_seed_once(tmp_path: Path) -> None:
    config = DocumentTemplateStoreConfig(
        db_option="sqlite",
        db_cloud="",
        sqlite_path=tmp_path / "document_templates.sqlite3",
    )
    store = DocumentTemplateStore(config)
    empty_version = store.update(
        template_key="sk.employment.employment_contract",
        jurisdiction="SK",
        payload=DocumentTemplateUpdateRequest(body=""),
    )
    assert empty_version.version == 2

    refreshed = DocumentTemplateStore(config).get(
        template_key="sk.employment.employment_contract",
        jurisdiction="SK",
    )
    assert refreshed.version == 3
    assert "Článok I" in refreshed.body

    unchanged = DocumentTemplateStore(config).get(
        template_key="sk.employment.employment_contract",
        jurisdiction="SK",
    )
    assert unchanged.version == 3


def test_document_template_store_versions_legacy_empty_sale_purchase_seed_once(tmp_path: Path) -> None:
    config = DocumentTemplateStoreConfig(
        db_option="sqlite",
        db_cloud="",
        sqlite_path=tmp_path / "document_templates.sqlite3",
    )
    store = DocumentTemplateStore(config)
    empty_version = store.update(
        template_key="sk.real_estate.sale_purchase",
        jurisdiction="SK",
        payload=DocumentTemplateUpdateRequest(body=""),
    )
    assert empty_version.version == 2

    refreshed = DocumentTemplateStore(config).get(
        template_key="sk.real_estate.sale_purchase",
        jurisdiction="SK",
    )
    assert refreshed.version == 3
    assert "Článok I" in refreshed.body

    unchanged = DocumentTemplateStore(config).get(
        template_key="sk.real_estate.sale_purchase",
        jurisdiction="SK",
    )
    assert unchanged.version == 3


def test_document_template_store_does_not_overwrite_non_empty_employment_body(tmp_path: Path) -> None:
    config = DocumentTemplateStoreConfig(
        db_option="sqlite",
        db_cloud="",
        sqlite_path=tmp_path / "document_templates.sqlite3",
    )
    store = DocumentTemplateStore(config)
    customized = store.update(
        template_key="sk.employment.employment_contract",
        jurisdiction="SK",
        payload=DocumentTemplateUpdateRequest(
            body="CUSTOM PRACOVNA ZMLUVA\n\nČlánok I\nVlastné znenie.",
            source_url="https://example.com/custom-pracovna-zmluva",
        ),
    )
    assert customized.version == 2

    reloaded = DocumentTemplateStore(config).get(
        template_key="sk.employment.employment_contract",
        jurisdiction="SK",
    )
    assert reloaded.version == 2
    assert reloaded.body == "CUSTOM PRACOVNA ZMLUVA\n\nČlánok I\nVlastné znenie."
    assert reloaded.source_url == "https://example.com/custom-pracovna-zmluva"


def test_document_template_store_does_not_overwrite_non_empty_sale_purchase_body(tmp_path: Path) -> None:
    config = DocumentTemplateStoreConfig(
        db_option="sqlite",
        db_cloud="",
        sqlite_path=tmp_path / "document_templates.sqlite3",
    )
    store = DocumentTemplateStore(config)
    customized = store.update(
        template_key="sk.real_estate.sale_purchase",
        jurisdiction="SK",
        payload=DocumentTemplateUpdateRequest(
            body="CUSTOM KUPNA ZMLUVA\n\nČlánok I\nVlastné znenie.",
            source_url="https://example.com/custom-kupna-zmluva",
        ),
    )
    assert customized.version == 2

    reloaded = DocumentTemplateStore(config).get(
        template_key="sk.real_estate.sale_purchase",
        jurisdiction="SK",
    )
    assert reloaded.version == 2
    assert reloaded.body == "CUSTOM KUPNA ZMLUVA\n\nČlánok I\nVlastné znenie."
    assert reloaded.source_url == "https://example.com/custom-kupna-zmluva"


def test_employment_template_maps_structured_aliases_into_placeholders(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    template = store.get(template_key="sk.employment.employment_contract", jurisdiction="SK")

    rendered = render_template(
        template=template,
        facts={
            "obchodne_meno": "Fiktíva Digital Solutions",
            "sidlo": "Inovačná 18, 040 01 Košice",
            "ico": "99 999 999",
            "zastupeny": "Ing. Martin Vzorový, konateľ",
            "meno_a_priezvisko": "Lucia Vzorová",
            "datum_narodenia": "14. februára 1994",
            "trvaly_pobyt": "Vzorová 27, 058 01 Poprad",
            "druh_prace": "návrh, vývoj a údržba AI riešení",
            "pracovna_pozicia": "AI vývojár",
            "miesto_vykonu_prace": "Košice a práca na diaľku",
            "den_nastupu": "1. októbra 2026",
            "druh_pracovneho_pomeru": "dobu neurčitú",
            "zakladna_mesacna_mzda": "3 200 EUR",
            "tyzdenny_pracovny_cas": "40 hodín",
        },
        country="SK",
        language="sk-SK",
    )

    rendered_text = "\n".join(rendered.lines)
    assert "Fiktíva Digital Solutions" in rendered_text
    assert "Lucia Vzorová" in rendered_text
    assert "AI vývojár" in rendered_text
    assert rendered.missing_required_fields == []
    assert rendered.follow_up_question is None


def test_sale_purchase_template_maps_structured_aliases_into_placeholders(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    template = store.get(template_key="sk.real_estate.sale_purchase", jurisdiction="SK")

    rendered = render_template(
        template=template,
        facts={
            "predavajuci": "Ján Novák, trvale bytom Hlavná 12, 058 01 Poprad",
            "kupujuci": "Mária Kováčová, trvale bytom Dunajská 8, 811 08 Bratislava",
            "nehnutelnost": "byt č. 12 na adrese Ludvíka Svobodu 2953/50, Poprad, zapísaný na LV č. 1234",
            "kupna_cena": "154 000 EUR",
            "platobne_podmienky": "notárska úschova s uvoľnením po povolení vkladu",
            "tarchy": "bez tiarch okrem zákonných obmedzení uvedených na LV",
            "stav_nehnutelnosti": "v stave známom kupujúcemu po osobnej obhliadke",
            "termin_odovzdania": "do 5 pracovných dní od povolenia vkladu",
            "navrh_na_vklad_poda": "kupujúci",
        },
        country="SK",
        language="sk-SK",
    )

    rendered_text = "\n".join(rendered.lines)
    assert "Ján Novák" in rendered_text
    assert "Mária Kováčová" in rendered_text
    assert "Ludvíka Svobodu 2953/50" in rendered_text
    assert "154 000 EUR" in rendered_text
    assert rendered.missing_required_fields == []
    assert rendered.follow_up_question is None


def test_employment_template_reports_first_missing_required_field(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    template = store.get(template_key="sk.employment.employment_contract", jurisdiction="SK")

    rendered = render_template(
        template=template,
        facts={
            "obchodne_meno": "Fiktíva Digital Solutions",
            "sidlo": "Inovačná 18, 040 01 Košice",
            "ico": "99 999 999",
            "zastupeny": "Ing. Martin Vzorový, konateľ",
            "meno_a_priezvisko": "Lucia Vzorová",
            "datum_narodenia": "14. februára 1994",
            "trvaly_pobyt": "Vzorová 27, 058 01 Poprad",
            "druh_prace": "návrh, vývoj a údržba AI riešení",
            "pracovna_pozicia": "AI vývojár",
            "miesto_vykonu_prace": "Košice a práca na diaľku",
            "druh_pracovneho_pomeru": "dobu neurčitú",
            "zakladna_mesacna_mzda": "3 200 EUR",
            "tyzdenny_pracovny_cas": "40 hodín",
        },
        country="SK",
        language="sk-SK",
    )

    assert rendered.missing_required_fields == ["start_date"]
    assert rendered.follow_up_question == "Aký je dohodnutý deň nástupu do práce?"
    assert "start_date" in rendered.unresolved_fields


def test_sale_purchase_template_reports_first_missing_required_field(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    template = store.get(template_key="sk.real_estate.sale_purchase", jurisdiction="SK")

    rendered = render_template(
        template=template,
        facts={
            "predavajuci": "Ján Novák, trvale bytom Hlavná 12, 058 01 Poprad",
            "nehnutelnost": "byt č. 12 na adrese Ludvíka Svobodu 2953/50, Poprad, zapísaný na LV č. 1234",
            "kupna_cena": "154 000 EUR",
        },
        country="SK",
        language="sk-SK",
    )

    assert rendered.missing_required_fields == ["buyer_identification"]
    assert rendered.follow_up_question == "Kto je kupujúci a ako má byť v zmluve presne označený?"
    assert "buyer_identification" in rendered.unresolved_fields


def test_employment_profile_defaults_fill_missing_identity_fields() -> None:
    enriched = apply_employment_profile_defaults(
        facts={"job_position": "AI vývojár"},
        profile_defaults={
            "display_name": "Lucia Vzorová",
            "address": "Vzorová 27, 058 01 Poprad, SK",
            "date_of_birth": "1994-02-14",
            "birth_number": "945214/0000",
            "identity_card_number": "TEST000001",
            "email": "lucia@example.com",
            "phone_number": "+421900111222",
        },
    )

    assert enriched["employee_full_name"] == "Lucia Vzorová"
    assert enriched["employee_signatory_name"] == "Lucia Vzorová"
    assert enriched["employee_residence"] == "Vzorová 27, 058 01 Poprad, SK"
    assert enriched["employee_birth_date"] == "1994-02-14"
    assert enriched["employee_birth_number"] == "945214/0000"
    assert enriched["employee_id_card_number"] == "TEST000001"
    assert enriched["employee_email"] == "lucia@example.com"
    assert enriched["employee_phone"] == "+421900111222"


def test_document_template_store_crud_lifecycle(tmp_path: Path) -> None:
    store = _build_store(tmp_path)

    created = store.create(
        DocumentTemplateCreateRequest(
            template_key="sk.custom.consulting_agreement",
            jurisdiction="SK",
            language="sk-SK",
            category="Obchodne a spolocenske zmluvy",
            title="Konzultacna zmluva",
            template_kind="consulting_agreement",
            description="Custom template",
            source_format="DOCX",
            source_url="https://example.com/consulting.docx",
            body="Konzultacna zmluva medzi {{seller_identification}} a {{buyer_identification}}.",
            keywords=["konzultacna zmluva", "consulting agreement"],
            placeholders=["seller_identification", "buyer_identification"],
            source_refs=[],
            is_enabled=True,
        )
    )
    assert created.title == "Konzultacna zmluva"
    assert created.version == 1
    assert created.is_latest_version is True

    updated = store.update(
        template_key="sk.custom.consulting_agreement",
        jurisdiction="SK",
        payload=DocumentTemplateUpdateRequest(
            title="Konzultacna zmluva updated",
            keywords=["konzultacna zmluva", "sluzby"],
            is_enabled=False,
        ),
    )
    assert updated.title == "Konzultacna zmluva updated"
    assert updated.is_enabled is False
    assert updated.version == 2
    assert updated.latest_version == 2

    first_version = store.get(template_key="sk.custom.consulting_agreement", jurisdiction="SK", version=1)
    assert first_version.newer_version_available is True
    assert first_version.is_latest_version is False

    versions = store.list_versions(template_key="sk.custom.consulting_agreement", jurisdiction="SK")
    assert [item.version for item in versions] == [2, 1]

    deleted = store.soft_delete(template_key="sk.custom.consulting_agreement", jurisdiction="SK", version=2)
    assert deleted.is_deleted is True
    assert deleted.is_enabled is False


def test_document_template_store_match_finds_lease_template(tmp_path: Path) -> None:
    store = _build_store(tmp_path)

    score, matched = store.find_best_match(
        request_text="Potrebujem pripravit najomnu zmluvu na byt v Bratislave.",
        country="SK",
        template_kind="rental_agreement",
    )

    assert score > 0
    assert matched is not None
    assert matched.template_key == "sk.real_estate.lease_agreement"


def test_document_template_api_crud_and_match_endpoints(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    client = _build_client(store)

    list_response = client.get("/v1/document-templates")
    assert list_response.status_code == 200
    assert any(item["template_key"] == "sk.company.share_transfer" for item in list_response.json()["items"])

    create_response = client.post(
        "/v1/document-templates",
        json={
            "template_key": "sk.custom.loan_agreement",
            "jurisdiction": "SK",
            "language": "sk-SK",
            "category": "Obchodne a spolocenske zmluvy",
            "title": "Pozickova zmluva",
            "template_kind": "loan_agreement",
            "description": "Custom loan template",
            "source_format": "DOCX",
            "source_url": "https://example.com/loan.docx",
            "body": "Pozickova zmluva",
            "keywords": ["pozicka", "pozickova zmluva"],
            "flow_keys": [],
            "placeholders": [],
            "source_refs": [],
            "disclaimer_title": "Dolezite upozornenie",
            "disclaimer_text": "Pred podpisom nechajte text skontrolovat advokatom.",
            "disclaimer_footer": "Pravny navrh",
            "is_enabled": True,
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["template_key"] == "sk.custom.loan_agreement"
    assert create_response.json()["disclaimer_text"] == "Pred podpisom nechajte text skontrolovat advokatom."
    assert create_response.json()["version"] == 1

    patch_response = client.patch(
        "/v1/document-templates/sk.custom.loan_agreement?jurisdiction=SK",
        json={"title": "Pozickova zmluva updated", "disclaimer_footer": "Vyziaduje pravnu kontrolu"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["title"] == "Pozickova zmluva updated"
    assert patch_response.json()["disclaimer_footer"] == "Vyziaduje pravnu kontrolu"
    assert patch_response.json()["version"] == 2

    versions_response = client.get(
        "/v1/document-templates/sk.custom.loan_agreement/versions",
        params={"jurisdiction": "SK"},
    )
    assert versions_response.status_code == 200
    assert [item["version"] for item in versions_response.json()["items"]] == [2, 1]

    match_response = client.get(
        "/v1/document-templates/match/search",
        params={"request_text": "Chcem pozickovu zmluvu medzi dvoma osobami", "country": "SK"},
    )
    assert match_response.status_code == 200
    assert match_response.json()["matched"] is True
    assert match_response.json()["template"]["template_key"] == "sk.custom.loan_agreement"

    preview_response = client.get(
        "/v1/document-templates/sk.real_estate.lease_agreement/preview/pdf",
        params={"jurisdiction": "SK"},
    )
    assert preview_response.status_code == 200
    assert preview_response.headers["content-type"].startswith("application/pdf")
    assert "sk.real_estate.lease_agreement-preview.pdf" in preview_response.headers["content-disposition"]
    assert preview_response.content.startswith(b"%PDF")
    preview_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(preview_response.content)).pages
    )
    preview_text_normalized = _canonical_text(preview_text)
    assert "dolezite upozornenie" in preview_text_normalized
    assert "JurisDigta" in preview_text
    assert "Skore overenia dokumentu: -" in preview_text
    assert "právny návrh" in preview_text
    assert "Poprad, Slovakia, 05801" in preview_text
    assert "Template preview" not in preview_text
    assert "sk.real_estate.lease_agreement" not in preview_text
    assert "Táto šablóna zatiaľ nemá uložené telo dokumentu" not in preview_text
    assert "https://www.aksamec.sk/najomna-zmluva-vzor-2026/" not in preview_text
    assert "PREDMET NÁJMU" in preview_text
    assert "NÁJOMNÉ A PLATOBNÉ PODMIENKY" in preview_text
    assert "Ján Novák" in preview_text
    assert "Mária Kováčová" in preview_text
    assert "ludvika svobodu 2953/50" in preview_text_normalized
    assert "individualnu" in preview_text_normalized
    assert "ludsku kontrolu" in preview_text_normalized
    assert "Nevyriešené polia náhľadu" not in preview_text
    assert "Prvá odporúčaná doplňujúca otázka" not in preview_text

    sale_purchase_preview = client.get(
        "/v1/document-templates/sk.real_estate.sale_purchase/preview/pdf",
        params={"jurisdiction": "SK"},
    )
    assert sale_purchase_preview.status_code == 200
    sale_purchase_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(sale_purchase_preview.content)).pages
    )
    sale_purchase_text_normalized = _canonical_text(sale_purchase_text)
    assert "Táto šablóna zatiaľ nemá uložené telo dokumentu" not in sale_purchase_text
    assert "https://www.aksamec.sk/kupna-zmluva-2026/" not in sale_purchase_text
    assert "PREDMET PREVODU" in sale_purchase_text
    assert "KÚPNA CENA A PLATOBNÉ PODMIENKY" in sale_purchase_text
    assert "Peter Horváth" in sale_purchase_text
    assert "Jana Černá" in sale_purchase_text
    assert "5 000 EUR" in sale_purchase_text
    assert "spravidla niekoľko pracovných dní až týždňov" in sale_purchase_text
    assert "individualnu" in sale_purchase_text_normalized
    assert "ludsku kontrolu" in sale_purchase_text_normalized
    assert "Nevyriešené polia náhľadu" not in sale_purchase_text
    assert "Prvá odporúčaná doplňujúca otázka" not in sale_purchase_text

    employment_preview = client.get(
        "/v1/document-templates/sk.employment.employment_contract/preview/pdf",
        params={"jurisdiction": "SK"},
    )
    assert employment_preview.status_code == 200
    employment_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(employment_preview.content)).pages
    )
    employment_text_normalized = _canonical_text(employment_text)
    assert "Táto šablóna zatiaľ nemá uložené telo dokumentu" not in employment_text
    assert "https://www.aksamec.sk/vzory/pracovna-zmluva-vzor/" not in employment_text
    assert "DRUH PRÁCE A JEHO STRUČNÁ CHARAKTERISTIKA" in employment_text
    assert "MZDOVÉ PODMIENKY" in employment_text
    assert "Fiktíva Digital Solutions" in employment_text
    assert "Lucia Vzorová" in employment_text
    assert "ai vyvojar / softverovy inzinier" in employment_text_normalized
    assert "Za zamestnávateľa" in employment_text
    assert "individualnu" in employment_text_normalized
    assert "ludsku kontrolu" in employment_text_normalized
    assert "Nevyriešené polia náhľadu" not in employment_text
    assert "Prvá odporúčaná doplňujúca otázka" not in employment_text

    delete_response = client.delete("/v1/document-templates/sk.custom.loan_agreement?jurisdiction=SK&version=2")
    assert delete_response.status_code == 200
    assert delete_response.json()["is_deleted"] is True

