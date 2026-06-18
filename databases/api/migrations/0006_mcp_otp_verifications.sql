CREATE TABLE IF NOT EXISTS mcp_otp_verifications (
    user_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    PRIMARY KEY(user_id, purpose),
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
