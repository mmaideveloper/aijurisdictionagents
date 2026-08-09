from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from reportlab.pdfgen import canvas


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "prepare-golden-test"
    / "scripts"
    / "prepare_golden_test.py"
)


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()


def _pdf_bytes() -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    lines = [
        "Potvrdenie o splateni pozicky",
        "Peter Vzorovy a Jan Testovaci",
        "3 000 EUR je uplne splatena.",
        "Naroky z tejto konkretnej pozicky su vysporiadane.",
        "Podpis veritela",
        "Pred podpisom skontrolujte clovekom.",
    ]
    for index, line in enumerate(lines):
        pdf.drawString(72, 760 - index * 24, line)
    pdf.save()
    return output.getvalue()


def _write_export(path: Path, *, audit: bool = True, exported_by: str = "case-owner") -> None:
    case_id = "golden-case-602"
    audit_entries = (
        [
            {
                "usage_id": "usage-1",
                "case_id": case_id,
                "provider": "azurefoundry",
                "model": "gpt-4o-mini",
                "route_type": "external",
                "status": "success",
            }
        ]
        if audit
        else []
    )
    models_used = (
        [
            {
                "provider": "azurefoundry",
                "model": "gpt-4o-mini",
                "route_type": "external",
                "status": "success",
                "usage_count": 1,
            }
        ]
        if audit
        else []
    )
    document_text = (
        "Potvrdenie o splatení pôžičky\n"
        "Veriteľ Peter Vzorový a dlžník Ján Testovací.\n"
        "Suma 3 000 EUR je úplne splatená. Veriteľ nemá ďalšie nároky "
        "z tejto konkrétnej pôžičky.\nPodpis veriteľa.\n"
        "Pred podpisom skontrolujte človekom."
    )
    files = {
        "case.json": _json_bytes(
            {
                "schema": "jurisdigta.case-export.case.v1",
                "case_id": case_id,
                "user_id": "synthetic-user-602",
                "title": "Synthetic loan confirmation",
            }
        ),
        "messages.jsonl": (
            json.dumps(
                {
                    "role": "user",
                    "content": "Priprav potvrdenie pre Petra Vzorového na 3 000 EUR.",
                },
                ensure_ascii=False,
            )
            + "\n"
            + json.dumps(
                {
                    "role": "assistant",
                    "content": (
                        "Potvrdenie pre Peter Vzorový na 3 000 EUR je pripravené; "
                        "pred podpisom ho skontrolujte človekom."
                    ),
                },
                ensure_ascii=False,
            )
        ).encode(),
        "ai-model-audit.json": _json_bytes(
            {
                "schema": "jurisdigta.case-export.ai-model-audit.v1",
                "case_id": case_id,
                "entries": audit_entries,
            }
        ),
        "citations.json": _json_bytes(
            {
                "schema": "jurisdigta.case-export.citations.v1",
                "case_id": case_id,
                "items": [{"source_type": "law", "title": "Synthetic legal source"}],
            }
        ),
        "warnings.json": _json_bytes(
            {
                "schema": "jurisdigta.case-export.warnings.v1",
                "case_id": case_id,
                "items": [],
            }
        ),
        "documents/generated/01-confirmation.txt": document_text.encode(),
        "documents/generated/rendered-pdf/01-confirmation.pdf": _pdf_bytes(),
    }
    manifest = {
        "schema": "jurisdigta.case-export.v1",
        "generated_at": "2026-08-09T10:00:00Z",
        "exported_by": exported_by,
        "correlation_id": "synthetic-correlation-602",
        "case_id": case_id,
        "user_id": "synthetic-user-602",
        "case_title": "Synthetic loan confirmation",
        "artifact_count": len(files) + 2,
        "message_count": 2,
        "document_count": 1,
        "ai_model_audit_count": len(audit_entries),
        "models_used": models_used,
        "citation_count": 1,
        "documents": [
            {
                "doc_id": "document-1",
                "kind": "generated_document",
                "source_artifact": "documents/generated/01-confirmation.txt",
                "rendered_pdf_artifact": ("documents/generated/rendered-pdf/01-confirmation.pdf"),
            }
        ],
    }
    files["manifest.json"] = _json_bytes(manifest)
    files["sha256sums.txt"] = "".join(
        f"{sha256(payload).hexdigest()}  {name}\n" for name, payload in sorted(files.items())
    ).encode()
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, payload in sorted(files.items()):
            archive.writestr(name, payload)


def _write_inputs(root: Path) -> tuple[Path, Path, Path]:
    issue = root / "issue.json"
    issue.write_text(
        json.dumps(
            {
                "number": 602,
                "url": "https://github.com/mmaideveloper/aijurisdictionagents/issues/602",
                "title": "Synthetic golden case",
                "body": (
                    "Všetky údaje sú fiktívne a syntetické. Peter Vzorový prijal "
                    "3 000 EUR od Jána Testovacieho. Má ísť o potvrdenie, že suma je "
                    "úplne splatená iba z tejto konkrétnej pôžičky, s podpisom a "
                    "kontrolou človekom."
                ),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assertions = root / "assertions.json"
    assertions.write_text(
        json.dumps(
            {
                "case_key": "issue-602-private-loan-confirmation",
                "scenario_id": "01-private-loan-payment-confirmation",
                "language": "sk-SK",
                "country": "SK",
                "category": "legal_document_generation",
                "fixture_purpose": "Validate a synthetic private-loan payment confirmation.",
                "source_facts": ["Peter Vzorový", "3 000 EUR", "úplne splatená"],
                "answer": {
                    "must_contain": ["Peter Vzorový", "3 000 EUR", "skontrolujte človekom"],
                    "must_not_contain": ["CASE_UPDATE_JSON"],
                    "similarity_min": 0.82,
                },
                "document": {
                    "type": "private_loan_payment_confirmation",
                    "must_contain": ["Ján Testovací", "3 000 EUR", "Podpis veriteľa"],
                    "must_not_contain": ["všetkých budúcich nárokov"],
                    "similarity_min": 0.9,
                    "marker_phrases": {
                        "document_title": ["Potvrdenie o splatení pôžičky"],
                        "parties": ["Peter Vzorový", "Ján Testovací"],
                        "operative_statement": ["úplne splatená"],
                        "signature_block": ["Podpis veriteľa"],
                        "limited_claim_scope": ["z tejto konkrétnej pôžičky"],
                        "human_review_disclosure": ["skontrolujte človekom"],
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    registry = root / "modelsTesting" / "index.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "schema_version": "jurisdigta.models-testing.index.v1",
                "cases": [],
            }
        ),
        encoding="utf-8",
    )
    return issue, assertions, registry


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _prepare_command(
    root: Path, export: Path, issue: Path, assertions: Path, registry: Path, run_id: str
) -> list[str]:
    return [
        "prepare",
        "--issue",
        "602",
        "--zip",
        str(export),
        "--issue-json",
        str(issue),
        "--assertions-json",
        str(assertions),
        "--registry",
        str(registry),
        "--fixture-root",
        str(root / "modelsTesting"),
        "--quarantine-root",
        str(root / "runs"),
        "--run-id",
        run_id,
    ]


def test_prepare_registers_unchanged_technical_fixture_and_pdf_evidence(tmp_path: Path) -> None:
    issue, assertions, registry = _write_inputs(tmp_path)
    export = tmp_path / "export.zip"
    _write_export(export)

    result = _run(
        tmp_path,
        *_prepare_command(tmp_path, export, issue, assertions, registry, "valid-run"),
    )

    assert result.returncode == 0, result.stderr
    index = json.loads(registry.read_text(encoding="utf-8"))
    entry = index["cases"][0]
    fixture = tmp_path / "modelsTesting" / entry["zip_path"]
    assert fixture.read_bytes() == export.read_bytes()
    assert entry["fixture_status"] == "technical_reviewed"
    assert entry["actual_audited_routes"][0]["provider"] == "azurefoundry"
    assert entry["documents"]["rendered_pdf_count"] == 1
    assert (tmp_path / "runs" / "issue-602" / "valid-run" / "validation-report.json").is_file()
    assert (
        tmp_path / "runs" / "issue-602" / "valid-run" / "evidence" / "document-01.pdf"
    ).is_file()
    assert (
        tmp_path / "runs" / "issue-602" / "valid-run" / "evidence" / "document-01-first-page.png"
    ).is_file()


def test_prepare_rejects_archive_traversal_before_fixture_promotion(tmp_path: Path) -> None:
    issue, assertions, registry = _write_inputs(tmp_path)
    export = tmp_path / "unsafe.zip"
    _write_export(export)
    with ZipFile(export, "a", ZIP_DEFLATED) as archive:
        archive.writestr("../outside.txt", "unsafe")

    result = _run(
        tmp_path,
        *_prepare_command(tmp_path, export, issue, assertions, registry, "unsafe-run"),
    )

    assert result.returncode == 2
    assert "unsafe_archive_path" in result.stderr
    assert json.loads(registry.read_text(encoding="utf-8"))["cases"] == []
    assert not (tmp_path / "modelsTesting" / "cases").exists()


def test_prepare_rejects_missing_persisted_model_audit(tmp_path: Path) -> None:
    issue, assertions, registry = _write_inputs(tmp_path)
    export = tmp_path / "no-audit.zip"
    _write_export(export, audit=False)

    result = _run(
        tmp_path,
        *_prepare_command(tmp_path, export, issue, assertions, registry, "no-audit-run"),
    )

    assert result.returncode == 2
    assert "model_audit_missing" in result.stderr
    assert json.loads(registry.read_text(encoding="utf-8"))["cases"] == []


def test_promote_requires_explicit_human_approval_and_revalidates(tmp_path: Path) -> None:
    issue, assertions, registry = _write_inputs(tmp_path)
    export = tmp_path / "export.zip"
    _write_export(export)
    prepared = _run(
        tmp_path,
        *_prepare_command(tmp_path, export, issue, assertions, registry, "prepare-run"),
    )
    assert prepared.returncode == 0, prepared.stderr

    missing = _run(
        tmp_path,
        "promote",
        "--issue",
        "602",
        "--case-key",
        "issue-602-private-loan-confirmation",
        "--issue-json",
        str(issue),
        "--human-approval-json",
        str(tmp_path / "missing-approval.json"),
        "--registry",
        str(registry),
        "--fixture-root",
        str(tmp_path / "modelsTesting"),
        "--quarantine-root",
        str(tmp_path / "runs"),
    )
    assert missing.returncode == 2
    assert json.loads(registry.read_text(encoding="utf-8"))["cases"][0]["fixture_status"] == (
        "technical_reviewed"
    )

    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "reviewer": "human-reviewer",
                "approval_reference": (
                    "https://github.com/mmaideveloper/aijurisdictionagents/pull/700"
                    "#pullrequestreview-123"
                ),
                "approved_at": "2026-08-09T12:00:00Z",
                "production_path_confirmed": True,
            }
        ),
        encoding="utf-8",
    )
    promoted = _run(
        tmp_path,
        "promote",
        "--issue",
        "602",
        "--case-key",
        "issue-602-private-loan-confirmation",
        "--issue-json",
        str(issue),
        "--human-approval-json",
        str(approval),
        "--registry",
        str(registry),
        "--fixture-root",
        str(tmp_path / "modelsTesting"),
        "--quarantine-root",
        str(tmp_path / "runs"),
        "--run-id",
        "human-approved",
    )
    assert promoted.returncode == 0, promoted.stderr
    entry = json.loads(registry.read_text(encoding="utf-8"))["cases"][0]
    assert entry["fixture_status"] == "native_reviewed"
    assert entry["review"]["human_reviewer"] == "human-reviewer"


def test_manually_assembled_export_cannot_become_native_reviewed(tmp_path: Path) -> None:
    issue, assertions, registry = _write_inputs(tmp_path)
    export = tmp_path / "manual-export.zip"
    _write_export(export, exported_by="manually-assembled")
    prepared = _run(
        tmp_path,
        *_prepare_command(tmp_path, export, issue, assertions, registry, "manual-prepare"),
    )
    assert prepared.returncode == 0, prepared.stderr

    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "reviewer": "human-reviewer",
                "approval_reference": (
                    "https://github.com/mmaideveloper/aijurisdictionagents/pull/701"
                    "#pullrequestreview-124"
                ),
                "approved_at": "2026-08-09T12:00:00Z",
                "production_path_confirmed": True,
            }
        ),
        encoding="utf-8",
    )
    promoted = _run(
        tmp_path,
        "promote",
        "--issue",
        "602",
        "--case-key",
        "issue-602-private-loan-confirmation",
        "--issue-json",
        str(issue),
        "--human-approval-json",
        str(approval),
        "--registry",
        str(registry),
        "--fixture-root",
        str(tmp_path / "modelsTesting"),
        "--quarantine-root",
        str(tmp_path / "runs"),
        "--run-id",
        "manual-human-approved",
    )

    assert promoted.returncode == 2
    assert "native_production_export_provenance_missing" in promoted.stderr
    entry = json.loads(registry.read_text(encoding="utf-8"))["cases"][0]
    assert entry["fixture_status"] == "technical_reviewed"
