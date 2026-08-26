CREATE TABLE IF NOT EXISTS document_templates (
    template_id TEXT PRIMARY KEY,
    template_key TEXT NOT NULL,
    lineage_key TEXT NOT NULL DEFAULT '',
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
    version INTEGER NOT NULL DEFAULT 1,
    stored_at TEXT,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NULL
);

ALTER TABLE document_templates
    ADD COLUMN IF NOT EXISTS lineage_key TEXT NOT NULL DEFAULT '';

ALTER TABLE document_templates
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE document_templates
    ADD COLUMN IF NOT EXISTS stored_at TEXT;

UPDATE document_templates
SET stored_at = COALESCE(stored_at, created_at, updated_at)
WHERE stored_at IS NULL OR stored_at = '';

UPDATE document_templates
SET lineage_key = concat_ws(
    '|',
    trim(
        regexp_replace(
            translate(
                lower(COALESCE(title, '')),
                'áäčďéíľĺňóôŕšťúýžÁÄČĎÉÍĽĹŇÓÔŔŠŤÚÝŽ|',
                'aacdeillnoorstuyzaacdeillnoorstuyz '
            ),
            '\s+',
            ' ',
            'g'
        )
    ),
    trim(
        regexp_replace(
            translate(
                lower(COALESCE(template_kind, '')),
                'áäčďéíľĺňóôŕšťúýžÁÄČĎÉÍĽĹŇÓÔŔŠŤÚÝŽ|',
                'aacdeillnoorstuyzaacdeillnoorstuyz '
            ),
            '\s+',
            ' ',
            'g'
        )
    ),
    trim(
        regexp_replace(
            translate(
                lower(COALESCE(jurisdiction, '')),
                'áäčďéíľĺňóôŕšťúýžÁÄČĎÉÍĽĹŇÓÔŔŠŤÚÝŽ|',
                'aacdeillnoorstuyzaacdeillnoorstuyz '
            ),
            '\s+',
            ' ',
            'g'
        )
    ),
    trim(
        regexp_replace(
            translate(
                lower(COALESCE(NULLIF(language, ''), 'none')),
                'áäčďéíľĺňóôŕšťúýžÁÄČĎÉÍĽĹŇÓÔŔŠŤÚÝŽ|',
                'aacdeillnoorstuyzaacdeillnoorstuyz '
            ),
            '\s+',
            ' ',
            'g'
        )
    )
)
WHERE lineage_key IS NULL OR lineage_key = '';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'document_templates'::regclass
          AND conname = 'document_templates_jurisdiction_template_key_key'
    ) THEN
        ALTER TABLE document_templates
            DROP CONSTRAINT document_templates_jurisdiction_template_key_key;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'document_templates'::regclass
          AND conname = 'document_templates_jurisdiction_template_key_version_key'
    ) THEN
        ALTER TABLE document_templates
            ADD CONSTRAINT document_templates_jurisdiction_template_key_version_key
            UNIQUE (jurisdiction, template_key, version);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_document_templates_key
    ON document_templates(template_key);
CREATE INDEX IF NOT EXISTS idx_document_templates_lineage
    ON document_templates(lineage_key);
CREATE INDEX IF NOT EXISTS idx_document_templates_jurisdiction
    ON document_templates(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_document_templates_enabled
    ON document_templates(is_enabled);
CREATE INDEX IF NOT EXISTS idx_document_templates_deleted
    ON document_templates(is_deleted);

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
