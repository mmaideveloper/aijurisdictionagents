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
    issue_date_normalized DATE,
    court_name_normalized TEXT NOT NULL DEFAULT '',
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
    work_class TEXT NOT NULL DEFAULT 'legacy',
    event_metadata_json JSONB NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS court_decision_scheduler_state (
    source_system TEXT PRIMARY KEY,
    discovered_source_total BIGINT NOT NULL DEFAULT 0,
    source_updated_at TEXT NOT NULL DEFAULT '',
    backfill_next_page BIGINT NOT NULL DEFAULT 0,
    backfill_generation BIGINT NOT NULL DEFAULT 0,
    quota_day DATE NOT NULL,
    quota_used INTEGER NOT NULL DEFAULT 0,
    daily_new_limit INTEGER NOT NULL DEFAULT 10000,
    last_discovery_at TEXT NOT NULL DEFAULT '',
    last_new_success_at TEXT NOT NULL DEFAULT '',
    last_backfill_success_at TEXT NOT NULL DEFAULT '',
    checkpoint_failures BIGINT NOT NULL DEFAULT 0,
    retry_count BIGINT NOT NULL DEFAULT 0,
    pages_scanned_without_write BIGINT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'not_started',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (discovered_source_total >= 0),
    CHECK (backfill_next_page >= 0),
    CHECK (quota_used >= 0),
    CHECK (daily_new_limit >= 1)
);

CREATE TABLE IF NOT EXISTS court_decision_import_queue (
    source_system TEXT NOT NULL,
    source_guid TEXT NOT NULL,
    work_class TEXT NOT NULL CHECK (work_class IN ('new', 'backfill')),
    source_page BIGINT NOT NULL CHECK (source_page >= 0),
    source_ordinal BIGINT NOT NULL CHECK (source_ordinal >= 0),
    counts_toward_quota BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'retryable', 'completed')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_type TEXT NOT NULL DEFAULT '',
    discovered_at TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(source_system, source_guid)
);

CREATE INDEX IF NOT EXISTS idx_court_decision_import_queue_pending
ON court_decision_import_queue(source_system, work_class, status, source_ordinal);

CREATE INDEX IF NOT EXISTS idx_court_decision_documents_source
ON court_decision_documents(source_system, source_guid);

CREATE INDEX IF NOT EXISTS idx_court_decision_documents_issue_date_normalized
ON court_decision_documents(issue_date_normalized);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_court_decision_documents_status_issue_date_normalized
ON court_decision_documents(current_status, issue_date_normalized DESC, updated_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_court_decision_documents_court_name_normalized
ON court_decision_documents(court_name_normalized);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_court_decision_documents_metadata_search_text
ON court_decision_documents USING GIN (
    to_tsvector(
        'simple'::regconfig,
        COALESCE(court_name, '') || ' ' ||
        COALESCE(court_type, '') || ' ' ||
        COALESCE(file_number, '') || ' ' ||
        COALESCE(case_number, '') || ' ' ||
        COALESCE(ecli, '')
    )
);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_court_decision_versions_decision_stored_at
ON court_decision_versions(decision_id, stored_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_court_decision_search_text
ON court_decision_versions USING GIN (
    to_tsvector('simple', pseudonymized_text)
);
