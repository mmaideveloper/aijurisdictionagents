from __future__ import annotations

import pytest

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import E2E_TEST_PAID_EMAIL
from aijurisdictionagents.privacy import CONSENT_VERSION, PrivacyControls
from scripts.provision_e2e_users import _grant_synthetic_model_consent


def test_consent_is_current_idempotent_and_limited_to_synthetic_accounts(tmp_path):
    store = ApiDatabaseStore(db_path=tmp_path / "sqlite/consent.db", blob_root=tmp_path / "files")
    store.initialize()
    synthetic = store.create_user(email=E2E_TEST_PAID_EMAIL, password="synthetic-only")
    other = store.create_user(email="ordinary@example.test", password="synthetic-only")
    controls = PrivacyControls(store)
    assert not controls.has_consent(synthetic.user_id, "external_models")
    _grant_synthetic_model_consent(store=store, user_id=synthetic.user_id)
    _grant_synthetic_model_consent(store=store, user_id=synthetic.user_id)
    assert controls.has_consent(synthetic.user_id, "external_models")
    with store._connect() as conn:
        row = store._fetchone(conn, "SELECT COUNT(*) FROM privacy_consent_events WHERE user_id = ?", (synthetic.user_id,))
    assert row[0] == 1
    controls.consent(synthetic.user_id, "external_models", False, version=CONSENT_VERSION)
    _grant_synthetic_model_consent(store=store, user_id=synthetic.user_id)
    assert controls.has_consent(synthetic.user_id, "external_models")
    with pytest.raises(ValueError, match="restricted to approved synthetic"):
        _grant_synthetic_model_consent(store=store, user_id=other.user_id)
    assert not controls.has_consent(other.user_id, "external_models")
    assert not controls.has_consent(synthetic.user_id, "external_checks")
    assert not controls.has_consent(synthetic.user_id, "marketing")
