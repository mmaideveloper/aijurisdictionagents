CREATE TABLE IF NOT EXISTS privacy_consent_events (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    text_version TEXT NOT NULL,
    granted INTEGER NOT NULL CHECK (granted IN (0, 1)),
    captured_at TEXT NOT NULL,
    source TEXT NOT NULL,
    country TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS privacy_consent_latest ON privacy_consent_events(user_id, scope, sequence_id);
CREATE TABLE IF NOT EXISTS privacy_subject_state (
    user_id TEXT PRIMARY KEY,
    restricted INTEGER NOT NULL DEFAULT 0,
    legal_hold INTEGER NOT NULL DEFAULT 0,
    sensitive_consent_required INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS privacy_requests (
    request_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('delete', 'anonymize')),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS privacy_compliance_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS privacy_events_no_update BEFORE UPDATE ON privacy_compliance_events
BEGIN SELECT RAISE(ABORT, 'Compliance events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS privacy_events_no_delete BEFORE DELETE ON privacy_compliance_events
BEGIN SELECT RAISE(ABORT, 'Compliance events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS privacy_consents_no_update BEFORE UPDATE ON privacy_consent_events
BEGIN SELECT RAISE(ABORT, 'Consent events are append-only'); END;
CREATE TABLE IF NOT EXISTS privacy_ai_artifacts (
    artifact_id TEXT PRIMARY KEY, case_id TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS privacy_file_cleanup (
    cleanup_id TEXT PRIMARY KEY, storage_uri TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL
);
