from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import uuid

import psycopg
from psycopg.rows import dict_row

from services.document_processor.runtime import (
    build_embedding_vector,
    cosine_similarity,
    lexical_overlap_score,
    parse_embedding_vector,
)

from .config import CourtDecisionCollectorConfig
from .domain import CourtDecisionRecord, CourtDecisionSearchResult, StoredCourtDecision


@dataclass(frozen=True)
class CourtDecisionCollectorStatus:
    last_processed_at: str
    last_source_guid: str
    status: str


class PostgresCourtDecisionStore:
    def __init__(self, *, connection_uri: str, embedding_dimensions: int = 32) -> None:
        self.connection_uri = connection_uri
        self.embedding_dimensions = embedding_dimensions

    @classmethod
    def from_config(cls, config: CourtDecisionCollectorConfig) -> "PostgresCourtDecisionStore":
        config.validate()
        return cls(connection_uri=config.db_cloud, embedding_dimensions=config.embedding_dimensions)

    def initialize(self) -> None:
        with self._connect() as conn:
            for statement in _SCHEMA_SQL:
                conn.execute(statement)
            conn.commit()

    def upsert_decision(self, record: CourtDecisionRecord) -> StoredCourtDecision:
        now = _now_iso()
        checksum = record.version_checksum()
        raw_checksum = sha256(record.raw_text.encode("utf-8")).hexdigest()
        public_checksum = sha256(record.public_text.encode("utf-8")).hexdigest()
        embedding_json = build_embedding_vector(
            _embedding_text(record),
            dimensions=self.embedding_dimensions,
        )
        metadata_json = json.dumps(record.metadata, ensure_ascii=True, sort_keys=True)
        payload = record.normalized_payload()
        normalized_json = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT decision_id FROM court_decision_documents
                WHERE source_system = %(source_system)s AND source_guid = %(source_guid)s
                """,
                {"source_system": record.source_system, "source_guid": record.source_guid},
            ).fetchone()
            created = row is None
            decision_id = str(uuid.uuid4()) if row is None else str(row["decision_id"])
            if created:
                conn.execute(
                    """
                    INSERT INTO court_decision_documents(
                        decision_id, source_system, source_guid, court_name, court_type,
                        decision_form, nature, file_number, case_number, ecli, issue_date,
                        indexed_at, update_date, source_url, current_status,
                        first_stored_at, last_stored_at, created_at, updated_at
                    ) VALUES (
                        %(decision_id)s, %(source_system)s, %(source_guid)s, %(court_name)s,
                        %(court_type)s, %(decision_form)s, %(nature)s, %(file_number)s,
                        %(case_number)s, %(ecli)s, %(issue_date)s, %(indexed_at)s,
                        %(update_date)s, %(source_url)s, 'published',
                        %(now)s, %(now)s, %(now)s, %(now)s
                    )
                    """,
                    _document_params(record, decision_id=decision_id, now=now),
                )
            else:
                conn.execute(
                    """
                    UPDATE court_decision_documents
                    SET court_name = %(court_name)s,
                        court_type = %(court_type)s,
                        decision_form = %(decision_form)s,
                        nature = %(nature)s,
                        file_number = %(file_number)s,
                        case_number = %(case_number)s,
                        ecli = %(ecli)s,
                        issue_date = %(issue_date)s,
                        indexed_at = %(indexed_at)s,
                        update_date = %(update_date)s,
                        source_url = %(source_url)s,
                        current_status = 'published',
                        last_stored_at = %(now)s,
                        updated_at = %(now)s
                    WHERE decision_id = %(decision_id)s
                    """,
                    _document_params(record, decision_id=decision_id, now=now),
                )
            version_row = conn.execute(
                """
                SELECT version_id, version_checksum
                FROM court_decision_versions
                WHERE decision_id = %(decision_id)s
                ORDER BY stored_at DESC
                LIMIT 1
                """,
                {"decision_id": decision_id},
            ).fetchone()
            if version_row is not None and str(version_row["version_checksum"]) == checksum:
                version_id = str(version_row["version_id"])
                state = "created" if created else "unchanged"
            else:
                version_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO court_decision_versions(
                        version_id, decision_id, version_checksum, raw_text_checksum,
                        pseudonymized_text_checksum, metadata_checksum, raw_text,
                        pseudonymized_text, normalized_json, metadata_json,
                        embedding_model, embedding_dimensions, embedding_vector_json, embedding_vector,
                        stored_at, created_at, updated_at
                    ) VALUES (
                        %(version_id)s, %(decision_id)s, %(version_checksum)s,
                        %(raw_text_checksum)s, %(pseudonymized_text_checksum)s,
                        %(metadata_checksum)s, %(raw_text)s, %(pseudonymized_text)s,
                        %(normalized_json)s, %(metadata_json)s, %(embedding_model)s,
                        %(embedding_dimensions)s, %(embedding_vector_json)s, %(embedding_vector)s::vector,
                        %(now)s, %(now)s, %(now)s
                    )
                    """,
                    {
                        "version_id": version_id,
                        "decision_id": decision_id,
                        "version_checksum": checksum,
                        "raw_text_checksum": raw_checksum,
                        "pseudonymized_text_checksum": public_checksum,
                        "metadata_checksum": sha256(metadata_json.encode("utf-8")).hexdigest(),
                        "raw_text": record.raw_text,
                        "pseudonymized_text": record.public_text,
                        "normalized_json": normalized_json,
                        "metadata_json": metadata_json,
                        "embedding_model": "jurisdigta-hash-bootstrap",
                        "embedding_dimensions": self.embedding_dimensions,
                        "embedding_vector_json": embedding_json,
                        "embedding_vector": embedding_json,
                        "now": now,
                    },
                )
                state = "created" if created else "updated"
            self._record_event(
                conn=conn,
                decision_id=decision_id,
                version_id=version_id,
                event_type=state,
                event_metadata={"source_guid": record.source_guid},
                now=now,
            )
            self.save_import_state(
                source_system=record.source_system,
                cursor_kind="latest",
                last_source_guid=record.source_guid,
                status="running",
                conn=conn,
            )
            conn.commit()
            return StoredCourtDecision(decision_id=decision_id, version_id=version_id, state=state)

    def search(self, *, query: str, limit: int = 10) -> list[CourtDecisionSearchResult]:
        query_vector = parse_embedding_vector(
            build_embedding_vector(query, dimensions=self.embedding_dimensions)
        )
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.decision_id, d.source_guid, d.court_name, d.court_type,
                       d.file_number, d.case_number, d.ecli, d.issue_date, d.source_url,
                       v.version_id, v.pseudonymized_text, v.embedding_vector_json
                FROM court_decision_documents AS d
                JOIN LATERAL (
                    SELECT version_id, pseudonymized_text, embedding_vector_json, stored_at
                    FROM court_decision_versions
                    WHERE decision_id = d.decision_id
                    ORDER BY stored_at DESC
                    LIMIT 1
                ) AS v ON true
                WHERE d.current_status = 'published'
                ORDER BY d.issue_date DESC NULLS LAST, d.updated_at DESC
                LIMIT 500
                """
            ).fetchall()
        scored: list[CourtDecisionSearchResult] = []
        for row in rows:
            public_text = str(row["pseudonymized_text"] or "")
            vector_score = cosine_similarity(query_vector, parse_embedding_vector(str(row["embedding_vector_json"])))
            lexical_score = lexical_overlap_score(query, public_text)
            score = vector_score + (lexical_score * 0.1)
            if score <= 0:
                continue
            scored.append(
                CourtDecisionSearchResult(
                    decision_id=str(row["decision_id"]),
                    version_id=str(row["version_id"]),
                    source_guid=str(row["source_guid"]),
                    court_name=str(row["court_name"] or ""),
                    court_type=str(row["court_type"] or ""),
                    file_number=str(row["file_number"] or ""),
                    case_number=str(row["case_number"] or ""),
                    ecli=str(row["ecli"] or ""),
                    issue_date=str(row["issue_date"] or ""),
                    source_url=str(row["source_url"] or ""),
                    snippet=_snippet(public_text, query=query),
                    score=round(score, 6),
                )
            )
        return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]

    def get_decision(self, *, decision_id: str, raw: bool = False) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT d.decision_id, d.source_guid, d.court_name, d.court_type,
                       d.file_number, d.case_number, d.ecli, d.issue_date, d.source_url,
                       v.version_id, v.raw_text, v.pseudonymized_text
                FROM court_decision_documents AS d
                JOIN court_decision_versions AS v ON v.decision_id = d.decision_id
                WHERE d.decision_id = %(decision_id)s
                ORDER BY v.stored_at DESC
                LIMIT 1
                """,
                {"decision_id": decision_id},
            ).fetchone()
        if row is None:
            return None
        text = str(row["raw_text"] if raw else row["pseudonymized_text"])
        return {
            "decision_id": str(row["decision_id"]),
            "version_id": str(row["version_id"]),
            "source_guid": str(row["source_guid"]),
            "court_name": str(row["court_name"] or ""),
            "court_type": str(row["court_type"] or ""),
            "file_number": str(row["file_number"] or ""),
            "case_number": str(row["case_number"] or ""),
            "ecli": str(row["ecli"] or ""),
            "issue_date": str(row["issue_date"] or ""),
            "source_url": str(row["source_url"] or ""),
            "output_mode": "internal_raw" if raw else "public",
            "text": text,
        }

    def save_import_state(
        self,
        *,
        source_system: str,
        cursor_kind: str,
        last_source_guid: str,
        status: str,
        conn: psycopg.Connection[dict[str, object]] | None = None,
    ) -> None:
        now = _now_iso()
        params = {
            "source_system": source_system,
            "cursor_kind": cursor_kind,
            "last_source_guid": last_source_guid,
            "status": status,
            "now": now,
        }
        query = """
            INSERT INTO court_decision_import_state(
                source_system, cursor_kind, last_source_guid, status,
                last_processed_at, created_at, updated_at
            ) VALUES (
                %(source_system)s, %(cursor_kind)s, %(last_source_guid)s, %(status)s,
                %(now)s, %(now)s, %(now)s
            )
            ON CONFLICT (source_system, cursor_kind)
            DO UPDATE SET
                last_source_guid = EXCLUDED.last_source_guid,
                status = EXCLUDED.status,
                last_processed_at = EXCLUDED.last_processed_at,
                updated_at = EXCLUDED.updated_at
        """
        if conn is not None:
            conn.execute(query, params)
            return
        with self._connect() as owned_conn:
            owned_conn.execute(query, params)
            owned_conn.commit()

    def status(self) -> CourtDecisionCollectorStatus:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT last_processed_at, last_source_guid, status
                FROM court_decision_import_state
                WHERE source_system = 'infosud' AND cursor_kind = 'latest'
                """
            ).fetchone()
        if row is None:
            return CourtDecisionCollectorStatus(last_processed_at="", last_source_guid="", status="not_started")
        return CourtDecisionCollectorStatus(
            last_processed_at=str(row["last_processed_at"] or ""),
            last_source_guid=str(row["last_source_guid"] or ""),
            status=str(row["status"] or ""),
        )

    def _record_event(
        self,
        *,
        conn: psycopg.Connection[dict[str, object]],
        decision_id: str,
        version_id: str,
        event_type: str,
        event_metadata: dict[str, object],
        now: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO court_decision_update_events(
                event_id, decision_id, version_id, event_type, event_metadata_json, created_at
            ) VALUES (%(event_id)s, %(decision_id)s, %(version_id)s, %(event_type)s, %(metadata)s, %(now)s)
            """,
            {
                "event_id": str(uuid.uuid4()),
                "decision_id": decision_id,
                "version_id": version_id,
                "event_type": event_type,
                "metadata": json.dumps(event_metadata, ensure_ascii=True, sort_keys=True),
                "now": now,
            },
        )

    def _connect(self) -> psycopg.Connection[dict[str, object]]:
        return psycopg.connect(self.connection_uri, row_factory=dict_row)


def _document_params(record: CourtDecisionRecord, *, decision_id: str, now: str) -> dict[str, object]:
    return {
        "decision_id": decision_id,
        "source_system": record.source_system,
        "source_guid": record.source_guid,
        "court_name": record.court_name,
        "court_type": record.court_type,
        "decision_form": record.decision_form,
        "nature": record.nature,
        "file_number": record.file_number,
        "case_number": record.case_number,
        "ecli": record.ecli,
        "issue_date": record.issue_date,
        "indexed_at": record.indexed_at,
        "update_date": record.update_date,
        "source_url": record.source_url,
        "now": now,
    }


def _embedding_text(record: CourtDecisionRecord) -> str:
    return "\n".join(
        part
        for part in (
            record.court_name,
            record.court_type,
            record.file_number,
            record.case_number,
            record.ecli,
            record.public_text,
        )
        if part
    )


def _snippet(text: str, *, query: str, max_chars: int = 500) -> str:
    normalized = text.strip().replace("\n", " ")
    if len(normalized) <= max_chars:
        return normalized
    query_word = next((word for word in query.lower().split() if len(word) >= 3), "")
    start = normalized.lower().find(query_word) if query_word else -1
    if start < 0:
        return normalized[:max_chars].rstrip()
    start = max(0, start - 120)
    return normalized[start : start + max_chars].rstrip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_SCHEMA_SQL = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS court_decision_documents (
        decision_id TEXT PRIMARY KEY,
        source_system TEXT NOT NULL,
        source_guid TEXT NOT NULL,
        court_name TEXT NOT NULL DEFAULT '',
        court_type TEXT NOT NULL DEFAULT '',
        decision_form TEXT NOT NULL DEFAULT '',
        nature TEXT NOT NULL DEFAULT '',
        file_number TEXT NOT NULL DEFAULT '',
        case_number TEXT NOT NULL DEFAULT '',
        ecli TEXT NOT NULL DEFAULT '',
        issue_date TEXT NOT NULL DEFAULT '',
        indexed_at TEXT NOT NULL DEFAULT '',
        update_date TEXT NOT NULL DEFAULT '',
        source_url TEXT NOT NULL DEFAULT '',
        current_status TEXT NOT NULL DEFAULT 'published',
        first_stored_at TEXT NOT NULL,
        last_stored_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(source_system, source_guid)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS court_decision_versions (
        version_id TEXT PRIMARY KEY,
        decision_id TEXT NOT NULL REFERENCES court_decision_documents(decision_id) ON DELETE CASCADE,
        version_checksum TEXT NOT NULL,
        raw_text_checksum TEXT NOT NULL,
        pseudonymized_text_checksum TEXT NOT NULL,
        metadata_checksum TEXT NOT NULL,
        raw_text TEXT NOT NULL,
        pseudonymized_text TEXT NOT NULL,
        normalized_json JSONB NOT NULL,
        metadata_json JSONB NOT NULL,
        embedding_model TEXT NOT NULL,
        embedding_dimensions INTEGER NOT NULL,
        embedding_vector_json JSONB NOT NULL,
        embedding_vector VECTOR(32),
        stored_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS court_decision_import_state (
        source_system TEXT NOT NULL,
        cursor_kind TEXT NOT NULL,
        last_source_guid TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL,
        last_processed_at TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(source_system, cursor_kind)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS court_decision_update_events (
        event_id TEXT PRIMARY KEY,
        decision_id TEXT NOT NULL REFERENCES court_decision_documents(decision_id) ON DELETE CASCADE,
        version_id TEXT NOT NULL REFERENCES court_decision_versions(version_id) ON DELETE CASCADE,
        event_type TEXT NOT NULL,
        event_metadata_json JSONB NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_court_decision_documents_source
    ON court_decision_documents(source_system, source_guid)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_court_decision_documents_issue_date
    ON court_decision_documents(issue_date)
    """,
)
