-- A 404/410 alone never sets source_unavailable. An audited human review does.
ALTER TABLE court_decision_import_queue
ADD COLUMN IF NOT EXISTS source_unavailable BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE court_decision_import_queue
ADD COLUMN IF NOT EXISTS last_http_status INTEGER;

CREATE TABLE IF NOT EXISTS court_decision_availability_reviews (
    review_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system TEXT NOT NULL,
    reference_hash TEXT NOT NULL CHECK (reference_hash ~ '^[0-9a-f]{64}$'),
    source_unavailable BOOLEAN NOT NULL,
    evidence_category TEXT NOT NULL CHECK (evidence_category IN (
        'source_withdrawal', 'operator_verified_unavailable',
        'operator_requeue', 'verified_source_change')),
    evidence_sha256 TEXT NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    reviewer_sha256 TEXT NOT NULL CHECK (reviewer_sha256 ~ '^[0-9a-f]{64}$'),
    last_http_status INTEGER,
    attempt_count INTEGER NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
