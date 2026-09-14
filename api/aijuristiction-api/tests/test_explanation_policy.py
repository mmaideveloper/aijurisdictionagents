import pytest

from app.chat.explanation_policy import is_general_explanation_request
from app.chat.mcp_law_context import _document_content


@pytest.mark.parametrize("query", [
    "Vysvetli možnosti pre odsúdeného s náramkom, môže ísť do práce? Do obchodu?",
    "Aké sú možnosti pri výkone trestu?", "Ako funguje domáce väzenie?",
    "Explain the conditions for electronic monitoring.",
])
def test_explicit_general_questions(query: str) -> None:
    assert is_general_explanation_request(query)


@pytest.mark.parametrize("query", [
    "Áno", "Priprav žiadosť", "Vysvetli pravidlá a priprav žiadosť.",
    "Explain this and draft an application.", "Posúď moje rozhodnutie a vysvetli riziká.",
])
def test_drafting_or_assessment_stays_in_existing_workflow(query: str) -> None:
    assert not is_general_explanation_request(query)


def test_model_evidence_keeps_public_labels_without_internal_document_ids() -> None:
    content = _document_content(
        laws=[{"law_identifier_text": "810/2026 Z. z.", "title": "Synthetic source", "document_id": "internal-secret-id"}],
        law_texts=[{"law_identifier_text": "810/2026 Z. z.", "content_text": "Synthetic provision."}],
        court_decisions=[], fallback_records=[],
    )
    assert "810/2026 Z. z." in content and "Synthetic provision." in content
    assert "internal-secret-id" not in content and "document_id=" not in content
