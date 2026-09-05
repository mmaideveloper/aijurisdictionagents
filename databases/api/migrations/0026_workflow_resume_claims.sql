CREATE TABLE IF NOT EXISTS workflow_resume_claims (
    claim_id TEXT PRIMARY KEY,
    workflow_run_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(workflow_run_id, checkpoint_id)
);

CREATE INDEX IF NOT EXISTS idx_workflow_resume_claims_run
ON workflow_resume_claims(workflow_run_id, created_at);
