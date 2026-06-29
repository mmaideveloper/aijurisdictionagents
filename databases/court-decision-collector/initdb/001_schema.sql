CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS court_decision_documents (
    decision_id TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    source_guid TEXT NOT NULL,
    court_name TEXT NOT NULL DEFAULT '',
    court_type TEXT NOT NULL DEFAULT '',
    decision_form TEXT NOT NULL DEFAULT '',
    nature TEXT NOT NULL DEFAULT '',
    file_number TEXT NOT NULL DEFAULT '',
    case_number TEXT NOT NULL DEFAULT '',
    ecli TEXT NOT NULL DEFAULT '',
    issue_date TEXT NOT NULL DEFAULT '',
    indexed_at TEXT NOT NULL DEFAULT '',
    update_date TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    current_status TEXT NOT NULL DEFAULT 'published',
    first_stored_at TEXT NOT NULL,
    last_stored_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_system, source_guid)
);

CREATE TABLE IF NOT EXISTS court_decision_versions (
    version_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES court_decision_documents(decision_id) ON DELETE CASCADE,
    version_checksum TEXT NOT NULL,
    raw_text_checksum TEXT NOT NULL,
    pseudonymized_text_checksum TEXT NOT NULL,
    metadata_checksum TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    pseudonymized_text TEXT NOT NULL,
    normalized_json JSONB NOT NULL,
    metadata_json JSONB NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL,
    embedding_vector_json JSONB NOT NULL,
    embedding_vector VECTOR(32),
    stored_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS court_decision_import_state (
    source_system TEXT NOT NULL,
    cursor_kind TEXT NOT NULL,
    last_source_guid TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    last_processed_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(source_system, cursor_kind)
);

CREATE TABLE IF NOT EXISTS court_decision_update_events (
    event_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES court_decision_documents(decision_id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES court_decision_versions(version_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_metadata_json JSONB NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_court_decision_documents_source
ON court_decision_documents(source_system, source_guid);

CREATE INDEX IF NOT EXISTS idx_court_decision_documents_issue_date
ON court_decision_documents(issue_date);
