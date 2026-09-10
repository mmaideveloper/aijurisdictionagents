"""Seed synthetic law evidence only into a designated loopback E2E database."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from aijurisdictionagents.llm import get_embedding_client
from services.laws_collector.domain import LawSnapshot, LawMetadataRecord, ProvisionRecord
from services.laws_collector.postgres_store import PostgresLawStore


def main() -> None:
    url = os.environ["LAWS_DB_CLOUD"]
    target = urlsplit(url)
    if target.hostname not in {"localhost", "127.0.0.1", "::1"} or "review_800" not in target.path:
        raise ValueError("Use a designated local review_800 test database.")
    text = "§ 1\nPri syntetickej kúpnej zmluve je kupujúci povinný zaplatiť kúpnu cenu do 15 dní od odovzdania veci. Dohoda o lehote 30 dní sa nahrádza lehotou 15 dní."
    source_url = "https://example.test/synthetic-law-9876-2026"
    metadata = LawMetadataRecord("9876/2026", "Syntetický zákon o skúšobnej kúpe", "zákon", None,
        "2026-01-01", "2026-01-01", None, "Synthetic E2E", ("zmluvné právo",), None)
    snapshot = LawSnapshot(source_system="synthetic-review-800", country_code="SK", collection_code="ZZ",
        year=2026, number=9876, official_name=metadata.title, lawyer_title=metadata.title,
        publication_date="2026-01-01", effective_from="2026-01-01", version_token="review800-v1",
        source_url=source_url, html_url=source_url, pdf_url=source_url, html_content=text, pdf_content=b"",
        provisions=(ProvisionRecord("paragraf-1", "§ 1", text),), metadata=metadata)
    embedding = get_embedding_client().embed_texts([text])
    store = PostgresLawStore(connection_uri=url)
    document_id, _ = store.upsert_document(snapshot)
    checksum = hashlib.sha256(text.encode()).hexdigest()
    version = store.upsert_version(document_id=document_id, snapshot=snapshot,
        version_checksum=snapshot.version_checksum(), html_checksum=checksum, pdf_checksum="",
        html_bytes=len(text.encode()), pdf_bytes=0, normalized_json=json.dumps(snapshot.normalized_payload()),
        embedding_model=embedding.model_name, embedding_dimensions=len(embedding.vectors[0]),
        embedding_vector=json.dumps(embedding.vectors[0]))
    store.replace_provisions(version_id=version.version_id, provisions=snapshot.provisions)
    store.upsert_law_metadata(document_id=document_id, version_id=version.version_id, metadata=metadata)
    store.upsert_artifact(document_id=document_id, version_id=version.version_id,
        source_system="synthetic-review-800", artifact_kind="html", source_url=source_url,
        checksum=checksum, storage_backend="inline", storage_path="", content_text=text,
        content_blob=None, content_bytes=len(text.encode()), http_etag="", http_last_modified="",
        should_redownload=False, verification_status="verified")
    out = Path("runs/document-review-800")
    out.mkdir(parents=True, exist_ok=True)
    (out / "seed.json").write_text(json.dumps({"source_id": document_id,
        "version_id": version.version_id, "run_id": "review800-v1", "synthetic": True}), encoding="utf-8")
    (out / "contract.txt").write_text("Syntetická kúpno-predajná zmluva\n\nStrany sú dve dospelé fyzické osoby, nekonajú ako podnikatelia. Predmetom kúpy je skúšobný stôl. Kúpna cena je 100 EUR.\n\nPodľa § 1 zákona č. 9876/2026 je splatnosť kúpnej ceny 30 dní od odovzdania veci.\n\nDátum uzavretia: 10. septembra 2026.", encoding="utf-8")
    print("Synthetic legal source seeded; sanitized IDs saved in runs/document-review-800/seed.json.")


if __name__ == "__main__":
    main()
