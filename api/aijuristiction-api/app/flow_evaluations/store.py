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
    ProductionApprovalResponse,
)
from app.flow_packs.store import FlowPackStoreConfig


class EvaluationNotFoundError(KeyError):
    pass


class EvaluationConflictError(ValueError):
    pass


class FlowEvaluationStore:
    def __init__(self, config: FlowPackStoreConfig) -> None:
        self._config = config
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
            conn.commit()

    @classmethod
    def from_env(cls) -> "FlowEvaluationStore":
        config = ApiDataConfig.from_env()
        configured = os.getenv("API_FLOW_PACKS_SQLITE_PATH", "").strip()
        repo_root = Path(__file__).resolve().parents[4]
        path = Path(configured) if configured else (
            repo_root / "runs" / "storage" / "api" / "sqlite" / "flow_packs.sqlite3"
        )
        return cls(FlowPackStoreConfig(config.db_option, config.db_cloud, path))

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
                        "UPDATE flow_packs SET lifecycle_state = 'production_approved', updated_at = ? "
                        "WHERE flow_id = ? AND lifecycle_state = 'test_passed' AND definition_hash = ?"
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
                    raise EvaluationConflictError("This immutable flow definition is already approved") from exc
                raise
        return ProductionApprovalResponse(
            approval_id=approval_id, flow_id=flow_id, run_id=run.run_id,
            definition_hash=run.flow_definition_hash, approved_by=actor_id,
            reason=reason.strip(), approved_at=_datetime(approved_at),
        )

    def purge_expired(self) -> int:
        now = _utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                self._sql("DELETE FROM flow_evaluation_runs WHERE expires_at < ?"), self._params(now)
            )
            conn.commit()
            return int(cursor.rowcount)

    def expiry(self, retention_days: int) -> str:
        return (datetime.now(timezone.utc) + timedelta(days=retention_days)).isoformat()

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


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _mapping(row: Any) -> dict[str, Any]:
    return dict(row)
