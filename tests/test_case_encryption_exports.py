import base64
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.case_crypto import CaseEncryptionError
from aijurisdictionagents.case_exports import CaseExports, ExportDenied, now


@pytest.fixture
def secured(tmp_path, monkeypatch):
    key_file = tmp_path / "keys.json"
    key_file.write_text(json.dumps({"active": "test-1", "keys": {"test-1": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()}}))
    monkeypatch.setenv("CASE_ENCRYPTION_KEY_FILE", str(key_file))
    store = ApiDatabaseStore(db_path=tmp_path / "api.sqlite3", blob_root=tmp_path / "blobs")
    store.initialize()
    users = [store.create_user(email=f"synthetic-{i}@example.invalid", password="synthetic-test-only", full_name=f"Synthetic {i}", phone_number=None) for i in range(3)]
    with store._connect() as conn:
        conn.execute("UPDATE users SET role = 'admin' WHERE user_id = ?", (users[2].user_id,))
        conn.execute("INSERT INTO case_export_permissions VALUES (?, ?)", (users[2].user_id, now()))
    cases = [store.create_case(user_id=u.user_id, company_id=None, title="Synthetic confidential title") for u in users[:2]]
    return store, users, cases, key_file


def test_encrypted_roundtrip_and_tampering(secured):
    store, users, cases, key_file = secured
    case = cases[0]
    doc_id = store.add_case_document(case_id=case.case_id, kind="uploaded", version=1, original_filename="private.txt", payload=b"Synthetic secret clause 123")
    store.upsert_document_content(doc_id=doc_id, case_id=case.case_id, extracted_text="Synthetic secret clause 123", embedding_vector="[0.2, 0.5]", embedding_model="synthetic", embedding_dimensions=2)
    store.add_case_message(case_id=case.case_id, role="user", content="Synthetic confidential question")
    doc = store.get_case_document(case_id=case.case_id, doc_id=doc_id)
    stored = store._resolve_storage_path(doc.storage_uri)
    assert stored.read_bytes().startswith(b"jdenc1:")
    assert store.read_storage_bytes(storage_uri=doc.storage_uri) == b"Synthetic secret clause 123"
    assert store.list_case_document_contents(case_id=case.case_id)[0][2:] == ("Synthetic secret clause 123", "[0.2, 0.5]")
    assert "confidential question" in store.list_case_communications(case_id=case.case_id)[0].summary
    with store._connect() as conn:
        assert conn.execute("SELECT title FROM cases WHERE case_id = ?", (case.case_id,)).fetchone()[0].startswith("jdenc1:")
        assert all(v.startswith("jdenc1:") for v in conn.execute("SELECT extracted_text, embedding_vector FROM case_document_contents").fetchone())
    original = stored.read_bytes()
    stored.write_bytes(original[:-5] + b"AAAAA")
    with pytest.raises(CaseEncryptionError):
        store.read_storage_bytes(storage_uri=doc.storage_uri)
    stored.write_bytes(original)
    ring = json.loads(key_file.read_text())
    ring["keys"]["test-2"] = base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()
    ring["active"] = "test-2"
    key_file.write_text(json.dumps(ring))
    store.case_cipher.rotate(case.case_id)
    del ring["keys"]["test-1"]
    key_file.write_text(json.dumps(ring))
    assert store.read_storage_bytes(storage_uri=doc.storage_uri) == b"Synthetic secret clause 123"
    key_file.unlink()
    with pytest.raises(CaseEncryptionError):
        store.read_storage_bytes(storage_uri=doc.storage_uri)
    # Restore the backed-up rotated key ring and open a fresh store/cache.
    key_file.write_text(json.dumps(ring))
    restored = ApiDatabaseStore(db_path=store.db_path, blob_root=store.blob_root)
    assert restored.read_storage_bytes(storage_uri=doc.storage_uri) == b"Synthetic secret clause 123"


def test_every_owner_required_and_single_download(secured):
    store, users, cases, _ = secured
    service = CaseExports(store)
    admin = users[2].user_id
    request_id = service.request(admin, [c.case_id for c in cases], "Synthetic support export")
    with pytest.raises(ExportDenied):
        service.generate(request_id, lambda _: b"archive")
    service.decide(request_id, users[0].user_id, "approved")
    with pytest.raises(ExportDenied):
        service.generate(request_id, lambda _: b"archive")
    service.decide(request_id, users[1].user_id, "approved")
    service.generate(request_id, lambda _: b"synthetic archive")
    with store._connect() as conn:
        assert conn.execute("SELECT artifact FROM case_export_requests").fetchone()[0].startswith("jdenc1:")

    def download():
        try:
            return service.download(request_id, admin)
        except ExportDenied:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: download(), range(2)))
    assert results.count(b"synthetic archive") == 1
    assert results.count(None) == 1


@pytest.mark.parametrize("failure", ["revoked", "permission", "expired"])
def test_download_rechecks_authorization(secured, failure):
    store, users, cases, _ = secured
    service = CaseExports(store)
    admin = users[2].user_id
    request_id = service.request(admin, [cases[0].case_id], "Synthetic export")
    service.decide(request_id, users[0].user_id, "approved")
    service.generate(request_id, lambda _: b"archive")
    if failure == "revoked":
        service.decide(request_id, users[0].user_id, "revoked")
    else:
        with store._connect() as conn:
            if failure == "permission":
                conn.execute("DELETE FROM case_export_permissions")
            else:
                conn.execute("UPDATE case_export_requests SET artifact_expires_at = '2000-01-01'")
    with pytest.raises(ExportDenied):
        service.download(request_id, admin)
    if failure == "expired":
        assert service.cleanup() == 1
        with store._connect() as conn:
            assert conn.execute("SELECT artifact FROM case_export_requests").fetchone()[0] is None


def test_case_revision_change_invalidates_consent(secured):
    store, users, cases, _ = secured
    service = CaseExports(store)
    request = service.request(users[2].user_id, [cases[0].case_id], "Synthetic review")
    service.decide(request, users[0].user_id, "approved")
    store.update_case_title(case_id=cases[0].case_id, user_id=users[0].user_id, title="Changed after consent")
    with pytest.raises(ExportDenied):
        service.generate(request, lambda _: b"must not export changed scope")


def test_purge_revokes_archive_and_erases_case_key(secured):
    from aijurisdictionagents.privacy_retention import purge_case
    store, users, cases, _ = secured
    service = CaseExports(store)
    request = service.request(users[2].user_id, [cases[0].case_id], "Synthetic review")
    service.decide(request, users[0].user_id, "approved")
    service.generate(request, lambda _: b"synthetic archive")
    assert purge_case(store, cases[0].case_id, users[0].user_id)
    with store._connect() as conn:
        assert conn.execute("SELECT 1 FROM case_encryption_keys WHERE case_id = ?", (cases[0].case_id,)).fetchone() is None
        assert conn.execute("SELECT status, artifact FROM case_export_requests WHERE request_id = ?", (request,)).fetchone() == ("revoked", None)
    with pytest.raises(ExportDenied):
        service.download(request, users[2].user_id)

    with pytest.raises(CaseEncryptionError):
        store.case_cipher.encrypt(cases[0].case_id, "title", b"must not resurrect")


def test_interrupted_plaintext_migration_resumes_and_is_idempotent(secured, monkeypatch):
    import runpy
    from pathlib import Path
    store, users, cases, _ = secured
    doc_id = store.add_case_document(case_id=cases[0].case_id, kind="uploaded", version=1, original_filename="legacy.txt", payload=b"Synthetic legacy payload")
    doc = store.get_case_document(case_id=cases[0].case_id, doc_id=doc_id)
    path = store._resolve_storage_path(doc.storage_uri)
    path.write_bytes(b"Synthetic legacy payload")
    with store._connect() as conn:
        conn.execute("UPDATE cases SET title = 'Synthetic legacy title' WHERE case_id = ?", (cases[0].case_id,))
        conn.execute("UPDATE case_documents SET original_filename = 'legacy.txt' WHERE doc_id = ?", (doc_id,))
    migrate = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/migrate_case_encryption.py"))["migrate"]
    original = store.case_cipher.encrypt
    calls = 0
    def interrupted(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic migration interruption")
        return original(*args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(store.case_cipher, "encrypt", interrupted)
        with pytest.raises(RuntimeError, match="synthetic migration interruption"):
            migrate(store)
    assert migrate(store) > 0
    assert migrate(store) == 0
    assert store.get_case(case_id=cases[0].case_id).title == "Synthetic legacy title"
    assert store.read_storage_bytes(storage_uri=doc.storage_uri) == b"Synthetic legacy payload"
    assert path.read_bytes().startswith(b"jdenc1:")


def test_file_rename_journal_recovers_after_database_failure(secured, monkeypatch):
    import runpy
    from pathlib import Path
    store, _, cases, _ = secured
    case_id = cases[0].case_id
    doc_id = store.add_case_document(case_id=case_id, kind="uploaded", version=1, original_filename="legacy.txt", payload=b"Synthetic journal payload")
    doc = store.get_case_document(case_id=case_id, doc_id=doc_id)
    opaque = store._resolve_storage_path(doc.storage_uri)
    legacy = opaque.with_name("private-legacy-name.txt")
    legacy.write_bytes(b"Synthetic journal payload")
    opaque.unlink()
    uri = legacy.relative_to(store.blob_root.resolve()).as_posix()
    with store._connect() as conn:
        conn.execute("UPDATE case_documents SET storage_uri = ? WHERE doc_id = ?", (uri, doc_id))
    migrate = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/migrate_case_encryption.py"))["migrate"]
    execute = store._execute
    def interrupted(conn, query, params=()):
        if query.startswith("UPDATE case_documents SET storage_uri"):
            raise RuntimeError("synthetic database interruption")
        return execute(conn, query, params)
    with monkeypatch.context() as patch:
        patch.setattr(store, "_execute", interrupted)
        with pytest.raises(RuntimeError, match="synthetic database interruption"):
            migrate(store)
    assert migrate(store) > 0
    assert migrate(store) == 0
    doc = store.get_case_document(case_id=case_id, doc_id=doc_id)
    assert "private-legacy-name" not in doc.storage_uri
    assert not legacy.exists()
    assert store.read_storage_bytes(storage_uri=doc.storage_uri) == b"Synthetic journal payload"
    with store._connect() as conn:
        assert conn.execute("SELECT count(*) FROM case_file_migration_journal").fetchone()[0] == 0
