ALTER TABLE court_decision_update_events
ADD COLUMN IF NOT EXISTS work_class TEXT NOT NULL DEFAULT 'legacy';

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

CREATE INDEX IF NOT EXISTS idx_court_decision_update_events_work_class_created
ON court_decision_update_events(work_class, created_at);
