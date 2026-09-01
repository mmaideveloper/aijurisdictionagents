"""Seed deterministic synthetic 2025 amendment relations for issue #721 E2E."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from dotenv import load_dotenv
import psycopg

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import E2E_TEST_PAID_EMAIL, provision_e2e_test_users
from aijurisdictionagents.llm.routing import get_routed_llm_client

REPO_ROOT = Path(__file__).resolve().parents[1]
PREFIX = "issue-721-"
WINNER_ID = f"{PREFIX}law-42-2025"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    load_dotenv(REPO_ROOT / ".env", override=False)
    connection = os.getenv("LAWS_DB_CLOUD", "").strip()
    parsed = urlsplit(connection)
    if os.getenv("LAWS_DB_BACKEND", "").strip().lower() != "postgres":
        raise RuntimeError("Issue #721 E2E requires LAWS_DB_BACKEND=postgres")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or "e2e" not in parsed.path.lower():
        raise RuntimeError("Issue #721 synthetic data requires a loopback E2E laws database")
    with psycopg.connect(connection) as conn:
        if args.cleanup:
            _cleanup(conn)
            return 0
        _cleanup(conn)
        _seed(conn)
    run_id = f"issue-721-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    api_connection = os.getenv("DB_CLOUD", "").strip()
    api_parsed = urlsplit(api_connection)
    if os.getenv("DB_OPTION", "").strip().lower() != "postgres" or api_parsed.hostname not in {
        "127.0.0.1", "localhost", "::1"
    }:
        raise RuntimeError("Issue #721 final E2E requires loopback API PostgreSQL")
    store = ApiDatabaseStore.from_env()
    store.initialize()
    password = os.getenv("JURISDIGTA_E2E_TEST_USER_PASSWORD", "").strip()
    users = provision_e2e_test_users(store=store, password=password)
    user = next(item for item in users if item.email == E2E_TEST_PAID_EMAIL)
    route = get_routed_llm_client(store=store, user_id=user.user_id, user_email=user.email, task_type="chat_reply")
    if route.provider == "mock" or route.route_type == "mock":
        raise RuntimeError("Real configured model route is required; mock is prohibited")
    case = store.create_case(user_id=user.user_id, company_id=None, title=f"[{run_id}] Law analytics 2025")
    evidence = REPO_ROOT / "runs" / "e2e" / "issue-721-law-analytics" / run_id
    evidence.mkdir(parents=True, exist_ok=True)
    manifest = {
        "syntheticOnly": True,
        "runId": run_id,
        "question": "What is the most incorrect recent law with most amendments from 2025?",
        "metric": "distinct_amending_acts",
        "publishedYear": 2025,
        "amendmentYear": 2025,
        "expectedDocumentId": WINNER_ID,
        "expectedLawIdentifier": "42/2025 Z. z.",
        "expectedAmendmentCount": 4,
        "user": {"userId": user.user_id, "email": user.email, "name": "Synthetic Law Analytics E2E"},
        "caseId": case.case_id,
        "caseTitle": case.title,
        "expectedProvider": route.provider,
        "expectedModel": route.model,
        "database": "loopback-postgresql-e2e",
    }
    path = evidence / "input-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest={path}")
    print(f"evidence={evidence}")
    return 0


def _cleanup(conn: psycopg.Connection) -> None:
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM law_documents WHERE document_id LIKE %s", (f"{PREFIX}%",))
    conn.commit()


def _seed(conn: psycopg.Connection) -> None:
    stored_at = datetime(2025, 12, 15, tzinfo=timezone.utc)
    laws = [
        (WINNER_ID, 42, "Synthetic 2025 Legal Analytics Act", "2025-02-01"),
        (f"{PREFIX}law-43-2025", 43, "Synthetic 2025 Comparison Act", "2025-02-02"),
        *[(f"{PREFIX}amendment-{number}-2025", number, f"Synthetic amendment {number}", f"2025-{month:02d}-01") for number, month in zip(range(801, 806), range(3, 8), strict=True)],
    ]
    with conn.cursor() as cursor:
        for document_id, number, title, publication_date in laws:
            version_id = f"{document_id}-v1"
            metadata_id = f"{document_id}-metadata"
            cursor.execute(
                """
                INSERT INTO law_documents (
                    document_id, country_code, collection_code, law_year, law_number,
                    official_name, lawyer_title, source_url, publication_date, current_status,
                    first_effective_date, applicable_to, first_stored_at, last_stored_at,
                    last_checked_at, last_download_status, last_download_error,
                    download_attempt_count, created_at, updated_at
                ) VALUES (%s, 'SK', 'ZZ', 2025, %s, %s, %s, %s, %s, 'published',
                          %s, 'synthetic E2E only', %s, %s, %s, 'stored', '', 1, %s, %s)
                """,
                (document_id, number, title, title, f"https://example.test/{number}-2025", publication_date,
                 publication_date, stored_at, stored_at, stored_at, stored_at, stored_at),
            )
            cursor.execute(
                """
                INSERT INTO law_versions (
                    version_id, document_id, version_token, effective_from, version_checksum,
                    status, html_checksum, pdf_checksum, html_bytes, pdf_bytes,
                    normalized_json, embedding_vector, stored_at, created_at, updated_at,
                    embedding_model, embedding_dimensions
                ) VALUES (%s, %s, 'e2e-v1', %s, %s, 'active', %s, %s, 1, 0,
                          '{"synthetic": true}', '[0,0,0,0,0,0,0,0]', %s, %s, %s,
                          'deterministic-legacy-8d', 8)
                """,
                (version_id, document_id, publication_date, f"checksum-{number}", f"html-{number}",
                 f"pdf-{number}", stored_at, stored_at, stored_at),
            )
            cursor.execute(
                """
                INSERT INTO law_metadata (
                    law_metadata_id, document_id, version_id, law_identifier_text, title,
                    law_type, publication_date, effective_from, legal_areas_json,
                    metadata_json, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 'Act', %s, %s, '[]',
                          '{"synthetic": true}', %s, %s)
                """,
                (metadata_id, document_id, version_id, f"{number}/2025 Z. z.", title,
                 publication_date, publication_date, stored_at, stored_at),
            )
        for ordinal, number in enumerate(range(801, 805), start=1):
            _insert_relation(cursor, source_number=number, target_number=42, ordinal=ordinal, stored_at=stored_at)
        _insert_relation(cursor, source_number=805, target_number=43, ordinal=1, stored_at=stored_at)
    conn.commit()


def _insert_relation(
    cursor: psycopg.Cursor, *, source_number: int, target_number: int, ordinal: int, stored_at: datetime
) -> None:
    source_id = f"{PREFIX}amendment-{source_number}-2025"
    cursor.execute(
        """
        INSERT INTO law_metadata_relations (
            law_metadata_relation_id, law_metadata_id, relation_type, relation_label,
            target_country_code, target_collection_code, target_law_year, target_law_number,
            target_law_identifier_text, target_title, target_url, ordinal, created_at
        ) VALUES (%s, %s, 'amends', 'amends', 'SK', 'ZZ', 2025, %s,
                  %s, %s, %s, %s, %s)
        """,
        (f"{source_id}-to-{target_number}", f"{source_id}-metadata", target_number,
         f"{target_number}/2025 Z. z.",
         "Synthetic 2025 Legal Analytics Act" if target_number == 42 else "Synthetic 2025 Comparison Act",
         f"https://example.test/{target_number}-2025", ordinal, stored_at),
    )


if __name__ == "__main__":
    raise SystemExit(main())
