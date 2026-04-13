from __future__ import annotations

from hashlib import sha256
import json
from math import fsum
from pathlib import PurePosixPath
from time import perf_counter
from typing import Protocol
from urllib.parse import urlparse

from aijurisdictionagents.llm.embeddings import EmbeddingClient, get_embedding_client
from services.document_processor.runtime import (
    chunk_document_text,
    cosine_similarity,
    parse_embedding_vector,
    serialize_embedding_vector,
)

from .config import LawsCollectorConfig
from .domain import (
    LawSemanticCandidate,
    LawSemanticSearchResult,
    LawMetadataRecord,
    LawRelationRecord,
    LawSnapshot,
    SyncSummary,
    UpdateCheckItem,
    UpdateCheckPlan,
    format_law_identifier,
)
from .source_artifact_storage import (
    SourceArtifactObjectStore,
    StoredSourceArtifactObject,
    build_source_artifact_object_store,
)


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
        embedding_model: str,
        embedding_dimensions: int,
        embedding_vector: str,
    ): ...

    def replace_provisions(self, *, version_id: str, provisions: tuple): ...

    def upsert_law_metadata(
        self,
        *,
        document_id: str,
        version_id: str,
        metadata: LawMetadataRecord,
    ) -> str: ...

    def replace_law_relations(
        self,
        *,
        law_metadata_id: str,
        relations: tuple[LawRelationRecord, ...],
    ) -> None: ...

    def upsert_artifact(
        self,
        *,
        document_id: str,
        version_id: str,
        source_system: str,
        artifact_kind: str,
        source_url: str,
        checksum: str,
        storage_backend: str,
        storage_path: str,
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

    def list_semantic_candidates(self) -> list[LawSemanticCandidate]: ...


class LawsCollectorService:
    """Ingest and monitor laws snapshots into a corpus store."""

    def __init__(
        self,
        *,
        config: LawsCollectorConfig,
        store: LawStore,
        embedding_client: EmbeddingClient | None = None,
        source_artifact_store: SourceArtifactObjectStore | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.store = store
        self.embedding_client = embedding_client or get_embedding_client()
        self.source_artifact_store = source_artifact_store or build_source_artifact_object_store(config)

    def sync(self, snapshots: tuple[LawSnapshot, ...]) -> SyncSummary:
        summary = SyncSummary()
        for snapshot in snapshots:
            if snapshot.country_code != self.config.country_code:
                raise ValueError(
                    f"Snapshot country {snapshot.country_code} does not match {self.config.country_code}"
                )

            started_at = perf_counter()
            law_id = format_law_identifier(year=snapshot.year, number=snapshot.number)
            _log(
                f"start law country={snapshot.country_code} law={law_id} source={snapshot.source_url}"
            )
            html_checksum = _hash_text(snapshot.html_content)
            pdf_checksum = _hash_bytes(snapshot.pdf_content)
            normalized_json = json.dumps(snapshot.normalized_payload(), ensure_ascii=True, sort_keys=True)

            document_id, document_created = self.store.upsert_document(snapshot)
            document_status = "created" if document_created else "updated"
            _log(f"database upload law={law_id} document_status={document_status}")

            _log(f"vector start law={law_id}")
            embedding_model, embedding_dimensions, embedding_vector = _embed_snapshot(
                snapshot=snapshot,
                embedding_client=self.embedding_client,
            )
            html_source_content = snapshot.html_source_content or snapshot.html_content.encode("utf-8")
            stored_version = self.store.upsert_version(
                document_id=document_id,
                snapshot=snapshot,
                version_checksum=snapshot.version_checksum(),
                html_checksum=html_checksum,
                pdf_checksum=pdf_checksum,
                html_bytes=len(snapshot.html_content.encode("utf-8")),
                pdf_bytes=len(snapshot.pdf_content),
                normalized_json=normalized_json,
                embedding_model=embedding_model,
                embedding_dimensions=embedding_dimensions,
                embedding_vector=embedding_vector,
            )
            if snapshot.metadata is not None:
                law_metadata_id = self.store.upsert_law_metadata(
                    document_id=document_id,
                    version_id=stored_version.version_id,
                    metadata=snapshot.metadata,
                )
                self.store.replace_law_relations(
                    law_metadata_id=law_metadata_id,
                    relations=snapshot.relations,
                )
            self.store.replace_provisions(version_id=stored_version.version_id, provisions=snapshot.provisions)
            html_artifact = _persist_source_artifact(
                source_artifact_store=self.source_artifact_store,
                country_code=snapshot.country_code,
                collection_code=snapshot.collection_code,
                year=snapshot.year,
                number=snapshot.number,
                version_token=snapshot.version_token,
                artifact_kind="html",
                source_url=snapshot.html_url,
                checksum=html_checksum,
                default_extension=".html",
                content=html_source_content,
            )
            self.store.upsert_artifact(
                document_id=document_id,
                version_id=stored_version.version_id,
                source_system=snapshot.source_system,
                artifact_kind="html",
                source_url=snapshot.html_url,
                checksum=html_checksum,
                storage_backend=html_artifact.storage_backend,
                storage_path=html_artifact.storage_path,
                content_text=snapshot.html_content,
                content_blob=None,
                content_bytes=len(html_source_content),
                http_etag=snapshot.http_etag,
                http_last_modified=snapshot.http_last_modified,
                should_redownload=False,
                verification_status="stored",
            )
            if snapshot.pdf_content:
                pdf_artifact = _persist_source_artifact(
                    source_artifact_store=self.source_artifact_store,
                    country_code=snapshot.country_code,
                    collection_code=snapshot.collection_code,
                    year=snapshot.year,
                    number=snapshot.number,
                    version_token=snapshot.version_token,
                    artifact_kind="pdf",
                    source_url=snapshot.pdf_url,
                    checksum=pdf_checksum,
                    default_extension=".pdf",
                    content=snapshot.pdf_content,
                )
                self.store.upsert_artifact(
                    document_id=document_id,
                    version_id=stored_version.version_id,
                    source_system=snapshot.source_system,
                    artifact_kind="pdf",
                    source_url=snapshot.pdf_url,
                    checksum=pdf_checksum,
                    storage_backend=pdf_artifact.storage_backend,
                    storage_path=pdf_artifact.storage_path,
                    content_text="",
                    content_blob=None,
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
            elapsed_seconds = perf_counter() - started_at
            _log(
                f"vector done law={law_id} version_status={stored_version.state} "
                f"final_status={event_type} embedding_model={embedding_model} "
                f"embedding_dimensions={embedding_dimensions} total_seconds={elapsed_seconds:.3f}"
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

    def search_semantic(self, query: str, *, limit: int = 5) -> list[LawSemanticSearchResult]:
        normalized_query = query.strip()
        if not normalized_query or limit < 1:
            return []

        query_batch = self.embedding_client.embed_texts([normalized_query])
        query_vector = query_batch.vectors[0]
        query_model_name = query_batch.model_name
        query_dimensions = len(query_vector)

        results: list[LawSemanticSearchResult] = []
        for candidate in self.store.list_semantic_candidates():
            if (
                candidate.embedding_model != query_model_name
                or candidate.embedding_dimensions != query_dimensions
            ):
                continue
            score = cosine_similarity(
                query_vector,
                parse_embedding_vector(candidate.embedding_vector),
            )
            results.append(
                LawSemanticSearchResult(
                    document_id=candidate.document_id,
                    version_id=candidate.version_id,
                    country_code=candidate.country_code,
                    collection_code=candidate.collection_code,
                    law_year=candidate.law_year,
                    law_number=candidate.law_number,
                    official_name=candidate.official_name,
                    lawyer_title=candidate.lawyer_title,
                    version_token=candidate.version_token,
                    effective_from=candidate.effective_from,
                    score=score,
                )
            )

        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]


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


def _persist_source_artifact(
    *,
    source_artifact_store: SourceArtifactObjectStore,
    country_code: str,
    collection_code: str,
    year: int,
    number: int,
    version_token: str,
    artifact_kind: str,
    source_url: str,
    checksum: str,
    default_extension: str,
    content: bytes,
) -> StoredSourceArtifactObject:
    relative_path = _build_source_artifact_storage_relative_path(
        country_code=country_code,
        collection_code=collection_code,
        year=year,
        number=number,
        version_token=version_token,
        artifact_kind=artifact_kind,
        source_url=source_url,
        checksum=checksum,
        default_extension=default_extension,
    )
    return source_artifact_store.persist_bytes(content=content, relative_path=relative_path)


def _build_source_artifact_storage_relative_path(
    *,
    country_code: str,
    collection_code: str,
    year: int,
    number: int,
    version_token: str,
    artifact_kind: str,
    source_url: str,
    checksum: str,
    default_extension: str,
) -> str:
    parsed = urlparse(source_url)
    extension = PurePosixPath(parsed.path).suffix or default_extension
    filename = f"{artifact_kind}-{checksum[:16]}{extension}"
    return (
        f"source-artifacts/{country_code.lower()}/{collection_code.lower()}/"
        f"{year}/{number}/{version_token}/{filename}"
    )


def _build_embedding_input(snapshot: LawSnapshot) -> str:
    return " ".join(
        [
            snapshot.official_name,
            snapshot.lawyer_title,
            snapshot.html_content,
            " ".join(item.text for item in snapshot.provisions),
        ]
    )


def _embed_snapshot(
    *,
    snapshot: LawSnapshot,
    embedding_client: EmbeddingClient,
) -> tuple[str, int, str]:
    chunks = _build_embedding_chunks(snapshot)
    embedding_result = embedding_client.embed_texts(chunks)
    if not embedding_result.vectors:
        raise ValueError("Embedding provider returned no vectors for laws collector snapshot.")
    averaged = _average_vectors(embedding_result.vectors)
    return (
        embedding_result.model_name,
        len(averaged),
        serialize_embedding_vector(averaged),
    )


def _build_embedding_chunks(snapshot: LawSnapshot) -> tuple[str, ...]:
    base_text = _build_embedding_input(snapshot)
    chunks = chunk_document_text(
        base_text,
        target_chars=4000,
        overlap_chars=250,
        min_chunk_chars=300,
    )
    if not chunks:
        return (base_text or snapshot.official_name or snapshot.lawyer_title or " ",)
    return tuple(chunk.text for chunk in chunks)


def _average_vectors(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dimensions = len(vectors[0])
    if dimensions == 0:
        return []
    for vector in vectors[1:]:
        if len(vector) != dimensions:
            raise ValueError("Embedding provider returned inconsistent vector dimensions.")
    scale = float(len(vectors))
    return [
        fsum(vector[index] for vector in vectors) / scale
        for index in range(dimensions)
    ]


def _log(message: str) -> None:
    print(f"[laws-collector] {message}", flush=True)
