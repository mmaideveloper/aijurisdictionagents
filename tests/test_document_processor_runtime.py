from services.document_processor import runtime


def test_extract_document_text_reads_plain_text() -> None:
    extracted = runtime.extract_document_text(
        filename="evidence.txt",
        payload=b"Important clause in plain text.",
    )

    assert extracted.extraction_method == "plain_text"
    assert extracted.text == "Important clause in plain text."


def test_extract_document_text_uses_ocr_for_scanned_pdf(monkeypatch) -> None:
    monkeypatch.setattr(runtime, "_extract_pdf_text", lambda _payload: "short text")
    monkeypatch.setattr(
        runtime,
        "_extract_pdf_text_with_ocr",
        lambda _payload: "This scanned contract was recovered with OCR and contains the meaningful body text.",
    )

    extracted = runtime.extract_document_text(
        filename="scan.pdf",
        payload=b"%PDF-fake",
    )

    assert extracted.extraction_method == "pdf_ocr"
    assert "recovered with OCR" in extracted.text


def test_embedding_helpers_support_similarity_and_parsing() -> None:
    query_vector = runtime.parse_embedding_vector(runtime.build_embedding_vector("lease termination notice"))
    similar_vector = runtime.parse_embedding_vector(runtime.build_embedding_vector("lease termination notice"))
    different_vector = runtime.parse_embedding_vector(runtime.build_embedding_vector("criminal sentencing memo"))

    assert len(query_vector) == 32
    assert runtime.cosine_similarity(query_vector, similar_vector) > 0.99
    assert runtime.cosine_similarity(query_vector, different_vector) < 0.95
