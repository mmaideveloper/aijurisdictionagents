ALTER TABLE document_templates
    ADD COLUMN IF NOT EXISTS body_completeness_status TEXT NOT NULL DEFAULT 'metadata_only';
