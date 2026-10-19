"""Encrypt LangGraph values, including primitives otherwise inlined by PostgresSaver."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import json
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from aijurisdictionagents.api_db import ApiDatabaseStore

_scope: ContextVar[str] = ContextVar("checkpoint_case_scope")


@dataclass
class _PrivateValue:
    value: Any


class CaseCheckpointSerializer:
    def __init__(self, store: ApiDatabaseStore) -> None:
        self.store = store
        self.inner = JsonPlusSerializer()

    def dumps_typed(self, value: Any) -> tuple[str, bytes]:
        if isinstance(value, _PrivateValue):
            value = value.value
        kind, payload = self.inner.dumps_typed(value)
        scope = _scope.get()
        if self.store.case_cipher is None:
            raise RuntimeError("Checkpoint encryption key required")
        encrypted = self.store.case_cipher.encrypt(scope, "checkpoint:" + kind, payload)
        return "case-encrypted-v1", json.dumps([scope, kind, encrypted]).encode()

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        if data[0] != "case-encrypted-v1" or self.store.case_cipher is None:
            raise RuntimeError("Legacy checkpoint requires encrypted migration")
        scope, kind, encrypted = json.loads(data[1])
        payload = self.store.case_cipher.decrypt(scope, "checkpoint:" + kind, encrypted)
        return self.inner.loads_typed((kind, payload))


class EncryptedPostgresSaver(PostgresSaver):
    def __init__(self, pool: Any, store: ApiDatabaseStore) -> None:
        super().__init__(pool, serde=CaseCheckpointSerializer(store))
        self.store = store

    def _case_scope(self, thread_id: str, values: dict[str, Any] | None = None) -> str:
        values = values or {}
        initial = values.get("__start__")
        case_id = str(values.get("case_id") or (initial.get("case_id") if isinstance(initial, dict) else "") or "")
        with self.store._connect() as conn:
            if case_id:
                self.store._execute(conn, "INSERT INTO case_workflow_encryption_scopes(thread_id, case_id) VALUES (?, ?) ON CONFLICT(thread_id) DO NOTHING", (thread_id, case_id))
            row = self.store._fetchone(conn, "SELECT case_id FROM case_workflow_encryption_scopes WHERE thread_id = ?", (thread_id,))
        if row:
            if case_id and row[0] != case_id:
                raise RuntimeError("Checkpoint case ownership cannot change")
            return str(row[0])
        # Workflows without a case still have an isolated encrypted scope.
        return "workflow:" + thread_id

    def put(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        scope = self._case_scope(str(config["configurable"]["thread_id"]), checkpoint["channel_values"])
        token = _scope.set(scope)
        try:
            protected: Any = dict(checkpoint)
            protected["channel_values"] = {key: _PrivateValue(value) for key, value in checkpoint["channel_values"].items()}
            # Checkpoint metadata is operational only. Do not duplicate input/output
            # values or arbitrary caller metadata in its unencrypted JSONB column.
            safe_metadata: Any = {key: metadata[key] for key in ("source", "step", "parents") if key in metadata}
            safe_config: Any = {"configurable": {key: value for key, value in config["configurable"].items() if key in {"thread_id", "checkpoint_ns", "checkpoint_id"}}}
            return super().put(safe_config, protected, safe_metadata, new_versions)
        finally:
            _scope.reset(token)

    def put_writes(self, config: Any, writes: Any, task_id: str, task_path: str = "") -> None:
        token = _scope.set(self._case_scope(str(config["configurable"]["thread_id"])))
        try:
            super().put_writes(config, writes, task_id, task_path)
        finally:
            _scope.reset(token)
