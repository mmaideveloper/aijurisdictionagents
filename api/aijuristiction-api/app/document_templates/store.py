from __future__ import annotations

import builtins
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator
import unicodedata
from uuid import uuid4

from aijurisdictionagents.api_db.config import ApiDataConfig

from app.document_templates.catalog import build_default_document_templates
from app.document_templates.models import (
    DocumentTemplateCreateRequest,
    DocumentTemplateDefinition,
    DocumentTemplateUpdateRequest,
    TemplateSourceReference,
)


@dataclass(frozen=True)
class DocumentTemplateStoreConfig:
    db_option: str
    db_cloud: str
    sqlite_path: Path


class DocumentTemplateNotFoundError(KeyError):
    pass


class DocumentTemplateConflictError(ValueError):
    pass


class DocumentTemplateAmbiguousError(ValueError):
    pass


class DocumentTemplateStore:
    def __init__(self, config: DocumentTemplateStoreConfig) -> None:
        self._config = config
        self._config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._seed_defaults_if_empty()

    @classmethod
    def from_env(cls) -> "DocumentTemplateStore":
        api_db_config = ApiDataConfig.from_env()
        configured = os.getenv("API_DOCUMENT_TEMPLATES_SQLITE_PATH", "").strip()
        if configured:
            path = Path(configured)
        else:
            repo_root = Path(__file__).resolve().parents[4]
            path = repo_root / "runs" / "storage" / "api" / "sqlite" / "document_templates.sqlite3"
        return cls(
            DocumentTemplateStoreConfig(
                db_option=api_db_config.db_option,
                db_cloud=api_db_config.db_cloud,
                sqlite_path=path,
            )
        )

    def list(
        self,
        *,
        include_deleted: bool = False,
        jurisdiction: str | None = None,
        category: str | None = None,
        template_kind: str | None = None,
    ) -> builtins.list[DocumentTemplateDefinition]:
        clauses: list[str] = []
        params: list[object] = []
        if not include_deleted:
            clauses.append("is_deleted = 0")
        if jurisdiction:
            clauses.append("jurisdiction = ?")
            params.append(jurisdiction.strip().upper())
        if category:
            clauses.append("category = ?")
            params.append(category.strip())
        if template_kind:
            clauses.append("template_kind = ?")
            params.append(template_kind.strip().lower())
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM document_templates {where_sql} ORDER BY category ASC, title ASC"
        with self._connect() as conn:
            rows = conn.execute(self._sql(query), self._params(*params)).fetchall()
        return [self._row_to_definition(_row_to_mapping(row)) for row in rows]

    def get(self, *, template_key: str, jurisdiction: str | None = None) -> DocumentTemplateDefinition:
        with self._connect() as conn:
            if jurisdiction:
                row = conn.execute(
                    self._sql("SELECT * FROM document_templates WHERE template_key = ? AND jurisdiction = ?"),
                    self._params(template_key.strip(), jurisdiction.strip().upper()),
                ).fetchone()
                if row is None:
                    raise DocumentTemplateNotFoundError(
                        f"Document template '{template_key}' for jurisdiction '{jurisdiction}' was not found"
                    )
                return self._row_to_definition(_row_to_mapping(row))
            rows = conn.execute(
                self._sql("SELECT * FROM document_templates WHERE template_key = ?"),
                self._params(template_key.strip()),
            ).fetchall()
        if not rows:
            raise DocumentTemplateNotFoundError(f"Document template '{template_key}' was not found")
        if len(rows) > 1:
            raise DocumentTemplateAmbiguousError(
                f"Document template '{template_key}' exists in multiple jurisdictions; specify jurisdiction."
            )
        return self._row_to_definition(_row_to_mapping(rows[0]))

    def create(self, payload: DocumentTemplateCreateRequest) -> DocumentTemplateDefinition:
        template_key = payload.template_key.strip()
        jurisdiction = payload.jurisdiction.strip().upper()
        if self._exists(template_key=template_key, jurisdiction=jurisdiction):
            raise DocumentTemplateConflictError(
                f"Document template '{template_key}' for jurisdiction '{jurisdiction}' already exists"
            )
        now = _utc_now_iso()
        template_id = str(uuid4())
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                    INSERT INTO document_templates (
                        template_id, template_key, jurisdiction, language, category, title, template_kind,
                        description, source_format, source_url, body, keywords_json, flow_keys_json,
                        placeholders_json, source_refs_json, disclaimer_title, disclaimer_text, disclaimer_footer,
                        is_enabled, is_deleted, created_at, updated_at, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL)
                    """
                ),
                self._params(
                    template_id,
                    template_key,
                    jurisdiction,
                    (payload.language or "").strip() or None,
                    payload.category.strip(),
                    payload.title.strip(),
                    payload.template_kind.strip().lower(),
                    payload.description.strip(),
                    payload.source_format.strip().upper(),
                    payload.source_url.strip(),
                    payload.body,
                    json.dumps(payload.keywords, ensure_ascii=False, sort_keys=True),
                    json.dumps(payload.flow_keys, ensure_ascii=False, sort_keys=True),
                    json.dumps(payload.placeholders, ensure_ascii=False, sort_keys=True),
                    json.dumps([item.model_dump(mode="json") for item in payload.source_refs], ensure_ascii=False, sort_keys=True),
                    payload.disclaimer_title.strip(),
                    payload.disclaimer_text.strip(),
                    payload.disclaimer_footer.strip(),
                    1 if payload.is_enabled else 0,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get(template_key=template_key, jurisdiction=jurisdiction)

    def update(
        self,
        *,
        template_key: str,
        payload: DocumentTemplateUpdateRequest,
        jurisdiction: str | None = None,
    ) -> DocumentTemplateDefinition:
        current = self.get(template_key=template_key, jurisdiction=jurisdiction)
        if current.is_deleted:
            raise DocumentTemplateNotFoundError(f"Document template '{template_key}' is deleted")
        updated = {
            "jurisdiction": (payload.jurisdiction or current.jurisdiction).strip().upper(),
            "language": (
                payload.language.strip() if isinstance(payload.language, str) else current.language
            ),
            "category": (payload.category or current.category).strip(),
            "title": (payload.title or current.title).strip(),
            "template_kind": (payload.template_kind or current.template_kind).strip().lower(),
            "description": (payload.description if payload.description is not None else current.description).strip(),
            "source_format": (payload.source_format or current.source_format).strip().upper(),
            "source_url": (payload.source_url or current.source_url).strip(),
            "body": payload.body if payload.body is not None else current.body,
            "keywords_json": json.dumps(payload.keywords if payload.keywords is not None else list(current.keywords), ensure_ascii=False, sort_keys=True),
            "flow_keys_json": json.dumps(payload.flow_keys if payload.flow_keys is not None else list(current.flow_keys), ensure_ascii=False, sort_keys=True),
            "placeholders_json": json.dumps(payload.placeholders if payload.placeholders is not None else list(current.placeholders), ensure_ascii=False, sort_keys=True),
            "source_refs_json": json.dumps(
                [item.model_dump(mode="json") for item in payload.source_refs]
                if payload.source_refs is not None
                else [item.model_dump(mode="json") for item in current.source_refs],
                ensure_ascii=False,
                sort_keys=True,
            ),
            "disclaimer_title": (
                payload.disclaimer_title.strip()
                if isinstance(payload.disclaimer_title, str)
                else current.disclaimer_title
            ),
            "disclaimer_text": (
                payload.disclaimer_text.strip()
                if isinstance(payload.disclaimer_text, str)
                else current.disclaimer_text
            ),
            "disclaimer_footer": (
                payload.disclaimer_footer.strip()
                if isinstance(payload.disclaimer_footer, str)
                else current.disclaimer_footer
            ),
            "is_enabled": 1 if (payload.is_enabled if payload.is_enabled is not None else current.is_enabled) else 0,
            "updated_at": _utc_now_iso(),
        }
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                    UPDATE document_templates
                    SET jurisdiction = ?, language = ?, category = ?, title = ?, template_kind = ?,
                        description = ?, source_format = ?, source_url = ?, body = ?, keywords_json = ?,
                        flow_keys_json = ?, placeholders_json = ?, source_refs_json = ?, disclaimer_title = ?,
                        disclaimer_text = ?, disclaimer_footer = ?, is_enabled = ?, updated_at = ?
                    WHERE template_key = ? AND jurisdiction = ?
                    """
                ),
                self._params(
                    updated["jurisdiction"],
                    updated["language"],
                    updated["category"],
                    updated["title"],
                    updated["template_kind"],
                    updated["description"],
                    updated["source_format"],
                    updated["source_url"],
                    updated["body"],
                    updated["keywords_json"],
                    updated["flow_keys_json"],
                    updated["placeholders_json"],
                    updated["source_refs_json"],
                    updated["disclaimer_title"],
                    updated["disclaimer_text"],
                    updated["disclaimer_footer"],
                    updated["is_enabled"],
                    updated["updated_at"],
                    current.template_key,
                    current.jurisdiction,
                ),
            )
            conn.commit()
        return self.get(template_key=template_key, jurisdiction=str(updated["jurisdiction"]))

    def soft_delete(self, *, template_key: str, jurisdiction: str | None = None) -> DocumentTemplateDefinition:
        current = self.get(template_key=template_key, jurisdiction=jurisdiction)
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                    UPDATE document_templates
                    SET is_deleted = 1, is_enabled = 0, updated_at = ?, deleted_at = ?
                    WHERE template_key = ? AND jurisdiction = ?
                    """
                ),
                self._params(now, now, current.template_key, current.jurisdiction),
            )
            conn.commit()
        return self.get(template_key=template_key, jurisdiction=current.jurisdiction)

    def find_best_match(
        self,
        *,
        request_text: str,
        country: str,
        template_kind: str | None = None,
    ) -> tuple[int, DocumentTemplateDefinition | None]:
        normalized_text = _normalize_for_match(request_text)
        if not normalized_text:
            return 0, None
        candidates = [
            item
            for item in self.list(include_deleted=False, jurisdiction=country, template_kind=template_kind)
            if item.is_enabled
        ]
        text_roots = _token_roots(normalized_text)
        scored: list[tuple[int, DocumentTemplateDefinition]] = []
        for item in candidates:
            score = 0
            if template_kind and item.template_kind.strip().lower() == template_kind.strip().lower():
                score += 4
            for keyword in item.keywords:
                normalized_keyword = _normalize_for_match(keyword)
                if normalized_keyword in normalized_text:
                    score += 3
                    continue
                keyword_roots = _token_roots(normalized_keyword)
                if keyword_roots and keyword_roots.issubset(text_roots):
                    score += 1
            title_roots = _token_roots(_normalize_for_match(item.title))
            if title_roots and title_roots.issubset(text_roots):
                score += 2
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[0] if scored else (0, None)

    def _seed_defaults_if_empty(self) -> None:
        with self._connect() as conn:
            row = conn.execute(self._sql("SELECT COUNT(1) AS count FROM document_templates")).fetchone()
        if row is not None and int(row["count"]) > 0:
            return
        for item in build_default_document_templates():
            self.create(
                DocumentTemplateCreateRequest(
                    template_key=item.template_key,
                    jurisdiction=item.jurisdiction,
                    language=item.language,
                    category=item.category,
                    title=item.title,
                    template_kind=item.template_kind,
                    description=item.description,
                    source_format=item.source_format,
                    source_url=item.source_url,
                    body=item.body,
                    keywords=list(item.keywords),
                    flow_keys=list(item.flow_keys),
                    placeholders=list(item.placeholders),
                    source_refs=list(item.source_refs),
                    disclaimer_title=item.disclaimer_title,
                    disclaimer_text=item.disclaimer_text,
                    disclaimer_footer=item.disclaimer_footer,
                    is_enabled=item.is_enabled,
                )
            )

    def _initialize(self) -> None:
        with self._connect() as conn:
            if self._is_postgres:
                schema_statements = [statement.strip() for statement in _load_schema_sql().split(";") if statement.strip()]
                for statement in schema_statements:
                    conn.execute(statement)
            else:
                conn.executescript(_load_schema_sql())
            self._ensure_compatibility_columns(conn)
            conn.commit()

    @property
    def _is_postgres(self) -> bool:
        return self._config.db_option in {"postgres", "azure"}

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self._is_postgres:
            psycopg = _load_psycopg()
            if not self._config.db_cloud:
                raise RuntimeError("DB_CLOUD is required for postgres/azure document-template storage")
            conn = psycopg.connect(self._config.db_cloud, row_factory=psycopg.rows.dict_row)
            try:
                yield conn
            finally:
                conn.close()
            return
        conn = sqlite3.connect(self._config.sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _exists(self, *, template_key: str, jurisdiction: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT 1 FROM document_templates WHERE template_key = ? AND jurisdiction = ? LIMIT 1"),
                self._params(template_key.strip(), jurisdiction.strip().upper()),
            ).fetchone()
        return row is not None

    def _row_to_definition(self, row: dict[str, Any]) -> DocumentTemplateDefinition:
        return DocumentTemplateDefinition(
            template_id=str(row["template_id"]),
            template_key=str(row["template_key"]),
            jurisdiction=str(row["jurisdiction"]),
            language=str(row["language"]).strip() or None if row.get("language") is not None else None,
            category=str(row["category"]),
            title=str(row["title"]),
            template_kind=str(row["template_kind"]),
            description=str(row["description"]),
            source_format=str(row["source_format"]),
            source_url=str(row["source_url"]),
            body=str(row["body"] or ""),
            keywords=tuple(_parse_json_array(row.get("keywords_json"))),
            flow_keys=tuple(_parse_json_array(row.get("flow_keys_json"))),
            placeholders=tuple(_parse_json_array(row.get("placeholders_json"))),
            source_refs=tuple(
                TemplateSourceReference.model_validate(item)
                for item in _parse_json_array(row.get("source_refs_json"))
                if isinstance(item, dict)
            ),
            disclaimer_title=str(row.get("disclaimer_title") or ""),
            disclaimer_text=str(row.get("disclaimer_text") or ""),
            disclaimer_footer=str(row.get("disclaimer_footer") or ""),
            is_enabled=bool(row["is_enabled"]),
            is_deleted=bool(row["is_deleted"]),
            created_at=_parse_timestamp(row.get("created_at")),
            updated_at=_parse_timestamp(row.get("updated_at")),
            deleted_at=_parse_timestamp(row.get("deleted_at")),
        )

    def _sql(self, statement: str) -> str:
        if self._is_postgres:
            return statement.replace("?", "%s")
        return statement

    def _params(self, *values: object) -> tuple[object, ...]:
        return tuple(values)

    def _ensure_compatibility_columns(self, conn: Any) -> None:
        existing_columns = self._existing_columns(conn)
        compatibility_columns = {
            "disclaimer_title": "TEXT NOT NULL DEFAULT ''",
            "disclaimer_text": "TEXT NOT NULL DEFAULT ''",
            "disclaimer_footer": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, definition in compatibility_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(
                self._sql(f"ALTER TABLE document_templates ADD COLUMN {column_name} {definition}")
            )

    def _existing_columns(self, conn: Any) -> set[str]:
        if self._is_postgres:
            rows = conn.execute(
                self._sql(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = ? AND table_schema = current_schema()
                    """
                ),
                self._params("document_templates"),
            ).fetchall()
            return {str(row["column_name"]) for row in rows}
        rows = conn.execute(self._sql("PRAGMA table_info(document_templates)")).fetchall()
        return {str(row["name"]) for row in rows}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_schema_sql() -> str:
    schema_path = Path(__file__).resolve().parents[4] / "databases" / "api" / "document_templates_schema.sql"
    return schema_path.read_text(encoding="utf-8")


def _load_psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required when DB_OPTION is postgres or azure") from exc
    return psycopg


def _row_to_mapping(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(row)


def _parse_json_array(raw: Any) -> list[Any]:
    if raw in (None, ""):
        return []
    loaded = json.loads(str(raw))
    if isinstance(loaded, list):
        return loaded
    return []


def _parse_timestamp(raw: Any) -> datetime | None:
    if raw in (None, ""):
        return None
    return datetime.fromisoformat(str(raw))


def _normalize_for_match(value: str) -> str:
    lowered = value.lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    no_diacritics = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(no_diacritics.split())


def _token_roots(value: str) -> set[str]:
    roots: set[str] = set()
    for token in value.split():
        cleaned = "".join(char for char in token if char.isalnum())
        if cleaned:
            roots.add(cleaned[:4])
    return roots


_store: DocumentTemplateStore | None = None


def get_document_template_store() -> DocumentTemplateStore:
    global _store
    if _store is None:
        _store = DocumentTemplateStore.from_env()
    return _store

