"""Deterministic offline metadata example; not real-local E2E acceptance."""

from datetime import datetime, timedelta, timezone
import gc
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig
from aijurisdictionagents.api_db import ApiDatabaseStore


def main() -> None:
    storage = Path(__file__).resolve().parents[1] / "runs/storage/api/sqlite"
    storage.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="audit-search-demo-", dir=storage) as temporary:
        root = Path(temporary)
        owners = ApiDatabaseStore(db_path=root / "api.sqlite3", blob_root=root / "files")
        owners.initialize()
        user = owners.create_user(email="audit-demo@example.test", password="synthetic-offline-demo-only",
                                  full_name="Synthetic Audit Demo")
        case = owners.create_case(user_id=user.user_id, company_id=None, title="Synthetic audit example")
        traces = CaseWorkflowStore(CaseWorkflowStoreConfig("local", "", root / "traces.sqlite3"))
        for session in ("synthetic-session-a", "synthetic-session-b"):
            traces.record_debug_event(
                correlation_id=f"corr-{session}", session_id=session, request_id="synthetic-request",
                parent_request_id="", component="demo", stage="completed", status="completed", payload={},
            )
            traces.register_trace_session(
                correlation_id=f"corr-{session}", session_id=session,
                user_id=user.user_id, case_id=case.case_id, owner_store=owners,
            )
        now = datetime.now(timezone.utc)
        items, _ = traces.search_trace_sessions(
            filters={"user_id": user.user_id, "case_id": case.case_id},
            start=(now - timedelta(days=7)).isoformat(), end=now.isoformat(), limit=25,
        )
        assert len(items) == 2 and all("payload" not in item for item in items)
        print(json.dumps({"synthetic_only": True, "metadata_results": items}, indent=2))
        # The API store uses SQLite transaction contexts; release their connection
        # cycles before TemporaryDirectory removes the files on Windows.
        gc.collect()


if __name__ == "__main__":
    main()
