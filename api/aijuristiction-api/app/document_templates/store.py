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

from app.case_types.models import (
    CasePromptDefinition,
    CaseTypeCreateRequest,
    CaseTypeDefinition,
    CaseTypeUpdateRequest,
)
from app.case_types.seed import build_default_case_types
from app.document_templates.catalog import build_default_document_templates
from app.document_templates.models import (
    DocumentTemplateCreateRequest,
    DocumentTemplateDefinition,
    DocumentTemplateResponse,
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


class CaseTypeNotFoundError(KeyError):
    pass


class CaseTypeConflictError(ValueError):
    pass


class DocumentTemplateStore:
    def __init__(self, config: DocumentTemplateStoreConfig) -> None:
        self._config = config
        self._config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._seed_defaults_if_empty()
        self._seed_case_types_if_empty()
        self._refresh_seeded_case_type_descriptions()

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

    def list_case_types(
        self,
        *,
        include_deleted: bool = False,
        jurisdiction: str | None = None,
    ) -> builtins.list[CaseTypeDefinition]:
        clauses: list[str] = []
        params: list[object] = []
        if not include_deleted:
            clauses.append("is_deleted = 0")
        if jurisdiction:
            clauses.append("jurisdiction = ?")
            params.append(jurisdiction.strip().upper())
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM case_types {where_sql} ORDER BY name ASC"
        with self._connect() as conn:
            rows = conn.execute(self._sql(query), self._params(*params)).fetchall()
        return [self._case_row_to_definition(_row_to_mapping(row)) for row in rows]

    def get_case_type(
        self,
        *,
        case_type_key: str,
        jurisdiction: str | None = None,
    ) -> CaseTypeDefinition:
        normalized_key = case_type_key.strip().lower()
        with self._connect() as conn:
            if jurisdiction:
                row = conn.execute(
                    self._sql("SELECT * FROM case_types WHERE case_type_key = ? AND jurisdiction = ?"),
                    self._params(normalized_key, jurisdiction.strip().upper()),
                ).fetchone()
                if row is None:
                    raise CaseTypeNotFoundError(
                        f"Case type '{case_type_key}' for jurisdiction '{jurisdiction}' was not found"
                    )
                return self._case_row_to_definition(_row_to_mapping(row))
            rows = conn.execute(
                self._sql("SELECT * FROM case_types WHERE case_type_key = ?"),
                self._params(normalized_key),
            ).fetchall()
        if not rows:
            raise CaseTypeNotFoundError(f"Case type '{case_type_key}' was not found")
        if len(rows) > 1:
            raise CaseTypeConflictError(
                f"Case type '{case_type_key}' exists in multiple jurisdictions; specify jurisdiction."
            )
        return self._case_row_to_definition(_row_to_mapping(rows[0]))

    def create_case_type(self, payload: CaseTypeCreateRequest) -> CaseTypeDefinition:
        case_type_key = payload.case_type_key.strip().lower()
        jurisdiction = payload.jurisdiction.strip().upper()
        if self._case_type_exists(case_type_key=case_type_key, jurisdiction=jurisdiction):
            raise CaseTypeConflictError(
                f"Case type '{case_type_key}' for jurisdiction '{jurisdiction}' already exists"
            )
        now = _utc_now_iso()
        case_type_id = str(uuid4())
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                    INSERT INTO case_types (
                        case_type_id, case_type_key, jurisdiction, language, name, description,
                        keywords_json, is_enabled, is_deleted, created_at, updated_at, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL)
                    """
                ),
                self._params(
                    case_type_id,
                    case_type_key,
                    jurisdiction,
                    (payload.language or "").strip() or None,
                    payload.name.strip(),
                    payload.description.strip(),
                    json.dumps(_dedupe_preserve_order(payload.keywords), ensure_ascii=False, sort_keys=True),
                    1 if payload.is_enabled else 0,
                    now,
                    now,
                ),
            )
            conn.commit()
        if payload.prompt_text is not None and payload.prompt_text.strip():
            self._upsert_case_prompt(
                case_type_id=case_type_id,
                prompt_text=payload.prompt_text,
            )
        self._replace_case_type_templates(
            case_type_id=case_type_id,
            template_keys=payload.template_keys,
            jurisdiction=jurisdiction,
        )
        return self.get_case_type(case_type_key=case_type_key, jurisdiction=jurisdiction)

    def update_case_type(
        self,
        *,
        case_type_key: str,
        payload: CaseTypeUpdateRequest,
        jurisdiction: str | None = None,
    ) -> CaseTypeDefinition:
        current = self.get_case_type(case_type_key=case_type_key, jurisdiction=jurisdiction)
        if current.is_deleted:
            raise CaseTypeNotFoundError(f"Case type '{case_type_key}' is deleted")
        updated_jurisdiction = (payload.jurisdiction or current.jurisdiction).strip().upper()
        updated = {
            "jurisdiction": updated_jurisdiction,
            "language": payload.language.strip() if isinstance(payload.language, str) else current.language,
            "name": (payload.name or current.name).strip(),
            "description": (payload.description if payload.description is not None else current.description).strip(),
            "keywords_json": json.dumps(
                _dedupe_preserve_order(payload.keywords)
                if payload.keywords is not None
                else list(current.keywords),
                ensure_ascii=False,
                sort_keys=True,
            ),
            "is_enabled": 1 if (payload.is_enabled if payload.is_enabled is not None else current.is_enabled) else 0,
            "updated_at": _utc_now_iso(),
        }
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                    UPDATE case_types
                    SET jurisdiction = ?, language = ?, name = ?, description = ?, keywords_json = ?,
                        is_enabled = ?, updated_at = ?
                    WHERE case_type_key = ? AND jurisdiction = ?
                    """
                ),
                self._params(
                    updated["jurisdiction"],
                    updated["language"],
                    updated["name"],
                    updated["description"],
                    updated["keywords_json"],
                    updated["is_enabled"],
                    updated["updated_at"],
                    current.case_type_key,
                    current.jurisdiction,
                ),
            )
            conn.commit()
        if payload.prompt_text is not None:
            self._upsert_case_prompt(case_type_id=current.case_type_id, prompt_text=payload.prompt_text)
        if payload.template_keys is not None:
            self._replace_case_type_templates(
                case_type_id=current.case_type_id,
                template_keys=payload.template_keys,
                jurisdiction=updated_jurisdiction,
            )
        return self.get_case_type(case_type_key=case_type_key, jurisdiction=updated_jurisdiction)

    def soft_delete_case_type(
        self,
        *,
        case_type_key: str,
        jurisdiction: str | None = None,
    ) -> CaseTypeDefinition:
        current = self.get_case_type(case_type_key=case_type_key, jurisdiction=jurisdiction)
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                    UPDATE case_types
                    SET is_deleted = 1, is_enabled = 0, updated_at = ?, deleted_at = ?
                    WHERE case_type_key = ? AND jurisdiction = ?
                    """
                ),
                self._params(now, now, current.case_type_key, current.jurisdiction),
            )
            conn.commit()
        return self.get_case_type(case_type_key=case_type_key, jurisdiction=current.jurisdiction)

    def resolve_case_type(
        self,
        *,
        request_text: str,
        country: str,
    ) -> tuple[int, CaseTypeDefinition | None]:
        ranked = self.rank_case_types(request_text=request_text, country=country, limit=1)
        if ranked:
            return ranked[0]
        return 0, None

    def rank_case_types(
        self,
        *,
        request_text: str,
        country: str,
        limit: int | None = None,
    ) -> builtins.list[tuple[int, CaseTypeDefinition]]:
        normalized_text = _normalize_for_match(request_text)
        if not normalized_text:
            return []
        candidates = [
            item
            for item in self.list_case_types(include_deleted=False, jurisdiction=country)
            if item.is_enabled
        ]
        scored = self._score_case_types(
            normalized_text=normalized_text,
            candidates=candidates,
            allow_stem_fallback=False,
        )
        if not scored:
            scored = self._score_case_types(
                normalized_text=normalized_text,
                candidates=candidates,
                allow_stem_fallback=True,
            )
        scored.sort(key=lambda pair: pair[0], reverse=True)
        if scored:
            return scored[:limit] if limit is not None else scored
        template_score, matched_template = self.find_best_match(request_text=request_text, country=country)
        if matched_template is None:
            return []
        linked_case = self._find_case_type_by_template_id(template_id=matched_template.template_id)
        if linked_case is None:
            return []
        return [(template_score, linked_case)]

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
        scored = self._score_templates(
            normalized_text=normalized_text,
            candidates=candidates,
            template_kind=template_kind,
            allow_stem_fallback=False,
        )
        if not scored:
            scored = self._score_templates(
                normalized_text=normalized_text,
                candidates=candidates,
                template_kind=template_kind,
                allow_stem_fallback=True,
            )
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[0] if scored else (0, None)

    def _score_case_types(
        self,
        *,
        normalized_text: str,
        candidates: builtins.list[CaseTypeDefinition],
        allow_stem_fallback: bool,
    ) -> builtins.list[tuple[int, CaseTypeDefinition]]:
        text_roots = _token_roots(normalized_text)
        text_stems = _token_stems(normalized_text) if allow_stem_fallback else set()
        scored: builtins.list[tuple[int, CaseTypeDefinition]] = []
        for item in candidates:
            score = 0
            for keyword in item.keywords:
                normalized_keyword = _normalize_for_match(keyword)
                if normalized_keyword in normalized_text:
                    score += 3
                    continue
                keyword_roots = _token_roots(normalized_keyword)
                if keyword_roots and keyword_roots.issubset(text_roots):
                    score += 1
                    continue
                if allow_stem_fallback:
                    keyword_stems = _token_stems(normalized_keyword)
                    if keyword_stems and keyword_stems.issubset(text_stems):
                        score += 1
            name_normalized = _normalize_for_match(item.name)
            name_roots = _token_roots(name_normalized)
            if name_roots and name_roots.issubset(text_roots):
                score += 2
            elif allow_stem_fallback:
                name_stems = _token_stems(name_normalized)
                if name_stems and name_stems.issubset(text_stems):
                    score += 1
            if item.description:
                description_roots = _token_roots(_normalize_for_match(item.description))
                if description_roots and description_roots.issubset(text_roots):
                    score += 1
            for template in item.templates:
                title_normalized = _normalize_for_match(template.title)
                template_title_roots = _token_roots(title_normalized)
                if template_title_roots and template_title_roots.issubset(text_roots):
                    score += 1
                elif allow_stem_fallback:
                    template_title_stems = _token_stems(title_normalized)
                    if template_title_stems and template_title_stems.issubset(text_stems):
                        score += 1
                for keyword in template.keywords:
                    normalized_keyword = _normalize_for_match(keyword)
                    if normalized_keyword in normalized_text:
                        score += 2
                        break
                    if allow_stem_fallback:
                        keyword_stems = _token_stems(normalized_keyword)
                        if keyword_stems and keyword_stems.issubset(text_stems):
                            score += 1
                            break
            if score > 0:
                scored.append((score, item))
        return scored

    def _score_templates(
        self,
        *,
        normalized_text: str,
        candidates: builtins.list[DocumentTemplateDefinition],
        template_kind: str | None,
        allow_stem_fallback: bool,
    ) -> builtins.list[tuple[int, DocumentTemplateDefinition]]:
        text_roots = _token_roots(normalized_text)
        text_stems = _token_stems(normalized_text) if allow_stem_fallback else set()
        scored: builtins.list[tuple[int, DocumentTemplateDefinition]] = []
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
                    continue
                if allow_stem_fallback:
                    keyword_stems = _token_stems(normalized_keyword)
                    if keyword_stems and keyword_stems.issubset(text_stems):
                        score += 1
            title_normalized = _normalize_for_match(item.title)
            title_roots = _token_roots(title_normalized)
            if title_roots and title_roots.issubset(text_roots):
                score += 2
            elif allow_stem_fallback:
                title_stems = _token_stems(title_normalized)
                if title_stems and title_stems.issubset(text_stems):
                    score += 1
            if score > 0:
                scored.append((score, item))
        return scored

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

    def _seed_case_types_if_empty(self) -> None:
        with self._connect() as conn:
            row = conn.execute(self._sql("SELECT COUNT(1) AS count FROM case_types")).fetchone()
        if row is not None and int(row["count"]) > 0:
            return
        templates = self.list(include_deleted=False)
        for item in build_default_case_types(templates):
            self.create_case_type(item)

    def _refresh_seeded_case_type_descriptions(self) -> None:
        default_items = build_default_case_types(self.list(include_deleted=False))
        if not default_items:
            return
        updates: list[tuple[str, str, str, str]] = []
        for item in default_items:
            try:
                current = self.get_case_type(
                    case_type_key=item.case_type_key,
                    jurisdiction=item.jurisdiction,
                )
            except CaseTypeNotFoundError:
                continue
            if current.description.strip() == item.description.strip():
                continue
            updates.append(
                (
                    item.description.strip(),
                    _utc_now_iso(),
                    current.case_type_key,
                    current.jurisdiction,
                )
            )
        if not updates:
            return
        with self._connect() as conn:
            conn.executemany(
                self._sql(
                    """
                    UPDATE case_types
                    SET description = ?, updated_at = ?
                    WHERE case_type_key = ? AND jurisdiction = ?
                    """
                ),
                [self._params(*values) for values in updates],
            )
            conn.commit()

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
        conn.execute("PRAGMA foreign_keys = ON")
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

    def _case_type_exists(self, *, case_type_key: str, jurisdiction: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT 1 FROM case_types WHERE case_type_key = ? AND jurisdiction = ? LIMIT 1"),
                self._params(case_type_key.strip().lower(), jurisdiction.strip().upper()),
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

    def _case_row_to_definition(self, row: dict[str, Any]) -> CaseTypeDefinition:
        case_type_id = str(row["case_type_id"])
        prompt = self._get_case_prompt(case_type_id=case_type_id)
        templates = self._get_case_templates(case_type_id=case_type_id)
        return CaseTypeDefinition(
            case_type_id=case_type_id,
            case_type_key=str(row["case_type_key"]),
            jurisdiction=str(row["jurisdiction"]),
            language=str(row["language"]).strip() or None if row.get("language") is not None else None,
            name=str(row["name"]),
            description=str(row["description"]),
            keywords=tuple(_parse_json_array(row.get("keywords_json"))),
            is_enabled=bool(row["is_enabled"]),
            is_deleted=bool(row["is_deleted"]),
            prompt=prompt,
            templates=tuple(DocumentTemplateResponse.from_definition(item) for item in templates),
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

    def _get_case_prompt(self, *, case_type_id: str) -> CasePromptDefinition | None:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT * FROM case_prompts WHERE case_type_id = ?"),
                self._params(case_type_id),
            ).fetchone()
        if row is None:
            return None
        mapped = _row_to_mapping(row)
        return CasePromptDefinition(
            case_prompt_id=str(mapped["case_prompt_id"]),
            case_type_id=str(mapped["case_type_id"]),
            prompt_text=str(mapped["prompt_text"]),
            created_at=_parse_timestamp(mapped.get("created_at")),
            updated_at=_parse_timestamp(mapped.get("updated_at")),
        )

    def _get_case_templates(self, *, case_type_id: str) -> builtins.list[DocumentTemplateDefinition]:
        query = """
            SELECT dt.*
            FROM case_type_templates AS ctt
            INNER JOIN document_templates AS dt ON dt.template_id = ctt.template_id
            WHERE ctt.case_type_id = ? AND dt.is_deleted = 0
            ORDER BY ctt.suitability_score DESC, dt.title ASC
        """
        with self._connect() as conn:
            rows = conn.execute(self._sql(query), self._params(case_type_id)).fetchall()
        return [self._row_to_definition(_row_to_mapping(row)) for row in rows]

    def _find_case_type_by_template_id(self, *, template_id: str) -> CaseTypeDefinition | None:
        query = """
            SELECT ct.*
            FROM case_types AS ct
            INNER JOIN case_type_templates AS ctt ON ctt.case_type_id = ct.case_type_id
            WHERE ctt.template_id = ? AND ct.is_deleted = 0 AND ct.is_enabled = 1
            ORDER BY ctt.suitability_score DESC, ct.name ASC
            LIMIT 1
        """
        with self._connect() as conn:
            row = conn.execute(self._sql(query), self._params(template_id)).fetchone()
        if row is None:
            return None
        return self._case_row_to_definition(_row_to_mapping(row))

    def _upsert_case_prompt(self, *, case_type_id: str, prompt_text: str) -> None:
        current = self._get_case_prompt(case_type_id=case_type_id)
        now = _utc_now_iso()
        with self._connect() as conn:
            if current is None:
                conn.execute(
                    self._sql(
                        """
                        INSERT INTO case_prompts (
                            case_prompt_id, case_type_id, prompt_text, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """
                    ),
                    self._params(str(uuid4()), case_type_id, prompt_text.strip(), now, now),
                )
            else:
                conn.execute(
                    self._sql(
                        """
                        UPDATE case_prompts
                        SET prompt_text = ?, updated_at = ?
                        WHERE case_type_id = ?
                        """
                    ),
                    self._params(prompt_text.strip(), now, case_type_id),
                )
            conn.commit()

    def _replace_case_type_templates(
        self,
        *,
        case_type_id: str,
        template_keys: builtins.list[str],
        jurisdiction: str,
    ) -> None:
        normalized_keys = _dedupe_preserve_order(template_keys)
        now = _utc_now_iso()
        templates: list[DocumentTemplateDefinition] = []
        for key in normalized_keys:
            templates.append(self.get(template_key=key, jurisdiction=jurisdiction))
        with self._connect() as conn:
            conn.execute(
                self._sql("DELETE FROM case_type_templates WHERE case_type_id = ?"),
                self._params(case_type_id),
            )
            for template in templates:
                conn.execute(
                    self._sql(
                        """
                        INSERT INTO case_type_templates (
                            case_type_template_id, case_type_id, template_id, suitability_score, notes,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """
                    ),
                    self._params(
                        str(uuid4()),
                        case_type_id,
                        template.template_id,
                        100,
                        "",
                        now,
                        now,
                    ),
                )
            conn.commit()


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


def _token_stems(value: str) -> set[str]:
    stems: set[str] = set()
    for token in value.split():
        cleaned = "".join(char for char in token if char.isalnum())
        if len(cleaned) >= 3:
            stems.add(cleaned[:3])
    return stems


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for raw in values:
        normalized = raw.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


_store: DocumentTemplateStore | None = None


def get_document_template_store() -> DocumentTemplateStore:
    global _store
    if _store is None:
        _store = DocumentTemplateStore.from_env()
    return _store

