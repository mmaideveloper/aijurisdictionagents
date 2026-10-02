"""Seed isolated synthetic accounts and a public-law snapshot for real #746 acceptance."""
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from dotenv import load_dotenv
import psycopg

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import E2E_TEST_PAID_EMAIL, provision_e2e_test_users
from aijurisdictionagents.db_migrations import apply_sql_migrations

ROOT = Path(__file__).resolve().parents[1]
API_DB = "postgresql://postgres:postgres@127.0.0.1:55446/issue746_api"
LAWS_DB = "postgresql://postgres:postgres@127.0.0.1:55446/issue746_laws"
SOURCE_ID = "issue-746-public-law"
QUESTION = "Ake skupiny zbrani definuje zakon, strucne popis?"


class Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def plain(html: str) -> str:
    parser = Text()
    parser.feed(html)
    return "\n".join(parser.parts)


def main() -> None:
    load_dotenv(ROOT / ".env")
    os.environ.update(DB_OPTION="postgres", DB_CLOUD=API_DB, STORAGE_OPTION="local",
                      STORE_LOCAL=str(ROOT / "runs/storage/issue746/files"))
    apply_sql_migrations(project="laws", db_option="azure", target=LAWS_DB)
    now = datetime.now(timezone.utc)
    html_path = ROOT / "runs/e2e/issue746/law.html"
    html = html_path.read_text(encoding="utf-8-sig")
    # Public source only; no production account or case records are imported.
    text = plain(html)
    sql_root = ROOT / "databases/laws-collector/seeds/issue746"
    title = "Zákon o strelných zbraniach a strelive"
    with psycopg.connect(LAWS_DB) as conn:
        for filename, parameters in (
            ("01_seed.sql", (SOURCE_ID,)),
            ("02_seed.sql", (SOURCE_ID, title, title, now, now, now, now, now)),
            ("03_seed.sql", (SOURCE_ID, now, now, now)),
            ("04_seed.sql", (SOURCE_ID, "190/2003 Z. z.", title, now, now)),
            ("05_seed.sql", (SOURCE_ID, text, len(text.encode()), now, now)),
        ):
            conn.execute((sql_root / filename).read_text(encoding="utf-8-sig"), parameters)
        starts = list(re.finditer(r'<div[^>]+id="paragraf-(\d+)"', html))
        seeded_sections = []
        for index, match in enumerate(starts):
            number = int(match.group(1))
            end = starts[index + 1].start() if index + 1 < len(starts) else len(html)
            body = plain(html[match.start():end])
            heading = next((line for line in body.splitlines() if "kategórie" in line), f"§ {number}")
            conn.execute((sql_root / "06_seed.sql").read_text(encoding="utf-8-sig"),
                         (f"issue746-section-{number}", f"paragraf-{number}", heading, body, number, now))
            seeded_sections.append(number)
        assert {4, 5, 6, 7}.issubset(seeded_sections)
    store = ApiDatabaseStore.from_env()
    store.initialize()
    users = provision_e2e_test_users(store=store, password=os.environ["JURISDIGTA_E2E_TEST_USER_PASSWORD"])
    user = next(item for item in users if item.email == E2E_TEST_PAID_EMAIL)
    for task_type in ("default", "chat_reply"):
        store.upsert_ai_task_route_policy(
            policy_id=f"issue746:{task_type}", task_type=task_type, plan_code="case",
            preferred_external_model_profile_id="azurefoundryeu:gpt-5-mini",
            allow_external=True, require_external_ack=False, require_eu_data_zone=True,
            fallback_local_on_error=False, fallback_local_on_budget=False, priority=10000, enabled=True,
        )
    run_id = f"issue746-{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:6]}"
    output = ROOT / "runs/e2e/issue746"
    (output / "input-manifest.json").write_text(json.dumps({
        "runId": run_id, "userId": user.user_id, "email": user.email, "question": QUESTION,
        "sourceId": SOURCE_ID, "law": "190/2003 Z. z.", "sections": [4, 5, 6, 7],
        "publicSource": "https://static.slov-lex.sk/static/SK/ZZ/2003/190/20250701.print.html",
        "sourceSha256": hashlib.sha256(html_path.read_bytes()).hexdigest(),
        "retention": "Delete evidence within seven days; synthetic accounts/cases only, public legal source.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepared {run_id}; law 190/2003 with {len(seeded_sections)} sections; credentials redacted.")


if __name__ == "__main__":
    main()
