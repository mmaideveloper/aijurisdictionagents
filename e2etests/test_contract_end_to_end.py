from __future__ import annotations

from aijurisdictionagents.e2e_workflows import (
    simulate_contract_summary_case,
    simulate_slovak_lease_review,
)


def test_contract_summary_e2e(tmp_path) -> None:
    outcome = simulate_contract_summary_case(tmp_path / "contract_summary_case")

    assert len(outcome.uploaded_files) == 3
    assert all(path.suffix.lower() == ".pdf" for path in outcome.uploaded_files)
    assert "short contract summary" in outcome.summary.lower()
    assert "recommendation:" in outcome.recommendation.lower()
    assert outcome.weighted_accuracy >= 30
    assert set(outcome.citations) >= {
        "contract_page_1.pdf",
        "contract_page_2.pdf",
        "contract_page_3.pdf",
    }



def test_slovak_lease_review_e2e(tmp_path) -> None:
    outcome = simulate_slovak_lease_review(tmp_path / "slovak_lease_case")

    assert outcome.original_document.exists()
    assert outcome.revised_document.exists()
    assert outcome.diff_pdf.exists()
    assert outcome.invalid_areas
    assert "updated the legacy lease" in outcome.revised_summary.lower()
    assert outcome.weighted_accuracy >= 55
    revised_text = outcome.revised_document.read_text(encoding="utf-8").lower()
    assert "pisomna" in revised_text
    assert "depozit" in revised_text
    assert "opravy" in revised_text
