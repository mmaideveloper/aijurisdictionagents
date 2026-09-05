ALTER TABLE case_communications
ADD COLUMN IF NOT EXISTS presentation_json TEXT NOT NULL DEFAULT '{}';

COMMENT ON COLUMN case_communications.presentation_json IS
'Bounded user-visible presentation block; unrestricted tool payloads and prompts are prohibited.';
