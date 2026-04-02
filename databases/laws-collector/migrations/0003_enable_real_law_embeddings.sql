DROP INDEX IF EXISTS idx_law_versions_embedding;

ALTER TABLE law_versions
    ALTER COLUMN embedding_vector TYPE vector
    USING embedding_vector::vector;

ALTER TABLE law_versions
    ADD COLUMN IF NOT EXISTS embedding_model TEXT NOT NULL DEFAULT 'deterministic-legacy-8d';

ALTER TABLE law_versions
    ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER NOT NULL DEFAULT 8;

UPDATE law_versions
SET embedding_model = 'deterministic-legacy-8d'
WHERE COALESCE(embedding_model, '') = '';

UPDATE law_versions
SET embedding_dimensions = vector_dims(embedding_vector)
WHERE embedding_dimensions = 0;

CREATE INDEX IF NOT EXISTS idx_law_versions_embedding_metadata
    ON law_versions(embedding_model, embedding_dimensions);
