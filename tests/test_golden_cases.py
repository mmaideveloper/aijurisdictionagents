import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from aijurisdictionagents.golden_cases import canonical_text, compare_text, load_golden_case


def test_compare_text_normalizes_diacritics_and_reports_rules() -> None:
    result = compare_text(
        "Potvrdenie o prijatí 1 000 EUR. Kontrola človekom.",
        "Potvrdenie o prijati 1000 EUR. Kontrola clovekom.",
        required=("potvrdenie", "človekom"),
        forbidden=("CASE_UPDATE_JSON",),
        similarity_min=0.9,
    )
    assert result.passed
    assert canonical_text("Prijatí") == "prijati"


def test_loads_native_case_export(tmp_path: Path) -> None:
    fixture = tmp_path / "case.zip"
    manifest = {
        "schema": "jurisdigta.case-export.v1",
        "case_id": "case-01",
        "documents": [{"kind": "generated_document", "source_artifact": "documents/01.txt"}],
    }
    with ZipFile(fixture, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr(
            "messages.jsonl",
            '\n'.join(
                [
                    json.dumps({"role": "user", "content": "Priprav potvrdenie."}),
                    json.dumps({"role": "assistant", "content": "Tu je návrh."}),
                ]
            ),
        )
        archive.writestr("documents/01.txt", "Potvrdenie o prijatí peňazí")
        archive.writestr("ai-model-audit.json", json.dumps({"entries": [{"provider": "local_ollama"}]}))
        archive.writestr("warnings.json", json.dumps({"items": []}))
    loaded = load_golden_case(fixture)
    assert loaded.case_key == "case-01"
    assert loaded.prompts == ("Priprav potvrdenie.",)
    assert loaded.expected_documents == ("Potvrdenie o prijatí peňazí",)
    assert loaded.model_audit[0]["provider"] == "local_ollama"


def test_scenario_01_seed_is_loadable() -> None:
    fixture = Path("tests/modelsTesting/cases/issue-513-loan-confirmation-case-export.zip")
    loaded = load_golden_case(fixture)
    assert loaded.case_key == "issue-513-loan-confirmation"
    assert loaded.prompts
    assert loaded.expected_documents
    assert loaded.warnings[0]["code"] == "legacy_fixture"
