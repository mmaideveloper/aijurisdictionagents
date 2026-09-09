ALTER TABLE document_template_source_captures
    ADD COLUMN IF NOT EXISTS previous_content_sha256 TEXT NOT NULL DEFAULT '';
