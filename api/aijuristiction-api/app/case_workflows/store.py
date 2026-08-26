from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Literal, cast
from uuid import uuid4

from app.case_workflows.models import (
    WorkflowAssignmentResponse,
    WorkflowEventResponse,
    WorkflowRunResponse,
)
from aijurisdictionagents.api_db.config import ApiDataConfig
from aijurisdictionagents.orchestration.case_workflow import CaseWorkflowOutcome, CaseWorkflowState


@dataclass(frozen=True)
class CaseWorkflowStoreConfig:
    db_option: str
    db_cloud: str
    sqlite_path: Path


class WorkflowAssignmentNotFoundError(KeyError):
    pass


class WorkflowRunNotFoundError(KeyError):
    pass


class WorkflowOwnershipError(PermissionError):
    pass


class CaseWorkflowStore:
    def __init__(self, config: CaseWorkflowStoreConfig) -> None:
        self._config = config
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def from_env(cls) -> "CaseWorkflowStore":
        api = ApiDataConfig.from_env()
        configured = os.getenv("API_CASE_WORKFLOWS_SQLITE_PATH", "").strip()
        repo_root = Path(__file__).resolve().parents[4]
        path = (
            Path(configured)
            if configured
            else repo_root / "runs" / "storage" / "api" / "sqlite" / "case_workflows.sqlite3"
        )
        return cls(
            CaseWorkflowStoreConfig(
                db_option=api.db_option,
                db_cloud=api.db_cloud,
                sqlite_path=path,
            )
        )

    def list_assignments(
        self, *, case_type_key: str | None = None, jurisdiction: str | None = None
    ) -> list[WorkflowAssignmentResponse]:
        clauses: list[str] = []
        params: list[object] = []
        if case_type_key:
            clauses.append("case_type_key = ?")
            params.append(case_type_key.strip())
        if jurisdiction:
            clauses.append("jurisdiction = ?")
            params.append(jurisdiction.strip().upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    f"SELECT * FROM case_workflow_assignments {where} "
                    "ORDER BY case_type_key, created_at DESC"
                ),
                tuple(params),
            ).fetchall()
        return [_assignment(_row(row)) for row in rows]

    def get_active_assignment(
        self, *, case_type_key: str, jurisdiction: str
    ) -> WorkflowAssignmentResponse:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT * FROM case_workflow_assignments "
                    "WHERE case_type_key = ? AND jurisdiction = ? AND is_active = 1"
                ),
                (case_type_key.strip(), jurisdiction.strip().upper()),
            ).fetchone()
        if row is None:
            raise WorkflowAssignmentNotFoundError(
                f"No active workflow assignment for {jurisdiction}:{case_type_key}"
            )
        return _assignment(_row(row))

    def assign(
        self,
        *,
        case_type_key: str,
        jurisdiction: str,
        graph_key: str,
        graph_version: int,
        flow_key: str,
        flow_version: int,
        created_by: str,
        validation_status: str = "valid",
        validation_message: str = "",
    ) -> WorkflowAssignmentResponse:
        now = _utc_now()
        assignment_id = str(uuid4())
        previous: WorkflowAssignmentResponse | None
        try:
            previous = self.get_active_assignment(
                case_type_key=case_type_key, jurisdiction=jurisdiction
            )
        except WorkflowAssignmentNotFoundError:
            previous = None
        with self._connect() as conn:
            if previous is not None:
                conn.execute(
                    self._sql(
                        "UPDATE case_workflow_assignments SET is_active = 0, effective_to = ? "
                        "WHERE assignment_id = ?"
                    ),
                    (now, previous.assignment_id),
                )
            conn.execute(
                self._sql(
                    """
                    INSERT INTO case_workflow_assignments(
                        assignment_id, case_type_key, jurisdiction, graph_key, graph_version,
                        flow_key, flow_version, is_active, validation_status, validation_message,
                        effective_from, effective_to, created_by, created_at,
                        supersedes_assignment_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, NULL, ?, ?, ?)
                    """
                ),
                (
                    assignment_id,
                    case_type_key.strip(),
                    jurisdiction.strip().upper(),
                    graph_key,
                    graph_version,
                    flow_key,
                    flow_version,
                    validation_status,
                    validation_message,
                    now,
                    created_by,
                    now,
                    previous.assignment_id if previous else None,
                ),
            )
            conn.commit()
        return self.get_active_assignment(case_type_key=case_type_key, jurisdiction=jurisdiction)

    def save_run(
        self,
        *,
        assignment_id: str,
        outcome: CaseWorkflowOutcome,
        created_at: str | None = None,
    ) -> WorkflowRunResponse:
        state = outcome.state
        now = _utc_now()
        created = created_at or now
        with self._connect() as conn:
            existing = conn.execute(
                self._sql("SELECT created_at FROM case_workflow_runs WHERE workflow_run_id = ?"),
                (state["workflow_run_id"],),
            ).fetchone()
            if existing is not None:
                created = str(_row(existing)["created_at"])
                conn.execute(
                    self._sql(
                        "UPDATE case_workflow_runs SET status = ?, current_stage = ?, state_json = ?, "
                        "updated_at = ? WHERE workflow_run_id = ?"
                    ),
                    (
                        state["status"],
                        state["stage"],
                        json.dumps(state, ensure_ascii=False, sort_keys=True),
                        now,
                        state["workflow_run_id"],
                    ),
                )
            else:
                conn.execute(
                    self._sql(
                        """
                        INSERT INTO case_workflow_runs(
                            workflow_run_id, correlation_id, case_id, session_id, user_id,
                            jurisdiction, case_type_key, assignment_id, graph_key, graph_version,
                            flow_key, flow_version, status, current_stage, state_json, created_at,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """
                    ),
                    (
                        state["workflow_run_id"],
                        state["correlation_id"],
                        state.get("case_id", ""),
                        state.get("session_id", ""),
                        state.get("user_id", ""),
                        state.get("jurisdiction", ""),
                        state["case_type_key"],
                        assignment_id,
                        state["graph_key"],
                        state["graph_version"],
                        state["flow_key"],
                        state["flow_version"],
                        state["status"],
                        state["stage"],
                        json.dumps(state, ensure_ascii=False, sort_keys=True),
                        created,
                        now,
                    ),
                )
            for event in state.get("events", []):
                conn.execute(
                    self._sql(
                        """
                        INSERT INTO case_workflow_events(
                            event_id, workflow_run_id, correlation_id, event_type, stage,
                            status, details_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(event_id) DO NOTHING
                        """
                    ),
                    (
                        event["event_id"],
                        state["workflow_run_id"],
                        state["correlation_id"],
                        event["event_type"],
                        event["stage"],
                        event["status"],
                        json.dumps(event["details"], ensure_ascii=False, sort_keys=True),
                        event["created_at"],
                    ),
                )
            conn.commit()
        return self.get_run(state["workflow_run_id"], user_id=state.get("user_id", ""))

    def get_run_state(self, workflow_run_id: str, *, user_id: str) -> CaseWorkflowState:
        row = self._get_run_row(workflow_run_id, user_id=user_id)
        return CaseWorkflowState(**json.loads(str(row["state_json"])))

    def get_run(self, workflow_run_id: str, *, user_id: str) -> WorkflowRunResponse:
        row = self._get_run_row(workflow_run_id, user_id=user_id)
        state = json.loads(str(row["state_json"]))
        return WorkflowRunResponse(
            workflow_run_id=str(row["workflow_run_id"]),
            correlation_id=str(row["correlation_id"]),
            case_id=str(row["case_id"]),
            session_id=str(row["session_id"]),
            user_id=str(row["user_id"]),
            jurisdiction=str(row["jurisdiction"]),
            case_type_key=str(row["case_type_key"]),
            assignment_id=str(row["assignment_id"]),
            graph_key=str(row["graph_key"]),
            graph_version=int(row["graph_version"]),
            flow_key=str(row["flow_key"]),
            flow_version=int(row["flow_version"]),
            status=cast(
                Literal[
                    "running",
                    "waiting_for_user",
                    "completed",
                    "human_review_required",
                    "blocked",
                ],
                str(row["status"]),
            ),
            current_stage=str(row["current_stage"]),
            pending_action=dict(state.get("pending_action", {})),
            final_answer=str(state.get("final_answer", "")),
            artifacts=list(state.get("artifacts", [])),
            review_decisions=dict(state.get("review_decisions", {})),
            escalation_reason=str(state.get("escalation_reason", "")),
            created_at=_datetime(str(row["created_at"])),
            updated_at=_datetime(str(row["updated_at"])),
        )

    def get_latest_run_for_session(
        self, *, session_id: str, user_id: str
    ) -> WorkflowRunResponse | None:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT workflow_run_id FROM case_workflow_runs "
                    "WHERE session_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 1"
                ),
                (session_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return self.get_run(str(_row(row)["workflow_run_id"]), user_id=user_id)

    def get_latest_run_for_case(
        self, *, case_id: str, user_id: str
    ) -> WorkflowRunResponse | None:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT workflow_run_id FROM case_workflow_runs "
                    "WHERE case_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 1"
                ),
                (case_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return self.get_run(str(_row(row)["workflow_run_id"]), user_id=user_id)

    def list_events(self, workflow_run_id: str, *, user_id: str) -> list[WorkflowEventResponse]:
        self._get_run_row(workflow_run_id, user_id=user_id)
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT * FROM case_workflow_events WHERE workflow_run_id = ? ORDER BY created_at"
                ),
                (workflow_run_id,),
            ).fetchall()
        return [_event(_row(row)) for row in rows]

    def delete_case_workflows(self, *, case_id: str, user_id: str) -> int:
        """Delete case-scoped workflow state/checkpoints after authorized case deletion."""
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT workflow_run_id FROM case_workflow_runs WHERE case_id = ? AND user_id = ?"
                ),
                (case_id, user_id),
            ).fetchall()
            run_ids = [str(_row(row)["workflow_run_id"]) for row in rows]
            for run_id in run_ids:
                conn.execute(
                    self._sql("DELETE FROM case_workflow_events WHERE workflow_run_id = ?"),
                    (run_id,),
                )
                if self._is_postgres:
                    conn.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (run_id,))
                    conn.execute("DELETE FROM checkpoints WHERE thread_id = %s", (run_id,))
                    conn.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (run_id,))
            conn.execute(
                self._sql("DELETE FROM case_workflow_runs WHERE case_id = ? AND user_id = ?"),
                (case_id, user_id),
            )
            conn.commit()
        return len(run_ids)

    def _get_run_row(self, workflow_run_id: str, *, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT * FROM case_workflow_runs WHERE workflow_run_id = ?"),
                (workflow_run_id,),
            ).fetchone()
        if row is None:
            raise WorkflowRunNotFoundError(f"Workflow run {workflow_run_id} was not found")
        mapped = _row(row)
        if str(mapped["user_id"]) != user_id:
            raise WorkflowOwnershipError("Workflow run is not available to this user")
        return mapped

    def _initialize(self) -> None:
        schema = (
            Path(__file__).resolve().parents[4] / "databases" / "api" / "case_workflows_schema.sql"
        ).read_text(encoding="utf-8")
        with self._connect() as conn:
            if self._is_postgres:
                for statement in (item.strip() for item in schema.split(";")):
                    if statement:
                        conn.execute(statement)
            else:
                conn.executescript(schema)
            conn.commit()

    @property
    def _is_postgres(self) -> bool:
        return self._config.db_option in {"postgres", "azure"}

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self._is_postgres:
            import psycopg
            from psycopg.rows import dict_row

            if not self._config.db_cloud:
                raise RuntimeError("DB_CLOUD is required for PostgreSQL workflow persistence")
            with psycopg.connect(self._config.db_cloud, row_factory=dict_row) as pg_conn:
                yield pg_conn
            return
        sqlite_conn = sqlite3.connect(self._config.sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        try:
            yield sqlite_conn
        finally:
            sqlite_conn.close()

    def _sql(self, value: str) -> str:
        return value.replace("?", "%s") if self._is_postgres else value


def _assignment(row: dict[str, Any]) -> WorkflowAssignmentResponse:
    return WorkflowAssignmentResponse(
        assignment_id=str(row["assignment_id"]),
        case_type_key=str(row["case_type_key"]),
        jurisdiction=str(row["jurisdiction"]),
        graph_key=str(row["graph_key"]),
        graph_version=int(row["graph_version"]),
        flow_key=str(row["flow_key"]),
        flow_version=int(row["flow_version"]),
        is_active=bool(row["is_active"]),
        validation_status=str(row["validation_status"]),
        validation_message=str(row["validation_message"]),
        effective_from=_datetime(str(row["effective_from"])),
        effective_to=_datetime(str(row["effective_to"])) if row["effective_to"] else None,
        created_by=str(row["created_by"]),
        created_at=_datetime(str(row["created_at"])),
        supersedes_assignment_id=(
            str(row["supersedes_assignment_id"]) if row["supersedes_assignment_id"] else None
        ),
    )


def _event(row: dict[str, Any]) -> WorkflowEventResponse:
    return WorkflowEventResponse(
        event_id=str(row["event_id"]),
        workflow_run_id=str(row["workflow_run_id"]),
        correlation_id=str(row["correlation_id"]),
        event_type=str(row["event_type"]),
        stage=str(row["stage"]),
        status=str(row["status"]),
        details=json.loads(str(row["details_json"])),
        created_at=_datetime(str(row["created_at"])),
    )


def _row(value: Any) -> dict[str, Any]:
    return dict(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
