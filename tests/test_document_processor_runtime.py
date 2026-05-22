import sys
from pathlib import Path
from types import SimpleNamespace

from aijurisdictionagents.llm.embeddings import MockEmbeddingClient
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


def test_pdf_ocr_renders_pages_with_poppler_before_rapidocr(monkeypatch) -> None:
    poppler_calls = []

    class FakeRapidOCR:
        def __call__(self, _image_array):
            return [[None, "Text recovered from a rendered scanned page."]], 0.01

    class FakeNumpy:
        @staticmethod
        def array(value):
            return value

    fake_image_module = SimpleNamespace(open=lambda _buffer: object())
    monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(Image=fake_image_module))
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image_module)

    def fake_import_module(name: str):
        if name == "numpy":
            return FakeNumpy
        if name == "rapidocr_onnxruntime":
            return type("RapidOCRModule", (), {"RapidOCR": FakeRapidOCR})
        return __import__(name)

    monkeypatch.setattr(runtime.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(
        runtime,
        "render_pdf_pages_with_poppler",
        lambda payload: poppler_calls.append(payload) or [b"png-bytes"],
    )
    monkeypatch.setattr(runtime, "_render_pdf_pages_with_pymupdf", lambda _payload: [])

    text = runtime._extract_pdf_text_with_ocr(b"%PDF-scanned")

    assert poppler_calls == [b"%PDF-scanned"]
    assert "rendered scanned page" in text


def test_render_pdf_pages_with_poppler_uses_pdftoppm(monkeypatch) -> None:
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        Path(command[-1]).with_name("page-1.png").write_bytes(b"png-bytes")

    monkeypatch.setattr(runtime.shutil, "which", lambda name: "pdftoppm.exe" if name == "pdftoppm" else None)
    monkeypatch.setattr(runtime.subprocess, "run", fake_run)

    pages = runtime._render_pdf_pages_with_poppler(b"%PDF-1.7")

    assert pages == [b"png-bytes"]
    assert commands[0][:6] == ["pdftoppm.exe", "-png", "-r", "180", "-f", "1"]


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
