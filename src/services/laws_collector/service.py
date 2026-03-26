from __future__ import annotations

from hashlib import sha256
import json
from typing import Protocol

from .config import LawsCollectorConfig
from .domain import LawSnapshot, SyncSummary, UpdateCheckItem, UpdateCheckPlan


class LawStore(Protocol):
    def upsert_document(self, snapshot: LawSnapshot) -> tuple[str, bool]: ...

    def upsert_version(
        self,
        *,
        document_id: str,
        snapshot: LawSnapshot,
        version_checksum: str,
        html_checksum: str,
        pdf_checksum: str,
        html_bytes: int,
        pdf_bytes: int,
        normalized_json: str,
        embedding_vector: str,
    ): ...

    def replace_provisions(self, *, version_id: str, provisions: tuple): ...

    def upsert_artifact(
        self,
        *,
        document_id: str,
        version_id: str,
        source_system: str,
        artifact_kind: str,
        source_url: str,
        checksum: str,
        content_text: str,
        content_blob: bytes | None,
        content_bytes: int,
        http_etag: str,
        http_last_modified: str,
        should_redownload: bool,
        verification_status: str,
        download_error: str = "",
    ) -> None: ...

    def record_update_event(
        self,
        *,
        document_id: str,
        version_id: str | None,
        event_type: str,
        event_status: str,
        payload: dict[str, object],
    ) -> None: ...


class LawsCollectorService:
    """Ingest and monitor laws snapshots into a corpus store."""

    def __init__(self, *, config: LawsCollectorConfig, store: LawStore) -> None:
        config.validate()
        self.config = config
        self.store = store

    def sync(self, snapshots: tuple[LawSnapshot, ...]) -> SyncSummary:
        summary = SyncSummary()
        for snapshot in snapshots:
            if snapshot.country_code != self.config.country_code:
                raise ValueError(
                    f"Snapshot country {snapshot.country_code} does not match {self.config.country_code}"
                )

            html_checksum = _hash_text(snapshot.html_content)
            pdf_checksum = _hash_bytes(snapshot.pdf_content)
            normalized_json = json.dumps(snapshot.normalized_payload(), ensure_ascii=True, sort_keys=True)
            embedding_vector = _embed_law(snapshot)

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
                embedding_vector=embedding_vector,
            )
            self.store.replace_provisions(version_id=stored_version.version_id, provisions=snapshot.provisions)
            self.store.upsert_artifact(
                document_id=document_id,
                version_id=stored_version.version_id,
                source_system=snapshot.source_system,
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
                source_system=snapshot.source_system,
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

    def plan_updates(
        self,
        *,
        known_snapshots: tuple[LawSnapshot, ...],
        latest_snapshots: tuple[LawSnapshot, ...],
    ) -> UpdateCheckPlan:
        known_by_key = {(item.document_key(), item.version_token): item for item in known_snapshots}
        results: list[UpdateCheckItem] = []
        updates = 0
        for item in latest_snapshots:
            key = (item.document_key(), item.version_token)
            old = known_by_key.get(key)
            reason = "no_change"
            has_update = False
            if old is None:
                has_update = True
                reason = "new_document_or_version"
            elif old.http_etag != item.http_etag or old.http_last_modified != item.http_last_modified:
                has_update = True
                reason = "source_headers_changed"
            elif old.version_checksum() != item.version_checksum():
                has_update = True
                reason = "content_checksum_changed"

            if has_update:
                updates += 1
            results.append(
                UpdateCheckItem(
                    document_key=item.document_key(),
                    country_code=item.country_code,
                    collection_code=item.collection_code,
                    year=item.year,
                    number=item.number,
                    version_token=item.version_token,
                    has_update=has_update,
                    reason=reason,
                )
            )

        return UpdateCheckPlan(
            checked_items=len(results),
            items_with_updates=updates,
            items=tuple(results),
        )


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


def _embed_law(snapshot: LawSnapshot) -> str:
    """Deterministic pseudo-embedding; can be swapped with model embeddings later."""
    text = " ".join(
        [
            snapshot.official_name,
            snapshot.lawyer_title,
            snapshot.html_content,
            " ".join(item.text for item in snapshot.provisions),
        ]
    )
    digest = sha256(text.encode("utf-8")).digest()
    dims = 8
    values = []
    for index in range(dims):
        raw = int.from_bytes(digest[index * 4 : (index + 1) * 4], byteorder="big", signed=False)
        normalized = (raw / 2**32) * 2 - 1
        values.append(f"{normalized:.6f}")
    return "[" + ",".join(values) + "]"
