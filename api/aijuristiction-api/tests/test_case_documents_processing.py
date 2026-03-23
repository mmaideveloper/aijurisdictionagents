from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unicodedata

from fastapi.testclient import TestClient

from app.main import app
from aijurisdictionagents.api_db import ApiDatabaseStore
from services.document_processor.service import DocumentProcessor
from services.document_processor.worker import run_document_processor


def _headers() -> dict[str, str]:
    return {"x-api-key": "aijuris"}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    return " ".join(normalized.encode("ascii", "ignore").decode("ascii").split())


def _configure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))


def _create_user(client: TestClient, phone: str, email: str) -> str:
    response = client.post(
        "/v1/users/sign-up",
        headers=_headers(),
        json={"phone_number": phone, "email": email, "password": "secret"},
    )
    assert response.status_code == 201
    return response.json()["user_id"]


class RecordingEmbeddingClient:
    model_name = "test-vector-3d"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> SimpleNamespace:
        self.calls.append(list(texts))
        return SimpleNamespace(
            model_name=self.model_name,
            vectors=[self._vector_for(text) for text in texts],
        )

    def _vector_for(self, text: str) -> list[float]:
        normalized = _normalize_text(text)
        if "67/2000" in normalized or "zmluva o prenajme bytu" in normalized:
            return [1.0, 0.0, 0.0]
        if (
            "najnovsieho zakona" in normalized
            or ("zakona" in normalized and "prenajme" in normalized and "summary" in normalized)
        ):
            return [1.0, 0.0, 0.0]
        if "vypoved" in normalized or "depozit" in normalized:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


class RecordingLLMClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def complete(self, agent_name: str, system_prompt: str, conversation, documents) -> str:
        self.calls.append(
            {
                "agent_name": agent_name,
                "system_prompt": system_prompt,
                "conversation": list(conversation),
                "documents": list(documents),
            }
        )
        primary = documents[0] if documents else None
        snippet = " ".join(primary.content.split())[:240] if primary else ""
        return (
            "Pozrel som dokument a upravil zmluvu. "
            f"Summary: {snippet}. "
            "Cerpal som zo zakona c. 67/2000 Z.z. o najme bytov."
        )


def test_case_document_upload_limit_and_processing_context(monkeypatch, tmp_path) -> None:
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("DOCUMENT_PROCESSOR", "azure")
    client = TestClient(app)
    user_id = _create_user(client, "+421900222111", "docs@example.com")
    case_id = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Documents"},
    ).json()["case_id"]

    upload = client.post(
        f"/v1/cases/{case_id}/documents?user_id={user_id}",
        headers=_headers(),
        files=[
            ("files", ("one.txt", b"alpha evidence", "text/plain")),
            ("files", ("two.txt", b"beta evidence", "text/plain")),
        ],
    )
    assert upload.status_code == 201
    assert len(upload.json()["uploaded"]) == 2

    blocked = client.post(
        f"/v1/cases/{case_id}/documents?user_id={user_id}",
        headers=_headers(),
        files=[("files", ("three.txt", b"gamma evidence", "text/plain"))],
    )
    assert blocked.status_code == 409

    before = client.get(
        f"/v1/cases/{case_id}/documents/context?user_id={user_id}",
        headers=_headers(),
    )
    assert before.status_code == 200
    assert before.json()["processed_documents"] == []
    assert before.json()["unprocessed_documents"] == ["two.txt", "one.txt"]

    processed = run_document_processor(limit=10)
    assert len(processed) == 2

    after = client.get(
        f"/v1/cases/{case_id}/documents/context?user_id={user_id}",
        headers=_headers(),
    )
    assert after.status_code == 200
    assert sorted(after.json()["processed_documents"]) == ["one.txt", "two.txt"]
    assert after.json()["unprocessed_documents"] == []

    history = client.get(f"/v1/cases/{case_id}/history?user_id={user_id}", headers=_headers())
    assert history.status_code == 200
    assert {item["processing_status"] for item in history.json()["documents"]} == {"processed"}


def test_case_document_upload_processes_immediately_in_local_mode(monkeypatch, tmp_path) -> None:
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("DOCUMENT_PROCESSOR", "local")
    client = TestClient(app)
    user_id = _create_user(client, "+421900222112", "docs-local@example.com")
    case_id = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Immediate processing"},
    ).json()["case_id"]

    upload = client.post(
        f"/v1/cases/{case_id}/documents?user_id={user_id}",
        headers=_headers(),
        files=[("files", ("one.txt", b"alpha evidence", "text/plain"))],
    )
    assert upload.status_code == 201
    uploaded = upload.json()["uploaded"]
    assert len(uploaded) == 1
    assert uploaded[0]["processing_status"] == "processed"
    assert upload.json()["processed_document_count"] == 1
    assert upload.json()["unprocessed_document_count"] == 0

    context = client.get(
        f"/v1/cases/{case_id}/documents/context?user_id={user_id}",
        headers=_headers(),
    )
    assert context.status_code == 200
    assert context.json()["processed_documents"] == ["one.txt"]
    assert context.json()["unprocessed_documents"] == []

    store = ApiDatabaseStore.from_env()
    store.initialize()
    contents = store.list_case_document_contents(case_id=case_id)
    assert len(contents) == 1
    doc_id, filename, text, vector = contents[0]
    assert doc_id
    assert filename == "one.txt"
    assert text == "alpha evidence"
    assert vector.startswith("[")
    chunks = store.list_case_document_chunks(case_id=case_id)
    assert len(chunks) == 1
    assert chunks[0].doc_id == doc_id
    assert chunks[0].chunk_text == "alpha evidence"
    assert chunks[0].embedding_vector.startswith("[")
    assert chunks[0].embedding_model == "mock-embedding-32d"


def test_whitelisted_phone_gets_extended_free_document_limit(monkeypatch, tmp_path) -> None:
    _configure(monkeypatch, tmp_path)
    client = TestClient(app)
    user_id = _create_user(client, "+421944400166", "test-phone@example.com")
    case_id = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Premium by phone"},
    ).json()["case_id"]

    files = [("files", (f"doc-{index}.txt", f"evidence-{index}".encode(), "text/plain")) for index in range(3)]
    response = client.post(
        f"/v1/cases/{case_id}/documents?user_id={user_id}",
        headers=_headers(),
        files=files,
    )
    assert response.status_code == 201
    assert len(response.json()["uploaded"]) == 3

    store = ApiDatabaseStore.from_env()
    store.initialize()
    assert store.get_document_upload_limit(user_id=user_id) == 50


def test_chunk_retrieval_adds_relevant_document_excerpt_to_prompt_context(monkeypatch, tmp_path) -> None:
    _configure(monkeypatch, tmp_path)

    from app.chat.api import _load_case_documents_for_llm

    store = ApiDatabaseStore.from_env()
    store.initialize()
    user = store.create_user(
        email="chunks@example.com",
        password="secret",
        phone_number="+421900222113",
    )
    case = store.create_case(user_id=user.user_id, company_id=None, title="Chunk retrieval")
    payload = (
        ("General case background. " * 120)
        + "\n\n"
        + ("Termination notice clause and notice deadline. " * 80)
        + "\n\n"
        + ("Signature appendix and witness blocks. " * 100)
    ).encode("utf-8")
    doc_id = store.add_case_document(
        case_id=case.case_id,
        kind="uploaded",
        version=1,
        original_filename="lease.txt",
        payload=payload,
        uploaded_by_user_id=user.user_id,
    )
    document = store.get_case_document(case_id=case.case_id, doc_id=doc_id)
    DocumentProcessor(store).process_documents([document])

    documents, processed_names, unprocessed_names = _load_case_documents_for_llm(
        case_id=case.case_id,
        query="What does the termination notice clause require?",
    )

    assert processed_names == ["lease.txt"]
    assert unprocessed_names == []
    assert documents
    assert any("termination notice clause" in document.content.lower() for document in documents)
    assert all("#chunk-" in document.path for document in documents)


def test_case_document_debug_reports_vectors_and_selected_prompt_chunks(monkeypatch, tmp_path) -> None:
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("DOCUMENT_PROCESSOR", "local")
    client = TestClient(app)
    user_id = _create_user(client, "+421900222114", "docs-debug@example.com")
    case_id = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Debug case"},
    ).json()["case_id"]

    upload = client.post(
        f"/v1/cases/{case_id}/documents?user_id={user_id}",
        headers=_headers(),
        files=[
            (
                "files",
                (
                    "lease.txt",
                    (
                        ("General background. " * 90)
                        + "\n\n"
                        + ("Termination notice clause and notice deadline. " * 60)
                    ).encode("utf-8"),
                    "text/plain",
                ),
            )
        ],
    )
    assert upload.status_code == 201

    response = client.get(
        f"/v1/cases/{case_id}/documents/debug?user_id={user_id}&query=What is the termination notice deadline?",
        headers=_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["db_option"] == "local"
    assert payload["uses_postgres"] is False
    assert payload["stored_documents"][0]["vector_present"] is True
    assert payload["stored_documents"][0]["chunk_count"] >= 1
    assert payload["selected_prompt_chunks"]
    assert "termination notice clause" in payload["prompt_preview"].lower()


def test_uploaded_pdf_is_stored_vectorized_and_used_for_vector_prompt_context(
    monkeypatch,
    tmp_path,
) -> None:
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("DOCUMENT_PROCESSOR", "local")
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    from app.chat import api as chat_api
    import aijurisdictionagents.llm as llm_module
    from services.document_processor import service as document_processor_service

    embedding_client = RecordingEmbeddingClient()
    llm_client = RecordingLLMClient()

    monkeypatch.setattr(document_processor_service, "get_embedding_client", lambda: embedding_client)
    monkeypatch.setattr(chat_api, "get_embedding_client", lambda: embedding_client)
    monkeypatch.setattr(chat_api, "lexical_overlap_score", lambda _query, _text: 0)
    monkeypatch.setattr(llm_module, "get_llm_client", lambda: llm_client)

    client = TestClient(app)
    user_id = _create_user(client, "+421900222115", "docs-pdf-vector@example.com")
    case_id = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Lease vector retrieval"},
    ).json()["case_id"]

    pdf_path = (
        Path(__file__).resolve().parents[3]
        / "e2etests"
        / "Zmluva_test_nevyhodna_2000.pdf"
    )
    user_prompt = (
        "Pozri na document a uprav zmvluvu podla najnovsieho zakona o prenajme, "
        "priprav summary a uved z ktoreho zakona si cerpal."
    )

    upload = client.post(
        f"/v1/cases/{case_id}/documents?user_id={user_id}",
        headers=_headers(),
        files=[("files", (pdf_path.name, pdf_path.read_bytes(), "application/pdf"))],
    )
    assert upload.status_code == 201
    assert upload.json()["uploaded"][0]["processing_status"] == "processed"

    store = ApiDatabaseStore.from_env()
    store.initialize()
    contents = store.list_case_document_contents(case_id=case_id)
    assert len(contents) == 1
    doc_id, filename, extracted_text, embedding_vector = contents[0]
    normalized_text = _normalize_text(extracted_text)
    assert filename == pdf_path.name
    assert "zmluva o prenajme bytu" in normalized_text
    assert "67/2000" in normalized_text
    parsed_document_vector = json.loads(embedding_vector)
    assert len(parsed_document_vector) == 3

    chunks = store.list_case_document_chunks(case_id=case_id)
    assert chunks
    assert all(chunk.doc_id == doc_id for chunk in chunks)
    assert all(chunk.embedding_model == embedding_client.model_name for chunk in chunks)
    assert all(len(json.loads(chunk.embedding_vector)) == 3 for chunk in chunks)
    assert any("67/2000" in _normalize_text(chunk.chunk_text) for chunk in chunks)

    debug_response = client.get(
        f"/v1/cases/{case_id}/documents/debug",
        headers=_headers(),
        params={"user_id": user_id, "query": user_prompt},
    )
    assert debug_response.status_code == 200
    debug_payload = debug_response.json()
    assert debug_payload["stored_documents"][0]["vector_present"] is True
    assert debug_payload["stored_documents"][0]["embedding_model"] == embedding_client.model_name
    assert debug_payload["stored_documents"][0]["chunk_count"] >= 1
    assert debug_payload["selected_prompt_chunks"]
    assert "67/2000" in _normalize_text(debug_payload["prompt_preview"])

    session_response = client.post(
        "/v1/chat/sessions",
        headers=_headers(),
        json={
            "country": "SK",
            "language": "SK",
            "discussion_type": "advice",
            "case_id": case_id,
        },
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    reply_response = client.post(
        f"/v1/chat/sessions/{session_id}/reply",
        headers=_headers(),
        json={"content": user_prompt},
    )
    assert reply_response.status_code == 200
    reply_content = _normalize_text(reply_response.json()["content"])
    assert "summary" in reply_content
    assert "67/2000" in reply_content

    assert [user_prompt] in embedding_client.calls
    assert llm_client.calls
    llm_documents = llm_client.calls[0]["documents"]
    assert llm_documents
    assert any("#chunk-" in document.path for document in llm_documents)
    assert any("67/2000" in _normalize_text(document.content) for document in llm_documents)
