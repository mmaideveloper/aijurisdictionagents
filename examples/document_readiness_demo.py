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
    if os.name == "nt":
        # Use long paths for both writes and TemporaryDirectory cleanup.
        storage_root = Path("\\\\?\\" + str(storage_root))
    storage_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="demo-", dir=storage_root) as directory:
        blob_root = str(Path(directory) / "storage")
        os.environ.update({
            "DB_OPTION": "local", "STORAGE_OPTION": "local",
            "DB_LOCAL": str(Path(directory) / "api.sqlite3"),
            "STORE_LOCAL": blob_root, "LLM_PROVIDER": "mock",
        })
        from app.document_content import is_status_only_document
        assert is_status_only_document("Document is ready for download.")
        print("Download announcement without document body: rejected")
        from app.chat import api
        from app.chat.models import Message, MessageRole, Session

        store = api._get_store()
        user = store.create_user(email="readiness@example.test", password="synthetic-only",
                                 phone_number="+421900000835")
        case = store.create_case(user_id=user.user_id, company_id=None, title="Synthetic draft")
        session = Session(case_id=case.case_id, user_id=UUID(user.user_id), country="SK", language="sk-SK")
        api._repository.create_session(session)
        message = Message(session_id=session.id, role=MessageRole.ASSISTANT,
                          content="Dokument je pripraveny na stiahnutie.")
        assert not api._document_export_ready([message])
        print("Confirmed prose without storage: not ready")
        draft = (
            "Pracovná zmluva\nZamestnávateľ: Demo Firma\nZamestnanec: Demo Osoba\n"
            "Druh práce: Vývoj softvéru.\nMesačná mzda: 3 200 EUR brutto.\n"
            "Pracovný čas: 40 hodín týždenne.\nPodpis zamestnanca: __________\n\n"
            "Mám pripraviť tento dokument vo formáte PDF?"
        )
        api._repository.add_message(Message(session_id=session.id, role=MessageRole.ASSISTANT, content=draft))
        _, message, _, _, route = api._run_direct_lawyer_turn(
            session_id=session.id, session=session, content="dobre",
        )
        assert route is None  # Saving the confirmed draft makes no model call.
        assert len(message.generated_document_ids) == 1
        assert api._document_export_ready([message])
        documents = [doc for doc in store.list_case_documents(case_id=case.case_id) if doc.kind == "generated_document"]
        saved = store.read_storage_bytes(storage_uri=documents[0].storage_uri).decode("utf-8")
        assert "3 200 EUR" in saved and "Mám pripraviť" not in saved
        print("Confirmed employment draft saved without model rewrite: ready")
        gc.collect()  # Release SQLite connections before Windows removes temporary files.


if __name__ == "__main__":
    main()
