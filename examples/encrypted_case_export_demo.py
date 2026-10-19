"""Synthetic-only runnable encryption and consent example; no real model invoked."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.case_exports import CaseExports, ExportDenied, now


def main() -> None:
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        key_file = root / "synthetic-key.json"
        key_file.write_text(json.dumps({"active": "demo", "keys": {"demo": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()}}))
        previous = os.environ.get("CASE_ENCRYPTION_KEY_FILE")
        os.environ["CASE_ENCRYPTION_KEY_FILE"] = str(key_file)
        try:
            store = ApiDatabaseStore(db_path=root / "case.sqlite3", blob_root=root / "files")
            store.initialize()
            owner = store.create_user(email="owner@example.invalid", password="synthetic-only")
            admin = store.create_user(email="admin@example.invalid", password="synthetic-only")
            with store._connect() as conn:
                conn.execute("UPDATE users SET role = 'admin' WHERE user_id = ?", (admin.user_id,))
                conn.execute("INSERT INTO case_export_permissions VALUES (?, ?)", (admin.user_id, now()))
            case = store.create_case(user_id=owner.user_id, company_id=None, title="Synthetic case")
            document = store.add_case_document(case_id=case.case_id, kind="uploaded", version=1, original_filename="synthetic.txt", payload=b"Synthetic private text")
            uri = store.get_case_document(case_id=case.case_id, doc_id=document).storage_uri
            assert b"Synthetic private text" not in store._resolve_storage_path(uri).read_bytes()
            assert store.read_storage_bytes(storage_uri=uri) == b"Synthetic private text"
            exports = CaseExports(store)
            request = exports.request(admin.user_id, [case.case_id], "Synthetic demonstration")
            try:
                exports.generate(request, lambda _: b"synthetic archive")
            except ExportDenied:
                pass
            else:
                raise AssertionError("Export must require consent")
            exports.decide(request, owner.user_id, "approved")
            exports.generate(request, lambda _: b"synthetic archive")
            assert exports.download(request, admin.user_id) == b"synthetic archive"
            print("PASS: encrypted storage, authorized read, denied export, consented one-time export")
        finally:
            if previous is None:
                os.environ.pop("CASE_ENCRYPTION_KEY_FILE", None)
            else:
                os.environ["CASE_ENCRYPTION_KEY_FILE"] = previous


if __name__ == "__main__":
    main()
