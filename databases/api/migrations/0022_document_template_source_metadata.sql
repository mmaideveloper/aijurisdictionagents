ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS source_profile TEXT NOT NULL DEFAULT '';
ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS source_captured_at TEXT NULL;
ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS source_review_status TEXT NOT NULL DEFAULT 'unreviewed';
ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS reviewed_by TEXT NOT NULL DEFAULT '';
ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS normalization_notes TEXT NOT NULL DEFAULT '';
ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS legal_basis_refs_json TEXT NOT NULL DEFAULT '[]';
