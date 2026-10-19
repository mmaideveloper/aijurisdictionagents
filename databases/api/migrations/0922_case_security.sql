CREATE TABLE IF NOT EXISTS case_encryption_keys (
    case_id TEXT PRIMARY KEY,
    key_id TEXT NOT NULL,
    wrapped_key TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_export_permissions (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    granted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_export_requests (
    request_id TEXT PRIMARY KEY,
    admin_id TEXT NOT NULL REFERENCES users(user_id),
    purpose TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL,
    case_count INTEGER NOT NULL,
    artifact_expires_at TEXT,
    artifact TEXT
);
CREATE TABLE IF NOT EXISTS case_export_grants (
    request_id TEXT NOT NULL REFERENCES case_export_requests(request_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL REFERENCES users(user_id),
    decision TEXT NOT NULL DEFAULT 'pending',
    decided_at TEXT,
    PRIMARY KEY(request_id, case_id)
);
CREATE TABLE IF NOT EXISTS case_export_events (
    event_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_export_owner ON case_export_grants(owner_id, request_id);


CREATE TABLE IF NOT EXISTS case_workflow_encryption_scopes (thread_id TEXT PRIMARY KEY, case_id TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS case_export_snapshots (request_id TEXT NOT NULL REFERENCES case_export_requests(request_id) ON DELETE CASCADE, case_id TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(request_id, case_id));

CREATE TABLE IF NOT EXISTS case_encryption_erased (case_id TEXT PRIMARY KEY, erased_at TEXT NOT NULL);
