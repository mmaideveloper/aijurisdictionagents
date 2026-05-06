CREATE TABLE IF NOT EXISTS document_templates (
    template_id TEXT PRIMARY KEY,
    template_key TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    language TEXT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    template_kind TEXT NOT NULL,
    description TEXT NOT NULL,
    source_format TEXT NOT NULL,
    source_url TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    keywords_json TEXT NOT NULL,
    flow_keys_json TEXT NOT NULL,
    placeholders_json TEXT NOT NULL,
    source_refs_json TEXT NOT NULL,
    disclaimer_title TEXT NOT NULL DEFAULT '',
    disclaimer_text TEXT NOT NULL DEFAULT '',
    disclaimer_footer TEXT NOT NULL DEFAULT '',
    is_enabled INTEGER NOT NULL DEFAULT 1,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NULL,
    UNIQUE(jurisdiction, template_key)
);

CREATE INDEX IF NOT EXISTS idx_document_templates_key ON document_templates(template_key);
CREATE INDEX IF NOT EXISTS idx_document_templates_jurisdiction ON document_templates(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_document_templates_enabled ON document_templates(is_enabled);
CREATE INDEX IF NOT EXISTS idx_document_templates_deleted ON document_templates(is_deleted);

