ALTER TABLE source_artifacts
    ADD COLUMN IF NOT EXISTS storage_backend TEXT NOT NULL DEFAULT '';

ALTER TABLE source_artifacts
    ADD COLUMN IF NOT EXISTS storage_path TEXT NOT NULL DEFAULT '';
