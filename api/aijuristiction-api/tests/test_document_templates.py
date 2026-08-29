from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.document_templates.api import get_document_template_store, router
from app.document_templates.models import DocumentTemplateCreateRequest, DocumentTemplateUpdateRequest
from app.document_templates.store import DocumentTemplateStore, DocumentTemplateStoreConfig, _load_schema_sql
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


def test_pracovna_zmluva_seed_has_reviewed_body_and_exact_source(tmp_path: Path) -> None:
    store = _build_store(tmp_path)

    template = store.get(template_key="sk.employment.employment_contract", jurisdiction="SK")

    assert template.source_url == "https://www.aksamec.sk/vzory/pracovna-zmluva-vzor/"
    assert "Clanok I." in template.body
    assert "Zakonnik prace" in template.body
    assert template.placeholders[0] == "employer_business_name"
    assert template.source_refs[0].url == "https://www.aksamec.sk/vzory/pracovna-zmluva-vzor/"
    assert template.source_refs[1].url == "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2001/311/"


def test_store_refreshes_metadata_only_pracovna_zmluva_seed(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "document_templates.sqlite3"
    conn = sqlite3.connect(sqlite_path)
    try:
        conn.executescript(_load_schema_sql())
        conn.execute(
            """
            INSERT INTO document_templates (
                template_id, template_key, lineage_key, jurisdiction, language, category, title, template_kind,
                description, source_format, source_url, body, keywords_json, flow_keys_json, placeholders_json,
                source_refs_json, disclaimer_title, disclaimer_text, disclaimer_footer, version, stored_at,
                is_enabled, is_deleted, created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                "seed-sk-employment-contract-v1",
                "sk.employment.employment_contract",
                "pracovna zmluva|employment_contract|sk|sk-sk",
                "SK",
                "sk-SK",
                "Pracovne a personalne dokumenty",
                "Pracovna zmluva",
                "employment_contract",
                "Seed metadata pre pracovnu zmluvu.",
                "DOCX/PDF",
                "https://www.aksamec.sk/vzory/",
                "",
                '["pracovna zmluva", "zamestnanec", "zamestnavatel"]',
                "[]",
                '["principal_identification", "agent_identification"]',
                '[{"label":"AK Samec vzory","notes":"Seed URL dodana pouzivatelom.","publisher":"AK Samec","source_kind":"external_template_index","url":"https://www.aksamec.sk/vzory/"}]',
                "",
                "",
                "",
                1,
                "2026-08-28T00:00:00+00:00",
                1,
                0,
                "2026-08-28T00:00:00+00:00",
                "2026-08-28T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    store = _build_store(tmp_path)
    refreshed = store.get(template_key="sk.employment.employment_contract", jurisdiction="SK")
    assert refreshed.version == 2
    assert refreshed.latest_version == 2
    assert refreshed.source_url == "https://www.aksamec.sk/vzory/pracovna-zmluva-vzor/"
    assert "Clanok IX." in refreshed.body

    reloaded = _build_store(tmp_path).get(template_key="sk.employment.employment_contract", jurisdiction="SK")
    assert reloaded.version == 2
    assert reloaded.latest_version == 2


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
    assert "Dolezite upozornenie" in preview_text
    assert "JurisDigta" in preview_text
    assert "Skore overenia dokumentu: -" in preview_text
    assert "právny návrh" in preview_text
    assert "Poprad, Slovakia, 05801" in preview_text
    assert "Template preview" not in preview_text
    assert "sk.real_estate.lease_agreement" not in preview_text

    employment_preview_response = client.get(
        "/v1/document-templates/sk.employment.employment_contract/preview/pdf",
        params={"jurisdiction": "SK"},
    )
    assert employment_preview_response.status_code == 200
    employment_preview_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(employment_preview_response.content)).pages
    )
    assert "Pracovna zmluva" in employment_preview_text
    assert "Clanok I." in employment_preview_text
    assert "Clanok IV." in employment_preview_text
    assert "Clanok IX." in employment_preview_text
    assert "Fiktiva Digital Solutions s.r.o." in employment_preview_text
    assert "Tato sablona zatial nema ulozene telo dokumentu." not in employment_preview_text

    delete_response = client.delete("/v1/document-templates/sk.custom.loan_agreement?jurisdiction=SK&version=2")
    assert delete_response.status_code == 200
    assert delete_response.json()["is_deleted"] is True

