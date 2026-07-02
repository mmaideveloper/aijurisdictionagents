from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from uuid import uuid4

from aijurisdictionagents.api_db.config import ApiDataConfig

from app.provider_credentials.models import (
    ProviderCredentialCreateRequest,
    ProviderCredentialResponse,
    ProviderCredentialUpdateRequest,
)


@dataclass(frozen=True)
class ProviderCredentialStoreConfig:
    db_option: str
    db_cloud: str
    sqlite_path: Path


class ProviderCredentialNotFoundError(KeyError):
    pass


class ProviderCredentialConflictError(ValueError):
    pass


class ProviderCredentialStore:
    def __init__(self, config: ProviderCredentialStoreConfig) -> None:
        self._config = config
        self._config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._seed_azure_foundry_from_env()

    @classmethod
    def from_env(cls) -> "ProviderCredentialStore":
        api_db_config = ApiDataConfig.from_env()
        configured = os.getenv("API_PROVIDER_CREDENTIALS_SQLITE_PATH", "").strip()
        if configured:
            path = Path(configured)
        else:
            repo_root = Path(__file__).resolve().parents[4]
            path = repo_root / "runs" / "storage" / "api" / "sqlite" / "provider_credentials.sqlite3"
        return cls(
            ProviderCredentialStoreConfig(
                db_option=api_db_config.db_option,
                db_cloud=api_db_config.db_cloud,
                sqlite_path=path,
            )
        )

    def list(self, *, include_deleted: bool = False) -> list[ProviderCredentialResponse]:
        clauses: list[str] = []
        if not include_deleted:
            clauses.append("is_deleted = 0")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(f"SELECT * FROM provider_credentials {where_sql} ORDER BY display_name ASC")
            ).fetchall()
        return [self._row_to_response(_row_to_mapping(row)) for row in rows]

    def get(self, *, provider_key: str, include_deleted: bool = False) -> ProviderCredentialResponse:
        clauses = ["provider_key = ?"]
        params: list[object] = [_normalize_provider_key(provider_key)]
        if not include_deleted:
            clauses.append("is_deleted = 0")
        with self._connect() as conn:
            row = conn.execute(
                self._sql(f"SELECT * FROM provider_credentials WHERE {' AND '.join(clauses)}"),
                self._params(*params),
            ).fetchone()
        if row is None:
            raise ProviderCredentialNotFoundError(
                f"Provider credential '{provider_key}' was not found"
            )
        return self._row_to_response(_row_to_mapping(row))

    def create(self, payload: ProviderCredentialCreateRequest) -> ProviderCredentialResponse:
        provider_key = _normalize_provider_key(payload.provider_key)
        if self._exists(provider_key):
            raise ProviderCredentialConflictError(
                f"Provider credential '{provider_key}' already exists"
            )
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                    INSERT INTO provider_credentials (
                        credential_id, provider_key, display_name, description, endpoint,
                        deployment, embeddings_model, api_version, auth_method, secret_name,
                        has_secret, metadata_json, is_enabled, is_deleted, created_at, updated_at,
                        deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL)
                    """
                ),
                self._params(
                    str(uuid4()),
                    provider_key,
                    payload.display_name.strip(),
                    payload.description.strip(),
                    payload.endpoint.strip(),
                    payload.deployment.strip(),
                    payload.embeddings_model.strip(),
                    payload.api_version.strip(),
                    payload.auth_method.strip(),
                    payload.secret_name.strip(),
                    1 if payload.has_secret else 0,
                    json.dumps(payload.metadata, ensure_ascii=False, sort_keys=True),
                    1 if payload.is_enabled else 0,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get(provider_key=provider_key)

    def update(
        self,
        *,
        provider_key: str,
        payload: ProviderCredentialUpdateRequest,
    ) -> ProviderCredentialResponse:
        current = self.get(provider_key=provider_key)
        values = {
            "display_name": _coalesce_text(payload.display_name, current.display_name),
            "description": _coalesce_text(payload.description, current.description),
            "endpoint": _coalesce_text(payload.endpoint, current.endpoint),
            "deployment": _coalesce_text(payload.deployment, current.deployment),
            "embeddings_model": _coalesce_text(payload.embeddings_model, current.embeddings_model),
            "api_version": _coalesce_text(payload.api_version, current.api_version),
            "auth_method": _coalesce_text(payload.auth_method, current.auth_method),
            "secret_name": _coalesce_text(payload.secret_name, current.secret_name),
            "has_secret": current.has_secret if payload.has_secret is None else payload.has_secret,
            "metadata": current.metadata if payload.metadata is None else payload.metadata,
            "is_enabled": current.is_enabled if payload.is_enabled is None else payload.is_enabled,
            "updated_at": _utc_now_iso(),
        }
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                    UPDATE provider_credentials
                    SET display_name = ?, description = ?, endpoint = ?, deployment = ?,
                        embeddings_model = ?, api_version = ?, auth_method = ?, secret_name = ?,
                        has_secret = ?, metadata_json = ?, is_enabled = ?, updated_at = ?
                    WHERE provider_key = ?
                    """
                ),
                self._params(
                    values["display_name"],
                    values["description"],
                    values["endpoint"],
                    values["deployment"],
                    values["embeddings_model"],
                    values["api_version"],
                    values["auth_method"],
                    values["secret_name"],
                    1 if values["has_secret"] else 0,
                    json.dumps(values["metadata"], ensure_ascii=False, sort_keys=True),
                    1 if values["is_enabled"] else 0,
                    values["updated_at"],
                    current.provider_key,
                ),
            )
            conn.commit()
        return self.get(provider_key=current.provider_key)

    def soft_delete(self, *, provider_key: str) -> ProviderCredentialResponse:
        current = self.get(provider_key=provider_key)
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    """
                    UPDATE provider_credentials
                    SET is_deleted = 1, is_enabled = 0, deleted_at = ?, updated_at = ?
                    WHERE provider_key = ?
                    """
                ),
                self._params(now, now, current.provider_key),
            )
            conn.commit()
        return self.get(provider_key=current.provider_key, include_deleted=True)

    def _initialize(self) -> None:
        with self._connect() as conn:
            if self._is_postgres:
                for statement in _schema_statements():
                    conn.execute(statement)
            else:
                conn.executescript(_load_schema_sql())
            conn.commit()

    def _seed_azure_foundry_from_env(self) -> None:
        provider = os.getenv("LLM_PROVIDER", "azurefoundry").strip().lower()
        if provider not in {"", "azure", "azurefoundry"}:
            return
        provider_key = "azurefoundry"
        if self._exists(provider_key):
            return
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
        embeddings_model = os.getenv("AZURE_OPENAI_EMBEDDINGS_MODEL", "").strip()
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
        has_api_key = bool(os.getenv("AZURE_OPENAI_API_KEY", "").strip())
        has_ad_token = bool(os.getenv("AZURE_OPENAI_AD_TOKEN", "").strip())
        auth_method = "api_key" if has_api_key else "entra_id" if has_ad_token else ""
        self.create(
            ProviderCredentialCreateRequest(
                provider_key=provider_key,
                display_name="Azure Foundry",
                description="Azure OpenAI/Azure Foundry LLM provider used by the API runtime.",
                endpoint=endpoint,
                deployment=deployment,
                embeddings_model=embeddings_model,
                api_version=api_version,
                auth_method=auth_method,
                secret_name="AZURE_OPENAI_API_KEY" if has_api_key else "AZURE_OPENAI_AD_TOKEN" if has_ad_token else "",
                has_secret=has_api_key or has_ad_token,
                metadata={
                    "source": "environment",
                    "llm_provider": "azurefoundry",
                    "configured": bool(endpoint and deployment and api_version and (has_api_key or has_ad_token)),
                },
                is_enabled=True,
            )
        )

    @property
    def _is_postgres(self) -> bool:
        return self._config.db_option in {"postgres", "azure"}

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self._is_postgres:
            psycopg = _load_psycopg()
            if not self._config.db_cloud:
                raise RuntimeError("DB_CLOUD is required for postgres/azure provider credential storage")
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

    def _exists(self, provider_key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT 1 FROM provider_credentials WHERE provider_key = ? LIMIT 1"),
                self._params(_normalize_provider_key(provider_key)),
            ).fetchone()
        return row is not None

    @staticmethod
    def _row_to_response(row: dict[str, Any]) -> ProviderCredentialResponse:
        return ProviderCredentialResponse(
            credential_id=str(row["credential_id"]),
            provider_key=str(row["provider_key"]),
            display_name=str(row["display_name"]),
            description=str(row["description"]),
            endpoint=str(row["endpoint"]),
            deployment=str(row["deployment"]),
            embeddings_model=str(row["embeddings_model"]),
            api_version=str(row["api_version"]),
            auth_method=str(row["auth_method"]),
            secret_name=str(row["secret_name"]),
            has_secret=bool(row["has_secret"]),
            metadata=json.loads(str(row["metadata_json"])) if row["metadata_json"] else {},
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
    schema_path = Path(__file__).resolve().parents[4] / "databases" / "api" / "provider_credentials_schema.sql"
    return schema_path.read_text(encoding="utf-8")


def _schema_statements() -> list[str]:
    return [statement.strip() for statement in _load_schema_sql().split(";") if statement.strip()]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _normalize_provider_key(value: str) -> str:
    return value.strip().lower()


def _coalesce_text(value: str | None, fallback: str) -> str:
    return fallback if value is None else value.strip()


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
