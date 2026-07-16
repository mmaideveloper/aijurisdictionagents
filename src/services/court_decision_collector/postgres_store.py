from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any
import unicodedata
import uuid

import psycopg
from psycopg.rows import dict_row

from services.document_processor.runtime import (
    DocumentChunk,
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


@dataclass(frozen=True)
class CourtDecisionStatistics:
    total_decisions: int
    published_decisions: int
    total_versions: int
    last_imported_decision_id: str
    last_imported_source_guid: str
    last_imported_at: str
    last_imported_court_name: str
    last_imported_court_type: str
    last_imported_issue_date: str
    last_imported_ecli: str
    last_imported_file_number: str
    collector_last_processed_at: str
    collector_last_source_guid: str
    collector_status: str


class PostgresCourtDecisionStore:
    def __init__(
        self,
        *,
        connection_uri: str,
        embedding_dimensions: int = 32,
        connect_timeout_seconds: int | None = None,
        statement_timeout_ms: int | None = None,
    ) -> None:
        self.connection_uri = connection_uri
        self.embedding_dimensions = embedding_dimensions
        self.connect_timeout_seconds = connect_timeout_seconds
        self.statement_timeout_ms = statement_timeout_ms

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
                        issue_date_normalized, court_name_normalized,
                        indexed_at, update_date, source_url, current_status,
                        first_stored_at, last_stored_at, created_at, updated_at
                    ) VALUES (
                        %(decision_id)s, %(source_system)s, %(source_guid)s, %(court_name)s,
                        %(court_type)s, %(decision_form)s, %(nature)s, %(file_number)s,
                        %(case_number)s, %(ecli)s, %(issue_date)s, %(issue_date_normalized)s,
                        %(court_name_normalized)s, %(indexed_at)s,
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
                        issue_date_normalized = %(issue_date_normalized)s,
                        court_name_normalized = %(court_name_normalized)s,
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

    def search(
        self,
        *,
        query: str,
        limit: int = 10,
        offset: int = 0,
        published_year: int | None = None,
        year_filter_mode: str = "published_in",
        court_type: str = "",
        court_name: str = "",
        sort: str = "relevance",
    ) -> list[CourtDecisionSearchResult]:
        if year_filter_mode != "published_in":
            raise ValueError("Only year_filter_mode=published_in is supported.")
        if sort not in {"relevance", "latest"}:
            raise ValueError("sort must be relevance or latest.")
        query_vector = parse_embedding_vector(
            build_embedding_vector(query, dimensions=self.embedding_dimensions)
        )
        candidate_limit = max((limit + offset) * 10, 100)
        pattern = f"%{query.lower()}%"
        filters = ""
        params: dict[str, object] = {
            "query": query,
            "pattern": pattern,
            "candidate_limit": candidate_limit,
        }
        if published_year is not None:
            filters += " AND EXTRACT(YEAR FROM d.issue_date_normalized) = %(published_year)s"
            params["published_year"] = published_year
        if court_type.strip():
            filters += " AND LOWER(d.court_type) = %(court_type)s"
            params["court_type"] = court_type.strip().lower()
        if court_name.strip():
            filters += " AND d.court_name_normalized = %(court_name_normalized)s"
            params["court_name_normalized"] = normalize_court_name(court_name)
        order_by = (
            "d.issue_date_normalized DESC NULLS LAST, d.updated_at DESC, lexical_rank DESC"
            if sort == "latest"
            else "lexical_rank DESC, d.issue_date_normalized DESC NULLS LAST, d.updated_at DESC"
        )
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                WITH search_query AS (
                    SELECT websearch_to_tsquery('simple', %(query)s) AS tsq
                ),
                text_candidates AS (
                    SELECT
                        v.decision_id,
                        MAX(ts_rank_cd(to_tsvector('simple', v.pseudonymized_text), search_query.tsq)) AS lexical_rank
                    FROM court_decision_versions AS v
                    CROSS JOIN search_query
                    WHERE to_tsvector('simple', v.pseudonymized_text) @@ search_query.tsq
                    GROUP BY v.decision_id
                ),
                metadata_candidates AS (
                    SELECT
                        d.decision_id,
                        ts_rank_cd(
                            to_tsvector(
                                'simple'::regconfig,
                                COALESCE(d.court_name, '') || ' ' ||
                                COALESCE(d.court_type, '') || ' ' ||
                                COALESCE(d.file_number, '') || ' ' ||
                                COALESCE(d.case_number, '') || ' ' ||
                                COALESCE(d.ecli, '')
                            ),
                            search_query.tsq
                        ) AS lexical_rank
                    FROM court_decision_documents AS d
                    CROSS JOIN search_query
                    WHERE d.current_status = 'published'
                      AND (
                          to_tsvector(
                              'simple'::regconfig,
                              COALESCE(d.court_name, '') || ' ' ||
                              COALESCE(d.court_type, '') || ' ' ||
                              COALESCE(d.file_number, '') || ' ' ||
                              COALESCE(d.case_number, '') || ' ' ||
                              COALESCE(d.ecli, '')
                          ) @@ search_query.tsq
                          OR LOWER(d.court_name) LIKE %(pattern)s
                          OR LOWER(d.court_type) LIKE %(pattern)s
                          OR LOWER(d.file_number) LIKE %(pattern)s
                          OR LOWER(d.case_number) LIKE %(pattern)s
                          OR LOWER(d.ecli) LIKE %(pattern)s
                      )
                      {filters}
                ),
                candidate_ids AS (
                    SELECT decision_id, MAX(lexical_rank) AS lexical_rank
                    FROM (
                        SELECT decision_id, lexical_rank FROM text_candidates
                        UNION ALL
                        SELECT decision_id, lexical_rank FROM metadata_candidates
                    ) AS candidates
                    GROUP BY decision_id
                )
                SELECT d.decision_id, d.source_guid, d.court_name, d.court_type,
                       d.file_number, d.case_number, d.ecli, d.issue_date,
                       d.issue_date_normalized, d.source_url,
                       v.version_id, v.pseudonymized_text, v.embedding_vector_json,
                       candidate_ids.lexical_rank
                FROM candidate_ids
                JOIN court_decision_documents AS d ON d.decision_id = candidate_ids.decision_id
                JOIN LATERAL (
                    SELECT version_id, pseudonymized_text, embedding_vector_json, stored_at
                    FROM court_decision_versions
                    WHERE decision_id = d.decision_id
                    ORDER BY stored_at DESC
                    LIMIT 1
                ) AS v ON true
                WHERE d.current_status = 'published'
                  {filters}
                ORDER BY {order_by}
                LIMIT %(candidate_limit)s
                """,
                params,
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
        if sort == "latest":
            return sorted(
                scored,
                key=lambda item: (_parse_issue_date(item.issue_date) or date.min, item.score),
                reverse=True,
            )[offset : offset + limit]
        return sorted(scored, key=lambda item: item.score, reverse=True)[offset : offset + limit]

    def get_decision(self, *, decision_id: str, raw: bool = False) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT d.decision_id, d.source_guid, d.court_name, d.court_type,
                       d.file_number, d.case_number, d.ecli, d.issue_date, d.source_url,
                       v.version_id, v.raw_text, v.pseudonymized_text,
                       e.status AS enrichment_status, e.pseudonymized_summary,
                       e.legal_topics, e.pdf_sha256, e.extraction_method,
                       e.embedding_model AS enrichment_embedding_model,
                       e.embedding_dimensions AS enrichment_embedding_dimensions
                FROM court_decision_documents AS d
                JOIN court_decision_versions AS v ON v.decision_id = d.decision_id
                LEFT JOIN court_decision_enrichments AS e ON e.version_id = v.version_id
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
            "enrichment_status": str(row["enrichment_status"] or "not_started"),
            "summary": str(row["pseudonymized_summary"] or ""),
            "legal_topics": row["legal_topics"] or [],
            "pdf_sha256": str(row["pdf_sha256"] or ""),
            "extraction_method": str(row["extraction_method"] or ""),
            "embedding_model": str(row["enrichment_embedding_model"] or ""),
            "embedding_dimensions": int(str(row["enrichment_embedding_dimensions"] or 0)),
            "summary_ai_generated": bool(row["pseudonymized_summary"]),
        }

    def get_enrichment(self, *, version_id: str) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT e.*, (SELECT COUNT(*) FROM court_decision_content_chunks c
                       WHERE c.version_id=e.version_id) AS chunk_count
                   FROM court_decision_enrichments e WHERE e.version_id=%(version_id)s""",
                {"version_id": version_id},
            ).fetchone()
        return dict(row) if row else None

    def mark_enrichment_processing(
        self, *, decision_id: str, version_id: str, source_url: str, pdf_url: str,
        pdf_filename: str, expected_size: int, metadata: dict[str, object],
    ) -> None:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO court_decision_enrichments(
                       version_id,decision_id,status,source_url,pdf_url,pdf_filename,
                       expected_size,source_metadata_json,attempt_count,created_at,updated_at)
                   VALUES (%(version_id)s,%(decision_id)s,'processing',%(source_url)s,%(pdf_url)s,
                       %(pdf_filename)s,%(expected_size)s,%(metadata)s,1,%(now)s,%(now)s)
                   ON CONFLICT(version_id) DO UPDATE SET status='processing', source_url=EXCLUDED.source_url,
                       pdf_url=EXCLUDED.pdf_url,pdf_filename=EXCLUDED.pdf_filename,
                       expected_size=EXCLUDED.expected_size,source_metadata_json=EXCLUDED.source_metadata_json,
                       attempt_count=court_decision_enrichments.attempt_count+1,last_error_type='',updated_at=EXCLUDED.updated_at""",
                {"version_id": version_id, "decision_id": decision_id, "source_url": source_url,
                 "pdf_url": pdf_url, "pdf_filename": pdf_filename, "expected_size": expected_size,
                 "metadata": json.dumps(metadata, ensure_ascii=False), "now": now},
            )
            conn.commit()

    def mark_enrichment_failed(self, *, version_id: str, error_type: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE court_decision_enrichments SET status='retryable_failure',last_error_type=%s,updated_at=%s WHERE version_id=%s", (error_type, _now_iso(), version_id))
            conn.commit()

    def save_enrichment(
        self, *, decision_id: str, version_id: str, pdf_path: str, pdf_sha256: str,
        actual_size: int, extraction_method: str, raw_text: str, pseudonymized_text: str,
        summary: str, legal_topics: tuple[str, ...], embedding_model: str,
        vectors: list[list[float]], chunks: list[DocumentChunk],
    ) -> None:
        now = _now_iso()
        summary_vector = vectors[0] if vectors else []
        dimensions = len(summary_vector)
        with self._connect() as conn:
            conn.execute(
                """UPDATE court_decision_enrichments SET status='ready',pdf_path=%(pdf_path)s,
                       pdf_sha256=%(pdf_sha256)s,actual_size=%(actual_size)s,
                       extraction_method=%(extraction_method)s,raw_text=%(raw_text)s,
                       pseudonymized_text=%(public_text)s,pseudonymized_summary=%(summary)s,
                       legal_topics=%(topics)s,summary_model='jurisdigta-local-extractive-v1',
                       embedding_model=%(embedding_model)s,embedding_dimensions=%(dimensions)s,
                       summary_embedding_json=%(summary_vector)s,completed_at=%(now)s,updated_at=%(now)s
                   WHERE version_id=%(version_id)s""",
                {"pdf_path": pdf_path, "pdf_sha256": pdf_sha256, "actual_size": actual_size,
                 "extraction_method": extraction_method, "raw_text": raw_text,
                 "public_text": pseudonymized_text, "summary": summary,
                 "topics": json.dumps(legal_topics, ensure_ascii=False),
                 "embedding_model": embedding_model, "dimensions": dimensions,
                 "summary_vector": json.dumps(summary_vector), "now": now, "version_id": version_id},
            )
            conn.execute("DELETE FROM court_decision_content_chunks WHERE version_id=%s", (version_id,))
            for chunk, vector in zip(chunks, vectors[1:]):
                conn.execute(
                    """INSERT INTO court_decision_content_chunks(
                           chunk_id,decision_id,version_id,chunk_index,pseudonymized_text,
                           embedding_model,embedding_dimensions,embedding_vector_json,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (str(uuid.uuid4()), decision_id, version_id, chunk.chunk_index, chunk.text,
                     embedding_model, len(vector), json.dumps(vector), now),
                )
            conn.commit()

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

    def get_import_state(
        self,
        *,
        source_system: str,
        cursor_kind: str,
    ) -> CourtDecisionCollectorStatus:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT last_processed_at, last_source_guid, status
                FROM court_decision_import_state
                WHERE source_system = %(source_system)s AND cursor_kind = %(cursor_kind)s
                """,
                {"source_system": source_system, "cursor_kind": cursor_kind},
            ).fetchone()
        if row is None:
            return CourtDecisionCollectorStatus(last_processed_at="", last_source_guid="", status="not_started")
        return CourtDecisionCollectorStatus(
            last_processed_at=str(row["last_processed_at"] or ""),
            last_source_guid=str(row["last_source_guid"] or ""),
            status=str(row["status"] or ""),
        )

    def status(self) -> CourtDecisionCollectorStatus:
        return self.get_import_state(source_system="infosud", cursor_kind="latest")

    def statistics(self) -> CourtDecisionStatistics:
        status = self.status()
        with self._connect() as conn:
            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_decisions,
                    COALESCE(SUM(CASE WHEN current_status = 'published' THEN 1 ELSE 0 END), 0)
                        AS published_decisions
                FROM court_decision_documents
                """
            ).fetchone()
            versions = conn.execute("SELECT COUNT(*) AS total_versions FROM court_decision_versions").fetchone()
            latest = conn.execute(
                """
                SELECT decision_id, source_guid, court_name, court_type, issue_date, ecli,
                       file_number, last_stored_at
                FROM court_decision_documents
                ORDER BY last_stored_at DESC, updated_at DESC
                LIMIT 1
                """
            ).fetchone()
        return CourtDecisionStatistics(
            total_decisions=int(str(totals["total_decisions"] if totals else 0)),
            published_decisions=int(str(totals["published_decisions"] if totals else 0)),
            total_versions=int(str(versions["total_versions"] if versions else 0)),
            last_imported_decision_id=str(latest["decision_id"] if latest else ""),
            last_imported_source_guid=str(latest["source_guid"] if latest else ""),
            last_imported_at=str(latest["last_stored_at"] if latest else ""),
            last_imported_court_name=str(latest["court_name"] if latest else ""),
            last_imported_court_type=str(latest["court_type"] if latest else ""),
            last_imported_issue_date=str(latest["issue_date"] if latest else ""),
            last_imported_ecli=str(latest["ecli"] if latest else ""),
            last_imported_file_number=str(latest["file_number"] if latest else ""),
            collector_last_processed_at=status.last_processed_at,
            collector_last_source_guid=status.last_source_guid,
            collector_status=status.status,
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
        kwargs: dict[str, Any] = {"row_factory": dict_row}
        if self.connect_timeout_seconds is not None:
            kwargs["connect_timeout"] = self.connect_timeout_seconds
        if self.statement_timeout_ms is not None:
            kwargs["options"] = f"-c statement_timeout={self.statement_timeout_ms}"
        return psycopg.connect(self.connection_uri, **kwargs)


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
        "issue_date_normalized": _parse_issue_date(record.issue_date),
        "court_name_normalized": normalize_court_name(record.court_name),
        "indexed_at": record.indexed_at,
        "update_date": record.update_date,
        "source_url": record.source_url,
        "now": now,
    }


def _parse_issue_date(value: str) -> date | None:
    normalized = value.strip()
    if not normalized:
        return None
    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(normalized, pattern).date()
        except ValueError:
            continue
    return None


def normalize_court_name(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).split())


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
        issue_date_normalized DATE,
        court_name_normalized TEXT NOT NULL DEFAULT '',
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
    "ALTER TABLE court_decision_documents ADD COLUMN IF NOT EXISTS issue_date_normalized DATE",
    "ALTER TABLE court_decision_documents ADD COLUMN IF NOT EXISTS court_name_normalized TEXT NOT NULL DEFAULT ''",
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
    CREATE INDEX IF NOT EXISTS idx_court_decision_documents_issue_date_normalized
    ON court_decision_documents(issue_date_normalized)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_court_decision_documents_status_issue_date_normalized
    ON court_decision_documents(current_status, issue_date_normalized DESC, updated_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_court_decision_documents_court_name_normalized
    ON court_decision_documents(court_name_normalized)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_court_decision_documents_metadata_search_text
    ON court_decision_documents USING GIN (
        to_tsvector(
            'simple'::regconfig,
            COALESCE(court_name, '') || ' ' ||
            COALESCE(court_type, '') || ' ' ||
            COALESCE(file_number, '') || ' ' ||
            COALESCE(case_number, '') || ' ' ||
            COALESCE(ecli, '')
        )
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_court_decision_versions_decision_stored_at
    ON court_decision_versions(decision_id, stored_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_court_decision_search_text
    ON court_decision_versions USING GIN (
        to_tsvector('simple', pseudonymized_text)
    )
    """,
    """CREATE TABLE IF NOT EXISTS court_decision_enrichments (
        version_id TEXT PRIMARY KEY REFERENCES court_decision_versions(version_id) ON DELETE CASCADE,
        decision_id TEXT NOT NULL REFERENCES court_decision_documents(decision_id) ON DELETE CASCADE,
        status TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', pdf_url TEXT NOT NULL DEFAULT '',
        pdf_filename TEXT NOT NULL DEFAULT '', expected_size BIGINT NOT NULL DEFAULT 0,
        actual_size BIGINT NOT NULL DEFAULT 0, pdf_path TEXT NOT NULL DEFAULT '',
        pdf_sha256 TEXT NOT NULL DEFAULT '', extraction_method TEXT NOT NULL DEFAULT '',
        raw_text TEXT NOT NULL DEFAULT '', pseudonymized_text TEXT NOT NULL DEFAULT '',
        pseudonymized_summary TEXT NOT NULL DEFAULT '', legal_topics JSONB NOT NULL DEFAULT '[]'::jsonb,
        summary_model TEXT NOT NULL DEFAULT '', embedding_model TEXT NOT NULL DEFAULT '',
        embedding_dimensions INTEGER NOT NULL DEFAULT 0,
        summary_embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, attempt_count INTEGER NOT NULL DEFAULT 0,
        last_error_type TEXT NOT NULL DEFAULT '', completed_at TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS court_decision_content_chunks (
        chunk_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL REFERENCES court_decision_documents(decision_id) ON DELETE CASCADE,
        version_id TEXT NOT NULL REFERENCES court_decision_versions(version_id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL, pseudonymized_text TEXT NOT NULL,
        embedding_model TEXT NOT NULL, embedding_dimensions INTEGER NOT NULL,
        embedding_vector_json JSONB NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(version_id, chunk_index))""",
)
