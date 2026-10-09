-- Search metadata never copies protected diagnostic payloads.
CREATE TABLE IF NOT EXISTS debug_trace_sessions (
    correlation_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_id TEXT,
    case_id TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (correlation_id, session_id)
);
CREATE INDEX IF NOT EXISTS idx_debug_trace_user
ON debug_trace_sessions(user_id, created_at, correlation_id, session_id);
CREATE INDEX IF NOT EXISTS idx_debug_trace_case
ON debug_trace_sessions(case_id, created_at, correlation_id, session_id);
CREATE INDEX IF NOT EXISTS idx_debug_trace_session
ON debug_trace_sessions(session_id, created_at, correlation_id);
CREATE INDEX IF NOT EXISTS idx_debug_trace_time
ON debug_trace_sessions(created_at, correlation_id, session_id);
CREATE INDEX IF NOT EXISTS idx_debug_trace_expiry
ON debug_trace_sessions(expires_at);
