"""Prepare isolated PostgreSQL data for the issue #810 real local E2E."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from uuid import uuid4

from dotenv import load_dotenv
import psycopg

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import E2E_TEST_PAID_EMAIL, provision_e2e_test_users
from aijurisdictionagents.llm.routing import get_routed_llm_client

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_DOCUMENT_ID = "issue-810-legal-explanation"
SYNTHETIC_IDENTIFIER = "810/2026 Z. z."
SYNTHETIC_TITLE = "Syntetický test: odsúdený s náramkom, práca a obchod"
SYNTHETIC_CONTENT = (
    "§ 1 Syntetický scenár elektronického monitoringu odsúdeného s náramkom. "
    "Práca aj cesta do práce v tomto testovacom scenári vyžadujú individuálne povolený režim. "
    "Nákup v obchode nie je automaticky povolený; rozhodujú podmienky režimu. "
    "Kontrolná značka zdroja je EXPLANATION810. Nejde o skutočný právny predpis ani právne poradenstvo. "
    "Tento testovací obsah musí pred použitím v reálnej veci overiť človek."
)


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    os.environ.update({"DB_OPTION": "postgres", "DB_CLOUD": "postgresql://postgres:postgres@127.0.0.1:55410/issue810_api",
                       "LAWS_DB_BACKEND": "postgres", "LAWS_DB_CLOUD": "postgresql://postgres:postgres@127.0.0.1:55410/issue810_laws"})
    _require_loopback_e2e_postgres("DB_CLOUD")
    _require_loopback_e2e_postgres("LAWS_DB_CLOUD")
    if os.getenv("DB_OPTION", "").strip().lower() != "postgres":
        raise RuntimeError("Issue #810 E2E requires DB_OPTION=postgres")
    if os.getenv("LAWS_DB_BACKEND", "").strip().lower() != "postgres":
        raise RuntimeError("Issue #810 E2E requires LAWS_DB_BACKEND=postgres")

    import sys
    if "--cleanup" in sys.argv:
        store = ApiDatabaseStore.from_env()
        user = store.find_user_by_email(email=E2E_TEST_PAID_EMAIL)
        if user is not None:
            for case in store.list_cases(user_id=user.user_id):
                if case.title.startswith("[issue-810-legal-explanation-"):
                    store.soft_delete_case(case_id=case.case_id, user_id=user.user_id)
            store.update_user(
                user_id=user.user_id, phone_number=user.phone_number, first_name=user.first_name,
                last_name=user.last_name, address=user.address, city=user.city, country=user.country,
                zip_code=user.zip_code, tax_number=user.tax_number, identity_card_number=user.identity_card_number,
                date_of_birth=user.date_of_birth, social_security_number=user.social_security_number,
                password=secrets.token_urlsafe(32),
            )
        with psycopg.connect(os.environ["LAWS_DB_CLOUD"]) as conn:
            conn.execute((REPO_ROOT / "databases/laws-collector/seeds/issue810/01_seed.sql").read_text(encoding="utf-8"), (SYNTHETIC_DOCUMENT_ID,))
        for filename in ("issue810-login.json", "issue810-otp.json", "issue810-login-result.txt", "issue810-otp-result.txt"):
            (REPO_ROOT / "runs/storage" / filename).unlink(missing_ok=True)
        print("Task cases soft-deleted, synthetic source removed, local test password rotated, login material removed.")
        return 0
    if "--login-material" in sys.argv:
        private = REPO_ROOT / "runs/storage/issue810-login.json"
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_text(json.dumps({"email": E2E_TEST_PAID_EMAIL,
                                      "password": os.environ["JURISDIGTA_E2E_TEST_USER_PASSWORD"]}), encoding="utf-8")
        print("Synthetic login material ready; values redacted.")
        return 0
    if "--otp" in sys.argv:
        import re
        with psycopg.connect(os.environ["DB_CLOUD"]) as conn:
            row = conn.execute("SELECT body FROM email_outbox WHERE recipient=%s ORDER BY created_at DESC LIMIT 1", (E2E_TEST_PAID_EMAIL,)).fetchone()
        if not row or not (match := re.search(r"login code is: (\d+)", row[0])):
            raise RuntimeError("Synthetic login verification is unavailable in local PostgreSQL")
        private = REPO_ROOT / "runs/storage/issue810-otp.json"
        private.write_text(json.dumps({"otp": match[1]}), encoding="utf-8")
        print("Synthetic verification ready; value redacted.")
        return 0
    _seed_synthetic_latest_law(os.environ["LAWS_DB_CLOUD"])
    store = ApiDatabaseStore.from_env()
    store.initialize()
    users = provision_e2e_test_users(
        store=store,
        password=os.getenv("JURISDIGTA_E2E_TEST_USER_PASSWORD", "").strip(),
    )
    user = next(item for item in users if item.email == E2E_TEST_PAID_EMAIL)
    # Match the production profile explicitly; acceptance must never pass on fallback.
    required_model = "gpt-5-mini"
    for task_type in ("default", "chat_reply"):
        store.upsert_ai_task_route_policy(
            policy_id=f"issue810:{task_type}:case", task_type=task_type, plan_code="case",
            preferred_external_model_profile_id="azurefoundryeu:gpt-5-mini",
            allow_external=True, require_external_ack=False, require_eu_data_zone=True,
            fallback_local_on_error=False, fallback_local_on_budget=False,
            priority=10000, enabled=True,
        )
    for prior in store.list_cases(user_id=user.user_id):
        if prior.title.startswith("[issue-810-legal-explanation-"):
            store.soft_delete_case(case_id=prior.case_id, user_id=user.user_id)

    run_id = f"issue-810-legal-explanation-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    route = get_routed_llm_client(
        store=store,
        user_id=user.user_id,
        user_email=user.email,
        task_type="chat_reply",
    )
    if route.provider == "mock" or route.route_type == "mock":
        raise RuntimeError("Real Azure Foundry route is required; mock is prohibited")
    if route.model != required_model or route.provider != "azurefoundryeu":
        raise RuntimeError("Production-model comparison requires azurefoundryeu / gpt-5-mini exactly")

    evidence_root = REPO_ROOT / "runs" / "e2e" / "issue-810-legal-explanation" / run_id
    evidence_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schemaVersion": 1,
        "syntheticOnly": True,
        "runId": run_id,
        "user": {"userId": user.user_id, "email": user.email, "name": "JurisDigta Synthetic E2E"},
        "question": "Vysvetli možnosti pre odsúdeného s náramkom, podmienky, môže ísť do práce? Do obchodu?",
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
    if parsed.port != 55410 or parsed.path not in {"/issue810_api", "/issue810_laws"}:
        raise RuntimeError(f"{name} must target an isolated E2E database")


def _seed_synthetic_latest_law(connection: str) -> None:
    stored_at = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    with psycopg.connect(connection) as conn:
        with conn.cursor() as cursor:
            cursor.execute((REPO_ROOT / "databases/laws-collector/seeds/issue810/01_seed.sql").read_text(encoding="utf-8"), (SYNTHETIC_DOCUMENT_ID,))
            cursor.execute(
                (REPO_ROOT / "databases/laws-collector/seeds/issue810/02_seed.sql").read_text(encoding="utf-8"),
                (SYNTHETIC_DOCUMENT_ID, SYNTHETIC_TITLE, SYNTHETIC_TITLE, *(stored_at for _ in range(5))),
            )
            cursor.execute(
                (REPO_ROOT / "databases/laws-collector/seeds/issue810/03_seed.sql").read_text(encoding="utf-8"),
                (SYNTHETIC_DOCUMENT_ID, stored_at, stored_at, stored_at),
            )
            cursor.execute(
                (REPO_ROOT / "databases/laws-collector/seeds/issue810/04_seed.sql").read_text(encoding="utf-8"),
                (SYNTHETIC_DOCUMENT_ID, SYNTHETIC_IDENTIFIER, SYNTHETIC_TITLE, stored_at, stored_at),
            )
            cursor.execute(
                (REPO_ROOT / "databases/laws-collector/seeds/issue810/05_seed.sql").read_text(encoding="utf-8"),
                (
                    SYNTHETIC_DOCUMENT_ID,
                    SYNTHETIC_CONTENT,
                    len(SYNTHETIC_CONTENT.encode("utf-8")),
                    stored_at,
                    stored_at,
                ),
            )
            cursor.execute(
                (REPO_ROOT / "databases/laws-collector/seeds/issue810/06_seed.sql").read_text(encoding="utf-8"),
                (SYNTHETIC_CONTENT, stored_at),
            )
        conn.commit()


if __name__ == "__main__":
    raise SystemExit(main())
