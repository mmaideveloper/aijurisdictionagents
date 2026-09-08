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
    retention_until = COALESCE(
        promotion.retention_until,
        (promotion.promoted_at::timestamptz + INTERVAL '6 years')::text
    )
FROM flow_evaluation_approvals AS approval
WHERE promotion.approval_id = approval.approval_id;

ALTER TABLE flow_promotion_provenance ALTER COLUMN idempotency_key SET NOT NULL;
ALTER TABLE flow_promotion_provenance ALTER COLUMN request_hash SET NOT NULL;
ALTER TABLE flow_promotion_provenance ALTER COLUMN action SET NOT NULL;
ALTER TABLE flow_promotion_provenance ALTER COLUMN run_id SET NOT NULL;
ALTER TABLE flow_promotion_provenance ALTER COLUMN case_type_key SET NOT NULL;
ALTER TABLE flow_promotion_provenance ALTER COLUMN jurisdiction SET NOT NULL;
ALTER TABLE flow_promotion_provenance ALTER COLUMN reason SET NOT NULL;
ALTER TABLE flow_promotion_provenance ALTER COLUMN retention_until SET NOT NULL;

ALTER TABLE flow_evaluation_approvals
    DROP CONSTRAINT IF EXISTS flow_evaluation_approvals_flow_id_definition_hash_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_flow_evaluation_approvals_flow_run
ON flow_evaluation_approvals(flow_id, run_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_flow_promotion_provenance_idempotency
ON flow_promotion_provenance(idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_flow_promotion_provenance_assignment
ON flow_promotion_provenance(jurisdiction, case_type_key, promoted_at);
