from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Literal, cast
from uuid import uuid4

from aijurisdictionagents.api_db.config import ApiDataConfig

from app.flow_evaluations.models import (
    EvaluationRunResponse,
    EvaluationSuiteCreate,
    EvaluationSuiteResponse,
    FlowPromotionResponse,
    PromotionApprovalSummary,
    ProductionApprovalResponse,
)
from app.flow_packs.store import FlowPackStoreConfig
from app.case_workflows.models import WorkflowAssignmentResponse


class EvaluationNotFoundError(KeyError):
    pass


class EvaluationConflictError(ValueError):
    pass


class FlowEvaluationStore:
    def __init__(
        self,
        config: FlowPackStoreConfig,
        *,
        assignment_sqlite_path: Path | None = None,
    ) -> None:
        self._config = config
        repo_root = Path(__file__).resolve().parents[4]
        self._assignment_sqlite_path = assignment_sqlite_path or (
            repo_root / "runs" / "storage" / "api" / "sqlite" / "case_workflows.sqlite3"
        )
        self._config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            sql = _schema_sql()
            if self._is_postgres:
                for statement in (part.strip() for part in sql.split(";")):
                    if statement:
                        conn.execute(statement)
            else:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.executescript(sql)
            self._ensure_promotion_columns(conn)
            conn.commit()

    @classmethod
    def from_env(cls) -> "FlowEvaluationStore":
        config = ApiDataConfig.from_env()
        configured = os.getenv("API_FLOW_PACKS_SQLITE_PATH", "").strip()
        repo_root = Path(__file__).resolve().parents[4]
        path = Path(configured) if configured else (
            repo_root / "runs" / "storage" / "api" / "sqlite" / "flow_packs.sqlite3"
        )
        configured_assignments = os.getenv("API_CASE_WORKFLOWS_SQLITE_PATH", "").strip()
        assignment_path = Path(configured_assignments) if configured_assignments else (
            repo_root / "runs" / "storage" / "api" / "sqlite" / "case_workflows.sqlite3"
        )
        return cls(
            FlowPackStoreConfig(config.db_option, config.db_cloud, path),
            assignment_sqlite_path=assignment_path,
        )

    def create_suite(self, payload: EvaluationSuiteCreate, *, actor_id: str) -> EvaluationSuiteResponse:
        canonical_payload = payload.model_dump(exclude={"synthetic_data_confirmed"})
        suite_hash = _hash(canonical_payload)
        suite_id = str(uuid4())
        now = _utc_now()
        with self._connect() as conn:
            try:
                conn.execute(
                    self._sql(
                        "INSERT INTO flow_evaluation_suites "
                        "(suite_id, suite_key, version, jurisdiction, title, synthetic_only, "
                        "routing_accuracy_threshold, retention_days, suite_hash, created_by, created_at) "
                        "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)"
                    ),
                    self._params(
                        suite_id, payload.suite_key.strip(), payload.version,
                        payload.jurisdiction.strip().upper(), payload.title.strip(),
                        payload.routing_accuracy_threshold, payload.retention_days,
                        suite_hash, actor_id, now,
                    ),
                )
                for case in payload.cases:
                    case_json = json.dumps(case.synthetic_input, ensure_ascii=False, sort_keys=True)
                    conn.execute(
                        self._sql(
                            "INSERT INTO flow_evaluation_cases "
                            "(case_id, suite_id, case_key, mode, synthetic_input_json, input_hash, "
                            "expected_route, required_source_ids_json, human_review_required) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                        ),
                        self._params(
                            str(uuid4()), suite_id, case.case_key.strip(), case.mode,
                            case_json, _hash(case.synthetic_input), case.expected_route.strip(),
                            json.dumps(case.required_source_ids, sort_keys=True),
                            1 if case.human_review_required else 0,
                        ),
                    )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                    raise EvaluationConflictError("Evaluation suite version or case key already exists") from exc
                raise
        return self.get_suite(suite_id)

    def get_suite(self, suite_id: str) -> EvaluationSuiteResponse:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT s.*, COUNT(c.case_id) AS case_count FROM flow_evaluation_suites s "
                    "LEFT JOIN flow_evaluation_cases c ON c.suite_id = s.suite_id "
                    "WHERE s.suite_id = ? GROUP BY s.suite_id"
                ), self._params(suite_id),
            ).fetchone()
        if row is None:
            raise EvaluationNotFoundError(f"Evaluation suite '{suite_id}' was not found")
        item = _mapping(row)
        return EvaluationSuiteResponse(
            suite_id=str(item["suite_id"]), suite_key=str(item["suite_key"]),
            version=int(item["version"]), jurisdiction=str(item["jurisdiction"]),
            title=str(item["title"]), synthetic_only=bool(item["synthetic_only"]),
            routing_accuracy_threshold=float(item["routing_accuracy_threshold"]),
            retention_days=int(item["retention_days"]), suite_hash=str(item["suite_hash"]),
            case_count=int(item["case_count"]), created_by=str(item["created_by"]),
            created_at=_datetime(str(item["created_at"])),
        )

    def get_cases(self, suite_id: str, *, mode: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                self._sql("SELECT * FROM flow_evaluation_cases WHERE suite_id = ? AND mode = ? ORDER BY case_key"),
                self._params(suite_id, mode),
            ).fetchall()
        return [_mapping(row) for row in rows]

    def get_run_by_idempotency_key(self, key: str) -> EvaluationRunResponse | None:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT * FROM flow_evaluation_runs WHERE idempotency_key = ?"),
                self._params(key),
            ).fetchone()
        return self._run_response(_mapping(row)) if row else None

    def get_run(self, run_id: str) -> EvaluationRunResponse:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT * FROM flow_evaluation_runs WHERE run_id = ?"), self._params(run_id)
            ).fetchone()
        if row is None:
            raise EvaluationNotFoundError(f"Evaluation run '{run_id}' was not found")
        return self._run_response(_mapping(row))

    def get_latest_run_for_flow(self, flow_id: str) -> EvaluationRunResponse | None:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT * FROM flow_evaluation_runs WHERE flow_id = ? "
                    "ORDER BY created_at DESC, run_id DESC LIMIT 1"
                ), self._params(flow_id),
            ).fetchone()
        return self._run_response(_mapping(row)) if row else None

    def record_run(self, *, values: dict[str, Any], results: list[dict[str, Any]]) -> EvaluationRunResponse:
        with self._connect() as conn:
            try:
                conn.execute(
                    self._sql(
                        "INSERT INTO flow_evaluation_runs "
                        "(run_id, idempotency_key, synthetic_run_id, suite_id, suite_key, suite_version, suite_hash, flow_id, "
                        "flow_key, flow_version, flow_definition_hash, graph_version, routing_policy_json, "
                        "routing_policy_hash, provider, model, provider_route, mode, status, metrics_json, "
                        "gates_json, created_by, created_at, expires_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    self._params(*(values[name] for name in (
                        "run_id", "idempotency_key", "synthetic_run_id", "suite_id", "suite_key",
                        "suite_version", "suite_hash",
                        "flow_id", "flow_key", "flow_version", "flow_definition_hash", "graph_version",
                        "routing_policy_json", "routing_policy_hash", "provider", "model", "provider_route",
                        "mode", "status", "metrics_json", "gates_json", "created_by", "created_at", "expires_at",
                    ))),
                )
                for result in results:
                    conn.execute(
                        self._sql(
                            "INSERT INTO flow_evaluation_results "
                            "(result_id, run_id, case_id, actual_route, source_ids_json, schema_valid, "
                            "provenance_valid, privacy_violation_count, unsupported_auto_finalization, "
                            "human_review_present, passed, reason_codes_json) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                        ), self._params(*(result[name] for name in (
                            "result_id", "run_id", "case_id", "actual_route", "source_ids_json",
                            "schema_valid", "provenance_valid", "privacy_violation_count",
                            "unsupported_auto_finalization", "human_review_present", "passed",
                            "reason_codes_json",
                        ))),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self.get_run(str(values["run_id"]))

    def create_approval(
        self, *, flow_id: str, run: EvaluationRunResponse, actor_id: str, reason: str
    ) -> ProductionApprovalResponse:
        approval_id = str(uuid4())
        approved_at = _utc_now()
        with self._connect() as conn:
            try:
                lock = " FOR UPDATE" if self._is_postgres else ""
                existing = conn.execute(
                    self._sql(
                        "SELECT approval_id, run_id FROM flow_evaluation_approvals "
                        "WHERE flow_id = ? AND definition_hash = ?" + lock
                    ),
                    self._params(flow_id, run.flow_definition_hash),
                ).fetchone()
                if existing is not None:
                    existing_item = _mapping(existing)
                    if str(existing_item["run_id"]) == run.run_id:
                        raise EvaluationConflictError("This evaluation run is already approved")
                    approval_id = str(existing_item["approval_id"])
                    conn.execute(
                        self._sql(
                            "UPDATE flow_evaluation_approvals SET run_id = ?, approved_by = ?, "
                            "reason = ?, approved_at = ? WHERE approval_id = ?"
                        ),
                        self._params(
                            run.run_id, actor_id, reason.strip(), approved_at, approval_id
                        ),
                    )
                else:
                    conn.execute(
                        self._sql(
                            "INSERT INTO flow_evaluation_approvals "
                            "(approval_id, flow_id, run_id, definition_hash, approved_by, reason, approved_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)"
                        ), self._params(
                            approval_id, flow_id, run.run_id, run.flow_definition_hash,
                            actor_id, reason.strip(), approved_at,
                        ),
                    )
                cursor = conn.execute(
                    self._sql(
                        "UPDATE flow_packs SET lifecycle_state = CASE "
                        "WHEN lifecycle_state = 'test_passed' THEN 'production_approved' "
                        "ELSE lifecycle_state END, updated_at = ? WHERE flow_id = ? "
                        "AND lifecycle_state IN ('test_passed', 'published') AND definition_hash = ?"
                    ),
                    self._params(approved_at, flow_id, run.flow_definition_hash),
                )
                if cursor.rowcount != 1:
                    raise EvaluationConflictError(
                        "Flow state or definition changed before production approval"
                    )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                if isinstance(exc, EvaluationConflictError):
                    raise
                if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                    raise EvaluationConflictError("This evaluation run is already approved") from exc
                raise
        return ProductionApprovalResponse(
            approval_id=approval_id, flow_id=flow_id, run_id=run.run_id,
            definition_hash=run.flow_definition_hash, approved_by=actor_id,
            reason=reason.strip(), approved_at=_datetime(approved_at),
        )

    def get_latest_approval_for_flow(self, flow_id: str) -> PromotionApprovalSummary | None:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT a.approval_id, a.run_id, a.definition_hash, a.approved_by, "
                    "a.reason AS approval_reason, a.approved_at, r.expires_at AS run_expires_at, "
                    "r.suite_key, r.suite_version, r.suite_hash, r.graph_version, "
                    "r.routing_policy_hash, r.provider, r.model, r.provider_route, r.gates_json "
                    "FROM flow_evaluation_approvals a "
                    "JOIN flow_evaluation_runs r ON r.run_id = a.run_id "
                    "WHERE a.flow_id = ? ORDER BY a.approved_at DESC, a.approval_id DESC LIMIT 1"
                ),
                self._params(flow_id),
            ).fetchone()
        return self._approval_summary(_mapping(row)) if row else None

    def get_promotion_by_idempotency_key(self, key: str) -> FlowPromotionResponse | None:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT promotion_id FROM flow_promotion_provenance WHERE idempotency_key = ?"),
                self._params(key),
            ).fetchone()
        return self.get_promotion(str(_mapping(row)["promotion_id"])) if row else None

    def get_promotion(self, promotion_id: str) -> FlowPromotionResponse:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(self._promotion_select() + " WHERE p.promotion_id = ?"),
                self._params(promotion_id),
            ).fetchone()
        if row is None:
            raise EvaluationNotFoundError(f"Flow promotion '{promotion_id}' was not found")
        return self._promotion_response(_mapping(row))

    def list_promotions(
        self, *, jurisdiction: str | None = None, case_type_key: str | None = None
    ) -> list[FlowPromotionResponse]:
        clauses: list[str] = []
        params: list[object] = []
        if jurisdiction:
            clauses.append("p.jurisdiction = ?")
            params.append(jurisdiction.strip().upper())
        if case_type_key:
            clauses.append("p.case_type_key = ?")
            params.append(case_type_key.strip())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(self._promotion_select() + where + " ORDER BY p.promoted_at DESC"),
                self._params(*params),
            ).fetchall()
        return [self._promotion_response(_mapping(row)) for row in rows]

    def record_promotion(
        self,
        *,
        idempotency_key: str,
        request_hash: str,
        action: Literal["promote", "rollback"],
        flow_id: str,
        approval_id: str,
        case_type_key: str,
        jurisdiction: str,
        graph_key: str,
        graph_version: int,
        flow_key: str,
        flow_version: int,
        actor_id: str,
        reason: str,
        expected_current_assignment_id: str | None,
        rollback_of_promotion_id: str | None = None,
    ) -> FlowPromotionResponse:
        promotion_id = str(uuid4())
        assignment_id = str(uuid4())
        now = _utc_now()
        retention_until = (
            datetime.now(timezone.utc) + timedelta(days=2190)
        ).isoformat()
        normalized_jurisdiction = jurisdiction.strip().upper()
        with self._promotion_connection() as (conn, assignment_table):
            try:
                if not self._is_postgres:
                    conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    self._sql(
                        "SELECT promotion_id, request_hash FROM flow_promotion_provenance "
                        "WHERE idempotency_key = ?"
                    ),
                    self._params(idempotency_key),
                ).fetchone()
                if existing is not None:
                    existing_item = _mapping(existing)
                    if str(existing_item["request_hash"]) != request_hash:
                        raise EvaluationConflictError(
                            "Idempotency key was already used for a different promotion request"
                        )
                    conn.commit()
                    return self.get_promotion(str(existing_item["promotion_id"]))

                lock = " FOR UPDATE" if self._is_postgres else ""
                candidate = conn.execute(
                    self._sql(
                        "SELECT f.flow_id, f.flow_key, f.version AS flow_version, f.jurisdiction, "
                        "f.definition_hash AS current_definition_hash, f.lifecycle_state, f.is_deleted, "
                        "a.approval_id, a.run_id, a.definition_hash, r.status AS run_status, "
                        "a.approved_by, a.reason AS approval_reason, a.approved_at, "
                        "r.expires_at, r.graph_version AS tested_graph_version, r.gates_json "
                        "FROM flow_packs f JOIN flow_evaluation_approvals a ON a.flow_id = f.flow_id "
                        "JOIN flow_evaluation_runs r ON r.run_id = a.run_id "
                        "WHERE f.flow_id = ? AND a.approval_id = ?" + lock
                    ),
                    self._params(flow_id, approval_id),
                ).fetchone()
                if candidate is None:
                    raise EvaluationConflictError("Production approval does not belong to this flow version")
                candidate_item = _mapping(candidate)
                self._validate_promotion_candidate(
                    candidate_item,
                    flow_key=flow_key,
                    flow_version=flow_version,
                    jurisdiction=normalized_jurisdiction,
                    graph_reference=f"{graph_key}@{graph_version}",
                    now=now,
                )

                current = conn.execute(
                    self._sql(
                        f"SELECT * FROM {assignment_table} WHERE case_type_key = ? "
                        "AND jurisdiction = ? AND is_active = 1" + lock
                    ),
                    self._params(case_type_key.strip(), normalized_jurisdiction),
                ).fetchone()
                current_item = _mapping(current) if current else None
                current_id = str(current_item["assignment_id"]) if current_item else None
                if current_id != expected_current_assignment_id:
                    raise EvaluationConflictError(
                        "Active assignment changed after preview; refresh and review the impact again"
                    )
                if current_item and (
                    str(current_item["graph_key"]) == graph_key
                    and int(current_item["graph_version"]) == graph_version
                    and str(current_item["flow_key"]) == flow_key
                    and int(current_item["flow_version"]) == flow_version
                ):
                    raise EvaluationConflictError("This exact workflow version is already active")

                if current_item:
                    conn.execute(
                        self._sql(
                            f"UPDATE {assignment_table} SET is_active = 0, effective_to = ? "
                            "WHERE assignment_id = ? AND is_active = 1"
                        ),
                        self._params(now, current_id),
                    )
                conn.execute(
                    self._sql(
                        f"INSERT INTO {assignment_table} (assignment_id, case_type_key, jurisdiction, "
                        "graph_key, graph_version, flow_key, flow_version, is_active, validation_status, "
                        "validation_message, effective_from, effective_to, created_by, created_at, "
                        "supersedes_assignment_id) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'valid', ?, ?, NULL, ?, ?, ?)"
                    ),
                    self._params(
                        assignment_id,
                        case_type_key.strip(),
                        normalized_jurisdiction,
                        graph_key,
                        graph_version,
                        flow_key,
                        flow_version,
                        "Approved immutable flow promotion",
                        now,
                        actor_id,
                        now,
                        current_id,
                    ),
                )
                conn.execute(
                    self._sql(
                        "UPDATE flow_packs SET lifecycle_state = 'published', is_enabled = 1, updated_at = ? "
                        "WHERE flow_id = ? AND lifecycle_state IN ('production_approved', 'published')"
                    ),
                    self._params(now, flow_id),
                )
                target_assignment = {
                    "assignment_id": assignment_id,
                    "case_type_key": case_type_key.strip(),
                    "jurisdiction": normalized_jurisdiction,
                    "graph_key": graph_key,
                    "graph_version": graph_version,
                    "flow_key": flow_key,
                    "flow_version": flow_version,
                    "is_active": True,
                    "validation_status": "valid",
                    "validation_message": "Approved immutable flow promotion",
                    "effective_from": now,
                    "effective_to": None,
                    "created_by": actor_id,
                    "created_at": now,
                    "supersedes_assignment_id": current_id,
                }
                target_json = json.dumps(target_assignment, ensure_ascii=False, sort_keys=True)
                prior_json = (
                    json.dumps(
                        self._assignment_response(current_item).model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    if current_item else None
                )
                conn.execute(
                    self._sql(
                        "INSERT INTO flow_promotion_provenance (promotion_id, idempotency_key, "
                        "request_hash, action, flow_id, approval_id, run_id, case_type_key, jurisdiction, "
                        "reason, prior_assignment_json, target_assignment_json, target_assignment_hash, "
                        "promoted_by, promoted_at, approved_by_snapshot, approval_reason_snapshot, "
                        "approved_at_snapshot, retention_until, rollback_of_promotion_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    self._params(
                        promotion_id,
                        idempotency_key,
                        request_hash,
                        action,
                        flow_id,
                        approval_id,
                        str(candidate_item["run_id"]),
                        case_type_key.strip(),
                        normalized_jurisdiction,
                        reason.strip(),
                        prior_json,
                        target_json,
                        _hash(target_assignment),
                        actor_id,
                        now,
                        str(candidate_item["approved_by"]),
                        str(candidate_item["approval_reason"]),
                        str(candidate_item["approved_at"]),
                        retention_until,
                        rollback_of_promotion_id,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self.get_promotion(promotion_id)

    def purge_expired(self) -> int:
        now = _utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                self._sql(
                    "DELETE FROM flow_evaluation_runs WHERE expires_at < ? AND NOT EXISTS "
                    "(SELECT 1 FROM flow_evaluation_approvals a "
                    "WHERE a.run_id = flow_evaluation_runs.run_id) AND NOT EXISTS "
                    "(SELECT 1 FROM flow_promotion_provenance p "
                    "WHERE p.run_id = flow_evaluation_runs.run_id)"
                ), self._params(now)
            )
            conn.commit()
            return int(cursor.rowcount)

    def purge_expired_promotions(self) -> int:
        now = _utc_now()
        deleted = 0
        with self._connect() as conn:
            while True:
                cursor = conn.execute(
                    self._sql(
                        "DELETE FROM flow_promotion_provenance WHERE retention_until < ? "
                        "AND NOT EXISTS (SELECT 1 FROM flow_promotion_provenance child "
                        "WHERE child.rollback_of_promotion_id = flow_promotion_provenance.promotion_id)"
                    ),
                    self._params(now),
                )
                count = int(cursor.rowcount)
                deleted += count
                if count == 0:
                    break
            conn.execute(
                self._sql(
                    "DELETE FROM flow_evaluation_approvals WHERE NOT EXISTS "
                    "(SELECT 1 FROM flow_promotion_provenance p "
                    "WHERE p.approval_id = flow_evaluation_approvals.approval_id) "
                    "AND EXISTS (SELECT 1 FROM flow_evaluation_runs r "
                    "WHERE r.run_id = flow_evaluation_approvals.run_id AND r.expires_at < ?)"
                ),
                self._params(now),
            )
            conn.commit()
        self.purge_expired()
        return deleted

    def expiry(self, retention_days: int) -> str:
        return (datetime.now(timezone.utc) + timedelta(days=retention_days)).isoformat()

    @contextmanager
    def _promotion_connection(self) -> Iterator[tuple[Any, str]]:
        with self._connect() as conn:
            assignment_table = "case_workflow_assignments"
            if not self._is_postgres:
                flow_path = self._config.sqlite_path.resolve()
                assignment_path = self._assignment_sqlite_path.resolve()
                if assignment_path != flow_path:
                    assignment_path.parent.mkdir(parents=True, exist_ok=True)
                    conn.execute("ATTACH DATABASE ? AS workflow", (str(assignment_path),))
                    assignment_table = "workflow.case_workflow_assignments"
            try:
                conn.execute(f"SELECT 1 FROM {assignment_table} LIMIT 1")
            except Exception as exc:
                raise EvaluationConflictError(
                    "Workflow assignment storage is not initialized for atomic promotion"
                ) from exc
            yield conn, assignment_table

    def _ensure_promotion_columns(self, conn: Any) -> None:
        columns = {
            "idempotency_key": "TEXT",
            "request_hash": "TEXT",
            "action": "TEXT",
            "run_id": "TEXT",
            "case_type_key": "TEXT",
            "jurisdiction": "TEXT",
            "reason": "TEXT",
            "retention_until": "TEXT",
            "approved_by_snapshot": "TEXT",
            "approval_reason_snapshot": "TEXT",
            "approved_at_snapshot": "TEXT",
        }
        if self._is_postgres:
            for name, sql_type in columns.items():
                conn.execute(
                    f"ALTER TABLE flow_promotion_provenance ADD COLUMN IF NOT EXISTS {name} {sql_type}"
                )
            conn.execute(
                "UPDATE flow_promotion_provenance AS promotion SET "
                "idempotency_key = COALESCE(promotion.idempotency_key, 'legacy-' || promotion.promotion_id), "
                "request_hash = COALESCE(promotion.request_hash, promotion.target_assignment_hash), "
                "action = COALESCE(promotion.action, CASE WHEN promotion.rollback_of_promotion_id IS NULL "
                "THEN 'promote' ELSE 'rollback' END), "
                "run_id = COALESCE(promotion.run_id, approval.run_id), "
                "case_type_key = COALESCE(promotion.case_type_key, "
                "promotion.target_assignment_json::jsonb ->> 'case_type_key', 'legacy-unknown'), "
                "jurisdiction = COALESCE(promotion.jurisdiction, "
                "promotion.target_assignment_json::jsonb ->> 'jurisdiction', 'UNKNOWN'), "
                "reason = COALESCE(promotion.reason, 'Migrated legacy promotion provenance'), "
                "approved_by_snapshot = COALESCE(promotion.approved_by_snapshot, approval.approved_by), "
                "approval_reason_snapshot = COALESCE(promotion.approval_reason_snapshot, approval.reason), "
                "approved_at_snapshot = COALESCE(promotion.approved_at_snapshot, approval.approved_at), "
                "retention_until = COALESCE(promotion.retention_until, "
                "(promotion.promoted_at::timestamptz + INTERVAL '6 years')::text) "
                "FROM flow_evaluation_approvals AS approval "
                "WHERE promotion.approval_id = approval.approval_id"
            )
        else:
            rows = conn.execute("PRAGMA table_info(flow_promotion_provenance)").fetchall()
            existing = {str(_mapping(row)["name"]) for row in rows}
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.execute(
                        f"ALTER TABLE flow_promotion_provenance ADD COLUMN {name} {sql_type}"
                    )
            conn.execute(
                "UPDATE flow_promotion_provenance SET "
                "idempotency_key = COALESCE(idempotency_key, 'legacy-' || promotion_id), "
                "request_hash = COALESCE(request_hash, target_assignment_hash), "
                "action = COALESCE(action, CASE WHEN rollback_of_promotion_id IS NULL "
                "THEN 'promote' ELSE 'rollback' END), "
                "run_id = COALESCE(run_id, (SELECT run_id FROM flow_evaluation_approvals "
                "WHERE approval_id = flow_promotion_provenance.approval_id)), "
                "case_type_key = COALESCE(case_type_key, "
                "json_extract(target_assignment_json, '$.case_type_key'), 'legacy-unknown'), "
                "jurisdiction = COALESCE(jurisdiction, "
                "json_extract(target_assignment_json, '$.jurisdiction'), 'UNKNOWN'), "
                "reason = COALESCE(reason, 'Migrated legacy promotion provenance'), "
                "approved_by_snapshot = COALESCE(approved_by_snapshot, (SELECT approved_by "
                "FROM flow_evaluation_approvals WHERE approval_id = flow_promotion_provenance.approval_id)), "
                "approval_reason_snapshot = COALESCE(approval_reason_snapshot, (SELECT reason "
                "FROM flow_evaluation_approvals WHERE approval_id = flow_promotion_provenance.approval_id)), "
                "approved_at_snapshot = COALESCE(approved_at_snapshot, (SELECT approved_at "
                "FROM flow_evaluation_approvals WHERE approval_id = flow_promotion_provenance.approval_id)), "
                "retention_until = COALESCE(retention_until, datetime(promoted_at, '+6 years'))"
            )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_flow_promotion_provenance_idempotency "
            "ON flow_promotion_provenance(idempotency_key)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_flow_promotion_provenance_assignment "
            "ON flow_promotion_provenance(jurisdiction, case_type_key, promoted_at)"
        )

    @staticmethod
    def _validate_promotion_candidate(
        item: dict[str, Any],
        *,
        flow_key: str,
        flow_version: int,
        jurisdiction: str,
        graph_reference: str,
        now: str,
    ) -> None:
        if (
            str(item["flow_key"]) != flow_key
            or int(item["flow_version"]) != flow_version
            or str(item["jurisdiction"]) != jurisdiction
        ):
            raise EvaluationConflictError("Promotion target does not match the approved flow version")
        if bool(item["is_deleted"]) or str(item["lifecycle_state"]) not in {
            "production_approved",
            "published",
        }:
            raise EvaluationConflictError("Flow version is not approved and publishable")
        if str(item["definition_hash"]) != str(item["current_definition_hash"]):
            raise EvaluationConflictError("Production approval is stale because the definition changed")
        if str(item["run_status"]) != "passed":
            raise EvaluationConflictError("Production approval does not reference a passing run")
        if _datetime(item["expires_at"]) <= _datetime(now):
            raise EvaluationConflictError("Production review expired; rerun and approve the evaluation")
        gates = json.loads(str(item["gates_json"]))
        if not gates or not all(bool(value) for value in gates.values()):
            raise EvaluationConflictError("One or more required evaluation gates are not passing")
        if str(item["tested_graph_version"]) != graph_reference:
            raise EvaluationConflictError("Requested graph differs from the tested graph version")

    @staticmethod
    def _approval_summary(item: dict[str, Any]) -> PromotionApprovalSummary:
        return PromotionApprovalSummary(
            approval_id=str(item["approval_id"]),
            run_id=str(item["run_id"]),
            definition_hash=str(item["definition_hash"]),
            approved_by=str(item["approved_by"]),
            approval_reason=str(item["approval_reason"]),
            approved_at=_datetime(item["approved_at"]),
            run_expires_at=_datetime(item["run_expires_at"]),
            suite_key=str(item["suite_key"]),
            suite_version=int(item["suite_version"]),
            suite_hash=str(item["suite_hash"]),
            graph_version=str(item["graph_version"]),
            routing_policy_hash=str(item["routing_policy_hash"]),
            provider=str(item["provider"]),
            model=str(item["model"]),
            provider_route=str(item["provider_route"]),
            gates=json.loads(str(item["gates_json"])),
        )

    @staticmethod
    def _assignment_response(item: dict[str, Any]) -> WorkflowAssignmentResponse:
        return WorkflowAssignmentResponse(
            assignment_id=str(item["assignment_id"]),
            case_type_key=str(item["case_type_key"]),
            jurisdiction=str(item["jurisdiction"]),
            graph_key=str(item["graph_key"]),
            graph_version=int(item["graph_version"]),
            flow_key=str(item["flow_key"]),
            flow_version=int(item["flow_version"]),
            is_active=bool(item["is_active"]),
            validation_status=str(item["validation_status"]),
            validation_message=str(item["validation_message"]),
            effective_from=_datetime(item["effective_from"]),
            effective_to=(
                _datetime(item["effective_to"]) if item.get("effective_to") else None
            ),
            created_by=str(item["created_by"]),
            created_at=_datetime(item["created_at"]),
            supersedes_assignment_id=(
                str(item["supersedes_assignment_id"])
                if item.get("supersedes_assignment_id") else None
            ),
        )

    @staticmethod
    def _promotion_select() -> str:
        return (
            "SELECT p.*, a.definition_hash, "
            "COALESCE(p.approved_by_snapshot, a.approved_by) AS approved_by, "
            "COALESCE(p.approval_reason_snapshot, a.reason) AS approval_reason, "
            "COALESCE(p.approved_at_snapshot, a.approved_at) AS approved_at, "
            "r.expires_at AS run_expires_at, r.suite_key, r.suite_version, "
            "r.suite_hash, r.graph_version, r.routing_policy_hash, r.provider, r.model, "
            "r.provider_route, r.gates_json FROM flow_promotion_provenance p "
            "JOIN flow_evaluation_approvals a ON a.approval_id = p.approval_id "
            "JOIN flow_evaluation_runs r ON r.run_id = p.run_id"
        )

    @classmethod
    def _promotion_response(cls, item: dict[str, Any]) -> FlowPromotionResponse:
        prior_raw = json.loads(str(item["prior_assignment_json"])) if item.get(
            "prior_assignment_json"
        ) else None
        target_raw = json.loads(str(item["target_assignment_json"]))
        return FlowPromotionResponse(
            promotion_id=str(item["promotion_id"]),
            idempotency_key=str(item["idempotency_key"]),
            action=cast(Literal["promote", "rollback"], str(item["action"])),
            request_hash=str(item["request_hash"]),
            flow_id=str(item["flow_id"]),
            approval=cls._approval_summary(item),
            prior_assignment=cls._assignment_response(prior_raw) if prior_raw else None,
            target_assignment=cls._assignment_response(target_raw),
            target_assignment_hash=str(item["target_assignment_hash"]),
            promoted_by=str(item["promoted_by"]),
            reason=str(item["reason"]),
            promoted_at=_datetime(item["promoted_at"]),
            retention_until=_datetime(item["retention_until"]),
            rollback_of_promotion_id=(
                str(item["rollback_of_promotion_id"])
                if item.get("rollback_of_promotion_id") else None
            ),
        )

    @staticmethod
    def _run_response(item: dict[str, Any]) -> EvaluationRunResponse:
        return EvaluationRunResponse(
            run_id=str(item["run_id"]), idempotency_key=str(item["idempotency_key"]),
            synthetic_run_id=str(item["synthetic_run_id"]), suite_id=str(item["suite_id"]),
            suite_key=str(item["suite_key"]), suite_version=int(item["suite_version"]),
            suite_hash=str(item["suite_hash"]), flow_id=str(item["flow_id"]),
            flow_key=str(item["flow_key"]), flow_version=int(item["flow_version"]),
            flow_definition_hash=str(item["flow_definition_hash"]),
            graph_version=str(item["graph_version"]), routing_policy_hash=str(item["routing_policy_hash"]),
            provider=str(item["provider"]), model=str(item["model"]),
            provider_route=str(item["provider_route"]),
            mode=cast(Literal["routing_only", "full_graph"], str(item["mode"])),
            status=cast(Literal["passed", "failed"], str(item["status"])),
            metrics=json.loads(str(item["metrics_json"])),
            gates=json.loads(str(item["gates_json"])), created_by=str(item["created_by"]),
            created_at=_datetime(str(item["created_at"])), expires_at=_datetime(str(item["expires_at"])),
        )

    @property
    def _is_postgres(self) -> bool:
        return self._config.db_option in {"postgres", "azure"}

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        conn: Any
        if self._is_postgres:
            import psycopg
            conn = psycopg.connect(self._config.db_cloud, row_factory=psycopg.rows.dict_row)
        else:
            conn = sqlite3.connect(self._config.sqlite_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _sql(self, query: str) -> str:
        return query.replace("?", "%s") if self._is_postgres else query

    @staticmethod
    def _params(*values: object) -> tuple[object, ...]:
        return tuple(values)


def _schema_sql() -> str:
    path = Path(__file__).resolve().parents[4] / "databases" / "api" / "flow_evaluations_schema.sql"
    return path.read_text(encoding="utf-8")


def _hash(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _mapping(row: Any) -> dict[str, Any]:
    return dict(row)
