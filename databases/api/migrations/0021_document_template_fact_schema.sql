ALTER TABLE document_templates
    ADD COLUMN IF NOT EXISTS fact_schema_json TEXT NOT NULL DEFAULT '[]';
