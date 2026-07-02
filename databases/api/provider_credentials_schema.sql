CREATE TABLE IF NOT EXISTS provider_credentials (
    credential_id TEXT PRIMARY KEY,
    provider_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    endpoint TEXT NOT NULL DEFAULT '',
    deployment TEXT NOT NULL DEFAULT '',
    embeddings_model TEXT NOT NULL DEFAULT '',
    api_version TEXT NOT NULL DEFAULT '',
    auth_method TEXT NOT NULL DEFAULT '',
    secret_name TEXT NOT NULL DEFAULT '',
    has_secret INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    is_enabled INTEGER NOT NULL DEFAULT 1,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_provider_credentials_deleted
ON provider_credentials(is_deleted);
