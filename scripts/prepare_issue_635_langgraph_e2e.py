"""Prepare a synthetic PostgreSQL case and sanitized manifest for issue #635 E2E."""

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
from aijurisdictionagents.api_db.e2e_test_users import (
    E2E_TEST_PAID_EMAIL,
    provision_e2e_test_users,
)
from aijurisdictionagents.llm.routing import get_routed_llm_client

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_LAW_ID = "issue-635-civil-code"


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    connection = os.getenv("DB_CLOUD", "").strip()
    parsed = urlsplit(connection)
    if os.getenv("DB_OPTION", "").strip().lower() != "postgres":
        raise RuntimeError("Issue #635 final E2E requires DB_OPTION=postgres")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Issue #635 final E2E requires loopback PostgreSQL")
    _seed_synthetic_law()
    password = os.getenv("JURISDIGTA_E2E_TEST_USER_PASSWORD", "").strip()
    store = ApiDatabaseStore.from_env()
    store.initialize()
    users = provision_e2e_test_users(store=store, password=password)
    user = next(item for item in users if item.email == E2E_TEST_PAID_EMAIL)
    for prior in store.list_cases(user_id=user.user_id):
        if prior.title.startswith("[issue-635-langgraph-"):
            store.soft_delete_case(case_id=prior.case_id, user_id=user.user_id)
    run_id = f"issue-635-langgraph-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    case = store.create_case(
        user_id=user.user_id,
        company_id=None,
        title=f"[{run_id}] Potvrdenie o zaplatení pôžičky",
    )
    route = get_routed_llm_client(
        store=store,
        user_id=user.user_id,
        user_email=user.email,
        task_type="document_drafting",
    )
    if route.provider == "mock" or route.route_type == "mock":
        raise RuntimeError("Real Azure Foundry model route is required; mock is prohibited")
    evidence_root = REPO_ROOT / "runs" / "e2e" / "issue-635-langgraph" / run_id
    evidence_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "syntheticOnly": True,
        "runId": run_id,
        "user": {
            "userId": user.user_id,
            "email": user.email,
            "name": "JurisDigta Synthetic LangGraph E2E",
        },
        "caseId": case.case_id,
        "caseTitle": case.title,
        "expectedProvider": route.provider,
        "expectedModel": route.model,
        "database": "loopback-postgresql",
    }
    manifest_path = evidence_root / "input-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"manifest={manifest_path}")
    print(f"evidence={evidence_root}")
    print(f"provider={route.provider} model={route.model} route_type={route.route_type}")
    return 0


def _seed_synthetic_law() -> None:
    connection = os.getenv("LAWS_DB_CLOUD", "").strip()
    parsed = urlsplit(connection)
    database_name = parsed.path.lstrip("/").lower()
    if os.getenv("LAWS_DB_BACKEND", "").strip().lower() != "postgres":
        raise RuntimeError("Issue #635 final E2E requires LAWS_DB_BACKEND=postgres")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or "e2e" not in database_name:
        raise RuntimeError("Synthetic law seeding requires a loopback E2E PostgreSQL database")
    stored_at = datetime(2026, 8, 26, 18, 36, 22, tzinfo=timezone.utc)
    with psycopg.connect(connection) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO law_documents (
                    document_id, country_code, collection_code, law_year, law_number,
                    official_name, lawyer_title, source_url, publication_date, current_status,
                    first_effective_date, applicable_to, first_stored_at, last_stored_at,
                    last_checked_at, last_download_status, last_download_error,
                    download_attempt_count, created_at, updated_at
                ) VALUES (
                    %s, 'SK', 'ZZ', 1964, 40,
                    'Syntetický výrez Občianskeho zákonníka pre E2E',
                    'Občiansky zákonník – pôžička a potvrdenie splnenia dlhu',
                    'https://static.slov-lex.sk/static/SK/ZZ/1964/40/20240701.html',
                    '1964-03-05', 'published', '1964-04-01', 'synthetic E2E only',
                    %s, %s, %s, 'stored', '', 1, %s, %s
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    lawyer_title = EXCLUDED.lawyer_title,
                    last_checked_at = EXCLUDED.last_checked_at,
                    updated_at = EXCLUDED.updated_at
                """,
                (SYNTHETIC_LAW_ID, *(stored_at for _ in range(5))),
            )
            cursor.execute(
                """
                INSERT INTO law_versions (
                    version_id, document_id, version_token, effective_from, version_checksum,
                    status, html_checksum, pdf_checksum, html_bytes, pdf_bytes,
                    normalized_json, embedding_vector, stored_at, created_at, updated_at,
                    embedding_model, embedding_dimensions
                ) VALUES (
                    'issue-635-civil-code-v1', %s, 'e2e-v1', '2024-07-01',
                    'issue635checksum', 'active', 'html635', 'pdf635', 256, 0,
                    '{"synthetic": true}', '[0,0,0,0,0,0,0,0]', %s, %s, %s,
                    'deterministic-legacy-8d', 8
                )
                ON CONFLICT (version_id) DO UPDATE SET updated_at = EXCLUDED.updated_at
                """,
                (SYNTHETIC_LAW_ID, stored_at, stored_at, stored_at),
            )
            cursor.execute(
                """
                INSERT INTO law_provisions (
                    provision_id, version_id, anchor, heading, body_text, ordinal, created_at
                ) VALUES (
                    'issue-635-provision-569', 'issue-635-civil-code-v1', '§ 569',
                    'Potvrdenie o splnení dlhu',
                    'Syntetický E2E právny zdroj: veriteľ je povinný na požiadanie vydať '
                    'dlžníkovi písomné potvrdenie, že dlh bol úplne alebo čiastočne splnený. '
                    'Dokument musí byť pred použitím ľudsky skontrolovaný. Tento text nie je '
                    'produkčný právny obsah. Občiansky zákonník pôžička splnenie dlhu '
                    'potvrdenie o zaplatení.',
                    1, %s
                )
                ON CONFLICT (provision_id) DO UPDATE SET body_text = EXCLUDED.body_text
                """,
                (stored_at,),
            )
        conn.commit()


if __name__ == "__main__":
    raise SystemExit(main())
