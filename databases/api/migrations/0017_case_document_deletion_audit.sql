CREATE TABLE IF NOT EXISTS case_document_deletion_events (
    event_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    document_kind TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    deleted_at TEXT NOT NULL,
    communication_id TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY(actor_user_id) REFERENCES users(user_id),
    FOREIGN KEY(communication_id) REFERENCES case_communications(communication_id)
);

CREATE INDEX IF NOT EXISTS idx_case_document_deletion_events_case_deleted
ON case_document_deletion_events(case_id, deleted_at DESC);
