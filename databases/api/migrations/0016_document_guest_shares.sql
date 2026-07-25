CREATE TABLE IF NOT EXISTS document_shares (
    share_id TEXT PRIMARY KEY,
    token_hash TEXT UNIQUE NOT NULL,
    case_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    sender_user_id TEXT NOT NULL,
    recipient_email_protected TEXT NOT NULL,
    locale TEXT NOT NULL DEFAULT 'en',
    status TEXT NOT NULL DEFAULT 'active',
    expires_at TEXT NOT NULL,
    code_hash TEXT NOT NULL DEFAULT '',
    code_expires_at TEXT,
    code_attempts INTEGER NOT NULL DEFAULT 0,
    last_code_sent_at TEXT,
    session_token_hash TEXT NOT NULL DEFAULT '',
    session_expires_at TEXT,
    last_accessed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY(doc_id) REFERENCES case_documents(doc_id) ON DELETE CASCADE,
    FOREIGN KEY(sender_user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_document_shares_sender_document
ON document_shares(sender_user_id, case_id, doc_id, created_at);

CREATE TABLE IF NOT EXISTS document_share_audit_events (
    audit_event_id TEXT PRIMARY KEY,
    share_id TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(share_id) REFERENCES document_shares(share_id) ON DELETE CASCADE
);
