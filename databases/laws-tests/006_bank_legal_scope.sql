-- Publication is generic: legal dates belong to explicitly legal banks, not a
-- hardcoded allowlist of non-legal subjects. Preserve the existing firearms gate.
SET CONSTRAINTS ALL IMMEDIATE;
ALTER TABLE test_definitions ADD COLUMN requires_legal_date boolean NOT NULL DEFAULT false;
UPDATE test_definitions SET requires_legal_date=true
WHERE legal_date IS NOT NULL OR case_type='FIREARMS_LICENSE_TEST';
ALTER TABLE test_definitions DROP CONSTRAINT publication_review;
ALTER TABLE test_definitions ADD CONSTRAINT publication_review CHECK (
 status <> 'published' OR (
  ((NOT requires_legal_date AND case_type<>'FIREARMS_LICENSE_TEST') OR legal_date IS NOT NULL)
  AND reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL AND length(trim(reviewed_by))>0
  AND rights_confirmed AND jsonb_typeof(source_links)='array' AND jsonb_array_length(source_links)>0
 )
);
SET CONSTRAINTS ALL DEFERRED;
