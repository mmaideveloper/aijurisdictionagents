CREATE TABLE IF NOT EXISTS document_reviews (
    review_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES case_documents(doc_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
