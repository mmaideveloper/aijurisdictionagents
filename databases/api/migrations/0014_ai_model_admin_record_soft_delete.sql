ALTER TABLE ai_model_profiles
    ADD COLUMN IF NOT EXISTS deleted_at TEXT;

ALTER TABLE ai_model_profiles
    ADD COLUMN IF NOT EXISTS deleted_by_admin_user_id TEXT NOT NULL DEFAULT '';

ALTER TABLE ai_model_profiles
    ADD COLUMN IF NOT EXISTS deleted_reason TEXT NOT NULL DEFAULT '';

ALTER TABLE ai_model_groups
    ADD COLUMN IF NOT EXISTS deleted_at TEXT;

ALTER TABLE ai_model_groups
    ADD COLUMN IF NOT EXISTS deleted_by_admin_user_id TEXT NOT NULL DEFAULT '';

ALTER TABLE ai_model_groups
    ADD COLUMN IF NOT EXISTS deleted_reason TEXT NOT NULL DEFAULT '';

ALTER TABLE ai_task_route_policies
    ADD COLUMN IF NOT EXISTS deleted_at TEXT;

ALTER TABLE ai_task_route_policies
    ADD COLUMN IF NOT EXISTS deleted_by_admin_user_id TEXT NOT NULL DEFAULT '';

ALTER TABLE ai_task_route_policies
    ADD COLUMN IF NOT EXISTS deleted_reason TEXT NOT NULL DEFAULT '';
