from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from .config import LawsCollectorConfig
from .domain import LawSnapshot, ProvisionRecord, StoredVersion


@dataclass(frozen=True)
class CollectorCounts:
    documents: int
    versions: int
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
                """
            )

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
                        applicable_to, superseded_by_url, first_stored_at, last_stored_at, last_checked_at,
                        last_download_status, last_download_error, download_attempt_count, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        embedding_vector: str,
    ) -> StoredVersion:
        now = _now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT version_id, version_checksum, effective_from, html_checksum, pdf_checksum,
                       html_bytes, pdf_bytes, normalized_json, embedding_vector, status
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
                        embedding_vector, stored_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        embedding_vector = ?, stored_at = ?, updated_at = ?
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

    def get_counts(self) -> CollectorCounts:
        with self._connect() as conn:
            return CollectorCounts(
                documents=_count(conn, "law_documents"),
                versions=_count(conn, "law_versions"),
                provisions=_count(conn, "law_provisions"),
                update_events=_count(conn, "update_events"),
            )

    def list_document_overview(self) -> list[LawDocumentOverview]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT law_year, law_number, official_name, lawyer_title, publication_date,
                       first_effective_date, applicable_to, superseded_by_url,
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
