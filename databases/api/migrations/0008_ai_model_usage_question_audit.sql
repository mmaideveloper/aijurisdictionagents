ALTER TABLE ai_model_usage_ledger
ADD COLUMN IF NOT EXISTS session_id TEXT NOT NULL DEFAULT '';

ALTER TABLE ai_model_usage_ledger
ADD COLUMN IF NOT EXISTS question_id TEXT NOT NULL DEFAULT '';

ALTER TABLE ai_model_usage_ledger
ADD COLUMN IF NOT EXISTS question_preview TEXT NOT NULL DEFAULT '';

ALTER TABLE ai_model_usage_ledger
ADD COLUMN IF NOT EXISTS question_sha256 TEXT NOT NULL DEFAULT '';

ALTER TABLE ai_model_usage_ledger
ADD COLUMN IF NOT EXISTS answer_id TEXT NOT NULL DEFAULT '';

ALTER TABLE ai_model_usage_ledger
ADD COLUMN IF NOT EXISTS audit_metadata_json TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_ai_model_usage_case_question_time
ON ai_model_usage_ledger(case_id, question_id, request_completed_at);
