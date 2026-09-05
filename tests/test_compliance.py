from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.compliance import (
    CONSENT_SCOPE_EXTERNAL_MODEL,
    ComplianceService,
    build_ai_transparency_metadata,
)
from aijurisdictionagents.llm.routing import ModelRouteUnavailable, get_routed_llm_client


def _store(tmp_path: Path) -> ApiDatabaseStore:
    store = ApiDatabaseStore(db_path=tmp_path / "api.sqlite3", blob_root=tmp_path / "blob")
    store.initialize()
    return store


def test_consent_ledger_is_versioned_revocable_and_audited(tmp_path: Path) -> None:
    store = _store(tmp_path)
    user = store.create_user(email="consent@example.test", password="synthetic")
    service = ComplianceService(store)

    grant = service.record_consent(
        user_id=user.user_id,
        scope=CONSENT_SCOPE_EXTERNAL_MODEL,
        notice_version="external-model-v1",
        granted=True,
        source="ui",
        country="SK",
        purpose="external_ai_generation",
    )
    assert service.has_active_consent(
        user_id=user.user_id,
        scope=CONSENT_SCOPE_EXTERNAL_MODEL,
        notice_version="external-model-v1",
    )

    revoke = service.record_consent(
        user_id=user.user_id,
        scope=CONSENT_SCOPE_EXTERNAL_MODEL,
        notice_version="external-model-v1",
        granted=False,
        source="ui",
    )
    assert revoke.previous_event_id == grant.event_id
    assert not service.has_active_consent(
        user_id=user.user_id,
        scope=CONSENT_SCOPE_EXTERNAL_MODEL,
    )

    service.record_event(
        user_id=user.user_id,
        event_type="test",
        action="redaction",
        outcome="completed",
        metadata={"raw_prompt": "secret legal facts", "case_count": 2},
    )
    with sqlite3.connect(store.db_path) as conn:
        metadata = json.loads(
            conn.execute(
                "SELECT metadata_json FROM compliance_events WHERE event_type = 'test'"
            ).fetchone()[0]
        )
        assert metadata == {"case_count": 2}
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("UPDATE compliance_events SET outcome = 'changed'")


def test_dsar_export_restriction_and_erasure_cover_case_artifacts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    user = store.create_user(
        email="dsar@example.test",
        password="synthetic",
        full_name="Synthetic DSAR User",
    )
    case = store.create_case(user_id=user.user_id, company_id=None, title="Synthetic case")
    document_id = store.add_case_document(
        case_id=case.case_id,
        kind="uploaded",
        version=1,
        original_filename="synthetic.txt",
        payload=b"synthetic personal content",
        uploaded_by_user_id=user.user_id,
    )
    store.add_case_message(
        case_id=case.case_id,
        role="user",
        content="Synthetic user message",
    )
    document = store.get_case_document(case_id=case.case_id, doc_id=document_id)
    document_path = store._resolve_storage_path(document.storage_uri)
    service = ComplianceService(store)

    service.set_processing_restriction(
        user_id=user.user_id,
        restricted=True,
        reason_code="subject_request",
    )
    assert service.is_processing_restricted(user_id=user.user_id)
    export = service.export_subject_data(user_id=user.user_id)
    assert export["user"]["email"] == "dsar@example.test"  # type: ignore[index]
    assert export["documents_manifest"][0]["sha256"]  # type: ignore[index]
    assert export["messages_and_communications"][0]["transcript"]  # type: ignore[index]

    result = service.erase_subject_data(user_id=user.user_id, mode="delete")
    assert result["cases_anonymized"] == 1
    assert result["files_erased"] >= 2
    assert not document_path.exists()
    assert store.list_case_documents(case_id=case.case_id) == []
    erased_user = store.get_user(user_id=user.user_id)
    assert erased_user.email.endswith("@invalid.local")
    assert not erased_user.is_enabled


def test_retention_job_removes_expired_security_records_and_deleted_case_content(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    user = store.create_user(email="retention@example.test", password="synthetic")
    case = store.create_case(user_id=user.user_id, company_id=None, title="Expired case")
    store.add_case_document(
        case_id=case.case_id,
        kind="generated",
        version=1,
        original_filename="expired.txt",
        payload=b"expired synthetic content",
        uploaded_by_user_id=user.user_id,
    )
    old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE cases SET status = 'deleted', updated_at = ? WHERE case_id = ?",
            (old, case.case_id),
        )
        conn.execute(
            "INSERT INTO registration_codes(email, code_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
            ("expired@example.test", "hash", old, old),
        )

    result = ComplianceService(store).run_retention()
    assert result.deleted_rows["registration_codes"] == 1
    assert result.deleted_rows["deleted_case_content"] == 1
    assert store.list_case_documents(case_id=case.case_id) == []


def test_ai_transparency_contract_is_complete() -> None:
    metadata = build_ai_transparency_metadata(
        provider="azure_foundry",
        model="synthetic-model",
        source_provenance=[{"source_id": "SK:TEST:1"}],
        tool_provenance=[{"tool": "synthetic_lookup"}],
    )
    assert metadata["ai_generated"] is True
    assert metadata["model_provider"] == "azure_foundry"
    assert metadata["model_name"] == "synthetic-model"
    assert metadata["generated_at"]
    assert metadata["limitations_notice"]
    assert metadata["human_review_recommended"] is True
    assert metadata["source_provenance"] == [{"source_id": "SK:TEST:1"}]
    assert metadata["tool_provenance"] == [{"tool": "synthetic_lookup"}]


def test_processing_restriction_blocks_model_execution(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    store = _store(tmp_path)
    user = store.create_user(email="restricted@example.test", password="synthetic")
    ComplianceService(store).set_processing_restriction(
        user_id=user.user_id,
        restricted=True,
        reason_code="subject_request",
    )

    with pytest.raises(ModelRouteUnavailable) as exc_info:
        get_routed_llm_client(store=store, user_id=user.user_id, task_type="chat_reply")
    assert exc_info.value.status_code == 423
