CREATE TABLE IF NOT EXISTS workflow_tool_consent_events (
    consent_event_id TEXT PRIMARY KEY,
    workflow_run_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    consent_scope TEXT NOT NULL,
    consent_text_version TEXT NOT NULL,
    decision TEXT NOT NULL,
    provider TEXT NOT NULL,
    purpose TEXT NOT NULL,
    permitted_data_fields_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(workflow_run_id, tool_name, consent_scope, consent_text_version)
);

CREATE INDEX IF NOT EXISTS idx_workflow_tool_consent_case
ON workflow_tool_consent_events(case_id, user_id, created_at);

CREATE TABLE IF NOT EXISTS workflow_tool_execution_events (
    execution_event_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    consent_event_id TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    result_summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_tool_execution_case
ON workflow_tool_execution_events(case_id, user_id, created_at);
