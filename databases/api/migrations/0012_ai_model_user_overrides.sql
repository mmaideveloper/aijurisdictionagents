CREATE TABLE IF NOT EXISTS ai_model_user_overrides (
    override_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    model_profile_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_by_admin_user_id TEXT NOT NULL DEFAULT '',
    updated_by_admin_user_id TEXT NOT NULL DEFAULT '',
    disabled_by_admin_user_id TEXT NOT NULL DEFAULT '',
    created_reason TEXT NOT NULL DEFAULT '',
    updated_reason TEXT NOT NULL DEFAULT '',
    disabled_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    disabled_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY(model_profile_id) REFERENCES ai_model_profiles(model_profile_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_ai_model_user_overrides_enabled_user
ON ai_model_user_overrides(user_id, enabled);

CREATE INDEX IF NOT EXISTS idx_ai_model_user_overrides_profile
ON ai_model_user_overrides(model_profile_id);
