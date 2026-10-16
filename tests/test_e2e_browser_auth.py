from __future__ import annotations

import json
import os
import stat

import pytest

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import E2E_TEST_USER_EMAILS
from scripts.provision_e2e_browser_auth import create_fixture, revoke_fixture


def test_private_fixture_authenticates_and_revokes_only_its_devices(tmp_path):
    store = ApiDatabaseStore(db_path=tmp_path / "sqlite/auth.db", blob_root=tmp_path / "files")
    store.initialize()
    for email in E2E_TEST_USER_EMAILS:
        store.create_user(email=email, password="synthetic-only")
    other = store.create_user(email="ordinary@example.test", password="synthetic-only")
    existing = store.issue_device_auth_token(user_id=other.user_id, device_id="unrelated-device")
    path = tmp_path / "private/browser-auth.json"
    create_fixture(store, path)
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    records = json.loads(path.read_text())["users"]
    assert {record["email"] for record in records} == E2E_TEST_USER_EMAILS
    for record in records:
        assert (
            store.authenticate_user_device_auth_token(
                user_id=record["userId"],
                device_id=record["deviceId"],
                token=record["deviceAuthToken"],
            )
            is not None
        )
    with pytest.raises(FileExistsError):
        create_fixture(store, path)
    revoke_fixture(store, path)
    assert not path.exists()
    for record in records:
        assert (
            store.authenticate_user_device_auth_token(
                user_id=record["userId"],
                device_id=record["deviceId"],
                token=record["deviceAuthToken"],
            )
            is None
        )
    assert (
        store.authenticate_user_device_auth_token(
            user_id=other.user_id, device_id="unrelated-device", token=existing
        )
        is not None
    )


def test_cleanup_rejects_customer_records_before_revoking_anything(tmp_path):
    store = ApiDatabaseStore(db_path=tmp_path / "sqlite/auth.db", blob_root=tmp_path / "files")
    store.initialize()
    other = store.create_user(email="ordinary@example.test", password="synthetic-only")
    path = tmp_path / "forged.json"
    path.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "userId": other.user_id,
                        "email": other.email,
                        "deviceId": "prod-e2e-" + "a" * 32,
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="approved synthetic"):
        revoke_fixture(store, path)
    assert path.exists()
