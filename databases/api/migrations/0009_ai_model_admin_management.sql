CREATE TABLE IF NOT EXISTS ai_model_admin_audit_events (
    audit_event_id TEXT PRIMARY KEY,
    admin_user_id TEXT NOT NULL DEFAULT '',
    admin_email TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    old_value_summary_json TEXT NOT NULL DEFAULT '{}',
    new_value_summary_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_model_admin_audit_entity_time
ON ai_model_admin_audit_events(entity_type, entity_id, created_at);
