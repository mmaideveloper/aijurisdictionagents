ALTER TABLE flow_promotion_provenance
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
ALTER TABLE flow_promotion_provenance
    ADD COLUMN IF NOT EXISTS request_hash TEXT;
ALTER TABLE flow_promotion_provenance
    ADD COLUMN IF NOT EXISTS action TEXT;
ALTER TABLE flow_promotion_provenance
    ADD COLUMN IF NOT EXISTS run_id TEXT REFERENCES flow_evaluation_runs(run_id);
ALTER TABLE flow_promotion_provenance
    ADD COLUMN IF NOT EXISTS case_type_key TEXT;
ALTER TABLE flow_promotion_provenance
    ADD COLUMN IF NOT EXISTS jurisdiction TEXT;
ALTER TABLE flow_promotion_provenance
    ADD COLUMN IF NOT EXISTS reason TEXT;
ALTER TABLE flow_promotion_provenance
    ADD COLUMN IF NOT EXISTS retention_until TEXT;
ALTER TABLE flow_promotion_provenance
    ADD COLUMN IF NOT EXISTS approved_by_snapshot TEXT;
ALTER TABLE flow_promotion_provenance
    ADD COLUMN IF NOT EXISTS approval_reason_snapshot TEXT;
ALTER TABLE flow_promotion_provenance
    ADD COLUMN IF NOT EXISTS approved_at_snapshot TEXT;

UPDATE flow_promotion_provenance AS promotion
SET idempotency_key = COALESCE(promotion.idempotency_key, 'legacy-' || promotion.promotion_id),
    request_hash = COALESCE(promotion.request_hash, promotion.target_assignment_hash),
    action = COALESCE(
        promotion.action,
        CASE WHEN promotion.rollback_of_promotion_id IS NULL THEN 'promote' ELSE 'rollback' END
    ),
    run_id = COALESCE(promotion.run_id, approval.run_id),
    case_type_key = COALESCE(
        promotion.case_type_key,
        promotion.target_assignment_json::jsonb ->> 'case_type_key',
        'legacy-unknown'
    ),
    jurisdiction = COALESCE(
        promotion.jurisdiction,
        promotion.target_assignment_json::jsonb ->> 'jurisdiction',
        'UNKNOWN'
    ),
    reason = COALESCE(promotion.reason, 'Migrated legacy promotion provenance'),
    approved_by_snapshot = COALESCE(promotion.approved_by_snapshot, approval.approved_by),
    approval_reason_snapshot = COALESCE(promotion.approval_reason_snapshot, approval.reason),
    approved_at_snapshot = COALESCE(promotion.approved_at_snapshot, approval.approved_at),
    retention_until = COALESCE(
        promotion.retention_until,
        (promotion.promoted_at::timestamptz + INTERVAL '6 years')::text
    )
FROM flow_evaluation_approvals AS approval
WHERE promotion.approval_id = approval.approval_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_flow_promotion_provenance_idempotency
ON flow_promotion_provenance(idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_flow_promotion_provenance_assignment
ON flow_promotion_provenance(jurisdiction, case_type_key, promoted_at);
