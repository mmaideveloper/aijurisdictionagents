ALTER TABLE ai_model_profiles
ADD COLUMN is_default_for_free INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS ai_model_credentials (
    credential_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    credential_name TEXT NOT NULL DEFAULT 'default',
    secret_type TEXT NOT NULL DEFAULT 'api_key',
    protected_secret TEXT NOT NULL,
    secret_preview TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_revealed_at TEXT,
    UNIQUE(provider_id, credential_name, secret_type),
    FOREIGN KEY(provider_id) REFERENCES ai_model_providers(provider_id) ON DELETE CASCADE
);
