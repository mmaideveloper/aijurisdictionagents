"""Prepare isolated PostgreSQL data for the issue #713 real local E2E."""

from __future__ import annotations

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
SYNTHETIC_DOCUMENT_ID = "issue-713-latest-law"
SYNTHETIC_IDENTIFIER = "713/2026 Z. z."
SYNTHETIC_TITLE = "Syntetický zákon o transparentnom testovaní právnych asistentov"


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    _require_loopback_e2e_postgres("DB_CLOUD")
    _require_loopback_e2e_postgres("LAWS_DB_CLOUD")
    if os.getenv("DB_OPTION", "").strip().lower() != "postgres":
        raise RuntimeError("Issue #713 E2E requires DB_OPTION=postgres")
    if os.getenv("LAWS_DB_BACKEND", "").strip().lower() != "postgres":
        raise RuntimeError("Issue #713 E2E requires LAWS_DB_BACKEND=postgres")

    _seed_synthetic_latest_law(os.environ["LAWS_DB_CLOUD"])
    store = ApiDatabaseStore.from_env()
    store.initialize()
    users = provision_e2e_test_users(
        store=store,
        password=os.getenv("JURISDIGTA_E2E_TEST_USER_PASSWORD", "").strip(),
    )
    user = next(item for item in users if item.email == E2E_TEST_PAID_EMAIL)
    for prior in store.list_cases(user_id=user.user_id):
        if prior.title.startswith("[issue-713-latest-law-"):
            store.soft_delete_case(case_id=prior.case_id, user_id=user.user_id)

    run_id = f"issue-713-latest-law-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    case = store.create_case(
        user_id=user.user_id,
        company_id=None,
        title=f"[{run_id}] Syntetický existujúci prípad",
    )
    route = get_routed_llm_client(
        store=store,
        user_id=user.user_id,
        user_email=user.email,
        task_type="chat_reply",
    )
    if route.provider == "mock" or route.route_type == "mock":
        raise RuntimeError("Real Azure Foundry route is required; mock is prohibited")

    evidence_root = REPO_ROOT / "runs" / "e2e" / "issue-713-latest-law" / run_id
    evidence_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schemaVersion": 1,
        "syntheticOnly": True,
        "runId": run_id,
        "user": {"userId": user.user_id, "email": user.email, "name": "JurisDigta Synthetic E2E"},
        "caseId": case.case_id,
        "caseTitle": case.title,
        "question": "chcem vediet ktory je posledny zakon schvaleny na slovensku a coho sa tyka",
        "expectedProvider": route.provider,
        "expectedModel": route.model,
        "expectedSource": {
            "documentId": SYNTHETIC_DOCUMENT_ID,
            "identifier": SYNTHETIC_IDENTIFIER,
            "title": SYNTHETIC_TITLE,
        },
        "services": ["frontend", "api", "mcp", "postgresql", "azure-foundry"],
        "retention": "Delete ignored evidence within 7 days.",
    }
    manifest_path = evidence_root / "input-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"manifest={manifest_path}")
    print(f"evidence={evidence_root}")
    print(f"provider={route.provider} model={route.model} route_type={route.route_type}")
    return 0


def _require_loopback_e2e_postgres(name: str) -> None:
    parsed = urlsplit(os.getenv(name, "").strip())
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError(f"{name} must use PostgreSQL")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"{name} must target loopback PostgreSQL")
    if "e2e" not in parsed.path.lstrip("/").lower():
        raise RuntimeError(f"{name} must target an isolated E2E database")


def _seed_synthetic_latest_law(connection: str) -> None:
    stored_at = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    with psycopg.connect(connection) as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM law_documents WHERE document_id = %s", (SYNTHETIC_DOCUMENT_ID,))
            cursor.execute(
                """
                INSERT INTO law_documents (
                    document_id, country_code, collection_code, law_year, law_number,
                    official_name, lawyer_title, source_url, publication_date, current_status,
                    first_effective_date, applicable_to, first_stored_at, last_stored_at,
                    last_checked_at, last_download_status, last_download_error,
                    download_attempt_count, created_at, updated_at
                ) VALUES (
                    %s, 'SK', 'ZZ', 2026, 713, %s, %s,
                    'https://static.slov-lex.sk/static/SK/ZZ/2026/713/20260829.html',
                    '2026-08-29', 'published', '2026-08-30',
                    'Syntetický E2E predpis upravuje transparentnosť, auditné záznamy a ľudský dohľad pri testovaní právnych AI asistentov.',
                    %s, %s, %s, 'stored', '', 1, %s, %s
                )
                """,
                (SYNTHETIC_DOCUMENT_ID, SYNTHETIC_TITLE, SYNTHETIC_TITLE, *(stored_at for _ in range(5))),
            )
            cursor.execute(
                """
                INSERT INTO law_versions (
                    version_id, document_id, version_token, effective_from, version_checksum,
                    status, html_checksum, pdf_checksum, html_bytes, pdf_bytes,
                    normalized_json, embedding_vector, stored_at, created_at, updated_at,
                    embedding_model, embedding_dimensions
                ) VALUES (
                    'issue-713-latest-law-v1', %s, 'e2e-v1', '2026-08-30',
                    'issue713checksum', 'active', 'html713', 'pdf713', 256, 0,
                    '{"synthetic": true}', '[0,0,0,0,0,0,0,0]', %s, %s, %s,
                    'deterministic-legacy-8d', 8
                )
                """,
                (SYNTHETIC_DOCUMENT_ID, stored_at, stored_at, stored_at),
            )
            cursor.execute(
                """
                INSERT INTO law_metadata (
                    law_metadata_id, document_id, version_id, law_identifier_text,
                    title, law_type, approval_date, publication_date, effective_from,
                    author, issue_reference, legal_areas_json, metadata_json,
                    created_at, updated_at
                ) VALUES (
                    'issue-713-metadata-v1', %s, 'issue-713-latest-law-v1', %s,
                    %s, 'synthetic_e2e', '2026-08-28', '2026-08-29', '2026-08-30',
                    'Syntetický zákonodarca', 'issue-713', '["AI governance"]',
                    '{"synthetic": true}', %s, %s
                )
                """,
                (SYNTHETIC_DOCUMENT_ID, SYNTHETIC_IDENTIFIER, SYNTHETIC_TITLE, stored_at, stored_at),
            )
            cursor.execute(
                """
                INSERT INTO law_provisions (
                    provision_id, version_id, anchor, heading, body_text, ordinal, created_at
                ) VALUES (
                    'issue-713-provision-1', 'issue-713-latest-law-v1', '§ 1',
                    'Predmet syntetickej úpravy',
                    'Syntetický E2E právny zdroj upravuje transparentné testovanie právnych AI asistentov, auditné záznamy a povinný ľudský dohľad. Nejde o produkčný právny obsah.',
                    1, %s
                )
                """,
                (stored_at,),
            )
        conn.commit()


if __name__ == "__main__":
    raise SystemExit(main())
