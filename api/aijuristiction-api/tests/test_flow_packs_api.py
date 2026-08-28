from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
import tempfile
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.ai_model_admin_api import AdminContext, require_ai_model_admin
from app.flow_packs.api import get_flow_pack_store
from app.main import app

client = TestClient(app)
AUTH_HEADERS = {"x-api-key": "aijuris", "x-admin-api-key": "admin-secret"}


@pytest.fixture(autouse=True)
def isolated_flow_pack_store() -> Iterator[None]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "flow_packs.sqlite3"
        os.environ["API_FLOW_PACKS_SQLITE_PATH"] = str(db_path)
        os.environ["JURISDIGTA_ADMIN_API_KEY"] = "admin-secret"
        app.dependency_overrides[require_ai_model_admin] = lambda: AdminContext(
            user_id="test-admin", email="admin@example.test"
        )
        get_flow_pack_store.cache_clear()
        app.dependency_overrides.pop(require_ai_model_admin, None)
        yield
        get_flow_pack_store.cache_clear()
        os.environ.pop("API_FLOW_PACKS_SQLITE_PATH", None)
        os.environ.pop("JURISDIGTA_ADMIN_API_KEY", None)


def test_list_default_flow_packs() -> None:
    response = client.get("/v1/flow-packs", headers=AUTH_HEADERS)
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    flow_keys = {item["flow_key"] for item in payload["items"]}
    assert "sk.contract.sale_purchase" in flow_keys
    assert "sk.civil.power_of_attorney" in flow_keys
    assert "cz.contract.sale_purchase" in flow_keys


def test_create_update_enable_disable_soft_delete_and_version() -> None:
    flow_key = f"sk.civil.notice_template.{uuid4().hex[:8]}"
    create_response = client.post(
        "/v1/flow-packs",
        headers=AUTH_HEADERS,
        json={
            "flow_key": flow_key,
            "jurisdiction": "SK",
            "domain": "civil",
            "title": "Predžalobná výzva",
            "description": "Flow pre predzalobnu vyzvu",
            "definition": {"required_facts": ["counterparty", "claim_summary"]},
            "is_enabled": False,
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["version"] == 1

    update_response = client.patch(
        f"/v1/flow-packs/{flow_key}/versions/1",
        headers=AUTH_HEADERS,
        json={"title": "Predžalobná výzva - aktualizovaná"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Predžalobná výzva - aktualizovaná"

    enable_response = client.post(
        f"/v1/flow-packs/{flow_key}/versions/1/enable",
        headers=AUTH_HEADERS,
    )
    assert enable_response.status_code == 200
    assert enable_response.json()["is_enabled"] is True
    assert enable_response.json()["lifecycle_state"] == "published"

    immutable_response = client.patch(
        f"/v1/flow-packs/{flow_key}/versions/1",
        headers=AUTH_HEADERS,
        json={"title": "Published versions cannot change"},
    )
    assert immutable_response.status_code == 409

    disable_response = client.post(
        f"/v1/flow-packs/{flow_key}/versions/1/disable",
        headers=AUTH_HEADERS,
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["is_enabled"] is False
    assert disable_response.json()["lifecycle_state"] == "retired"

    create_version_response = client.post(
        f"/v1/flow-packs/{flow_key}/versions",
        headers=AUTH_HEADERS,
        json={
            "description": "Flow pre predzalobnu vyzvu - verzia 2",
            "definition": {"required_facts": ["counterparty", "claim_summary", "deadline"]},
            "is_enabled": False,
        },
    )
    assert create_version_response.status_code == 201
    created_version = create_version_response.json()
    assert created_version["version"] == 2
    assert created_version["is_enabled"] is False

    delete_response = client.delete(
        f"/v1/flow-packs/{flow_key}/versions/1",
        headers=AUTH_HEADERS,
    )
    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["is_deleted"] is True
    assert deleted["is_enabled"] is False

    list_versions_response = client.get(
        f"/v1/flow-packs/{flow_key}/versions",
        headers=AUTH_HEADERS,
    )
    assert list_versions_response.status_code == 200
    versions = list_versions_response.json()["versions"]
    assert [item["version"] for item in versions] == [2, 1]


def test_same_flow_key_can_exist_in_multiple_jurisdictions() -> None:
    common_key = f"contract.sale_purchase.{uuid4().hex[:6]}"
    for jurisdiction in ("SK", "CZ"):
        response = client.post(
            "/v1/flow-packs",
            headers=AUTH_HEADERS,
            json={
                "flow_key": common_key,
                "jurisdiction": jurisdiction,
                "domain": "civil",
                "title": f"Kupna zmluva {jurisdiction}",
                "description": f"Flow for {jurisdiction}",
                "definition": {"required_facts": ["seller_identification", "buyer_identification"]},
                "is_enabled": True,
            },
        )
        assert response.status_code == 201
        assert response.json()["version"] == 1
        assert response.json()["jurisdiction"] == jurisdiction

    ambiguous = client.get(f"/v1/flow-packs/{common_key}/versions/1", headers=AUTH_HEADERS)
    assert ambiguous.status_code == 400

    resolved = client.get(
        f"/v1/flow-packs/{common_key}/versions/1",
        params={"jurisdiction": "CZ"},
        headers=AUTH_HEADERS,
    )
    assert resolved.status_code == 200
    assert resolved.json()["jurisdiction"] == "CZ"
