from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.case_types.api import router
from app.case_types.models import CaseTypeCreateRequest, CaseTypeUpdateRequest
from app.document_templates.store import DocumentTemplateStore, DocumentTemplateStoreConfig, get_document_template_store
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


def test_case_type_store_seeds_case_types_from_templates(tmp_path: Path) -> None:
    store = _build_store(tmp_path)

    items = store.list_case_types(jurisdiction="SK")
    keys = {item.case_type_key for item in items}

    assert "sk.real_estate.lease_agreement" in keys
    assert "sk.justice.fees.exemption_fo" in keys

    ministry_case = store.get_case_type(case_type_key="sk.justice.fees.exemption_fo", jurisdiction="SK")
    assert ministry_case.prompt is not None
    assert ministry_case.templates
    assert ministry_case.templates[0].template_key == "sk.justice.fees.exemption_fo"
    assert "Typicky sa pouziva" in ministry_case.description
    assert "Zvycajne treba pripravit" in ministry_case.description
    assert "K pripadu existuje prepojena sablona v katalogu" in ministry_case.description
    assert "majetkove a prijmove pomery" in ministry_case.description


def test_case_type_store_refreshes_seeded_short_descriptions(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    db_path = tmp_path / "document_templates.sqlite3"

    store.update_case_type(
        case_type_key="sk.justice.company_registry.change_registration",
        jurisdiction="SK",
        payload=CaseTypeUpdateRequest(
            description="Navrh na zapis zmeny udajov do obchodneho registra pre podania v elektronickej podobe",
        ),
    )

    refreshed_store = DocumentTemplateStore(
        DocumentTemplateStoreConfig(
            db_option="sqlite",
            db_cloud="",
            sqlite_path=db_path,
        )
    )
    refreshed_case = refreshed_store.get_case_type(
        case_type_key="sk.justice.company_registry.change_registration",
        jurisdiction="SK",
    )
    assert "Typicky sa pouziva" in refreshed_case.description
    assert "identifikacne udaje spolocnosti" in refreshed_case.description


def test_case_type_store_supports_case_without_template_then_linking_one(tmp_path: Path) -> None:
    store = _build_store(tmp_path)

    created = store.create_case_type(
        CaseTypeCreateRequest(
            case_type_key="sk.custom.general_legal_consultation",
            jurisdiction="SK",
            language="sk-SK",
            name="Vseobecna pravna konzultacia",
            description="Pripad bez predpripravenej sablony.",
            keywords=["pravna konzultacia", "vseobecna rada"],
            template_keys=[],
            is_enabled=True,
        )
    )
    assert created.templates == ()
    assert created.prompt is not None
    assert "Vseobecna pravna konzultacia" in created.prompt.prompt_text

    updated = store.update_case_type(
        case_type_key="sk.custom.general_legal_consultation",
        jurisdiction="SK",
        payload=CaseTypeUpdateRequest(
            template_keys=["sk.real_estate.lease_agreement"],
            prompt_text="Pouzi najomnu sablonu iba ak sa skutkovy stav tyka najmu.",
        ),
    )
    assert len(updated.templates) == 1
    assert updated.templates[0].template_key == "sk.real_estate.lease_agreement"
    assert updated.prompt is not None
    assert updated.prompt.prompt_text == "Pouzi najomnu sablonu iba ak sa skutkovy stav tyka najmu."


def test_case_type_store_resolve_matches_seeded_case(tmp_path: Path) -> None:
    store = _build_store(tmp_path)

    score, matched = store.resolve_case_type(
        request_text="Potrebujem odpor proti platobnemu rozkazu v upominacom konani.",
        country="SK",
    )

    assert score > 0
    assert matched is not None
    assert matched.case_type_key == "sk.justice.payment_order.objection_banska_bystrica"
    assert matched.templates


def test_case_type_api_crud_and_resolve_endpoints(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    client = _build_client(store)

    list_response = client.get("/v1/case-types", params={"jurisdiction": "SK"})
    assert list_response.status_code == 200
    assert any(item["case_type_key"] == "sk.justice.fees.exemption_fo" for item in list_response.json()["items"])

    create_response = client.post(
        "/v1/case-types",
        json={
            "case_type_key": "sk.custom.share_transfer_consultation",
            "jurisdiction": "SK",
            "language": "sk-SK",
            "name": "Prevod obchodneho podielu",
            "description": "Konzultacia alebo priprava dokumentov pre prevod obchodneho podielu.",
            "keywords": ["prevod obchodneho podielu", "spolocnik"],
            "prompt_text": "Zisti udaje o spolocnosti, prevodcovi, nadobudatelovi a podiele.",
            "template_keys": ["sk.company.share_transfer"],
            "is_enabled": True,
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["templates"][0]["template_key"] == "sk.company.share_transfer"

    resolve_response = client.get(
        "/v1/case-types/resolve/search",
        params={"request_text": "Chcem previest obchodny podiel v s.r.o.", "country": "SK"},
    )
    assert resolve_response.status_code == 200
    assert resolve_response.json()["matched"] is True
    resolved_case = resolve_response.json()["case_type"]
    assert resolved_case is not None
    assert any(item["template_key"] == "sk.company.share_transfer" for item in resolved_case["templates"])

    patch_response = client.patch(
        "/v1/case-types/sk.custom.share_transfer_consultation",
        params={"jurisdiction": "SK"},
        json={"description": "Aktualizovany popis pripadu."},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["description"] == "Aktualizovany popis pripadu."

    delete_response = client.delete(
        "/v1/case-types/sk.custom.share_transfer_consultation",
        params={"jurisdiction": "SK"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["is_deleted"] is True
