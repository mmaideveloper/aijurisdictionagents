from services.document_processor import runtime
from aijurisdictionagents.llm.embeddings import MockEmbeddingClient


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


def test_mock_embedding_helpers_support_similarity_and_parsing() -> None:
    client = MockEmbeddingClient()
    query_vector = client.embed_texts(["lease termination notice"]).vectors[0]
    similar_vector = client.embed_texts(["lease termination notice"]).vectors[0]
    different_vector = client.embed_texts(["criminal sentencing memo"]).vectors[0]

    assert len(query_vector) == 32
    assert runtime.cosine_similarity(query_vector, similar_vector) > 0.99
    assert runtime.cosine_similarity(query_vector, different_vector) < 0.95


def test_chunk_document_text_creates_multiple_chunks_for_long_text() -> None:
    text = "\n\n".join(
        f"Paragraph {index} " + ("contract clause " * 80)
        for index in range(1, 5)
    )

    chunks = runtime.chunk_document_text(text, target_chars=500, overlap_chars=60, min_chunk_chars=100)

    assert len(chunks) >= 2
    assert chunks[0].chunk_index == 0
    assert all(chunk.text.strip() for chunk in chunks)
