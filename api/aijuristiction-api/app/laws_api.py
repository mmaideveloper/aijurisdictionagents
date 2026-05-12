from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import sqlite3
from typing import Any, Sequence, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.responses import Response

from app.law_citations import read_law_source
from app.security import require_api_key

router = APIRouter(prefix="/v1/laws", tags=["laws"], dependencies=[Depends(require_api_key)])
_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class _LawsDbConfig:
    backend: str
    local_path: Path
    cloud_uri: str


@router.get("/statistics")
def get_laws_statistics(
    country_code: str = Query("SK", min_length=2, max_length=2),
) -> JSONResponse:
    normalized_country = country_code.strip().upper()
    config = _laws_db_config()
    try:
        payload = _read_laws_statistics(config=config, country_code=normalized_country)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Laws statistics unavailable: {exc}") from exc
    return JSONResponse(payload)


@router.get("/source")
def download_law_source(
    country_code: str = Query(..., min_length=2, max_length=2),
    collection_code: str = Query("ZZ", min_length=1, max_length=8),
    law_year: int = Query(..., ge=1900),
    law_number: int = Query(..., ge=1),
    version_token: str = Query(..., min_length=1),
    artifact_kind: str = Query("html", pattern="^(html|pdf)$"),
) -> Response:
    payload = read_law_source(
        country_code=country_code.strip().upper(),
        collection_code=collection_code.strip().upper(),
        law_year=law_year,
        law_number=law_number,
        version_token=version_token.strip(),
        artifact_kind=artifact_kind.strip().lower(),
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Law source artifact not found.")
    content, media_type, filename = payload
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


def _laws_db_config() -> _LawsDbConfig:
    backend = os.getenv("LAWS_DB_BACKEND", "sqlite").strip().lower() or "sqlite"
    local_value = os.getenv(
        "LAWS_DB_LOCAL",
        "./runs/storage/laws-collector/sqlite/sk_laws.sqlite3",
    ).strip()
    cloud_uri = os.getenv("LAWS_DB_CLOUD", "").strip()
    return _LawsDbConfig(
        backend=backend,
        local_path=_resolve_repo_path(local_value),
        cloud_uri=cloud_uri,
    )


def _read_laws_statistics(*, config: _LawsDbConfig, country_code: str) -> dict[str, Any]:
    if config.backend == "sqlite":
        if not config.local_path.exists():
            raise FileNotFoundError(f"Laws SQLite database not found: {config.local_path}")
        with sqlite3.connect(config.local_path) as conn:
            return _build_statistics_payload(
                backend=config.backend,
                country_code=country_code,
                query_one=lambda query, params=(): cast(
                    Sequence[Any] | None,
                    conn.execute(query, params).fetchone(),
                ),
                param=lambda _name: "?",
            )

    if config.backend == "postgres":
        if not config.cloud_uri:
            raise ValueError("LAWS_DB_CLOUD must be set when LAWS_DB_BACKEND=postgres")
        psycopg = importlib.import_module("psycopg")
        with psycopg.connect(config.cloud_uri) as conn:
            return _build_statistics_payload(
                backend=config.backend,
                country_code=country_code,
                query_one=lambda query, params=(): cast(
                    Sequence[Any] | None,
                    conn.execute(query, params).fetchone(),
                ),
                param=lambda _name: "%s",
            )

    raise ValueError("LAWS_DB_BACKEND must be one of: sqlite, postgres")


def _build_statistics_payload(
    *,
    backend: str,
    country_code: str,
    query_one: Any,
    param: Any,
) -> dict[str, Any]:
    country_param = param("country_code")
    document_counts = _required_row(
        query_one(
            f"""
            SELECT
                COUNT(*) AS total_laws_imported,
                COALESCE(SUM(CASE WHEN current_status = 'published' THEN 1 ELSE 0 END), 0)
                    AS total_laws_finalized,
                MIN(law_year) AS earliest_law_year,
                MAX(law_year) AS latest_law_year,
                MAX(last_stored_at) AS last_stored_at
            FROM law_documents
            WHERE UPPER(country_code) = {country_param}
            """,
            (country_code,),
        )
    )
    version_counts = _required_row(
        query_one(
            f"""
            SELECT
                COUNT(*) AS total_versions_imported,
                COALESCE(SUM(
                    CASE
                        WHEN COALESCE(embedding_model, '') = ''
                          OR COALESCE(embedding_dimensions, 0) <= 0
                          OR COALESCE(CAST(embedding_vector AS TEXT), '') = ''
                        THEN 1
                        ELSE 0
                    END
                ), 0) AS versions_without_embedding
            FROM law_versions AS v
            JOIN law_documents AS d ON d.document_id = v.document_id
            WHERE UPPER(d.country_code) = {country_param}
            """,
            (country_code,),
        )
    )
    laws_without_embedding = _required_row(
        query_one(
            f"""
            SELECT COUNT(*) AS value
            FROM law_documents AS d
            WHERE UPPER(d.country_code) = {country_param}
              AND NOT EXISTS (
                  SELECT 1
                  FROM law_versions AS v
                  WHERE v.document_id = d.document_id
                    AND COALESCE(v.embedding_model, '') <> ''
                    AND COALESCE(v.embedding_dimensions, 0) > 0
                    AND COALESCE(CAST(v.embedding_vector AS TEXT), '') <> ''
              )
            """,
            (country_code,),
        )
    )
    progress = query_one(
        f"""
        SELECT
            source_system,
            last_collector_run_at,
            last_processed_at,
            last_processed_law_year,
            last_processed_law_number,
            next_probe_law_year,
            next_probe_law_number
        FROM collector_progress
        WHERE UPPER(country_code) = {country_param}
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (country_code,),
    )
    import_state = query_one(
        f"""
        SELECT
            import_key,
            import_label,
            status,
            last_processed_at,
            last_processed_law_year,
            last_processed_law_number,
            completed_at
        FROM collector_import_state
        WHERE UPPER(country_code) = {country_param}
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (country_code,),
    )
    asset_counts = _required_row(
        query_one(
            f"""
            SELECT
                COUNT(*) AS total_archive_assets,
                COALESCE(SUM(CASE WHEN processing_status = 'processed' THEN 1 ELSE 0 END), 0)
                    AS processed_archive_assets
            FROM archive_import_assets
            WHERE UPPER(country_code) = {country_param}
            """,
            (country_code,),
        )
    )

    last_processed_year = _optional_int(_row_value(progress, 3))
    last_processed_number = _optional_int(_row_value(progress, 4))
    import_processed_year = _optional_int(_row_value(import_state, 4))
    import_processed_number = _optional_int(_row_value(import_state, 5))
    next_probe_year = _optional_int(_row_value(progress, 5))
    next_probe_number = _optional_int(_row_value(progress, 6))

    return {
        "country_code": country_code,
        "db_backend": backend,
        "source_system": _optional_text(_row_value(progress, 0)),
        "collector": {
            "last_collector_run_at": _optional_text(_row_value(progress, 1)),
            "last_processed_at": _optional_text(_row_value(progress, 2)),
            "last_processed_law": _format_law(last_processed_year, last_processed_number),
            "last_processed_law_year": last_processed_year,
            "last_processed_law_number": last_processed_number,
            "next_law_to_check": _format_law(next_probe_year, next_probe_number),
            "next_law_year": next_probe_year,
            "next_law_number": next_probe_number,
        },
        "current_import": {
            "import_key": _optional_text(_row_value(import_state, 0)),
            "import_label": _optional_text(_row_value(import_state, 1)),
            "status": _optional_text(_row_value(import_state, 2)),
            "last_processed_at": _optional_text(_row_value(import_state, 3)),
            "last_processed_law": _format_law(import_processed_year, import_processed_number),
            "completed_at": _optional_text(_row_value(import_state, 6)),
        },
        "totals": {
            "laws_imported": int(_row_value(document_counts, 0) or 0),
            "laws_finalized": int(_row_value(document_counts, 1) or 0),
            "law_versions_imported": int(_row_value(version_counts, 0) or 0),
            "law_versions_without_embedding": int(_row_value(version_counts, 1) or 0),
            "laws_without_embedding": int(_row_value(laws_without_embedding, 0) or 0),
            "archive_assets": int(_row_value(asset_counts, 0) or 0),
            "archive_assets_processed": int(_row_value(asset_counts, 1) or 0),
        },
        "coverage": {
            "earliest_law_year": _optional_int(_row_value(document_counts, 2)),
            "latest_law_year": _optional_int(_row_value(document_counts, 3)),
            "last_stored_at": _optional_text(_row_value(document_counts, 4)),
        },
    }


def _required_row(row: Sequence[Any] | None) -> Sequence[Any]:
    if row is None:
        raise ValueError("Laws statistics query returned no row.")
    return row


def _row_value(row: Sequence[Any] | None, index: int) -> Any:
    if row is None:
        return None
    return row[index]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _format_law(year: int | None, number: int | None) -> str | None:
    if year is None or number is None:
        return None
    return f"{number}/{year}"


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate
