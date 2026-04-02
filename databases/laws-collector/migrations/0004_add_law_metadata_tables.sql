CREATE TABLE IF NOT EXISTS law_metadata (
    law_metadata_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES law_documents(document_id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES law_versions(version_id) ON DELETE CASCADE,
    law_identifier_text TEXT NOT NULL,
    title TEXT NOT NULL,
    law_type TEXT NOT NULL,
    approval_date DATE,
    publication_date DATE NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    author TEXT,
    issue_reference TEXT,
    legal_areas_json JSONB NOT NULL,
    metadata_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(version_id)
);

CREATE INDEX IF NOT EXISTS idx_law_metadata_document
    ON law_metadata(document_id);

CREATE TABLE IF NOT EXISTS law_metadata_relations (
    law_metadata_relation_id TEXT PRIMARY KEY,
    law_metadata_id TEXT NOT NULL REFERENCES law_metadata(law_metadata_id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    relation_label TEXT NOT NULL,
    target_country_code TEXT NOT NULL,
    target_collection_code TEXT NOT NULL,
    target_law_year INTEGER,
    target_law_number INTEGER,
    target_law_identifier_text TEXT NOT NULL,
    target_title TEXT NOT NULL,
    target_url TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_law_metadata_relations_lookup
    ON law_metadata_relations(relation_type, target_country_code, target_collection_code, target_law_year, target_law_number);
