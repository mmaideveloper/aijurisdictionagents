CREATE INDEX IF NOT EXISTS idx_law_provisions_version_ordinal
    ON law_provisions(version_id, ordinal);

CREATE INDEX IF NOT EXISTS idx_law_provisions_version_anchor
    ON law_provisions(version_id, anchor);

CREATE INDEX IF NOT EXISTS idx_law_provisions_body_text_fts
    ON law_provisions
    USING GIN (to_tsvector('simple', LOWER(body_text)));
