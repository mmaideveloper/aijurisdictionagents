from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from .schemas import Message
from .observability_decision_trace import (
    DecisionRecord,
    OrchestrationTraceEnvelope,
    serialize_decision_trace,
)


def create_run_dir(base_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def setup_logging(run_dir: Path, log_level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("aijurisdictionagents")
    if logger.handlers:
        return logger

    level = _parse_log_level(log_level)
    logger.setLevel(level)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def _parse_log_level(log_level: str) -> int:
    candidate = (log_level or "INFO").upper()
    return getattr(logging, candidate, logging.INFO)


class TraceRecorder:
    """Local privacy-safe trace sink.

    Legacy callers may keep using ``record_event`` while all payloads pass a
    narrow event allowlist. ``record_message`` intentionally stores metadata
    only; raw content and source snippets are never written.
    """

    def __init__(self, run_dir: Path, *, session_id: str | None = None) -> None:
        self.run_dir = run_dir
        self.trace_path = run_dir / "trace.jsonl"
        self._handle = self.trace_path.open("a", encoding="utf-8")
        self._session_id = session_id or f"local-{uuid4()}"
        self._correlation_id = f"local-{uuid4()}"

    def bind_context(self, *, session_id: str, correlation_id: str | None = None) -> None:
        if not session_id.strip():
            raise ValueError("session_id is required for decision tracing")
        self._session_id = session_id.strip()
        if correlation_id:
            self._correlation_id = correlation_id.strip()

    def record_message(self, message: Message) -> None:
        self.record_event(
            "message_metadata",
            {
                "role": message.role,
                "agent_name": message.agent_name,
                "source_count": len(message.sources),
            },
        )

    def record_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **_sanitize_legacy_event(event_type, payload),
        }
        try:
            self._handle.write(json.dumps(record, ensure_ascii=True) + "\n")
            self._handle.flush()
        except OSError:
            logging.getLogger(__name__).warning(
                "Optional local trace sink unavailable correlation_id=%s",
                self._correlation_id,
            )
        decision = _legacy_event_decision(
            event_type=event_type,
            payload=payload,
            session_id=self._session_id,
            correlation_id=self._correlation_id,
        )
        if decision is not None:
            try:
                self.record_decision(decision)
            except (OSError, ValueError):
                logging.getLogger(__name__).warning(
                    "Optional decision trace sink unavailable correlation_id=%s",
                    self._correlation_id,
                )

    def record_decision(self, trace: OrchestrationTraceEnvelope) -> None:
        record = {"type": "orchestration_decision", **serialize_decision_trace(trace)}
        self._handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


_LEGACY_EVENT_ALLOWLIST: dict[str, frozenset[str]] = {
    "case_context": frozenset({"country", "output_language", "discussion_type"}),
    "message_metadata": frozenset({"role", "agent_name", "source_count"}),
    "discussion_timeout": frozenset({"max_minutes"}),
    "user_timeout": frozenset({"timeout_seconds"}),
    "user_followup_timeout": frozenset({"timeout_seconds"}),
    "user_judge_review_timeout": frozenset({"timeout_seconds"}),
    "judge_decision": frozenset({"decision"}),
    "discussion_finished": frozenset({"reason"}),
    "result": frozenset({"citation_count"}),
}


def _sanitize_legacy_event(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    allowed = _LEGACY_EVENT_ALLOWLIST.get(event_type, frozenset())
    sanitized: Dict[str, Any] = {}
    for key in allowed:
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
    if event_type == "result":
        sanitized["citation_count"] = int(payload.get("citation_count", 0))
    return sanitized


def _legacy_event_decision(
    *, event_type: str, payload: Dict[str, Any], session_id: str, correlation_id: str
) -> OrchestrationTraceEnvelope | None:
    mapping = {
        "case_context": ("workflow_routing", "discussion_mode_selected", "running"),
        "discussion_timeout": ("workflow_timeout", "discussion_time_limit", "timed_out"),
        "user_timeout": ("workflow_timeout", "user_response_timeout", "timed_out"),
        "user_followup_timeout": ("workflow_timeout", "followup_timeout", "timed_out"),
        "user_judge_review_timeout": ("workflow_timeout", "judge_review_timeout", "timed_out"),
        "judge_decision": ("output_verification", "judge_decision_recorded", "completed"),
        "discussion_finished": ("final_disposition", "user_finished", "cancelled"),
        "result": ("final_disposition", "answer_finalized", "completed"),
    }
    if event_type not in mapping:
        return None
    decision_type, reason_code, status = mapping[event_type]
    selected = str(
        payload.get("decision")
        or payload.get("discussion_type")
        or ("completed" if event_type == "result" else status)
    )
    return OrchestrationTraceEnvelope(
        event_id=str(uuid4()),
        session_id=session_id,
        correlation_id=correlation_id,
        stage="legacy_orchestrator",
        actor="model" if event_type == "judge_decision" else "orchestrator",
        event_type=event_type,
        status=status,  # type: ignore[arg-type]
        orchestrator_version="legacy-v1",
        decision=DecisionRecord(
            decision_type=decision_type,
            policy_id="legacy-orchestrator",
            policy_version="1",
            selected_outcome=selected,
            reason_code=reason_code,
            escalation=selected == "rejected",
            human_review_required=selected == "rejected",
        ),
    )
