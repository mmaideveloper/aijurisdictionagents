-- Owner-authorized incomplete preview is distinct from a legally reviewed publication.
ALTER TABLE test_definitions DROP CONSTRAINT test_definitions_status_check;
ALTER TABLE test_definitions ADD CONSTRAINT test_definitions_status_check
    CHECK (status IN ('draft','development','preview','published','withdrawn'));
ALTER TABLE test_definitions ADD COLUMN preview_notice text NOT NULL DEFAULT '';
ALTER TABLE test_definitions ADD CONSTRAINT preview_transparency
    CHECK (status <> 'preview' OR length(trim(preview_notice)) > 0);
