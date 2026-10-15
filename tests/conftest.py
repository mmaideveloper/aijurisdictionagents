from __future__ import annotations

import os
import pytest

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.privacy import CONSENT_VERSION, PrivacyControls, privacy_scope

# Most tests intentionally stay offline/deterministic and still use the pre-existing
# mock/cloud embedding path unless they explicitly opt into the local model path.
os.environ.setdefault("SYSTEM_EMBEDDING_MODEL_OPTION", "cloud")


@pytest.fixture
def external_check_subject(tmp_path):
    """Supply a real consent context for deterministic external-tool fixtures."""
    store = ApiDatabaseStore(db_path=tmp_path / "sqlite/privacy.db", blob_root=tmp_path / "files")
    store.initialize()
    user = store.create_user(email="tools@example.test", password="synthetic-only")
    controls = PrivacyControls(store)
    controls.consent(user.user_id, "external_checks", True, version=CONSENT_VERSION)
    with privacy_scope(controls, user.user_id):
        yield controls, user
