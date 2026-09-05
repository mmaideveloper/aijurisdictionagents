CREATE TABLE IF NOT EXISTS orchestration_decision_traces (
    event_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(workflow_run_id) REFERENCES case_workflow_runs(workflow_run_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_orchestration_decision_traces_session
ON orchestration_decision_traces(session_id, created_at, event_id);

CREATE INDEX IF NOT EXISTS idx_orchestration_decision_traces_run
ON orchestration_decision_traces(workflow_run_id, created_at, event_id);
