"""Verify real persisted IT results from a case created through the local frontend."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
import httpx

from aijurisdictionagents.api_db import ApiDatabaseStore

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/e2e/issue909"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fallback", action="store_true", help="Request an unavailable profile using the real API")
    parser.add_argument("--finalize", action="store_true", help="Require screenshots and write sanitized result manifest")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    os.environ.update(DB_OPTION="postgres", DB_CLOUD="postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction_e2e_909",
                      STORAGE_OPTION="local", STORE_LOCAL=str(ROOT / "runs/storage/issue909/files"))
    inputs = json.loads((OUTPUT / "input-manifest.json").read_text(encoding="utf-8"))
    store = ApiDatabaseStore.from_env()
    user_id = inputs["synthetic_user_id"]
    cases = [case for case in store.list_cases(user_id=user_id) if case.title.startswith("issue909 synthetic")]
    if not cases:
        raise RuntimeError("Create the synthetic case in the real frontend first")
    case = cases[0]
    assessments = [item for item in store.list_software_assessments(case_id=case.case_id) if item.get("kind") == "organizational_it"]
    completed = [item for item in assessments if item.get("model_called")]
    if not completed:
        raise RuntimeError("No real frontend assessment was completed")
    value = completed[0]
    assert value["provider"] == "azure_foundry" and value["model"] == "gpt-4o-mini"
    assert value["graph"] == "organizational_it_assessment@1" and value["output"]["actions"]
    observed = {item["original_document_id"] for item in value["sources"]}
    assert set(inputs["expected_source_ids"]) <= observed
    assert any("ISSUE909_SECURITY_MARKER" in basis["excerpt"] for action in value["output"]["actions"] for basis in action["legal_basis"])
    assert not value["drafts"]
    if args.fallback:
        device = "issue909-synthetic-verifier"
        headers = {"x-api-key": "aijuris", "x-jurisdigta-device-id": device,
                   "x-jurisdigta-device-token": store.issue_device_auth_token(user_id=user_id, device_id=device)}
        with httpx.Client(timeout=240, headers=headers) as client:
            response = client.post(f"http://127.0.0.1:8199/v1/cases/{case.case_id}/it-assessments", params={"user_id": user_id},
                json={"request_id": str(uuid4()), "facts": value["facts"], "external_acknowledged": True,
                      "selected_model_profile_id": "issue909-model-does-not-exist"})
        response.raise_for_status()
        fallback = response.json()
        assert fallback["provider"] == "azure_foundry" and fallback["model"] == "gpt-4o-mini"
        assert "default real model" in fallback["fallback_reason"]
        (OUTPUT / "fallback-check.json").write_text(json.dumps({
            "assessment_id": fallback["assessment_id"], "provider": fallback["provider"], "model": fallback["model"],
            "disclosure": fallback["fallback_reason"], "created_at": fallback["created_at"],
        }, indent=2), encoding="utf-8")
        print("Unavailable profile fallback: actual Azure Foundry route and disclosure verified; select latest history entry in frontend.")
    if args.finalize:
        assert inputs["direct_mcp_checked"]
        assert all((OUTPUT / filename).exists() for filename in ("final-state.jpg", "cz-boundary.jpg", "fallback-state.jpg"))
        boundary = [item for item in assessments if "CZ" in item.get("facts", {}).get("it_context", {}).get("countries", [])]
        assert boundary and not boundary[0]["model_called"]
        fallback = json.loads((OUTPUT / "fallback-check.json").read_text(encoding="utf-8"))
        manifest = dict(inputs, actual_provider=value["provider"], actual_model=value["model"],
            observed_source_ids=sorted(observed), synthetic_case_id=case.case_id,
            assessment_id=value["assessment_id"], graph=value["graph"], frontend_case_created=True,
            mock_used=False, screenshot="final-state.jpg", jurisdiction_screenshot="cz-boundary.jpg",
            fallback_screenshot="fallback-state.jpg", document_screenshot="document-recommendations.jpg",
            unavailable_model_fallback=fallback, checked_at=datetime.now(timezone.utc).isoformat(),
            scope="Synthetic integration acceptance; substantive legal correctness still requires human review")
        (OUTPUT / "result-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Real-provider result, seeded citations and recommendation-only output verified.")


if __name__ == "__main__":
    main()
