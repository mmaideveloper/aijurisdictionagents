CREATE TABLE IF NOT EXISTS local_model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_code TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    model_cutoff_time TEXT NOT NULL,
    last_processed_law TEXT NOT NULL,
    base_model TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    quantization TEXT NOT NULL,
    training_documents INTEGER NOT NULL,
    output_format TEXT NOT NULL,
    output_uri TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(country_code, model_name, model_version)
);

CREATE INDEX IF NOT EXISTS idx_local_model_versions_country_created
    ON local_model_versions(country_code, created_at DESC);
