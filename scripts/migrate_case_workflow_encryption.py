"""Offline PostgreSQL migration for private workflow/trace/checkpoint payloads.

Run after migrate_case_encryption.py with API and workers stopped. Resumable;
existing encrypted values are verified, never treated as plaintext.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api/aijuristiction-api"))


def migrate(store):
    from app.case_workflows.store import _protect_json, _read_json
    from app.case_workflows.encrypted_checkpoints import CaseCheckpointSerializer, _scope
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    if not store.uses_postgres or store.case_cipher is None:
        raise RuntimeError("Encrypted PostgreSQL store required")
    changed = 0
    specifications = (
        ("case_workflow_runs", "workflow_run_id", "state_json", "case_id"),
        ("case_workflow_events", "event_id", "details_json", None),
        ("orchestration_decision_traces", "event_id", "payload_json", None),
        ("session_debug_events", "event_id", "payload_json", None),
        ("workflow_tool_execution_events", "execution_event_id", "result_summary_json", "case_id"),
    )
    for table, primary, field, case_column in specifications:
        with store._connect() as conn:
            if not conn.execute("SELECT to_regclass(%s)", (table,)).fetchone()[0]:
                continue
            cursor = conn.execute(f"SELECT * FROM {table}")
            names = [column.name for column in cursor.description]
            rows = [dict(zip(names, row)) for row in cursor.fetchall()]
        for row in rows:
            payload = json.loads(row[field])
            if isinstance(payload, dict) and "encrypted_payload" in payload:
                _read_json(row[field])
                continue
            case_id = row.get(case_column) if case_column else None
            if not case_id and row.get("workflow_run_id"):
                with store._connect() as conn:
                    owner = conn.execute("SELECT case_id FROM case_workflow_runs WHERE workflow_run_id = %s", (row["workflow_run_id"],)).fetchone()
                case_id = owner[0] if owner else None
            if not case_id and isinstance(payload, dict):
                case_id = (payload.get("session") or {}).get("case_id")
            scope = str(case_id or "session:" + str(row.get("session_id") or row.get("workflow_run_id") or row[primary]))
            protected = _protect_json(payload, scope)
            assert _read_json(protected) == payload
            with store._connect() as conn:
                conn.execute(f"UPDATE {table} SET {field} = %s WHERE {primary} = %s", (protected, row[primary]))
            changed += 1

    serializer = CaseCheckpointSerializer(store)
    legacy = JsonPlusSerializer()
    with store._connect() as conn:
        if not conn.execute("SELECT to_regclass('checkpoints')").fetchone()[0]:
            return changed
        threads = conn.execute("SELECT DISTINCT thread_id FROM checkpoints").fetchall()
    for (thread_id,) in threads:
        with store._connect() as conn:
            owner = conn.execute("SELECT case_id FROM case_workflow_runs WHERE workflow_run_id = %s", (thread_id,)).fetchone()
            checkpoints = conn.execute("SELECT checkpoint_ns, checkpoint_id, checkpoint, metadata FROM checkpoints WHERE thread_id = %s", (thread_id,)).fetchall()
        scope = str(owner[0]) if owner and owner[0] else "workflow:" + thread_id
        for _, _, checkpoint, _ in checkpoints:
            values = checkpoint.get("channel_values", {})
            initial = values.get("__start__", {})
            candidate = values.get("case_id") or (initial.get("case_id") if isinstance(initial, dict) else None)
            if candidate:
                scope = str(candidate)
                break
        # Prepare the key before the migration transaction. No plaintext files.
        store.case_cipher.key(scope, create=True)
        token = _scope.set(scope)
        try:
            with store._connect() as conn:
                conn.execute("INSERT INTO case_workflow_encryption_scopes VALUES (%s, %s) ON CONFLICT(thread_id) DO NOTHING", (thread_id, scope))
                for table, keys in (("checkpoint_blobs", ("checkpoint_ns", "channel", "version")), ("checkpoint_writes", ("checkpoint_ns", "checkpoint_id", "task_id", "idx"))):
                    rows = conn.execute(f"SELECT {', '.join(keys)}, type, blob FROM {table} WHERE thread_id = %s", (thread_id,)).fetchall()
                    for row in rows:
                        kind, blob = row[-2:]
                        if kind == "empty":
                            continue
                        if kind == "case-encrypted-v1":
                            serializer.loads_typed((kind, bytes(blob)))
                            continue
                        value = legacy.loads_typed((kind, bytes(blob)))
                        encrypted_kind, encrypted_blob = serializer.dumps_typed(value)
                        where = " AND ".join(f"{key} = %s" for key in keys)
                        conn.execute(f"UPDATE {table} SET type = %s, blob = %s WHERE thread_id = %s AND {where}", (encrypted_kind, encrypted_blob, thread_id, *row[:-2]))
                        changed += 1
                for namespace, checkpoint_id, checkpoint, metadata in checkpoints:
                    if checkpoint.get("pending_sends"):
                        raise RuntimeError("Legacy pending_sends require a reviewed LangGraph upgrade before migration")
                    for channel, value in checkpoint.get("channel_values", {}).items():
                        version = checkpoint["channel_versions"][channel]
                        kind, blob = serializer.dumps_typed(value)
                        conn.execute("INSERT INTO checkpoint_blobs(thread_id, checkpoint_ns, channel, version, type, blob) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(thread_id, checkpoint_ns, channel, version) DO UPDATE SET type=excluded.type, blob=excluded.blob", (thread_id, namespace, channel, version, kind, blob))
                        changed += 1
                    checkpoint["channel_values"] = {}
                    safe_metadata = {key: metadata[key] for key in ("source", "step", "parents") if key in metadata}
                    conn.execute("UPDATE checkpoints SET checkpoint=%s::jsonb, metadata=%s::jsonb WHERE thread_id=%s AND checkpoint_ns=%s AND checkpoint_id=%s", (json.dumps(checkpoint), json.dumps(safe_metadata), thread_id, namespace, checkpoint_id))
        finally:
            _scope.reset(token)
    return changed


def migrate_emails():
    from app.services.email_queue import EmailQueueStore
    from app.case_workflows.store import _protect_json, _read_json
    queue = EmailQueueStore.from_env()
    queue.initialize()
    local = queue.config.db_option == "local"
    connect = queue._connect_sqlite if local else queue._connect_postgres
    changed = 0
    with connect() as conn:
        rows = conn.execute("SELECT email_id, subject, body, metadata_json FROM email_outbox").fetchall()
    for email_id, subject, body, raw in rows:
        metadata = raw if isinstance(raw, dict) else json.loads(raw)
        if "protected_case_email" in metadata:
            _read_json(metadata["protected_case_email"])
            continue
        if not metadata.get("case_id"):
            continue
        protected = _protect_json({"subject": subject, "body": body, "metadata": metadata}, str(metadata["case_id"]))
        encoded = json.dumps({"case_id": metadata["case_id"], "protected_case_email": protected})
        query = "UPDATE email_outbox SET subject = ?, body = ?, metadata_json = ? WHERE email_id = ?"
        with connect() as conn:
            conn.execute(query if local else query.replace("?", "%s"), ("Private case notification", "Encrypted case message", encoded, email_id))
            conn.commit()
        changed += 1
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-confirmed", action="store_true", required=True)
    parser.parse_args()
    load_dotenv(ROOT / ".env")
    from aijurisdictionagents.api_db import ApiDatabaseStore
    store = ApiDatabaseStore.from_env()
    store.initialize()
    print(f"Encrypted/verified workflow records; changed={migrate(store)}")
    print(f"Encrypted/verified case emails; changed={migrate_emails()}")
