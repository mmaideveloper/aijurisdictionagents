CREATE TABLE IF NOT EXISTS flow_packs (
    flow_id TEXT PRIMARY KEY,
    flow_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    jurisdiction TEXT NOT NULL,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    question_kind TEXT NOT NULL DEFAULT 'legal_question',
    legal_domain TEXT NOT NULL DEFAULT 'general',
    requested_outcome TEXT NOT NULL DEFAULT 'legal_information',
    positive_examples_json TEXT NOT NULL DEFAULT '[]',
    negative_examples_json TEXT NOT NULL DEFAULT '[]',
    clarification_policy_json TEXT NOT NULL DEFAULT '{}',
    definition_hash TEXT NULL,
    locked_at TEXT NULL,
    locked_by TEXT NULL,
    locked_reason TEXT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 0,
    lifecycle_state TEXT NOT NULL DEFAULT 'draft',
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NULL,
    UNIQUE(jurisdiction, flow_key, version)
);

CREATE INDEX IF NOT EXISTS idx_flow_packs_key ON flow_packs(flow_key);
CREATE INDEX IF NOT EXISTS idx_flow_packs_jurisdiction ON flow_packs(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_flow_packs_enabled ON flow_packs(is_enabled);
CREATE INDEX IF NOT EXISTS idx_flow_packs_deleted ON flow_packs(is_deleted);
