CREATE TABLE IF NOT EXISTS session_debug_events (
    event_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    parent_request_id TEXT NOT NULL DEFAULT '',
    component TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_debug_events_correlation
ON session_debug_events(correlation_id, created_at, event_id);

CREATE INDEX IF NOT EXISTS idx_session_debug_events_expiry
ON session_debug_events(expires_at);
