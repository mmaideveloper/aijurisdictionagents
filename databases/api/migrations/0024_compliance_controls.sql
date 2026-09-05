CREATE TABLE IF NOT EXISTS consent_events (
    event_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    session_id TEXT NOT NULL DEFAULT '',
    consent_scope TEXT NOT NULL,
    consent_text_version TEXT NOT NULL,
    granted INTEGER NOT NULL,
    source TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL DEFAULT '',
    captured_at TEXT NOT NULL,
    expires_at TEXT,
    previous_event_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_consent_events_user_scope_time
ON consent_events(user_id, consent_scope, captured_at DESC);

CREATE TABLE IF NOT EXISTS processing_restrictions (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id),
    restricted INTEGER NOT NULL DEFAULT 1,
    reason_code TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    lifted_at TEXT
);

CREATE TABLE IF NOT EXISTS data_subject_requests (
    request_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    request_type TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    completed_at TEXT,
    result_manifest_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_dsar_user_requested
ON data_subject_requests(user_id, requested_at DESC);

CREATE TABLE IF NOT EXISTS compliance_events (
    event_id TEXT PRIMARY KEY,
    subject_ref TEXT NOT NULL,
    event_type TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    correlation_id TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    previous_event_hash TEXT NOT NULL DEFAULT '',
    event_hash TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_compliance_subject_time
ON compliance_events(subject_ref, occurred_at DESC);

CREATE TABLE IF NOT EXISTS retention_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}'
);

CREATE OR REPLACE FUNCTION reject_compliance_event_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'compliance_events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS compliance_events_no_update ON compliance_events;
CREATE TRIGGER compliance_events_no_update
BEFORE UPDATE ON compliance_events
FOR EACH ROW EXECUTE FUNCTION reject_compliance_event_mutation();

DROP TRIGGER IF EXISTS compliance_events_no_delete ON compliance_events;
CREATE TRIGGER compliance_events_no_delete
BEFORE DELETE ON compliance_events
FOR EACH ROW EXECUTE FUNCTION reject_compliance_event_mutation();
