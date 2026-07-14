CREATE TABLE IF NOT EXISTS court_decision_enrichments (
    version_id TEXT PRIMARY KEY REFERENCES court_decision_versions(version_id) ON DELETE CASCADE,
    decision_id TEXT NOT NULL REFERENCES court_decision_documents(decision_id) ON DELETE CASCADE,
    status TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', pdf_url TEXT NOT NULL DEFAULT '',
    pdf_filename TEXT NOT NULL DEFAULT '', expected_size BIGINT NOT NULL DEFAULT 0,
    actual_size BIGINT NOT NULL DEFAULT 0, pdf_path TEXT NOT NULL DEFAULT '', pdf_sha256 TEXT NOT NULL DEFAULT '',
    extraction_method TEXT NOT NULL DEFAULT '', raw_text TEXT NOT NULL DEFAULT '',
    pseudonymized_text TEXT NOT NULL DEFAULT '', pseudonymized_summary TEXT NOT NULL DEFAULT '',
    legal_topics JSONB NOT NULL DEFAULT '[]'::jsonb, summary_model TEXT NOT NULL DEFAULT '',
    embedding_model TEXT NOT NULL DEFAULT '', embedding_dimensions INTEGER NOT NULL DEFAULT 0,
    summary_embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_type TEXT NOT NULL DEFAULT '', completed_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS court_decision_content_chunks (
    chunk_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES court_decision_documents(decision_id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES court_decision_versions(version_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL, pseudonymized_text TEXT NOT NULL,
    embedding_model TEXT NOT NULL, embedding_dimensions INTEGER NOT NULL,
    embedding_vector_json JSONB NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(version_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_court_decision_enrichments_status
ON court_decision_enrichments(status, updated_at);

CREATE INDEX IF NOT EXISTS idx_court_decision_enrichments_topics
ON court_decision_enrichments USING GIN(legal_topics);

