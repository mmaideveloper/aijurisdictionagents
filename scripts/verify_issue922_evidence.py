"""Verify synthetic #922 browser export, checksums, PDF, MCP source and ciphertext."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
import shutil
import subprocess
import sys
from zipfile import ZipFile

from pypdf import PdfReader
from run_issue922_e2e import configure, OUTPUT, ROOT


def verify_archive(payload: bytes, expected_cases: set[str]) -> list[bytes]:
    pdfs = []
    with ZipFile(BytesIO(payload)) as outer:
        manifest = json.loads(outer.read("manifest.json"))
        assert {item["case_id"] for item in manifest["cases"]} == expected_cases
        assert set(outer.namelist()) == {"manifest.json", *(item["member"] for item in manifest["cases"])}
        for item in manifest["cases"]:
            data = outer.read(item["member"])
            assert hashlib.sha256(data).hexdigest() == item["sha256"]
            with ZipFile(BytesIO(data)) as case:
                checksums = dict(line.split("  ", 1)[::-1] for line in case.read("sha256sums.txt").decode().splitlines())
                assert set(case.namelist()) == {*checksums, "sha256sums.txt"}
                for name, digest in checksums.items():
                    content = case.read(name)
                    assert hashlib.sha256(content).hexdigest() == digest
                    assert not content.startswith(b"jdenc1:")
                    if content.startswith(b"%PDF-"):
                        pdfs.append(content)
                assert json.loads(case.read("case.json"))["case_id"] == item["case_id"]
                messages = case.read("messages.jsonl").decode()
                assert "BLUE-922" in messages and "7319" in messages
    return pdfs


def verify_checkpoints(store, case_id: str) -> None:
    from typing import TypedDict
    from uuid import uuid4
    from langgraph.graph import StateGraph, START, END
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    from app.case_workflows.encrypted_checkpoints import EncryptedPostgresSaver

    class State(TypedDict):
        case_id: str
        text: str

    thread = "issue922-checkpoint-" + uuid4().hex
    secret = "SYNTHETIC-CHECKPOINT-922"
    with ConnectionPool(store.db_cloud, min_size=1, max_size=2, kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}) as pool:
        saver = EncryptedPostgresSaver(pool, store)
        saver.setup()
        graph = StateGraph(State)
        graph.add_node("read", lambda state: {"text": state["text"] + "-read"})
        graph.add_edge(START, "read")
        graph.add_edge("read", END)
        compiled = graph.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": thread}}
        try:
            assert compiled.invoke({"case_id": case_id, "text": secret}, config)["text"] == secret + "-read"
            assert compiled.get_state(config).values["text"] == secret + "-read"
            with store._connect() as conn:
                blobs = store._execute(conn, "SELECT type, blob FROM checkpoint_blobs WHERE thread_id = ?", (thread,)).fetchall()
                assert blobs and all(kind == "case-encrypted-v1" and secret.encode() not in bytes(payload) for kind, payload in blobs)
                rows = store._execute(conn, "SELECT checkpoint, metadata FROM checkpoints WHERE thread_id = ?", (thread,)).fetchall()
                assert rows and secret not in str(rows)
        finally:
            with store._connect() as conn:
                for table in ("checkpoint_blobs", "checkpoint_writes", "checkpoints", "case_workflow_encryption_scopes"):
                    store._execute(conn, f"DELETE FROM {table} WHERE thread_id = ?", (thread,))


def main() -> None:
    configure()
    sys.path.insert(0, str(ROOT / "api/aijuristiction-api"))
    from app.chat.mcp_law_context import _call_mcp_tool
    from aijurisdictionagents.api_db import ApiDatabaseStore
    browser = json.loads((OUTPUT / "browser-result.json").read_text())
    seed = json.loads((OUTPUT / "input-manifest.json").read_text())
    payload = (OUTPUT / "consented-export.zip").read_bytes()
    pdfs = verify_archive(payload, {browser["caseId"]})
    source = (OUTPUT / "synthetic-source.pdf").read_bytes()
    assert source in pdfs
    reader = PdfReader(BytesIO(source), strict=True)
    assert len(reader.pages) == 1
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "7319" in text and "BLUE-922" in text and "SYNTHETIC" in text
    pdf_path = OUTPUT / "verified-exported-source.pdf"
    pdf_path.write_bytes(source)
    renderer = shutil.which("pdftoppm")
    if not renderer:
        raise RuntimeError("Poppler pdftoppm required for final evidence")
    subprocess.run([renderer, "-f", "1", "-singlefile", "-scale-to", "1400", "-png", str(pdf_path), str(OUTPUT / "verified-exported-source-page1")], check=True, capture_output=True)
    # Corrupt a case member while retaining its declared checksum.
    damaged = BytesIO()
    with ZipFile(BytesIO(payload)) as original, ZipFile(damaged, "w") as output:
        for name in original.namelist():
            data = original.read(name)
            output.writestr(name, data + b"tampered" if name.endswith(".zip") else data)
    try:
        verify_archive(damaged.getvalue(), {browser["caseId"]})
    except AssertionError:
        tampering_rejected = True
    else:
        raise AssertionError("Archive tampering was not detected")
    law = _call_mcp_tool("getLawText", {"document_id": seed["sourceId"], "section_number": 569, "max_chars": 12000})
    assert law["document_id"] == seed["sourceId"]
    assert "Syntetick" in str(law.get("content_text", ""))
    assert seed["sourceId"] in browser["observedSourceIds"]
    store = ApiDatabaseStore.from_env()
    with store._connect() as conn:
        for table, fields in (("cases", ("title",)), ("case_documents", ("original_filename",)),
                              ("case_communications", ("summary", "presentation_json")),
                              ("case_document_chunks", ("chunk_text", "embedding_vector"))):
            rows = store._execute(conn, f"SELECT {', '.join(fields)} FROM {table} WHERE case_id = ?", (browser["caseId"],)).fetchall()
            assert rows and all(str(value).startswith("jdenc1:") for row in rows for value in row if value is not None)
        request = store._fetchone(conn, "SELECT status, artifact FROM case_export_requests WHERE request_id = ?", (browser["exportId"],))
        assert request == ("downloaded", None)
    for document in store.list_case_documents(case_id=browser["caseId"]):
        assert store._resolve_storage_path(document.storage_uri).read_bytes().startswith(b"jdenc1:")
    verify_checkpoints(store, browser["caseId"])
    browser.update(checkpointRoundtrip="passed", archiveValidation="passed", archiveSha256=hashlib.sha256(payload).hexdigest(),
                   archiveTamperingRejected=tampering_rejected, pdfTextAndStructure="passed",
                   directMcpSourceId=law["document_id"], ciphertextInspection="passed", archiveDeletedAfterDownload=True,
                   retrievalBenchmark=json.loads((OUTPUT / "retrieval-benchmark.json").read_text()))
    (OUTPUT / "result-manifest.json").write_text(json.dumps(browser, indent=2))
    print("ZIP checksums, exact case scope, exported PDF, MCP citation and ciphertext verified")


if __name__ == "__main__":
    main()
