from pathlib import Path
import tempfile

from aijurisdictionagents.api_db import ApiDatabaseStore


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = ApiDatabaseStore(db_path=root / "api.sqlite3", blob_root=root / "blob")
        store.initialize()

        user = store.create_user(
            email="mobile.user@example.com",
            full_name="Mobile User",
            password="change-me",
        )
        company = store.create_company(legal_name="Demo Company Ltd")
        store.add_user_to_company(
            user_id=user.user_id, company_id=company.company_id, role="admin"
        )

        case = store.create_case(
            user_id=user.user_id,
            company_id=company.company_id,
            title="Employment contract review",
        )
        store.add_case_document(
            case_id=case.case_id,
            kind="source",
            version=1,
            original_filename="contract.docx",
            payload=b"sample-binary-content",
            uploaded_by_user_id=user.user_id,
        )
        store.add_case_communication(
            case_id=case.case_id,
            channel="audio",
            summary="Initial consultation recorded.",
            transcript_payload=b"audio transcript content",
            extension="txt",
        )

        print(f"Created user: {user.email}")
        print(f"Created company: {company.legal_name}")
        print(f"Created case: {case.case_id}")
        print(f"SQLite file: {store.db_path}")
        print(f"Blob root: {store.blob_root}")
        print(
            "Tip: local runtime data belongs under runs/storage/api/{sqlite,files,postgres}; SQL assets belong under databases/api/."
        )


if __name__ == "__main__":
    main()
