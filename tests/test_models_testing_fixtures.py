import hashlib
import json
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile

from pypdf import PdfReader


FIXTURE_ROOT = Path(__file__).resolve().parent / "modelsTesting"
INDEX_PATH = FIXTURE_ROOT / "index.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def test_model_testing_fixture_index_is_valid() -> None:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    assert index["schema_version"] == "jurisdigta.models-testing.index.v1"
    assert index["main_test_solution_issue"].endswith("/issues/422")
    assert index["compliance"]["data_policy"] == "synthetic_or_dedicated_test_accounts_only"
    assert index["compliance"]["legal_document_outputs_require_human_review"] is True
    assert index["cases"], "At least one model-testing fixture is required."

    for case in index["cases"]:
        zip_path = FIXTURE_ROOT / case["zip_path"]
        assert zip_path.exists(), f"Missing fixture ZIP: {zip_path}"
        assert _sha256(zip_path) == case["sha256"]
        assert case["related_test_solution_issue"] == index["main_test_solution_issue"]
        assert case["data_classification"] == "synthetic_test_fixture"
        assert case["expected_outputs"]["answer"]["similarity_min"] >= 0.7
        assert case["expected_outputs"]["document"]["similarity_min"] >= 0.8
        assert "signature_block" in case["expected_outputs"]["document"]["legal_document_markers"]
        assert (
            "human_review_disclosure"
            in case["expected_outputs"]["document"]["legal_document_markers"]
        )
        if case["fixture_status"] in {"technical_reviewed", "native_reviewed"}:
            assert case["actual_audited_routes"]
            assert case["review"]["state"] == case["fixture_status"]
            assert case["documents"]["generated_count"] >= 1
            assert case["documents"]["rendered_pdf_count"] >= 1
            assert case["source_facts"]
            assert (
                "limited_claim_scope"
                in case["expected_outputs"]["document"]["legal_document_markers"]
            )
        if case["fixture_status"] == "technical_reviewed":
            assert case["review"]["native_review_requires_human_approval"] is True
        if case["fixture_status"] == "native_reviewed":
            assert case["review"]["production_path_confirmed"] is True
            assert case["review"]["approval_reference"].startswith("https://github.com/")


def test_model_testing_fixture_zips_contain_required_case_files() -> None:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    legacy_required_files = {
        "case-export.json",
        "fixed-assistant-answer.txt",
        "generated-document.txt",
        "generated-document.pdf",
        "README.md",
    }

    for case in index["cases"]:
        zip_path = FIXTURE_ROOT / case["zip_path"]
        with ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            if "manifest.json" in names:
                assert {
                    "manifest.json",
                    "case.json",
                    "messages.jsonl",
                    "ai-model-audit.json",
                    "citations.json",
                    "warnings.json",
                    "sha256sums.txt",
                }.issubset(names)
                manifest = json.loads(archive.read("manifest.json"))
                assert manifest["schema"] == "jurisdigta.case-export.v1"
                audit = json.loads(archive.read("ai-model-audit.json"))
                assert audit["entries"]
                for entry in audit["entries"]:
                    assert all(
                        entry.get(field) for field in ("provider", "model", "route_type", "status")
                    )
                generated = [
                    item for item in manifest["documents"] if item["kind"] == "generated_document"
                ]
                assert generated
                for document in generated:
                    assert document["source_artifact"] in names
                    rendered = document["rendered_pdf_artifact"]
                    assert rendered in names
                    assert PdfReader(BytesIO(archive.read(rendered)), strict=True).pages
                continue

            assert legacy_required_files.issubset(names)
            case_export = json.loads(archive.read("case-export.json").decode("utf-8-sig"))
            answer = archive.read("fixed-assistant-answer.txt").decode("utf-8-sig")
            document = archive.read("generated-document.txt").decode("utf-8-sig")

        assert case_export["case_key"] == case["case_key"]
        assert case_export["category"] == case["category"]
        for marker in case["expected_outputs"]["answer"]["must_contain"]:
            assert marker in answer
        for marker in case["expected_outputs"]["answer"]["must_not_contain"]:
            assert marker not in answer
        for marker in case["expected_outputs"]["document"]["must_contain"]:
            assert marker in document
        for marker in case["expected_outputs"]["document"]["must_not_contain"]:
            assert marker not in document
