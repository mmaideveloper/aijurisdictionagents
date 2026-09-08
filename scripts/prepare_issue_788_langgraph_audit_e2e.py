"""Prepare synthetic identities and case data for issue #788 real E2E."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from dotenv import load_dotenv

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import (
    E2E_TEST_PAID_EMAIL,
    provision_e2e_test_users,
)
from aijurisdictionagents.llm.routing import get_routed_llm_client
from prepare_issue_635_langgraph_e2e import _seed_synthetic_law


REPO_ROOT = Path(__file__).resolve().parents[1]
ADMIN_EMAIL = "issue-788-admin@jurisdigta.eu"


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    parsed = urlsplit(os.getenv("DB_CLOUD", "").strip())
    if os.getenv("DB_OPTION", "").strip().lower() != "postgres":
        raise RuntimeError("Issue #788 final E2E requires DB_OPTION=postgres")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Issue #788 final E2E requires loopback PostgreSQL")
    _seed_synthetic_law()
    password = os.getenv("JURISDIGTA_E2E_TEST_USER_PASSWORD", "").strip()
    store = ApiDatabaseStore.from_env()
    store.initialize()
    users = provision_e2e_test_users(store=store, password=password)
    workflow_user = next(item for item in users if item.email == E2E_TEST_PAID_EMAIL)
    admin = store.find_user_by_email(email=ADMIN_EMAIL)
    if admin is None:
        admin = store.create_user(
            email=ADMIN_EMAIL,
            password=password,
            full_name="JurisDigta Synthetic LangGraph Audit Admin",
        )
    store.update_admin_user(user_id=admin.user_id, role="admin", is_enabled=True)
    for prior in store.list_cases(user_id=workflow_user.user_id):
        if prior.title.startswith("[issue-788-langgraph-audit-"):
            store.soft_delete_case(case_id=prior.case_id, user_id=workflow_user.user_id)
    run_id = (
        "issue-788-langgraph-audit-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    )
    case = store.create_case(
        user_id=workflow_user.user_id,
        company_id=None,
        title=f"[{run_id}] Auditable LangGraph",
    )
    route = get_routed_llm_client(
        store=store,
        user_id=workflow_user.user_id,
        user_email=workflow_user.email,
        task_type="document_drafting",
    )
    if route.provider == "mock" or route.route_type == "mock":
        raise RuntimeError("Real Azure Foundry model route is required; mock is prohibited")
    evidence_root = REPO_ROOT / "runs" / "e2e" / "issue-788-langgraph-audit" / run_id
    evidence_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "syntheticOnly": True,
        "runId": run_id,
        "correlationId": f"corr-{run_id}",
        "sessionId": f"session-{run_id}",
        "workflowUser": {
            "userId": workflow_user.user_id,
            "email": workflow_user.email,
        },
        "adminUser": {
            "userId": admin.user_id,
            "email": admin.email,
            "name": "JurisDigta Synthetic LangGraph Audit Admin",
            "role": "admin",
            "isEnabled": True,
        },
        "caseId": case.case_id,
        "expectedProvider": route.provider,
        "expectedModel": route.model,
        "database": "loopback-postgresql",
    }
    manifest_path = evidence_root / "input-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"manifest={manifest_path}")
    print(f"evidence={evidence_root}")
    print(f"provider={route.provider} model={route.model} route_type={route.route_type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
