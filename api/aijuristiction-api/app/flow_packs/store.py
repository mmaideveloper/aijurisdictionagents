from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
import unicodedata
from uuid import uuid4

from aijurisdictionagents.api_db.config import ApiDataConfig

from app.flow_packs.default_packs import build_default_slovak_flow_packs
from app.flow_packs.models import (
    FlowPackCreateRequest,
    FlowPackCreateVersionRequest,
    FlowPackResponse,
    FlowPackUpdateRequest,
)


@dataclass(frozen=True)
class FlowPackStoreConfig:
    db_option: str
    db_cloud: str
    sqlite_path: Path


class FlowPackNotFoundError(KeyError):
    pass


class FlowPackVersionConflictError(ValueError):
    pass


class FlowPackAmbiguousError(ValueError):
    pass


class FlowPackStore:
    def __init__(self, config: FlowPackStoreConfig) -> None:
        self._config = config
        self._config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._seed_defaults_if_empty()

    @classmethod
    def from_env(cls) -> "FlowPackStore":
        api_db_config = ApiDataConfig.from_env()
        configured = os.getenv("API_FLOW_PACKS_SQLITE_PATH", "").strip()
        if configured:
            path = Path(configured)
        else:
            repo_root = Path(__file__).resolve().parents[4]
            path = repo_root / "runs" / "storage" / "api" / "sqlite" / "flow_packs.sqlite3"
        return cls(
            FlowPackStoreConfig(
                db_option=api_db_config.db_option,
                db_cloud=api_db_config.db_cloud,
                sqlite_path=path,
            )
        )

    def list(
        self,
        *,
        include_deleted: bool = False,
        flow_key: str | None = None,
        jurisdiction: str | None = None,
    ) -> list[FlowPackResponse]:
        clauses: list[str] = []
        params: list[object] = []
        if not include_deleted:
            clauses.append("is_deleted = 0")
        if flow_key:
            clauses.append("flow_key = ?")
            params.append(flow_key.strip())
        if jurisdiction:
            clauses.append("jurisdiction = ?")
            params.append(jurisdiction.strip().upper())
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT * FROM flow_packs "
            f"{where_sql} "
            "ORDER BY flow_key ASC, version DESC"
        )
        with self._connect() as conn:
            rows = conn.execute(self._sql(query), self._params(*params)).fetchall()
        return [self._row_to_response(_row_to_mapping(row)) for row in rows]

    def list_versions(
        self,
        *,
        flow_key: str,
        jurisdiction: str | None = None,
        include_deleted: bool = True,
    ) -> list[FlowPackResponse]:
        return self.list(include_deleted=include_deleted, flow_key=flow_key, jurisdiction=jurisdiction)

    def get(self, *, flow_key: str, version: int, jurisdiction: str | None = None) -> FlowPackResponse:
        with self._connect() as conn:
            if jurisdiction:
                row = conn.execute(
                    self._sql("SELECT * FROM flow_packs WHERE flow_key = ? AND version = ? AND jurisdiction = ?"),
                    self._params(flow_key.strip(), version, jurisdiction.strip().upper()),
                ).fetchone()
                if row is None:
                    raise FlowPackNotFoundError(
                        f"Flow pack '{flow_key}' version {version} for jurisdiction '{jurisdiction}' was not found"
                    )
                return self._row_to_response(_row_to_mapping(row))

            rows = conn.execute(
                self._sql("SELECT * FROM flow_packs WHERE flow_key = ? AND version = ?"),
                self._params(flow_key.strip(), version),
            ).fetchall()
        if not rows:
            raise FlowPackNotFoundError(f"Flow pack '{flow_key}' version {version} was not found")
        if len(rows) > 1:
            raise FlowPackAmbiguousError(
                f"Flow pack '{flow_key}' version {version} exists in multiple jurisdictions; specify jurisdiction."
            )
        return self._row_to_response(_row_to_mapping(rows[0]))

    def create(self, payload: FlowPackCreateRequest) -> FlowPackResponse:
        flow_key = payload.flow_key.strip()
        jurisdiction = payload.jurisdiction.strip().upper()
        version = (
            payload.version
            or (self._next_version(flow_key, jurisdiction=jurisdiction) if self._exists(flow_key) else 1)
        )
        if self._version_exists(flow_key=flow_key, version=version, jurisdiction=jurisdiction):
            raise FlowPackVersionConflictError(
                f"Flow pack '{flow_key}' version {version} for jurisdiction '{jurisdiction}' already exists"
            )
        now = _utc_now_iso()
        flow_id = str(uuid4())
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                INSERT INTO flow_packs (
                    flow_id, flow_key, version, jurisdiction, domain, title, description,
                    definition_json, is_enabled, is_deleted, created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL)
                """
                ),
                self._params(
                    flow_id,
                    flow_key,
                    version,
                    jurisdiction,
                    payload.domain.strip().lower(),
                    payload.title.strip(),
                    payload.description.strip(),
                    json.dumps(payload.definition, ensure_ascii=False, sort_keys=True),
                    1 if payload.is_enabled else 0,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get(flow_key=flow_key, version=version, jurisdiction=jurisdiction)

    def create_version(
        self,
        *,
        flow_key: str,
        payload: FlowPackCreateVersionRequest,
        jurisdiction: str | None = None,
    ) -> FlowPackResponse:
        target_jurisdiction = (payload.jurisdiction or jurisdiction or "").strip().upper()
        latest = self._latest(flow_key, jurisdiction=target_jurisdiction or None)
        if latest is None:
            if target_jurisdiction:
                raise FlowPackNotFoundError(
                    f"Flow pack '{flow_key}' does not exist for jurisdiction '{target_jurisdiction}'"
                )
            raise FlowPackNotFoundError(f"Flow pack '{flow_key}' does not exist")
        create_payload = FlowPackCreateRequest(
            flow_key=flow_key,
            version=latest.version + 1,
            jurisdiction=target_jurisdiction or latest.jurisdiction,
            domain=payload.domain or latest.domain,
            title=payload.title or latest.title,
            description=payload.description or latest.description,
            definition=payload.definition if payload.definition is not None else latest.definition,
            is_enabled=payload.is_enabled,
        )
        return self.create(create_payload)

    def update(
        self,
        *,
        flow_key: str,
        version: int,
        payload: FlowPackUpdateRequest,
        jurisdiction: str | None = None,
    ) -> FlowPackResponse:
        current = self.get(flow_key=flow_key, version=version, jurisdiction=jurisdiction)
        if current.is_deleted:
            raise FlowPackNotFoundError(f"Flow pack '{flow_key}' version {version} is deleted")
        updated = {
            "jurisdiction": (payload.jurisdiction or current.jurisdiction).strip().upper(),
            "domain": (payload.domain or current.domain).strip().lower(),
            "title": (payload.title or current.title).strip(),
            "description": (payload.description or current.description).strip(),
            "definition_json": json.dumps(
                payload.definition if payload.definition is not None else current.definition,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "updated_at": _utc_now_iso(),
        }
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                UPDATE flow_packs
                SET jurisdiction = ?, domain = ?, title = ?, description = ?, definition_json = ?, updated_at = ?
                WHERE flow_key = ? AND version = ? AND jurisdiction = ?
                """
                ),
                self._params(
                    updated["jurisdiction"],
                    updated["domain"],
                    updated["title"],
                    updated["description"],
                    updated["definition_json"],
                    updated["updated_at"],
                    flow_key.strip(),
                    version,
                    current.jurisdiction,
                ),
            )
            conn.commit()
        return self.get(flow_key=flow_key, version=version, jurisdiction=current.jurisdiction)

    def set_enabled(
        self,
        *,
        flow_key: str,
        version: int,
        enabled: bool,
        jurisdiction: str | None = None,
    ) -> FlowPackResponse:
        current = self.get(flow_key=flow_key, version=version, jurisdiction=jurisdiction)
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    "UPDATE flow_packs SET is_enabled = ?, updated_at = ? WHERE flow_key = ? AND version = ? AND jurisdiction = ?"
                ),
                self._params(1 if enabled else 0, _utc_now_iso(), flow_key.strip(), version, current.jurisdiction),
            )
            conn.commit()
        return self.get(flow_key=flow_key, version=version, jurisdiction=current.jurisdiction)

    def soft_delete(self, *, flow_key: str, version: int, jurisdiction: str | None = None) -> FlowPackResponse:
        current = self.get(flow_key=flow_key, version=version, jurisdiction=jurisdiction)
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                UPDATE flow_packs
                SET is_deleted = 1, is_enabled = 0, deleted_at = ?, updated_at = ?
                WHERE flow_key = ? AND version = ? AND jurisdiction = ?
                """
                ),
                self._params(now, now, flow_key.strip(), version, current.jurisdiction),
            )
            conn.commit()
        return self.get(flow_key=flow_key, version=version, jurisdiction=current.jurisdiction)

    def find_best_match(
        self,
        *,
        request_text: str,
        country: str,
    ) -> FlowPackResponse | None:
        normalized_text = _normalize_for_match(request_text)
        if not normalized_text:
            return None
        candidates = [
            item
            for item in self.list(include_deleted=False)
            if item.is_enabled and item.jurisdiction.strip().upper() == country.strip().upper()
        ]
        text_roots = _token_roots(normalized_text)
        scored: list[tuple[int, FlowPackResponse]] = []
        for item in candidates:
            keywords = _extract_flow_keywords(item.definition)
            if not keywords:
                continue
            score = 0
            for keyword in keywords:
                normalized_keyword = _normalize_for_match(keyword)
                if normalized_keyword in normalized_text:
                    score += 2
                    continue
                keyword_roots = _token_roots(normalized_keyword)
                if keyword_roots and keyword_roots.issubset(text_roots):
                    score += 1
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[0][1] if scored else None

    def _seed_defaults_if_empty(self) -> None:
        with self._connect() as conn:
            row = conn.execute(self._sql("SELECT COUNT(1) as count FROM flow_packs")).fetchone()
        if row is not None and int(row["count"]) > 0:
            return
        for item in build_default_slovak_flow_packs():
            self.create(FlowPackCreateRequest.model_validate(item))

    def _initialize(self) -> None:
        with self._connect() as conn:
            if self._is_postgres:
                schema_statements = [statement.strip() for statement in _load_schema_sql().split(";") if statement.strip()]
                for statement in schema_statements:
                    conn.execute(statement)
            else:
                conn.executescript(_load_schema_sql())
            self._migrate_legacy_uniqueness(conn)
            conn.commit()

    @property
    def _is_postgres(self) -> bool:
        return self._config.db_option in {"postgres", "azure"}

    @contextmanager
    def _connect(self) -> sqlite3.Connection:
        if self._is_postgres:
            psycopg = _load_psycopg()
            if not self._config.db_cloud:
                raise RuntimeError("DB_CLOUD is required for postgres/azure flow-pack storage")
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

    def _exists(self, flow_key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT 1 FROM flow_packs WHERE flow_key = ? LIMIT 1"),
                self._params(flow_key.strip()),
            ).fetchone()
        return row is not None

    def _version_exists(self, *, flow_key: str, version: int, jurisdiction: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT 1 FROM flow_packs WHERE flow_key = ? AND version = ? AND jurisdiction = ? LIMIT 1"
                ),
                self._params(flow_key.strip(), version, jurisdiction.strip().upper()),
            ).fetchone()
        return row is not None

    def _next_version(self, flow_key: str, *, jurisdiction: str | None = None) -> int:
        clauses = ["flow_key = ?"]
        params: list[object] = [flow_key.strip()]
        if jurisdiction:
            clauses.append("jurisdiction = ?")
            params.append(jurisdiction.strip().upper())
        where_sql = " AND ".join(clauses)
        with self._connect() as conn:
            row = conn.execute(
                self._sql(f"SELECT COALESCE(MAX(version), 0) AS max_version FROM flow_packs WHERE {where_sql}"),
                self._params(*params),
            ).fetchone()
        max_version = int(row["max_version"]) if row is not None else 0
        return max_version + 1

    def _latest(self, flow_key: str, *, jurisdiction: str | None = None) -> FlowPackResponse | None:
        clauses = ["flow_key = ?"]
        params: list[object] = [flow_key.strip()]
        if jurisdiction:
            clauses.append("jurisdiction = ?")
            params.append(jurisdiction.strip().upper())
        where_sql = " AND ".join(clauses)
        with self._connect() as conn:
            row = conn.execute(
                self._sql(f"SELECT * FROM flow_packs WHERE {where_sql} ORDER BY version DESC LIMIT 1"),
                self._params(*params),
            ).fetchone()
        return self._row_to_response(_row_to_mapping(row)) if row is not None else None

    def _migrate_legacy_uniqueness(self, conn: Any) -> None:
        if self._is_postgres:
            conn.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'flow_packs_flow_key_version_key'
                    ) THEN
                        ALTER TABLE flow_packs DROP CONSTRAINT flow_packs_flow_key_version_key;
                    END IF;
                END
                $$;
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_flow_packs_jurisdiction_flow_key_version_unique
                ON flow_packs (jurisdiction, flow_key, version)
                """
            )
            return

        index_rows = conn.execute("PRAGMA index_list(flow_packs)").fetchall()
        for row in index_rows:
            if not int(row["unique"]):
                continue
            index_name = str(row["name"])
            columns = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
            column_names = [str(item["name"]) for item in columns]
            if column_names == ["flow_key", "version"]:
                self._rebuild_sqlite_table_with_country_unique(conn)
                break

    def _rebuild_sqlite_table_with_country_unique(self, conn: Any) -> None:
        conn.execute("ALTER TABLE flow_packs RENAME TO flow_packs_legacy")
        conn.executescript(_load_schema_sql())
        conn.execute(
            """
            INSERT INTO flow_packs (
                flow_id, flow_key, version, jurisdiction, domain, title, description,
                definition_json, is_enabled, is_deleted, created_at, updated_at, deleted_at
            )
            SELECT
                flow_id, flow_key, version, jurisdiction, domain, title, description,
                definition_json, is_enabled, is_deleted, created_at, updated_at, deleted_at
            FROM flow_packs_legacy
            """
        )
        conn.execute("DROP TABLE flow_packs_legacy")

    @staticmethod
    def _row_to_response(row: dict[str, Any]) -> FlowPackResponse:
        return FlowPackResponse(
            flow_id=str(row["flow_id"]),
            flow_key=str(row["flow_key"]),
            version=int(row["version"]),
            jurisdiction=str(row["jurisdiction"]),
            domain=str(row["domain"]),
            title=str(row["title"]),
            description=str(row["description"]),
            definition=json.loads(str(row["definition_json"])) if row["definition_json"] else {},
            is_enabled=bool(row["is_enabled"]),
            is_deleted=bool(row["is_deleted"]),
            created_at=_from_iso(str(row["created_at"])),
            updated_at=_from_iso(str(row["updated_at"])),
            deleted_at=_from_iso(str(row["deleted_at"])) if row["deleted_at"] else None,
        )

    def _sql(self, query: str) -> str:
        if not self._is_postgres:
            return query
        return query.replace("?", "%s")

    @staticmethod
    def _params(*values: object) -> tuple[object, ...]:
        return tuple(values)


def _load_schema_sql() -> str:
    schema_path = Path(__file__).resolve().parents[4] / "databases" / "api" / "flow_packs_schema.sql"
    return schema_path.read_text(encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _load_psycopg() -> Any:
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime extras.
        raise RuntimeError("psycopg is required when DB_OPTION is postgres or azure") from exc
    return psycopg


def _row_to_mapping(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(row)


def _extract_flow_keywords(definition: dict[str, Any]) -> tuple[str, ...]:
    intent = definition.get("intent")
    if isinstance(intent, dict):
        keywords = intent.get("keywords")
        if isinstance(keywords, list):
            normalized = [str(item).strip().lower() for item in keywords if str(item).strip()]
            if normalized:
                return tuple(normalized)
    raw_keywords = definition.get("keywords")
    if isinstance(raw_keywords, list):
        normalized = [str(item).strip().lower() for item in raw_keywords if str(item).strip()]
        if normalized:
            return tuple(normalized)
    return ()


def _normalize_for_match(value: str) -> str:
    lowered = value.lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    no_diacritics = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(no_diacritics.split())


def _token_roots(value: str) -> set[str]:
    roots: set[str] = set()
    for token in value.split():
        cleaned = "".join(char for char in token if char.isalnum())
        if not cleaned:
            continue
        roots.add(cleaned[:4])
    return roots
