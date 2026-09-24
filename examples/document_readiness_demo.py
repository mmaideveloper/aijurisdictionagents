"""Offline readiness demonstration using synthetic data in temporary storage."""
from pathlib import Path
import gc
import os
import sys
import tempfile
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "api" / "aijuristiction-api")]


def main() -> None:
    # This explicit offline example never selects a live LLM or reads case facts.
    storage_root = ROOT / "runs" / "storage" / "document-readiness" / "sqlite"
    storage_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="demo-", dir=storage_root) as directory:
        os.environ.update({
            "DB_OPTION": "local", "STORAGE_OPTION": "local",
            "DB_LOCAL": str(Path(directory) / "api.sqlite3"),
            "STORE_LOCAL": str(Path(directory) / "storage"), "LLM_PROVIDER": "mock",
        })
        from app.chat import api
        from app.chat.models import Message, MessageRole, Session

        store = api._get_store()
        user = store.create_user(email="readiness@example.test", password="synthetic-only",
                                 phone_number="+421900000835")
        case = store.create_case(user_id=user.user_id, company_id=None, title="Synthetic draft")
        session = Session(case_id=case.case_id, user_id=UUID(user.user_id), country="SK")
        api._repository.create_session(session)
        message = Message(session_id=session.id, role=MessageRole.ASSISTANT,
                          content="Dokument je pripraveny na stiahnutie.")
        assert not api._document_export_ready([message])
        print("Confirmed prose without storage: not ready")
        ids = api._persist_generated_case_document_drafts(
            session=session, case_id=case.case_id,
            drafts=[api._GeneratedCaseDocumentDraft(filename="synthetic.pdf", body="Synthetic legal draft for human review.")],
        )
        message.content = api._attach_generated_case_document_references(
            session=session, content=message.content, doc_ids=ids,
        )
        assert api._document_export_ready([message])
        print("Persisted nonempty document with ID: ready")
        gc.collect()  # Release SQLite connections before Windows removes temporary files.


if __name__ == "__main__":
    main()
