CREATE TABLE IF NOT EXISTS collector_import_state (
    country_code TEXT NOT NULL,
    source_system TEXT NOT NULL,
    import_key TEXT NOT NULL,
    import_label TEXT NOT NULL,
    source_url TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    last_processed_at TIMESTAMPTZ,
    last_processed_entry TEXT,
    last_processed_law_year INTEGER,
    last_processed_law_number INTEGER,
    completed_at TIMESTAMPTZ,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(country_code, import_key)
);
