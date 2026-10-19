"""Offline, resumable migration. Stop API/workers first; never downgrade to plaintext."""
from __future__ import annotations

import argparse
import os
import hashlib
import json
import re
from pathlib import Path

from dotenv import load_dotenv

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.case_crypto import PREFIX

# Identifiers below are constants, never supplied by an API caller.
FIELDS = {
    "privacy_ai_artifacts": ("artifact_id", {"metadata_json": "privacy-artifact"}),
    "software_assessments": ("assessment_id", {"payload_json": "assessment"}),
    "document_reviews": ("review_id", {"payload_json": "review"}),
    "case_catalog_selections": ("selection_id", {"first_message_preview": "catalog:preview", "clarification_question": "catalog:question"}),
    "case_catalog_events": ("event_id", {"summary": "catalog:summary", "details_json": "catalog:details"}),
    "case_citations": ("citation_id", {'source_url': 'citation:source_url', 'title': 'citation:title', 'citation_label': 'citation:citation_label', 'law_number': 'citation:law_number', 'section': 'citation:section', 'effective_from': 'citation:effective_from', 'court': 'citation:court', 'ecli': 'citation:ecli', 'file_number': 'citation:file_number', 'decision_date': 'citation:decision_date', 'snippet': 'citation:snippet'}),
    "ai_model_usage_ledger": ("usage_id", {"question_preview": "usage:preview", "audit_metadata_json": "usage:metadata"}),
    "cases": ("case_id", {"title": "title"}),
    "case_documents": ("doc_id", {"original_filename": "filename", "processing_error": "processing-error"}),
    "case_communications": ("communication_id", {"summary": "summary", "presentation_json": "presentation"}),
    "case_document_contents": ("content_id", {"extracted_text": "extracted", "embedding_vector": "vector"}),
    "case_document_chunks": ("chunk_id", {"chunk_text": "chunk", "embedding_vector": "vector"}),
}


def migrate(store: ApiDatabaseStore) -> int:
    cipher = store.case_cipher
    if cipher is None:
        raise RuntimeError("Case encryption key file required")
    changed = 0
    for table, (primary, fields) in FIELDS.items():
        with store._connect() as conn:
            # Honor existing erasure tombstones, including legacy schemas without cascades.
            store._execute(conn, f"DELETE FROM {table} WHERE case_id IN (SELECT case_id FROM case_encryption_erased)", ())
            rows = store._execute(conn, f"SELECT {primary}, case_id, {', '.join(fields)} FROM {table}", ()).fetchall()
        for row in rows:
            if not row[1]:
                continue
            updates = []
            values = []
            for column, purpose in fields.items():
                value = row[2 + list(fields).index(column)]
                if value is None:
                    continue
                if str(value).startswith(PREFIX):
                    cipher.decrypt(str(row[1]), purpose, str(value))
                    continue
                encrypted = cipher.encrypt(str(row[1]), purpose, str(value).encode())
                assert cipher.decrypt(str(row[1]), purpose, encrypted) == str(value).encode()
                updates.append(f"{column} = ?")
                values.append(encrypted)
            if updates:
                with store._connect() as conn:
                    store._execute(conn, f"UPDATE {table} SET {', '.join(updates)} WHERE {primary} = ?", (*values, row[0]))
                changed += 1
    changed += migrate_files(store)
    return changed


def migrate_files(store: ApiDatabaseStore) -> int:
    cipher = store.case_cipher
    assert cipher is not None
    with store._connect() as conn:
        store._execute_script(conn, (Path(__file__).resolve().parents[1] / "databases/api/migrations/0922_case_file_migration.sql").read_text())
        pending = store._execute(conn, "SELECT migration_id, case_id, payload FROM case_file_migration_journal", ()).fetchall()
    changed = 0
    for migration_id, case_id, encoded in pending:
        mapping = json.loads(cipher.decrypt(case_id, "file-migration:" + migration_id, encoded))
        _finish_file(store, migration_id, case_id, mapping["old"], mapping["new"])
        changed += 1
    with store._connect() as conn:
        uris = store._execute(conn, "SELECT storage_uri FROM case_documents UNION SELECT transcript_uri FROM case_communications WHERE transcript_uri IS NOT NULL", ()).fetchall()
    for (uri,) in uris:
        path = store._resolve_storage_path(str(uri))
        relative = path.relative_to(store.blob_root.resolve())
        opaque = bool(re.fullmatch(r"(?:v[0-9]+|encrypted-[a-f0-9]{64})\.bin", path.name))
        payload = path.read_bytes()
        if opaque and payload.startswith(PREFIX.encode()):
            cipher.decrypt(relative.parts[0], relative.as_posix(), payload.decode("ascii"))
            continue
        migration_id = hashlib.sha256(str(uri).encode()).hexdigest()
        new_relative = relative if opaque else relative.with_name("encrypted-" + migration_id + ".bin")
        new_uri = (store.store_cloud.rstrip("/") + "/" if str(uri).startswith("https://") else "") + new_relative.as_posix()
        encoded = cipher.encrypt(relative.parts[0], "file-migration:" + migration_id, json.dumps({"old": str(uri), "new": new_uri}).encode())
        with store._connect() as conn:
            store._execute(conn, "INSERT INTO case_file_migration_journal VALUES (?, ?, ?) ON CONFLICT(migration_id) DO NOTHING", (migration_id, relative.parts[0], encoded))
        _finish_file(store, migration_id, relative.parts[0], str(uri), new_uri)
        changed += 1
    return changed


def _finish_file(store: ApiDatabaseStore, migration_id: str, case_id: str, old_uri: str, new_uri: str) -> None:
    cipher = store.case_cipher
    assert cipher is not None
    old = store._resolve_storage_path(old_uri)
    target = store._resolve_storage_path(new_uri)
    old_relative = old.relative_to(store.blob_root.resolve()).as_posix()
    new_relative = target.relative_to(store.blob_root.resolve()).as_posix()
    if old.exists():
        payload = old.read_bytes()
        if payload.startswith(PREFIX.encode()):
            payload = cipher.decrypt(case_id, old_relative, payload.decode("ascii"))
        encrypted = cipher.encrypt(case_id, new_relative, payload)
        assert cipher.decrypt(case_id, new_relative, encrypted) == payload
        temporary = target.with_name(target.name + ".encrypted-pending")
        temporary.write_text(encrypted, encoding="ascii")
        os.replace(temporary, target)
    else:
        cipher.decrypt(case_id, new_relative, target.read_text(encoding="ascii"))
    with store._connect() as conn:
        store._execute(conn, "UPDATE case_documents SET storage_uri = ? WHERE storage_uri = ?", (new_uri, old_uri))
        store._execute(conn, "UPDATE case_communications SET transcript_uri = ? WHERE transcript_uri = ?", (new_uri, old_uri))
    if old != target:
        old.unlink(missing_ok=True)
    with store._connect() as conn:
        store._execute(conn, "DELETE FROM case_file_migration_journal WHERE migration_id = ?", (migration_id,))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-confirmed", action="store_true", required=True)
    parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    store = ApiDatabaseStore.from_env()
    store.initialize()
    print(f"Encrypted/verified records and files; changed={migrate(store)}")
