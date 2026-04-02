from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from .config import LawsCollectorConfig
from .domain import (
    CollectorProgress,
    LawMetadataRecord,
    LawRelationRecord,
    LawSnapshot,
    ProvisionRecord,
    StoredVersion,
)


@dataclass(frozen=True)
class CollectorCounts:
    documents: int
    versions: int
    metadata: int
    relations: int
    provisions: int
    update_events: int


@dataclass(frozen=True)
class LawDocumentOverview:
    law_year: int
    law_number: int
    official_name: str
    lawyer_title: str
    publication_date: str
    first_effective_date: str
    applicable_to: str | None
    superseded_by_url: str
    parent_law_year: int | None
    parent_law_number: int | None
    last_stored_at: str
    last_checked_at: str
    last_download_status: str
    download_attempt_count: int


class SqliteLawStore:
    """SQLite-backed law metadata store with documents stored inside the database."""

    def __init__(self, *, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_config(cls, config: LawsCollectorConfig) -> "SqliteLawStore":
        config.validate()
        if config.db_backend != "sqlite":
            raise ValueError("SqliteLawStore supports only LAWS_DB_BACKEND=sqlite")
        return cls(db_path=config.db_path)

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS law_documents (
                    document_id TEXT PRIMARY KEY,
                    country_code TEXT NOT NULL,
                    collection_code TEXT NOT NULL,
                    law_year INTEGER NOT NULL,
                    law_number INTEGER NOT NULL,
                    official_name TEXT NOT NULL,
                    lawyer_title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    publication_date TEXT NOT NULL,
                    current_status TEXT NOT NULL,
                    first_effective_date TEXT NOT NULL,
                    applicable_to TEXT,
                    superseded_by_url TEXT NOT NULL,
                    parent_law_year INTEGER,
                    parent_law_number INTEGER,
                    first_stored_at TEXT NOT NULL,
                    last_stored_at TEXT NOT NULL,
                    last_checked_at TEXT NOT NULL,
                    last_download_status TEXT NOT NULL,
                    last_download_error TEXT NOT NULL,
                    download_attempt_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(country_code, collection_code, law_year, law_number)
                );

                CREATE TABLE IF NOT EXISTS law_versions (
                    version_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    version_token TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    version_checksum TEXT NOT NULL,
                    status TEXT NOT NULL,
                    html_checksum TEXT NOT NULL,
                    pdf_checksum TEXT NOT NULL,
                    html_bytes INTEGER NOT NULL,
                    pdf_bytes INTEGER NOT NULL,
                    normalized_json TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_dimensions INTEGER NOT NULL,
                    embedding_vector TEXT NOT NULL,
                    stored_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES law_documents(document_id) ON DELETE CASCADE,
                    UNIQUE(document_id, version_token)
                );

                CREATE TABLE IF NOT EXISTS law_provisions (
                    provision_id TEXT PRIMARY KEY,
                    version_id TEXT NOT NULL,
                    anchor TEXT NOT NULL,
                    heading TEXT NOT NULL,
                    body_text TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(version_id) REFERENCES law_versions(version_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS source_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    artifact_kind TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    content_text TEXT NOT NULL,
                    content_blob BLOB,
                    content_bytes INTEGER NOT NULL,
                    http_etag TEXT NOT NULL,
                    http_last_modified TEXT NOT NULL,
                    should_redownload INTEGER NOT NULL,
                    verification_status TEXT NOT NULL,
                    download_error TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    last_checked_at TEXT NOT NULL,
                    UNIQUE(version_id, artifact_kind, checksum),
                    FOREIGN KEY(document_id) REFERENCES law_documents(document_id) ON DELETE CASCADE,
                    FOREIGN KEY(version_id) REFERENCES law_versions(version_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS law_metadata (
                    law_metadata_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    law_identifier_text TEXT NOT NULL,
                    title TEXT NOT NULL,
                    law_type TEXT NOT NULL,
                    approval_date TEXT,
                    publication_date TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    effective_to TEXT,
                    author TEXT,
                    issue_reference TEXT,
                    legal_areas_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(version_id),
                    FOREIGN KEY(document_id) REFERENCES law_documents(document_id) ON DELETE CASCADE,
                    FOREIGN KEY(version_id) REFERENCES law_versions(version_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS law_metadata_relations (
                    law_metadata_relation_id TEXT PRIMARY KEY,
                    law_metadata_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    relation_label TEXT NOT NULL,
                    target_country_code TEXT NOT NULL,
                    target_collection_code TEXT NOT NULL,
                    target_law_year INTEGER,
                    target_law_number INTEGER,
                    target_law_identifier_text TEXT NOT NULL,
                    target_title TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(law_metadata_id) REFERENCES law_metadata(law_metadata_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS update_events (
                    event_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    version_id TEXT,
                    event_type TEXT NOT NULL,
                    event_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES law_documents(document_id) ON DELETE CASCADE,
                    FOREIGN KEY(version_id) REFERENCES law_versions(version_id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS collector_progress (
                    country_code TEXT PRIMARY KEY,
                    source_system TEXT NOT NULL,
                    last_collector_run_at TEXT,
                    last_processed_at TEXT,
                    last_processed_law_year INTEGER,
                    last_processed_law_number INTEGER,
                    next_probe_law_year INTEGER NOT NULL,
                    next_probe_law_number INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            _ensure_law_versions_columns(conn)

    def upsert_document(self, snapshot: LawSnapshot) -> tuple[str, bool]:
        now = _now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT document_id FROM law_documents
                WHERE country_code = ? AND collection_code = ? AND law_year = ? AND law_number = ?
                """,
                (
                    snapshot.country_code,
                    snapshot.collection_code,
                    snapshot.year,
                    snapshot.number,
                ),
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
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        snapshot.country_code,
                        snapshot.collection_code,
                        snapshot.year,
                        snapshot.number,
                        snapshot.official_name,
                        snapshot.lawyer_title,
                        snapshot.source_url,
                        snapshot.publication_date,
                        snapshot.status,
                        snapshot.effective_from,
                        snapshot.applicable_to,
                        snapshot.superseded_by_url,
                        snapshot.parent_law_year,
                        snapshot.parent_law_number,
                        now,
                        now,
                        now,
                        "stored",
                        "",
                        1,
                        now,
                        now,
                    ),
                )
                return document_id, True

            document_id = str(row["document_id"])
            conn.execute(
                """
                UPDATE law_documents
                SET official_name = ?, lawyer_title = ?, source_url = ?, publication_date = ?,
                    current_status = ?, applicable_to = ?, superseded_by_url = ?,
                    parent_law_year = ?, parent_law_number = ?,
                    last_stored_at = ?, last_checked_at = ?,
                    last_download_status = ?, last_download_error = '',
                    download_attempt_count = download_attempt_count + 1, updated_at = ?
                WHERE document_id = ?
                """,
                (
                    snapshot.official_name,
                    snapshot.lawyer_title,
                    snapshot.source_url,
                    snapshot.publication_date,
                    snapshot.status,
                    snapshot.applicable_to,
                    snapshot.superseded_by_url,
                    snapshot.parent_law_year,
                    snapshot.parent_law_number,
                    now,
                    now,
                    "stored",
                    now,
                    document_id,
                ),
            )
            return document_id, False

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
    ) -> StoredVersion:
        now = _now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT version_id, version_checksum, effective_from, html_checksum, pdf_checksum,
                       html_bytes, pdf_bytes, normalized_json, embedding_model,
                       embedding_dimensions, embedding_vector, status
                FROM law_versions
                WHERE document_id = ? AND version_token = ?
                """,
                (document_id, snapshot.version_token),
            ).fetchone()

            if row is None:
                version_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO law_versions(
                        version_id, document_id, version_token, effective_from, version_checksum,
                        status, html_checksum, pdf_checksum, html_bytes, pdf_bytes, normalized_json,
                        embedding_model, embedding_dimensions, embedding_vector,
                        stored_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        version_id,
                        document_id,
                        snapshot.version_token,
                        snapshot.effective_from,
                        version_checksum,
                        snapshot.status,
                        html_checksum,
                        pdf_checksum,
                        html_bytes,
                        pdf_bytes,
                        normalized_json,
                        embedding_model,
                        embedding_dimensions,
                        embedding_vector,
                        now,
                        now,
                        now,
                    ),
                )
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
                    row["embedding_model"] != embedding_model,
                    row["embedding_dimensions"] != embedding_dimensions,
                    row["embedding_vector"] != embedding_vector,
                    row["status"] != snapshot.status,
                )
            )
            if changed:
                conn.execute(
                    """
                    UPDATE law_versions
                    SET effective_from = ?, version_checksum = ?, status = ?, html_checksum = ?,
                        pdf_checksum = ?, html_bytes = ?, pdf_bytes = ?, normalized_json = ?,
                        embedding_model = ?, embedding_dimensions = ?, embedding_vector = ?,
                        stored_at = ?, updated_at = ?
                    WHERE version_id = ?
                    """,
                    (
                        snapshot.effective_from,
                        version_checksum,
                        snapshot.status,
                        html_checksum,
                        pdf_checksum,
                        html_bytes,
                        pdf_bytes,
                        normalized_json,
                        embedding_model,
                        embedding_dimensions,
                        embedding_vector,
                        now,
                        now,
                        version_id,
                    ),
                )
                return StoredVersion(version_id=version_id, state="updated")

            return StoredVersion(version_id=version_id, state="unchanged")

    def replace_provisions(self, *, version_id: str, provisions: tuple[ProvisionRecord, ...]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM law_provisions WHERE version_id = ?", (version_id,))
            for ordinal, provision in enumerate(provisions, start=1):
                conn.execute(
                    """
                    INSERT INTO law_provisions(
                        provision_id, version_id, anchor, heading, body_text, ordinal, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        version_id,
                        provision.anchor,
                        provision.heading,
                        provision.text,
                        ordinal,
                        _now_iso(),
                    ),
                )

    def upsert_law_metadata(
        self,
        *,
        document_id: str,
        version_id: str,
        metadata: LawMetadataRecord,
    ) -> str:
        now = _now_iso()
        legal_areas_json = json.dumps(list(metadata.legal_areas), ensure_ascii=True)
        metadata_json = json.dumps(metadata.normalized_payload(), ensure_ascii=True, sort_keys=True)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT law_metadata_id, law_identifier_text, title, law_type, approval_date,
                       publication_date, effective_from, effective_to, author,
                       issue_reference, legal_areas_json, metadata_json
                FROM law_metadata
                WHERE version_id = ?
                """,
                (version_id,),
            ).fetchone()
            if row is None:
                law_metadata_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO law_metadata(
                        law_metadata_id, document_id, version_id, law_identifier_text,
                        title, law_type, approval_date, publication_date, effective_from,
                        effective_to, author, issue_reference, legal_areas_json,
                        metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        law_metadata_id,
                        document_id,
                        version_id,
                        metadata.law_identifier_text,
                        metadata.title,
                        metadata.law_type,
                        metadata.approval_date,
                        metadata.publication_date,
                        metadata.effective_from,
                        metadata.effective_to,
                        metadata.author,
                        metadata.issue_reference,
                        legal_areas_json,
                        metadata_json,
                        now,
                        now,
                    ),
                )
                return law_metadata_id

            law_metadata_id = str(row["law_metadata_id"])
            changed = any(
                (
                    row["law_identifier_text"] != metadata.law_identifier_text,
                    row["title"] != metadata.title,
                    row["law_type"] != metadata.law_type,
                    _as_nullable_text(row["approval_date"]) != metadata.approval_date,
                    _as_nullable_text(row["publication_date"]) != metadata.publication_date,
                    _as_nullable_text(row["effective_from"]) != metadata.effective_from,
                    _as_nullable_text(row["effective_to"]) != metadata.effective_to,
                    _as_nullable_text(row["author"]) != metadata.author,
                    _as_nullable_text(row["issue_reference"]) != metadata.issue_reference,
                    _json_text(row["legal_areas_json"]) != legal_areas_json,
                    _json_text(row["metadata_json"]) != metadata_json,
                )
            )
            if changed:
                conn.execute(
                    """
                    UPDATE law_metadata
                    SET law_identifier_text = ?, title = ?, law_type = ?, approval_date = ?,
                        publication_date = ?, effective_from = ?, effective_to = ?, author = ?,
                        issue_reference = ?, legal_areas_json = ?, metadata_json = ?, updated_at = ?
                    WHERE law_metadata_id = ?
                    """,
                    (
                        metadata.law_identifier_text,
                        metadata.title,
                        metadata.law_type,
                        metadata.approval_date,
                        metadata.publication_date,
                        metadata.effective_from,
                        metadata.effective_to,
                        metadata.author,
                        metadata.issue_reference,
                        legal_areas_json,
                        metadata_json,
                        now,
                        law_metadata_id,
                    ),
                )
            return law_metadata_id

    def replace_law_relations(
        self,
        *,
        law_metadata_id: str,
        relations: tuple[LawRelationRecord, ...],
    ) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM law_metadata_relations WHERE law_metadata_id = ?", (law_metadata_id,))
            for ordinal, relation in enumerate(relations, start=1):
                conn.execute(
                    """
                    INSERT INTO law_metadata_relations(
                        law_metadata_relation_id, law_metadata_id, relation_type,
                        relation_label, target_country_code, target_collection_code,
                        target_law_year, target_law_number, target_law_identifier_text,
                        target_title, target_url, ordinal, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        law_metadata_id,
                        relation.relation_type,
                        relation.relation_label,
                        relation.target_country_code,
                        relation.target_collection_code,
                        relation.target_law_year,
                        relation.target_law_number,
                        relation.target_law_identifier_text,
                        relation.target_title,
                        relation.target_url,
                        ordinal,
                        _now_iso(),
                    ),
                )

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
    ) -> None:
        now = _now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT artifact_id FROM source_artifacts
                WHERE version_id = ? AND artifact_kind = ? AND checksum = ?
                """,
                (version_id, artifact_kind, checksum),
            ).fetchone()

            if row is None:
                conn.execute(
                    """
                    INSERT INTO source_artifacts(
                        artifact_id, document_id, version_id, source_system, artifact_kind, source_url,
                        checksum, content_text, content_blob, content_bytes, http_etag,
                        http_last_modified, should_redownload, verification_status,
                        download_error, fetched_at, last_checked_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        document_id,
                        version_id,
                        source_system,
                        artifact_kind,
                        source_url,
                        checksum,
                        content_text,
                        content_blob,
                        content_bytes,
                        http_etag,
                        http_last_modified,
                        1 if should_redownload else 0,
                        verification_status,
                        download_error,
                        now,
                        now,
                    ),
                )
                return

            conn.execute(
                """
                UPDATE source_artifacts
                SET http_etag = ?, http_last_modified = ?, should_redownload = ?,
                    verification_status = ?, download_error = ?, last_checked_at = ?
                WHERE artifact_id = ?
                """,
                (
                    http_etag,
                    http_last_modified,
                    1 if should_redownload else 0,
                    verification_status,
                    download_error,
                    now,
                    row["artifact_id"],
                ),
            )

    def record_update_event(
        self,
        *,
        document_id: str,
        version_id: str | None,
        event_type: str,
        event_status: str,
        payload: dict[str, object],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO update_events(
                    event_id, document_id, version_id, event_type, event_status, payload_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    document_id,
                    version_id,
                    event_type,
                    event_status,
                    json.dumps(payload, ensure_ascii=True, sort_keys=True),
                    _now_iso(),
                ),
            )

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
                WHERE country_code = ?
                """,
                (country_code,),
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
                )
                VALUES (?, ?, NULL, NULL, NULL, NULL, ?, ?, ?, ?)
                """,
                (country_code, source_system, initial_year, 1, now, now),
            )
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
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE collector_progress
                SET source_system = ?, last_collector_run_at = ?, last_processed_at = ?,
                    last_processed_law_year = ?, last_processed_law_number = ?,
                    next_probe_law_year = ?, next_probe_law_number = ?, updated_at = ?
                WHERE country_code = ?
                """,
                (
                    progress.source_system,
                    progress.last_collector_run_at,
                    progress.last_processed_at,
                    progress.last_processed_law_year,
                    progress.last_processed_law_number,
                    progress.next_probe_law_year,
                    progress.next_probe_law_number,
                    now,
                    progress.country_code,
                ),
            )

    def get_counts(self) -> CollectorCounts:
        with self._connect() as conn:
            return CollectorCounts(
                documents=_count(conn, "law_documents"),
                versions=_count(conn, "law_versions"),
                metadata=_count(conn, "law_metadata"),
                relations=_count(conn, "law_metadata_relations"),
                provisions=_count(conn, "law_provisions"),
                update_events=_count(conn, "update_events"),
            )

    def list_document_overview(self) -> list[LawDocumentOverview]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT law_year, law_number, official_name, lawyer_title, publication_date,
                       first_effective_date, applicable_to, superseded_by_url,
                       parent_law_year, parent_law_number,
                       last_stored_at, last_checked_at, last_download_status, download_attempt_count
                FROM law_documents
                ORDER BY law_year, law_number
                """
            ).fetchall()

        return [
            LawDocumentOverview(
                law_year=int(row["law_year"]),
                law_number=int(row["law_number"]),
                official_name=str(row["official_name"]),
                lawyer_title=str(row["lawyer_title"]),
                publication_date=str(row["publication_date"]),
                first_effective_date=str(row["first_effective_date"]),
                applicable_to=(str(row["applicable_to"]) if row["applicable_to"] else None),
                superseded_by_url=str(row["superseded_by_url"]),
                parent_law_year=(int(row["parent_law_year"]) if row["parent_law_year"] is not None else None),
                parent_law_number=(int(row["parent_law_number"]) if row["parent_law_number"] is not None else None),
                last_stored_at=str(row["last_stored_at"]),
                last_checked_at=str(row["last_checked_at"]),
                last_download_status=str(row["last_download_status"]),
                download_attempt_count=int(row["download_attempt_count"]),
            )
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn


def _count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS value FROM {table_name}").fetchone()
    return int(row["value"]) if row is not None else 0


def _ensure_law_versions_columns(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(law_versions)").fetchall()
    existing = {str(row["name"]) for row in rows}
    if "embedding_model" not in existing:
        conn.execute(
            "ALTER TABLE law_versions ADD COLUMN embedding_model TEXT NOT NULL DEFAULT ''"
        )
    if "embedding_dimensions" not in existing:
        conn.execute(
            "ALTER TABLE law_versions ADD COLUMN embedding_dimensions INTEGER NOT NULL DEFAULT 0"
        )


def _as_nullable_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _json_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _collector_progress_from_row(row: sqlite3.Row) -> CollectorProgress:
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
