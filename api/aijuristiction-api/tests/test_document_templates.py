from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.document_templates.api import get_document_template_store, router
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


def test_document_template_store_seeds_initial_template_catalog(tmp_path: Path) -> None:
    store = _build_store(tmp_path)

    items = store.list(jurisdiction="SK")

    keys = {item.template_key for item in items}
    assert "sk.company.share_transfer" in keys
    assert "sk.real_estate.lease_agreement" in keys
    assert "sk.authorization.general_power_of_attorney" in keys
    assert "sk.employment.employment_contract" in keys


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

    deleted = store.soft_delete(template_key="sk.custom.consulting_agreement", jurisdiction="SK")
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
            "is_enabled": True,
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["template_key"] == "sk.custom.loan_agreement"

    patch_response = client.patch(
        "/v1/document-templates/sk.custom.loan_agreement?jurisdiction=SK",
        json={"title": "Pozickova zmluva updated"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["title"] == "Pozickova zmluva updated"

    match_response = client.get(
        "/v1/document-templates/match/search",
        params={"request_text": "Chcem pozickovu zmluvu medzi dvoma osobami", "country": "SK"},
    )
    assert match_response.status_code == 200
    assert match_response.json()["matched"] is True
    assert match_response.json()["template"]["template_key"] == "sk.custom.loan_agreement"

    delete_response = client.delete("/v1/document-templates/sk.custom.loan_agreement?jurisdiction=SK")
    assert delete_response.status_code == 200
    assert delete_response.json()["is_deleted"] is True

