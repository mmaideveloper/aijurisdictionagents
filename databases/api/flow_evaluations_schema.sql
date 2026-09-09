CREATE TABLE IF NOT EXISTS flow_evaluation_suites (
    suite_id TEXT PRIMARY KEY, suite_key TEXT NOT NULL, version INTEGER NOT NULL,
    jurisdiction TEXT NOT NULL, title TEXT NOT NULL, synthetic_only INTEGER NOT NULL,
    routing_accuracy_threshold REAL NOT NULL, retention_days INTEGER NOT NULL,
    suite_hash TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(suite_key, version)
);
CREATE TABLE IF NOT EXISTS flow_evaluation_cases (
    case_id TEXT PRIMARY KEY, suite_id TEXT NOT NULL, case_key TEXT NOT NULL,
    mode TEXT NOT NULL, synthetic_input_json TEXT NOT NULL, input_hash TEXT NOT NULL,
    expected_route TEXT NOT NULL, required_source_ids_json TEXT NOT NULL,
    human_review_required INTEGER NOT NULL, UNIQUE(suite_id, case_key),
    FOREIGN KEY(suite_id) REFERENCES flow_evaluation_suites(suite_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS flow_evaluation_runs (
    run_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
    synthetic_run_id TEXT NOT NULL UNIQUE, suite_id TEXT NOT NULL, suite_key TEXT NOT NULL,
    suite_version INTEGER NOT NULL, suite_hash TEXT NOT NULL,
    flow_id TEXT NOT NULL, flow_key TEXT NOT NULL, flow_version INTEGER NOT NULL,
    flow_definition_hash TEXT NOT NULL, graph_version TEXT NOT NULL,
    routing_policy_json TEXT NOT NULL, routing_policy_hash TEXT NOT NULL,
    provider TEXT NOT NULL, model TEXT NOT NULL, provider_route TEXT NOT NULL,
    mode TEXT NOT NULL, status TEXT NOT NULL, metrics_json TEXT NOT NULL,
    gates_json TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL, FOREIGN KEY(suite_id) REFERENCES flow_evaluation_suites(suite_id),
    FOREIGN KEY(flow_id) REFERENCES flow_packs(flow_id)
);
CREATE TABLE IF NOT EXISTS flow_evaluation_results (
    result_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, case_id TEXT NOT NULL,
    actual_route TEXT NOT NULL, source_ids_json TEXT NOT NULL, schema_valid INTEGER NOT NULL,
    provenance_valid INTEGER NOT NULL, privacy_violation_count INTEGER NOT NULL,
    unsupported_auto_finalization INTEGER NOT NULL, human_review_present INTEGER NOT NULL,
    passed INTEGER NOT NULL, reason_codes_json TEXT NOT NULL, UNIQUE(run_id, case_id),
    FOREIGN KEY(run_id) REFERENCES flow_evaluation_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(case_id) REFERENCES flow_evaluation_cases(case_id)
);
CREATE TABLE IF NOT EXISTS flow_evaluation_approvals (
    approval_id TEXT PRIMARY KEY, flow_id TEXT NOT NULL, run_id TEXT NOT NULL,
    definition_hash TEXT NOT NULL, approved_by TEXT NOT NULL, reason TEXT NOT NULL,
    approved_at TEXT NOT NULL, UNIQUE(flow_id, definition_hash),
    FOREIGN KEY(flow_id) REFERENCES flow_packs(flow_id),
    FOREIGN KEY(run_id) REFERENCES flow_evaluation_runs(run_id)
);
CREATE TABLE IF NOT EXISTS flow_promotion_provenance (
    promotion_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL, action TEXT NOT NULL,
    flow_id TEXT NOT NULL, approval_id TEXT NOT NULL, run_id TEXT NOT NULL,
    case_type_key TEXT NOT NULL, jurisdiction TEXT NOT NULL, reason TEXT NOT NULL,
    prior_assignment_json TEXT NULL, target_assignment_json TEXT NOT NULL,
    target_assignment_hash TEXT NOT NULL, promoted_by TEXT NOT NULL, promoted_at TEXT NOT NULL,
    approved_by_snapshot TEXT NOT NULL, approval_reason_snapshot TEXT NOT NULL,
    approved_at_snapshot TEXT NOT NULL,
    retention_until TEXT NOT NULL,
    rollback_of_promotion_id TEXT NULL, FOREIGN KEY(flow_id) REFERENCES flow_packs(flow_id),
    FOREIGN KEY(approval_id) REFERENCES flow_evaluation_approvals(approval_id),
    FOREIGN KEY(run_id) REFERENCES flow_evaluation_runs(run_id),
    FOREIGN KEY(rollback_of_promotion_id) REFERENCES flow_promotion_provenance(promotion_id)
);
CREATE INDEX IF NOT EXISTS idx_flow_evaluation_runs_flow ON flow_evaluation_runs(flow_id, created_at);
CREATE INDEX IF NOT EXISTS idx_flow_evaluation_runs_expiry ON flow_evaluation_runs(expires_at);
CREATE INDEX IF NOT EXISTS idx_flow_promotion_provenance_flow ON flow_promotion_provenance(flow_id, promoted_at);
CREATE INDEX IF NOT EXISTS idx_flow_promotion_provenance_assignment ON flow_promotion_provenance(jurisdiction, case_type_key, promoted_at);
