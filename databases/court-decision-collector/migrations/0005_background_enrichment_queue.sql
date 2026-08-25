CREATE TABLE IF NOT EXISTS court_decision_enrichment_control (
    source_system TEXT PRIMARY KEY,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    pause_reason TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS court_decision_enrichment_queue (
    version_id TEXT PRIMARY KEY REFERENCES court_decision_versions(version_id) ON DELETE CASCADE,
    decision_id TEXT NOT NULL REFERENCES court_decision_documents(decision_id) ON DELETE CASCADE,
    priority_class TEXT NOT NULL CHECK (priority_class IN ('user_requested', 'recent', 'background')),
    priority_rank INTEGER NOT NULL CHECK (priority_rank IN (0, 10, 20)),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'retryable', 'completed', 'dead_letter', 'quarantined')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    available_at TEXT NOT NULL,
    lease_token TEXT NOT NULL DEFAULT '',
    lease_expires_at TEXT NOT NULL DEFAULT '',
    last_error_type TEXT NOT NULL DEFAULT '',
    requested_at TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT '',
    completed_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_court_decision_enrichment_queue_claim
ON court_decision_enrichment_queue(status, available_at, priority_rank, requested_at);

CREATE INDEX IF NOT EXISTS idx_court_decision_enrichment_queue_decision
ON court_decision_enrichment_queue(decision_id, status);
