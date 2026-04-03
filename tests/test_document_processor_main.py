from __future__ import annotations

import argparse
import json
import logging

from services.document_processor import __main__ as document_processor_main
from services.document_processor.service import ProcessedDocumentResult


def test_document_processor_main_logs_batch_results_on_one_line(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        document_processor_main,
        "run_document_processor",
        lambda *, limit: [
            ProcessedDocumentResult(
                doc_id="doc-1",
                case_id="case-1",
                original_filename="lease.pdf",
                status="processed",
                extracted_characters=42,
                extraction_method="pdf-text",
            )
        ],
    )
    monkeypatch.setattr(
        document_processor_main.argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse.Namespace(limit=1),
    )
    caplog.set_level(logging.INFO, logger="document-processor")

    exit_code = document_processor_main.main()

    assert exit_code == 0
    message = caplog.messages[-1]
    assert message.startswith("[document-processor] batch_results=")
    payload = json.loads(message.split("=", 1)[1])
    assert payload["processed_documents"] == 1
    assert payload["results"][0]["doc_id"] == "doc-1"
