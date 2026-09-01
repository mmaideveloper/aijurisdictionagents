CREATE TABLE IF NOT EXISTS document_templates (
    template_id TEXT PRIMARY KEY,
    template_key TEXT NOT NULL,
    lineage_key TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    language TEXT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    template_kind TEXT NOT NULL,
    description TEXT NOT NULL,
    source_format TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_profile TEXT NOT NULL DEFAULT '',
    source_captured_at TEXT NULL,
    source_review_status TEXT NOT NULL DEFAULT 'unreviewed',
    reviewed_by TEXT NOT NULL DEFAULT '',
    normalization_notes TEXT NOT NULL DEFAULT '',
    legal_basis_refs_json TEXT NOT NULL DEFAULT '[]',
    body_completeness_status TEXT NOT NULL DEFAULT 'metadata_only',
    body TEXT NOT NULL DEFAULT '',
    keywords_json TEXT NOT NULL,
    flow_keys_json TEXT NOT NULL,
    placeholders_json TEXT NOT NULL,
    source_refs_json TEXT NOT NULL,
    disclaimer_title TEXT NOT NULL DEFAULT '',
    disclaimer_text TEXT NOT NULL DEFAULT '',
    disclaimer_footer TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    stored_at TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NULL,
    UNIQUE(jurisdiction, template_key, version)
);

CREATE INDEX IF NOT EXISTS idx_document_templates_key ON document_templates(template_key);
CREATE INDEX IF NOT EXISTS idx_document_templates_lineage ON document_templates(lineage_key);
CREATE INDEX IF NOT EXISTS idx_document_templates_jurisdiction ON document_templates(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_document_templates_enabled ON document_templates(is_enabled);
CREATE INDEX IF NOT EXISTS idx_document_templates_deleted ON document_templates(is_deleted);

CREATE TABLE IF NOT EXISTS case_types (
    case_type_id TEXT PRIMARY KEY,
    case_type_key TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    language TEXT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    keywords_json TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NULL,
    UNIQUE(jurisdiction, case_type_key)
);

CREATE TABLE IF NOT EXISTS case_type_templates (
    case_type_template_id TEXT PRIMARY KEY,
    case_type_id TEXT NOT NULL,
    template_id TEXT NOT NULL,
    suitability_score INTEGER NOT NULL DEFAULT 100,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(case_type_id, template_id),
    FOREIGN KEY(case_type_id) REFERENCES case_types(case_type_id),
    FOREIGN KEY(template_id) REFERENCES document_templates(template_id)
);

CREATE TABLE IF NOT EXISTS case_prompts (
    case_prompt_id TEXT PRIMARY KEY,
    case_type_id TEXT NOT NULL UNIQUE,
    prompt_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(case_type_id) REFERENCES case_types(case_type_id)
);

CREATE INDEX IF NOT EXISTS idx_case_types_key ON case_types(case_type_key);
CREATE INDEX IF NOT EXISTS idx_case_types_jurisdiction ON case_types(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_case_types_enabled ON case_types(is_enabled);
CREATE INDEX IF NOT EXISTS idx_case_types_deleted ON case_types(is_deleted);
CREATE INDEX IF NOT EXISTS idx_case_type_templates_case_type ON case_type_templates(case_type_id);
CREATE INDEX IF NOT EXISTS idx_case_type_templates_template ON case_type_templates(template_id);
