from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class LocalModelBuilderConfig:
    laws_db_path: str
    metadata_db_path: str = "./runs/storage/local-model-builder/sqlite/local_models.sqlite3"
    output_root: str = "./runs/storage/local-model-builder/models"
    sql_assets_root: str = "./databases/local-model-builder/migrations"

    @property
    def resolved_laws_db_path(self) -> Path:
        return _resolve_repo_path(self.laws_db_path)

    @property
    def resolved_metadata_db_path(self) -> Path:
        return _resolve_repo_path(self.metadata_db_path)

    @property
    def resolved_output_root(self) -> Path:
        return _resolve_repo_path(self.output_root)

    @property
    def resolved_sql_assets_root(self) -> Path:
        return _resolve_repo_path(self.sql_assets_root)


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate
