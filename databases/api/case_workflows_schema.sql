CREATE TABLE IF NOT EXISTS case_workflow_assignments (
    assignment_id TEXT PRIMARY KEY,
    case_type_key TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    graph_key TEXT NOT NULL,
    graph_version INTEGER NOT NULL,
    flow_key TEXT NOT NULL,
    flow_version INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    validation_status TEXT NOT NULL,
    validation_message TEXT NOT NULL DEFAULT '',
    effective_from TEXT NOT NULL,
    effective_to TEXT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    supersedes_assignment_id TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_case_workflow_assignments_case_type
ON case_workflow_assignments(jurisdiction, case_type_key, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_case_workflow_assignments_active
ON case_workflow_assignments(jurisdiction, case_type_key)
WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS case_workflow_runs (
    workflow_run_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    case_type_key TEXT NOT NULL,
    assignment_id TEXT NOT NULL,
    graph_key TEXT NOT NULL,
    graph_version INTEGER NOT NULL,
    flow_key TEXT NOT NULL,
    flow_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_case_workflow_runs_case
ON case_workflow_runs(case_id, created_at);

CREATE INDEX IF NOT EXISTS idx_case_workflow_runs_session
ON case_workflow_runs(session_id, created_at);

CREATE TABLE IF NOT EXISTS case_workflow_events (
    event_id TEXT PRIMARY KEY,
    workflow_run_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_case_workflow_events_run
ON case_workflow_events(workflow_run_id, created_at);

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
