ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS risk_tier TEXT NOT NULL DEFAULT 'standard';
ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS required_preflight_facts_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS human_review_required INTEGER NOT NULL DEFAULT 0;
ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS submission_mode TEXT NOT NULL DEFAULT 'draft';
