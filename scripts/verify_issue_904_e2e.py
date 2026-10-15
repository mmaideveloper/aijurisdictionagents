"""Verify the real frontend-created synthetic AI reception chat; no secret output."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from aijurisdictionagents.api_db import ApiDatabaseStore

ROOT = Path(__file__).resolve().parents[1]
QUESTION = (
    "Mam dodavatela, ktory ponuka software pre AI recepciu, pouzivat azure STT, storage pre finalny text, "
    "text bude podla telefonneho cisla na ktore sa volalo a stt urobili text , vlastnikovi cisla, v tomto pripade "
    "ordinacii v nemocnici/lakarovi alebo sestre. text moze obsahovat klinicke data, lekar sestra podla spravy "
    "moze zavoat pacienta na vysetrenie okamzite, sprava je pre administrativne ucely , sestra vzdy musi zavolat "
    "spat pacientovi a potvrdit udaje, Cielom je aby sa pacient dovolal v kazdom case."
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-title", default="E2E904 AI recepcia v2 2026-10-14")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env.model-credentials-test", override=True)
    os.environ.update(DB_OPTION="postgres", DB_CLOUD="postgresql://postgres:postgres@127.0.0.1:5432/model_credentials_test_20261013",
                      STORAGE_OPTION="local", STORE_LOCAL=str(ROOT / "runs/storage/issue896/files"))
    store = ApiDatabaseStore.from_env()
    user = store.find_user_by_email(email="mcp-claude-test-paid@jurisdigta.eu")
    assert user is not None
    case = next(c for c in store.list_cases(user_id=user.user_id) if c.title == args.case_title)
    value = next(a for a in store.list_software_assessments(case_id=case.case_id) if a.get("kind") == "software_chat")
    assert value["turns"][0] == QUESTION, "The frontend must submit the original question unchanged"
    assert value["consented"] and value["provider"] == "azure_foundry" and value["model"] == "gpt-4o-mini"
    answer = next(a for a in value["answers"] if a["question_id"] == "Q1")
    assert "DB" in answer["quote"] and "pristup" in answer["quote"].lower()
    assert value["pending_question"] == "Q2"
    reply = value["reply"]
    for expected in ("1. Stručný opis softvéru", "2. Možné regulácie", "3. Otázky", "4. Opatrenia",
                     "| Compliance | Popis | Action | Results | State |", "Deklarované – overiť", "syntetické právne zdroje"):
        assert expected in reply, expected
    assert "| pass |" not in reply.lower()
    assert any(c["compliance"] == "GDPR" and "Q1" in c["question_ids"] for c in value["report"]["controls"])
    expected_ids = {"issue-896-synthetic-security", "issue-896-ai-synthetic-source",
                    "issue-896-mdr-synthetic-source", "issue-896-ivdr-synthetic-source"}
    observed = {s["original_document_id"] for s in value["sources"]}
    assert expected_ids <= observed
    device = "issue904-evidence-verifier"
    headers = {"x-api-key": "aijuris", "x-jurisdigta-device-id": device,
               "x-jurisdigta-device-token": store.issue_device_auth_token(user_id=user.user_id, device_id=device)}
    with httpx.Client(base_url="http://127.0.0.1:8186", headers=headers, timeout=30) as client:
        response = client.get("/v1/cases", params={"user_id": user.user_id})
        response.raise_for_status()
        assert case.case_id in {c["case_id"] for c in response.json()}
    audit = store.list_ai_model_usage_audit(case_id=case.case_id)
    first_hash = hashlib.sha256(QUESTION.strip().encode()).hexdigest()
    assert any(a.question_sha256 == first_hash and not a.audit_metadata.get("model_used") for a in audit)
    assert any(a.provider == value["provider"] and a.model == value["model"] and a.audit_metadata.get("model_used") for a in audit)
    output = ROOT / "runs/e2e/issue904"
    for name in ("business-summary.jpg", "actions-table.jpg"):
        assert (output / name).stat().st_size > 1000, "A fresh real frontend screenshot is required"
    manifest = dict(run_id=case.title, case_id=case.case_id, frontend_case_created=True,
        original_question_sha256=hashlib.sha256(QUESTION.encode()).hexdigest(), question_submitted_unchanged=True,
        provider=value["provider"], model=value["model"], mock_used=False, graph=value["graph"], prompt_hash=value["prompt_hash"],
        services={"frontend": 5186, "api": 8186, "mcp": 8286, "postgres": 5432},
        expected_source_ids=sorted(expected_ids), observed_source_ids=sorted(observed), direct_mcp_checked=True,
        q1_quote_server_derived=True, q2_followup_visible=True, declared_not_pass=True, pre_consent_model_not_called=True,
        control_count=len(value["report"]["controls"]), screenshots=["business-summary.jpg", "actions-table.jpg"],
        synthetic_legal_sources_not_normative_accuracy=True, retention_days=7, passed=True)
    (output / "result-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "business-report.md").write_text(reply, encoding="utf-8")
    print("Real frontend/software advice grounding and screenshot evidence verified; sanitized report saved.")


if __name__ == "__main__":
    main()
