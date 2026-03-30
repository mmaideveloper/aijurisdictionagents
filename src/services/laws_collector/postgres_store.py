from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import uuid

import psycopg
from psycopg.rows import dict_row

from .config import LawsCollectorConfig
from .domain import CollectorProgress, LawSnapshot, ProvisionRecord, StoredVersion


@dataclass(frozen=True)
class CollectorCounts:
    documents: int
    versions: int
    provisions: int
    update_events: int


class PostgresLawStore:
    def __init__(self, *, connection_uri: str) -> None:
        self.connection_uri = connection_uri

    @classmethod
    def from_config(cls, config: LawsCollectorConfig) -> "PostgresLawStore":
        config.validate()
        if config.db_backend != "postgres":
            raise ValueError("PostgresLawStore supports only LAWS_DB_BACKEND=postgres")
        if not config.db_cloud:
            raise ValueError("LAWS_DB_CLOUD must be set for postgres backend")
        return cls(connection_uri=config.db_cloud)

    def initialize(self) -> None:
        return

    def upsert_document(self, snapshot: LawSnapshot) -> tuple[str, bool]:
        now = _now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT document_id FROM law_documents
                WHERE country_code = %(country)s AND collection_code = %(collection)s
                  AND law_year = %(year)s AND law_number = %(number)s
                """,
                {
                    "country": snapshot.country_code,
                    "collection": snapshot.collection_code,
                    "year": snapshot.year,
                    "number": snapshot.number,
                },
            ).fetchone()
            if row is None:
                document_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO law_documents(
                        document_id, country_code, collection_code, law_year, law_number, official_name,
                        lawyer_title, source_url, publication_date, current_status, first_effective_date,
                        applicable_to, superseded_by_url, parent_law_year, parent_law_number,
                        first_stored_at, last_stored_at, last_checked_at,
                        last_download_status, last_download_error, download_attempt_count, created_at, updated_at
                    ) VALUES (
                        %(document_id)s, %(country)s, %(collection)s, %(year)s, %(number)s, %(official_name)s,
                        %(lawyer_title)s, %(source_url)s, %(publication_date)s, %(status)s, %(effective_from)s,
                        %(applicable_to)s, %(superseded_by_url)s, %(parent_law_year)s, %(parent_law_number)s,
                        %(now)s, %(now)s, %(now)s, 'stored', '', 1,
                        %(now)s, %(now)s
                    )
                    """,
                    {
                        "document_id": document_id,
                        "country": snapshot.country_code,
                        "collection": snapshot.collection_code,
                        "year": snapshot.year,
                        "number": snapshot.number,
                        "official_name": snapshot.official_name,
                        "lawyer_title": snapshot.lawyer_title,
                        "source_url": snapshot.source_url,
                        "publication_date": snapshot.publication_date,
                        "status": snapshot.status,
                        "effective_from": snapshot.effective_from,
                        "applicable_to": snapshot.applicable_to,
                        "superseded_by_url": snapshot.superseded_by_url,
                        "parent_law_year": snapshot.parent_law_year,
                        "parent_law_number": snapshot.parent_law_number,
                        "now": now,
                    },
                )
                conn.commit()
                return document_id, True

            document_id = str(row["document_id"])
            conn.execute(
                """
                UPDATE law_documents
                SET official_name = %(official_name)s,
                    lawyer_title = %(lawyer_title)s,
                    source_url = %(source_url)s,
                    publication_date = %(publication_date)s,
                    current_status = %(status)s,
                    applicable_to = %(applicable_to)s,
                    superseded_by_url = %(superseded_by_url)s,
                    parent_law_year = %(parent_law_year)s,
                    parent_law_number = %(parent_law_number)s,
                    last_stored_at = %(now)s,
                    last_checked_at = %(now)s,
                    last_download_status = 'stored',
                    last_download_error = '',
                    download_attempt_count = download_attempt_count + 1,
                    updated_at = %(now)s
                WHERE document_id = %(document_id)s
                """,
                {
                    "document_id": document_id,
                    "official_name": snapshot.official_name,
                    "lawyer_title": snapshot.lawyer_title,
                    "source_url": snapshot.source_url,
                    "publication_date": snapshot.publication_date,
                    "status": snapshot.status,
                    "applicable_to": snapshot.applicable_to,
                    "superseded_by_url": snapshot.superseded_by_url,
                    "parent_law_year": snapshot.parent_law_year,
                    "parent_law_number": snapshot.parent_law_number,
                    "now": now,
                },
            )
            conn.commit()
            return document_id, False

    def upsert_version(self, *, document_id: str, snapshot: LawSnapshot, version_checksum: str, html_checksum: str, pdf_checksum: str, html_bytes: int, pdf_bytes: int, normalized_json: str, embedding_vector: str) -> StoredVersion:
        now = _now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT version_id, version_checksum, effective_from, html_checksum, pdf_checksum,
                       html_bytes, pdf_bytes, normalized_json, embedding_vector, status
                FROM law_versions
                WHERE document_id = %(document_id)s AND version_token = %(version_token)s
                """,
                {"document_id": document_id, "version_token": snapshot.version_token},
            ).fetchone()
            if row is None:
                version_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO law_versions(
                        version_id, document_id, version_token, effective_from, version_checksum,
                        status, html_checksum, pdf_checksum, html_bytes, pdf_bytes,
                        normalized_json, embedding_vector, stored_at, created_at, updated_at
                    ) VALUES (
                        %(version_id)s, %(document_id)s, %(version_token)s, %(effective_from)s,
                        %(version_checksum)s, %(status)s, %(html_checksum)s, %(pdf_checksum)s,
                        %(html_bytes)s, %(pdf_bytes)s, %(normalized_json)s, %(embedding_vector)s,
                        %(now)s, %(now)s, %(now)s
                    )
                    """,
                    {
                        "version_id": version_id,
                        "document_id": document_id,
                        "version_token": snapshot.version_token,
                        "effective_from": snapshot.effective_from,
                        "version_checksum": version_checksum,
                        "status": snapshot.status,
                        "html_checksum": html_checksum,
                        "pdf_checksum": pdf_checksum,
                        "html_bytes": html_bytes,
                        "pdf_bytes": pdf_bytes,
                        "normalized_json": normalized_json,
                        "embedding_vector": embedding_vector,
                        "now": now,
                    },
                )
                conn.commit()
                return StoredVersion(version_id=version_id, state="created")

            version_id = str(row["version_id"])
            changed = any(
                (
                    row["version_checksum"] != version_checksum,
                    row["effective_from"] != snapshot.effective_from,
                    row["html_checksum"] != html_checksum,
                    row["pdf_checksum"] != pdf_checksum,
                    row["html_bytes"] != html_bytes,
                    row["pdf_bytes"] != pdf_bytes,
                    row["normalized_json"] != normalized_json,
                    row["embedding_vector"] != embedding_vector,
                    row["status"] != snapshot.status,
                )
            )
            if changed:
                conn.execute(
                    """
                    UPDATE law_versions
                    SET effective_from = %(effective_from)s, version_checksum = %(version_checksum)s,
                        status = %(status)s, html_checksum = %(html_checksum)s,
                        pdf_checksum = %(pdf_checksum)s, html_bytes = %(html_bytes)s,
                        pdf_bytes = %(pdf_bytes)s, normalized_json = %(normalized_json)s,
                        embedding_vector = %(embedding_vector)s, stored_at = %(now)s, updated_at = %(now)s
                    WHERE version_id = %(version_id)s
                    """,
                    {
                        "effective_from": snapshot.effective_from,
                        "version_checksum": version_checksum,
                        "status": snapshot.status,
                        "html_checksum": html_checksum,
                        "pdf_checksum": pdf_checksum,
                        "html_bytes": html_bytes,
                        "pdf_bytes": pdf_bytes,
                        "normalized_json": normalized_json,
                        "embedding_vector": embedding_vector,
                        "now": now,
                        "version_id": version_id,
                    },
                )
                conn.commit()
                return StoredVersion(version_id=version_id, state="updated")
            return StoredVersion(version_id=version_id, state="unchanged")

    def replace_provisions(self, *, version_id: str, provisions: tuple[ProvisionRecord, ...]) -> None:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute("DELETE FROM law_provisions WHERE version_id = %(version_id)s", {"version_id": version_id})
            for ordinal, provision in enumerate(provisions, start=1):
                conn.execute(
                    """
                    INSERT INTO law_provisions(provision_id, version_id, anchor, heading, body_text, ordinal, created_at)
                    VALUES (%(provision_id)s, %(version_id)s, %(anchor)s, %(heading)s, %(body_text)s, %(ordinal)s, %(created_at)s)
                    """,
                    {
                        "provision_id": str(uuid.uuid4()),
                        "version_id": version_id,
                        "anchor": provision.anchor,
                        "heading": provision.heading,
                        "body_text": provision.text,
                        "ordinal": ordinal,
                        "created_at": now,
                    },
                )
            conn.commit()

    def upsert_artifact(self, *, document_id: str, version_id: str, source_system: str, artifact_kind: str, source_url: str, checksum: str, content_text: str, content_blob: bytes | None, content_bytes: int, http_etag: str, http_last_modified: str, should_redownload: bool, verification_status: str, download_error: str = "") -> None:
        now = _now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT artifact_id FROM source_artifacts
                WHERE version_id = %(version_id)s AND artifact_kind = %(artifact_kind)s AND checksum = %(checksum)s
                """,
                {"version_id": version_id, "artifact_kind": artifact_kind, "checksum": checksum},
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO source_artifacts(
                        artifact_id, document_id, version_id, source_system, artifact_kind, source_url,
                        checksum, content_text, content_blob, content_bytes, http_etag, http_last_modified,
                        should_redownload, verification_status, download_error, fetched_at, last_checked_at
                    ) VALUES (
                        %(artifact_id)s, %(document_id)s, %(version_id)s, %(source_system)s, %(artifact_kind)s,
                        %(source_url)s, %(checksum)s, %(content_text)s, %(content_blob)s, %(content_bytes)s,
                        %(http_etag)s, %(http_last_modified)s, %(should_redownload)s,
                        %(verification_status)s, %(download_error)s, %(now)s, %(now)s
                    )
                    """,
                    {
                        "artifact_id": str(uuid.uuid4()),
                        "document_id": document_id,
                        "version_id": version_id,
                        "source_system": source_system,
                        "artifact_kind": artifact_kind,
                        "source_url": source_url,
                        "checksum": checksum,
                        "content_text": content_text,
                        "content_blob": content_blob,
                        "content_bytes": content_bytes,
                        "http_etag": http_etag,
                        "http_last_modified": http_last_modified,
                        "should_redownload": should_redownload,
                        "verification_status": verification_status,
                        "download_error": download_error,
                        "now": now,
                    },
                )
            else:
                conn.execute(
                    """
                    UPDATE source_artifacts
                    SET http_etag = %(http_etag)s, http_last_modified = %(http_last_modified)s,
                        should_redownload = %(should_redownload)s, verification_status = %(verification_status)s,
                        download_error = %(download_error)s, last_checked_at = %(now)s
                    WHERE artifact_id = %(artifact_id)s
                    """,
                    {
                        "http_etag": http_etag,
                        "http_last_modified": http_last_modified,
                        "should_redownload": should_redownload,
                        "verification_status": verification_status,
                        "download_error": download_error,
                        "now": now,
                        "artifact_id": row["artifact_id"],
                    },
                )
            conn.commit()

    def record_update_event(self, *, document_id: str, version_id: str | None, event_type: str, event_status: str, payload: dict[str, object]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO update_events(event_id, document_id, version_id, event_type, event_status, payload_json, created_at)
                VALUES (%(event_id)s, %(document_id)s, %(version_id)s, %(event_type)s, %(event_status)s, %(payload_json)s, %(created_at)s)
                """,
                {
                    "event_id": str(uuid.uuid4()),
                    "document_id": document_id,
                    "version_id": version_id,
                    "event_type": event_type,
                    "event_status": event_status,
                    "payload_json": json.dumps(payload, ensure_ascii=True, sort_keys=True),
                    "created_at": _now_iso(),
                },
            )
            conn.commit()

    def get_or_create_collector_progress(
        self,
        *,
        country_code: str,
        source_system: str,
        initial_year: int,
    ) -> CollectorProgress:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT country_code, source_system, last_collector_run_at, last_processed_at,
                       last_processed_law_year, last_processed_law_number,
                       next_probe_law_year, next_probe_law_number
                FROM collector_progress
                WHERE country_code = %(country_code)s
                """,
                {"country_code": country_code},
            ).fetchone()
            if row is not None:
                return _collector_progress_from_row(row)

            now = _now_iso()
            conn.execute(
                """
                INSERT INTO collector_progress(
                    country_code, source_system, last_collector_run_at, last_processed_at,
                    last_processed_law_year, last_processed_law_number,
                    next_probe_law_year, next_probe_law_number, created_at, updated_at
                ) VALUES (
                    %(country_code)s, %(source_system)s, NULL, NULL, NULL, NULL,
                    %(next_probe_law_year)s, %(next_probe_law_number)s, %(now)s, %(now)s
                )
                """,
                {
                    "country_code": country_code,
                    "source_system": source_system,
                    "next_probe_law_year": initial_year,
                    "next_probe_law_number": 1,
                    "now": now,
                },
            )
            conn.commit()
            return CollectorProgress(
                country_code=country_code,
                source_system=source_system,
                last_collector_run_at=None,
                last_processed_at=None,
                last_processed_law_year=None,
                last_processed_law_number=None,
                next_probe_law_year=initial_year,
                next_probe_law_number=1,
            )

    def save_collector_progress(self, progress: CollectorProgress) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE collector_progress
                SET source_system = %(source_system)s,
                    last_collector_run_at = %(last_collector_run_at)s,
                    last_processed_at = %(last_processed_at)s,
                    last_processed_law_year = %(last_processed_law_year)s,
                    last_processed_law_number = %(last_processed_law_number)s,
                    next_probe_law_year = %(next_probe_law_year)s,
                    next_probe_law_number = %(next_probe_law_number)s,
                    updated_at = %(updated_at)s
                WHERE country_code = %(country_code)s
                """,
                {
                    "source_system": progress.source_system,
                    "last_collector_run_at": progress.last_collector_run_at,
                    "last_processed_at": progress.last_processed_at,
                    "last_processed_law_year": progress.last_processed_law_year,
                    "last_processed_law_number": progress.last_processed_law_number,
                    "next_probe_law_year": progress.next_probe_law_year,
                    "next_probe_law_number": progress.next_probe_law_number,
                    "updated_at": _now_iso(),
                    "country_code": progress.country_code,
                },
            )
            conn.commit()

    def get_counts(self) -> CollectorCounts:
        with self._connect() as conn:
            return CollectorCounts(
                documents=_count(conn, "law_documents"),
                versions=_count(conn, "law_versions"),
                provisions=_count(conn, "law_provisions"),
                update_events=_count(conn, "update_events"),
            )

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.connection_uri, row_factory=dict_row)


def _count(conn: psycopg.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS value FROM {table_name}").fetchone()
    return int(row["value"]) if row is not None else 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _collector_progress_from_row(row: dict[str, object]) -> CollectorProgress:
    return CollectorProgress(
        country_code=str(row["country_code"]),
        source_system=str(row["source_system"]),
        last_collector_run_at=(str(row["last_collector_run_at"]) if row["last_collector_run_at"] else None),
        last_processed_at=(str(row["last_processed_at"]) if row["last_processed_at"] else None),
        last_processed_law_year=(
            int(row["last_processed_law_year"]) if row["last_processed_law_year"] is not None else None
        ),
        last_processed_law_number=(
            int(row["last_processed_law_number"])
            if row["last_processed_law_number"] is not None
            else None
        ),
        next_probe_law_year=int(row["next_probe_law_year"]),
        next_probe_law_number=int(row["next_probe_law_number"]),
    )
