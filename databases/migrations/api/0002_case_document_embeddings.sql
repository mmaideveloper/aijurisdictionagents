ALTER TABLE case_documents
ADD COLUMN IF NOT EXISTS processing_status TEXT NOT NULL DEFAULT 'uploaded';

ALTER TABLE case_documents
ADD COLUMN IF NOT EXISTS processing_error TEXT;

ALTER TABLE case_documents
ADD COLUMN IF NOT EXISTS processed_at TEXT;

CREATE TABLE IF NOT EXISTS case_document_contents (
    content_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    extracted_text TEXT NOT NULL,
    embedding_vector TEXT NOT NULL,
    embedding_model TEXT NOT NULL DEFAULT '',
    embedding_dimensions INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(doc_id) REFERENCES case_documents(doc_id) ON DELETE CASCADE,
    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS case_document_chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding_vector TEXT NOT NULL,
    embedding_model TEXT NOT NULL DEFAULT '',
    embedding_dimensions INTEGER NOT NULL DEFAULT 0,
    start_offset INTEGER NOT NULL DEFAULT 0,
    end_offset INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(doc_id, chunk_index),
    FOREIGN KEY(doc_id) REFERENCES case_documents(doc_id) ON DELETE CASCADE,
    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_case_document_chunks_case_doc_chunk
ON case_document_chunks(case_id, doc_id, chunk_index);
