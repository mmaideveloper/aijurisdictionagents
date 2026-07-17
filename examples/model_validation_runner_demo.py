"""Offline minimal demo for validating a JurisDigta golden-case fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aijurisdictionagents.golden_cases import compare_text, load_golden_case, validate_model_audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("tests/modelsTesting/cases/issue-513-loan-confirmation-case-export.zip"),
    )
    args = parser.parse_args()
    golden = load_golden_case(args.fixture)
    model_validation = validate_model_audit(golden)
    answer_result = compare_text(
        golden.expected_answer,
        golden.expected_answer,
        required=("Potvrdenie o pozicke", "AI navrh pred pouzitim skontrolujte clovekom"),
        forbidden=("CASE_UPDATE_JSON",),
        similarity_min=0.82,
    )
    report = {
        "case_key": golden.case_key,
        "prompt_count": len(golden.prompts),
        "document_count": len(golden.expected_documents),
        "model_audit_count": len(golden.model_audit),
        "automation_ready": model_validation.automation_ready,
        "model_audit_errors": model_validation.errors,
        "warnings": list(golden.warnings),
        "answer": {
            "passed": answer_result.passed,
            "similarity": answer_result.similarity,
            "missing_required": answer_result.missing_required,
            "present_forbidden": answer_result.present_forbidden,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not answer_result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
