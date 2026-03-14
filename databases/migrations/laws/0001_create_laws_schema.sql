CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS law_documents (
    document_id TEXT PRIMARY KEY,
    country_code TEXT NOT NULL,
    collection_code TEXT NOT NULL,
    law_year INTEGER NOT NULL,
    law_number INTEGER NOT NULL,
    official_name TEXT NOT NULL,
    lawyer_title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    publication_date DATE NOT NULL,
    current_status TEXT NOT NULL,
    first_effective_date DATE NOT NULL,
    applicable_to TEXT,
    superseded_by_url TEXT NOT NULL DEFAULT '',
    first_stored_at TIMESTAMPTZ NOT NULL,
    last_stored_at TIMESTAMPTZ NOT NULL,
    last_checked_at TIMESTAMPTZ NOT NULL,
    last_download_status TEXT NOT NULL,
    last_download_error TEXT NOT NULL,
    download_attempt_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(country_code, collection_code, law_year, law_number)
);

CREATE TABLE IF NOT EXISTS law_versions (
    version_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES law_documents(document_id) ON DELETE CASCADE,
    version_token TEXT NOT NULL,
    effective_from DATE NOT NULL,
    version_checksum TEXT NOT NULL,
    status TEXT NOT NULL,
    html_checksum TEXT NOT NULL,
    pdf_checksum TEXT NOT NULL,
    html_bytes INTEGER NOT NULL,
    pdf_bytes INTEGER NOT NULL,
    normalized_json JSONB NOT NULL,
    embedding_vector VECTOR(8) NOT NULL,
    stored_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(document_id, version_token)
);

CREATE INDEX IF NOT EXISTS idx_law_versions_doc_effective
    ON law_versions(document_id, effective_from DESC);
CREATE INDEX IF NOT EXISTS idx_law_versions_embedding
    ON law_versions USING ivfflat (embedding_vector vector_cosine_ops);

CREATE TABLE IF NOT EXISTS law_provisions (
    provision_id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES law_versions(version_id) ON DELETE CASCADE,
    anchor TEXT NOT NULL,
    heading TEXT NOT NULL,
    body_text TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS source_artifacts (
    artifact_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES law_documents(document_id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES law_versions(version_id) ON DELETE CASCADE,
    source_system TEXT NOT NULL,
    artifact_kind TEXT NOT NULL,
    source_url TEXT NOT NULL,
    checksum TEXT NOT NULL,
    content_text TEXT NOT NULL,
    content_blob BYTEA,
    content_bytes INTEGER NOT NULL,
    http_etag TEXT NOT NULL,
    http_last_modified TEXT NOT NULL,
    should_redownload BOOLEAN NOT NULL,
    verification_status TEXT NOT NULL,
    download_error TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    last_checked_at TIMESTAMPTZ NOT NULL,
    UNIQUE(version_id, artifact_kind, checksum)
);

CREATE TABLE IF NOT EXISTS update_events (
    event_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES law_documents(document_id) ON DELETE CASCADE,
    version_id TEXT REFERENCES law_versions(version_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    event_status TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
