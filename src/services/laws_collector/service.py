from __future__ import annotations

from hashlib import sha256
import json

from .config import LawsCollectorConfig
from .domain import SlovLexLawSnapshot, SyncSummary
from .sqlite_store import SqliteLawStore


class SlovakLawsCollectorService:
    """Ingest Slov-Lex snapshots into the local law corpus store."""

    def __init__(self, *, config: LawsCollectorConfig, store: SqliteLawStore) -> None:
        config.validate()
        self.config = config
        self.store = store

    def sync(self, snapshots: tuple[SlovLexLawSnapshot, ...]) -> SyncSummary:
        summary = SyncSummary()
        for snapshot in snapshots:
            if snapshot.country_code != self.config.country_code:
                raise ValueError(
                    f"Snapshot country {snapshot.country_code} does not match {self.config.country_code}"
                )

            html_checksum = _hash_text(snapshot.html_content)
            pdf_checksum = _hash_bytes(snapshot.pdf_content)
            normalized_json = json.dumps(snapshot.normalized_payload(), ensure_ascii=True, sort_keys=True)

            document_id, document_created = self.store.upsert_document(snapshot)
            stored_version = self.store.upsert_version(
                document_id=document_id,
                snapshot=snapshot,
                version_checksum=snapshot.version_checksum(),
                html_checksum=html_checksum,
                pdf_checksum=pdf_checksum,
                html_bytes=len(snapshot.html_content.encode("utf-8")),
                pdf_bytes=len(snapshot.pdf_content),
                normalized_json=normalized_json,
            )
            self.store.replace_provisions(version_id=stored_version.version_id, provisions=snapshot.provisions)
            self.store.upsert_artifact(
                document_id=document_id,
                version_id=stored_version.version_id,
                artifact_kind="html",
                source_url=snapshot.html_url,
                checksum=html_checksum,
                content_text=snapshot.html_content,
                content_blob=None,
                content_bytes=len(snapshot.html_content.encode("utf-8")),
                http_etag=snapshot.http_etag,
                http_last_modified=snapshot.http_last_modified,
                should_redownload=False,
                verification_status="stored",
            )
            self.store.upsert_artifact(
                document_id=document_id,
                version_id=stored_version.version_id,
                artifact_kind="pdf",
                source_url=snapshot.pdf_url,
                checksum=pdf_checksum,
                content_text="",
                content_blob=snapshot.pdf_content,
                content_bytes=len(snapshot.pdf_content),
                http_etag=snapshot.http_etag,
                http_last_modified=snapshot.http_last_modified,
                should_redownload=False,
                verification_status="stored",
            )

            event_type = _event_type(document_created=document_created, version_state=stored_version.state)
            if event_type != "no_change":
                self.store.record_update_event(
                    document_id=document_id,
                    version_id=stored_version.version_id,
                    event_type=event_type,
                    event_status="recorded",
                    payload={
                        "document_key": snapshot.document_key(),
                        "version_token": snapshot.version_token,
                        "effective_from": snapshot.effective_from,
                        "official_name": snapshot.official_name,
                        "lawyer_title": snapshot.lawyer_title,
                        "source_url": snapshot.source_url,
                    },
                )

            summary = summary.merge(
                SyncSummary(
                    processed=1,
                    new_documents=1 if document_created else 0,
                    new_versions=1 if event_type == "new_version" else 0,
                    metadata_updates=1 if event_type == "metadata_change" else 0,
                    skipped=1 if event_type == "no_change" else 0,
                )
            )
        return summary


def _event_type(*, document_created: bool, version_state: str) -> str:
    if document_created:
        return "new_act"
    if version_state == "created":
        return "new_version"
    if version_state == "updated":
        return "metadata_change"
    return "no_change"


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _hash_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()
