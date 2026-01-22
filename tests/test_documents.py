from pathlib import Path

from aijurisdictionagents.documents import load_documents, select_sources


def test_load_documents_reads_txt(tmp_path: Path) -> None:
    doc_path = tmp_path / "doc.txt"
    doc_path.write_text("Hello from a document.", encoding="utf-8")

    documents = load_documents(tmp_path)

    assert len(documents) == 1
    assert documents[0].content == "Hello from a document."
    assert documents[0].path.endswith("doc.txt")


def test_select_sources_returns_snippet(tmp_path: Path) -> None:
    doc_path = tmp_path / "case.md"
    doc_path.write_text("The contract requires delivery by May 15.", encoding="utf-8")

    documents = load_documents(tmp_path)
    sources = select_sources(documents, "delivery contract")

    assert sources
    assert sources[0].filename == "case.md"
    assert "delivery" in sources[0].snippet.lower()
