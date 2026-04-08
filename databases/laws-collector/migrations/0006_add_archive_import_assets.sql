CREATE TABLE IF NOT EXISTS archive_import_assets (
    archive_import_asset_id TEXT PRIMARY KEY,
    country_code TEXT NOT NULL,
    source_system TEXT NOT NULL,
    import_key TEXT NOT NULL,
    import_label TEXT NOT NULL,
    phase TEXT NOT NULL,
    asset_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    storage_backend TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    checksum TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    processing_status TEXT NOT NULL,
    downloaded_at TIMESTAMPTZ NOT NULL,
    metadata_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(country_code, import_key, asset_name, checksum)
);

CREATE INDEX IF NOT EXISTS idx_archive_import_assets_lookup
    ON archive_import_assets(country_code, import_key, phase, processing_status, downloaded_at DESC);
