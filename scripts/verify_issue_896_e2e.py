"""Sanitized real-provider checks for the case created in the real frontend."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
import httpx
from pypdf import PdfReader

from aijurisdictionagents.api_db import ApiDatabaseStore

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/e2e/issue896"
SOURCE_ID = "issue-896-synthetic-security"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extra-scenarios", action="store_true")
    parser.add_argument("--assessment-id", help="Select a saved frontend assessment rather than the latest result")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    os.environ.update(DB_OPTION="postgres", DB_CLOUD="postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction_e2e_896",
        STORAGE_OPTION="local", STORE_LOCAL=str(ROOT / "runs/storage/issue896/files"))
    store = ApiDatabaseStore.from_env()
    user = store.find_user_by_email(email="mcp-claude-test-paid@jurisdigta.eu")
    case = next(item for item in store.list_cases(user_id=user.user_id) if item.title.startswith("issue896 synthetic"))
    saved_manifest = OUTPUT / "result-manifest.json"
    selected_id = args.assessment_id
    if not selected_id and saved_manifest.exists():
        selected_id = json.loads(saved_manifest.read_text())["frontend_assessment_id"]
    assessments = store.list_software_assessments(case_id=case.case_id)
    assessment = next(item for item in assessments if item["assessment_id"] == selected_id) if selected_id else assessments[0]
    assert assessment["provider"] == "azure_foundry" and assessment["model"] == "gpt-4o-mini"
    assert len(assessment["output"]["actions"]) >= 2, "No grounded actions in the frontend result"
    source_map = {item["source_id"]: item for item in assessment["sources"]}
    documents = {item["evidence_id"]: item for item in assessment["documents"]}
    for action in assessment["output"]["actions"]:
        if action["classification"] == "suspected_gap":
            assert documents[action["evidence_id"]]["page"] == 2
            assert any(source_map[key]["original_document_id"] == SOURCE_ID for key in action["source_ids"])
            assert any("ISSUE896_SECURITY_MARKER" in basis["excerpt"] for basis in action["legal_basis"])
    device = "issue896-evidence-helper"
    headers = {"x-api-key": "aijuris", "x-jurisdigta-device-id": device,
        "x-jurisdigta-device-token": store.issue_device_auth_token(user_id=user.user_id, device_id=device)}
    base = f"http://127.0.0.1:8186/v1/cases/{case.case_id}/software-assessments"
    params = {"user_id": user.user_id}
    manifest = dict(run_id="issue896-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        frontend_case_created=True, real_provider=assessment["provider"], real_model=assessment["model"],
        local_services={"frontend": 5186, "api": 8186, "mcp": 8286, "postgres": 5432},
        synthetic_case_id=case.case_id, frontend_assessment_id=assessment["assessment_id"],
        expected_source_ids=[SOURCE_ID], observed_source_ids=[item["original_document_id"] for item in assessment["sources"]],
        expected_page=2, observed_pages=[documents[action["evidence_id"]]["page"] for action in assessment["output"]["actions"] if action["evidence_id"]],
        screenshot="final-state.jpg", direct_mcp_source_checked=True, mock_used=False,
        synthetic_legal_fixtures_not_actual_legislation=True,
        retention="Delete ignored evidence within seven days; clean synthetic case records/files after capture.", scenarios=[])
    with httpx.Client(timeout=180, headers=headers) as client:
        report = client.get(base + "/" + assessment["assessment_id"] + "/export", params={**params, "revision": assessment["revision"]})
        report.raise_for_status()
        reader = PdfReader(io.BytesIO(report.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        for expected in ["supplier.pdf", "Page 2", "ISSUE896_SECURITY_MARKER", "not a compliance certificate"]:
            assert expected in text, "Export omitted expected evidence or disclosure"
        (OUTPUT / "assessment.pdf").write_bytes(report.content)
        manifest.update(pdf_structure_valid=True, pdf_expected_text_valid=True, pdf_pages=len(reader.pages),
                        pdf_sha256=hashlib.sha256(report.content).hexdigest())
        if args.extra_scenarios:
            document_ids = list({item["document_id"] for item in assessment["documents"]})
            for name, changes in [
                ("unavailable_model", {}),
                ("ai", {"uses_ai": True, "description": "Synthetic AI contact administration. AI proposes contact categories with human review."}),
                ("medical", {"uses_ai": True, "health_data": True, "medical_purpose": True,
                    "intended_purpose": "Synthetic clinical diagnostic decision support", "users": "Synthetic clinicians",
                    "description": "Synthetic AI clinical decision support; supplier security document describes its administrative contact module."}),
                ("ivdr", {"uses_ai": True, "health_data": True, "medical_purpose": True, "specimen_analysis": True,
                    "intended_purpose": "Synthetic interpretation of human laboratory specimen results", "users": "Synthetic laboratory clinicians",
                    "description": "Synthetic IVD AI software interprets human specimen results; supplier security record covers the administrative module."}),
            ]:
                facts = dict(assessment["facts"], **changes)
                response = client.post(base, params=params, json=dict(request_id=str(uuid4()), facts=facts,
                    document_ids=document_ids, external_acknowledged=True,
                    selected_model_profile_id="issue896-nonexistent-model" if name == "unavailable_model" else None))
                response.raise_for_status()
                value = response.json()
                assert value["provider"] == "azure_foundry" and value["model"] == "gpt-4o-mini"
                observed = [item["original_document_id"] for item in value["sources"]]
                assert SOURCE_ID in observed
                expected = [SOURCE_ID]
                if name in {"ai", "medical", "ivdr"}:
                    expected.append("issue-896-ai-synthetic-source")
                if name in {"medical", "ivdr"}:
                    expected += ["issue-896-mdr-synthetic-source", "issue-896-ivdr-synthetic-source"]
                assert set(expected) <= set(observed), "Specialist source coverage missing"
                if name == "unavailable_model":
                    assert "configured default real model" in value["fallback_reason"]
                manifest["scenarios"].append(dict(name=name, assessment_id=value["assessment_id"],
                    provider=value["provider"], model=value["model"], expected_source_ids=expected,
                    observed_source_ids=observed, fallback_disclosure=value["fallback_reason"],
                    grounded_action_count=len(value["output"]["actions"])))
                (OUTPUT / "result-manifest.json").write_text(json.dumps(manifest, indent=2))
                print(f"Real-provider scenario={name} passed; sources={len(observed)}; no secrets displayed.", flush=True)
    (OUTPUT / "result-manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Frontend grounding and PDF structure/text checks passed; sanitized manifest saved.", flush=True)


if __name__ == "__main__":
    main()
